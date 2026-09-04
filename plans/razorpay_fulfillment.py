"""
Shared Razorpay payment fulfillment for client verify and webhooks.

Idempotent on Transaction.transaction_id == razorpay payment id.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from accounts.models import User
from plans.models import Plan, Transaction, UserPlan
from plans.razorpay_client import inr_to_paise
from plans.services import (
    RAZORPAY_PURPOSE_PLAN_PURCHASE,
    RAZORPAY_PURPOSE_SERVICE_CHARGE,
    SamePlanAlreadyActiveError,
    activate_plan_purchase,
    compute_plan_purchase_amounts,
    compute_service_charge_remaining,
    pay_remaining_service_charge,
)

logger = logging.getLogger(__name__)

RAZORPAY_PURPOSE_ASTROLOGY_PDF = 'astrology_pdf'


class FulfillmentError(Exception):
    """Business/validation failure while fulfilling a captured payment."""

    def __init__(self, message: str, *, code: str = 'FULFILLMENT_ERROR'):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class FulfillmentResult:
    created: bool
    purpose: str
    transaction: Transaction | None = None
    user: User | None = None
    plan: Plan | None = None
    extra: dict[str, Any] | None = None
    credit: Any = None  # AstrologyPdfCredit when purpose is astrology_pdf
    message: str = ''


def _sync_order_record(
    *,
    order: dict,
    payment_id: str,
    result: FulfillmentResult | None = None,
    skipped_code: str | None = None,
    status: str | None = None,
) -> None:
    from plans.razorpay_records import record_order_outcome

    record_order_outcome(
        order=order,
        payment_id=payment_id,
        result=result,
        skipped_code=skipped_code,
        status=status,
    )


def resolve_user_from_notes(notes: dict | None) -> User:
    notes = notes or {}
    user_id = str(notes.get('user_id') or '').strip()
    if user_id:
        user = User.objects.filter(pk=user_id).first()
        if user:
            return user
    matri_id = str(notes.get('matri_id') or '').strip()
    if matri_id:
        user = User.objects.filter(matri_id=matri_id).first()
        if user:
            return user
    raise FulfillmentError('Unable to resolve user from order notes.', code='USER_NOT_FOUND')


def get_success_txn_by_payment_id(payment_id: str) -> Transaction | None:
    return (
        Transaction.objects.filter(
            transaction_id=payment_id,
            payment_status=Transaction.STATUS_SUCCESS,
        )
        .select_related('user', 'plan')
        .first()
    )


def fulfill_plan_purchase(
    *,
    payment_id: str,
    order: dict,
    expected_paise: int | None = None,
) -> FulfillmentResult:
    try:
        result = _fulfill_plan_purchase_impl(
            payment_id=payment_id, order=order, expected_paise=expected_paise
        )
    except FulfillmentError as exc:
        _sync_order_record(order=order, payment_id=payment_id, skipped_code=exc.code)
        raise
    _sync_order_record(order=order, payment_id=payment_id, result=result)
    return result


def _fulfill_plan_purchase_impl(
    *,
    payment_id: str,
    order: dict,
    expected_paise: int | None = None,
) -> FulfillmentResult:
    notes = order.get('notes') or {}
    if notes.get('purpose') != RAZORPAY_PURPOSE_PLAN_PURCHASE:
        raise FulfillmentError('Order is not for plan purchase.', code='WRONG_PURPOSE')

    existing = get_success_txn_by_payment_id(payment_id)
    if existing:
        return FulfillmentResult(
            created=False,
            purpose=RAZORPAY_PURPOSE_PLAN_PURCHASE,
            transaction=existing,
            user=existing.user,
            plan=existing.plan,
            message='Plan already activated for this payment.',
        )

    user = resolve_user_from_notes(notes)
    plan_id = str(notes.get('plan_id') or '').strip()
    if not plan_id:
        raise FulfillmentError('Order missing plan_id.', code='MISSING_PLAN')
    plan = Plan.objects.filter(pk=plan_id, is_active=True).first()
    if not plan:
        plan = Plan.objects.filter(pk=plan_id).first()
    if not plan:
        raise FulfillmentError('Plan not found for order.', code='PLAN_NOT_FOUND')

    payment_option = str(notes.get('payment_option') or 'plan_only').strip() or 'plan_only'
    amount_inr, _, _, _ = compute_plan_purchase_amounts(user, plan, payment_option)
    paise = inr_to_paise(amount_inr)
    if expected_paise is not None and int(expected_paise) != paise:
        raise FulfillmentError('Payment amount mismatch.', code='AMOUNT_MISMATCH')

    order_amount = order.get('amount')
    if order_amount is not None and int(order_amount) != paise:
        raise FulfillmentError('Order amount mismatch.', code='AMOUNT_MISMATCH')

    try:
        _, txn, extra = activate_plan_purchase(
            user=user,
            plan=plan,
            payment_option=payment_option,
            payment_method=Transaction.PAYMENT_RAZORPAY,
            razorpay_payment_id=payment_id,
        )
    except SamePlanAlreadyActiveError as exc:
        existing_after = get_success_txn_by_payment_id(payment_id)
        if existing_after:
            return FulfillmentResult(
                created=False,
                purpose=RAZORPAY_PURPOSE_PLAN_PURCHASE,
                transaction=existing_after,
                user=user,
                plan=plan,
                message=str(exc),
            )
        raise FulfillmentError(str(exc), code='ACTIVE_SAME_PLAN') from exc

    extra = dict(extra or {})
    message = extra.pop('message', 'Plan activated successfully.')
    return FulfillmentResult(
        created=True,
        purpose=RAZORPAY_PURPOSE_PLAN_PURCHASE,
        transaction=txn,
        user=user,
        plan=plan,
        extra=extra,
        message=message,
    )


def fulfill_service_charge(
    *,
    payment_id: str,
    order: dict,
    expected_paise: int | None = None,
) -> FulfillmentResult:
    try:
        result = _fulfill_service_charge_impl(
            payment_id=payment_id, order=order, expected_paise=expected_paise
        )
    except FulfillmentError as exc:
        _sync_order_record(order=order, payment_id=payment_id, skipped_code=exc.code)
        raise
    _sync_order_record(order=order, payment_id=payment_id, result=result)
    return result


def _fulfill_service_charge_impl(
    *,
    payment_id: str,
    order: dict,
    expected_paise: int | None = None,
) -> FulfillmentResult:
    notes = order.get('notes') or {}
    if notes.get('purpose') != RAZORPAY_PURPOSE_SERVICE_CHARGE:
        raise FulfillmentError('Order is not for service charge payment.', code='WRONG_PURPOSE')

    existing = get_success_txn_by_payment_id(payment_id)
    if existing:
        return FulfillmentResult(
            created=False,
            purpose=RAZORPAY_PURPOSE_SERVICE_CHARGE,
            transaction=existing,
            user=existing.user,
            plan=existing.plan,
            message='Service charge already paid for this payment.',
        )

    user = resolve_user_from_notes(notes)
    try:
        user_plan, remaining = compute_service_charge_remaining(user)
    except UserPlan.DoesNotExist as exc:
        raise FulfillmentError('No active plan found for service charge.', code='NO_PLAN') from exc

    if remaining <= 0:
        return FulfillmentResult(
            created=False,
            purpose=RAZORPAY_PURPOSE_SERVICE_CHARGE,
            user=user,
            plan=user_plan.plan if user_plan else None,
            message='No remaining service charge to pay.',
        )

    paise = inr_to_paise(remaining)
    if expected_paise is not None and int(expected_paise) != paise:
        order_amount = order.get('amount')
        # Allow fulfillment when payment matches the original order amount
        if order_amount is None or int(order_amount) != int(expected_paise):
            raise FulfillmentError('Payment amount mismatch.', code='AMOUNT_MISMATCH')

    user_plan, txn, amount_paid = pay_remaining_service_charge(
        user=user,
        payment_method=Transaction.PAYMENT_RAZORPAY,
        razorpay_payment_id=payment_id,
    )
    if txn is None:
        return FulfillmentResult(
            created=False,
            purpose=RAZORPAY_PURPOSE_SERVICE_CHARGE,
            user=user,
            plan=user_plan.plan if user_plan else None,
            message='No remaining service charge to pay.',
        )

    return FulfillmentResult(
        created=True,
        purpose=RAZORPAY_PURPOSE_SERVICE_CHARGE,
        transaction=txn,
        user=user,
        plan=user_plan.plan if user_plan else None,
        extra={'amount_paid': amount_paid},
        message='Remaining service charge paid successfully.',
    )


def fulfill_from_captured_payment(*, payment: dict, order: dict) -> FulfillmentResult | None:
    """
    Dispatch fulfillment by order notes.purpose.
    Returns None when purpose is unknown (caller should ignore with 200).
    """
    payment_id = str(payment.get('id') or '').strip()
    if not payment_id:
        raise FulfillmentError('Missing payment id.', code='MISSING_PAYMENT_ID')
    if payment.get('status') != 'captured':
        raise FulfillmentError('Payment is not captured.', code='NOT_CAPTURED')

    notes = order.get('notes') or {}
    purpose = str(notes.get('purpose') or '').strip()
    expected_paise = int(payment.get('amount') or 0) or None

    if purpose == RAZORPAY_PURPOSE_PLAN_PURCHASE:
        return fulfill_plan_purchase(
            payment_id=payment_id, order=order, expected_paise=expected_paise
        )
    if purpose == RAZORPAY_PURPOSE_SERVICE_CHARGE:
        return fulfill_service_charge(
            payment_id=payment_id, order=order, expected_paise=expected_paise
        )
    if purpose == RAZORPAY_PURPOSE_ASTROLOGY_PDF:
        from astrology.services.razorpay_pdf_orders import fulfill_pdf_payment

        return fulfill_pdf_payment(
            payment_id=payment_id, order=order, expected_paise=expected_paise
        )

    logger.info('Ignoring Razorpay payment %s with unknown purpose=%r', payment_id, purpose)
    _sync_order_record(order=order, payment_id=payment_id, skipped_code='UNKNOWN_PURPOSE')
    return None
