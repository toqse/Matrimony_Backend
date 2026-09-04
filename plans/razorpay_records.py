"""Persist Razorpay orders and webhook events for Django admin."""
from __future__ import annotations

import logging
from typing import Any

from accounts.models import User
from plans.models import Plan, RazorpayOrder, RazorpayWebhookEvent, Transaction

logger = logging.getLogger(__name__)

_STATUS_RANK = {
    RazorpayOrder.STATUS_CREATED: 0,
    RazorpayOrder.STATUS_PAID: 1,
    RazorpayOrder.STATUS_SKIPPED: 1,
    RazorpayOrder.STATUS_FULFILLED: 2,
}


def _stringify_notes(notes: dict | None) -> dict[str, str]:
    return {str(k): str(v) for k, v in (notes or {}).items()}


def _resolve_user(notes: dict) -> User | None:
    user_id = str(notes.get('user_id') or '').strip()
    if user_id:
        user = User.objects.filter(pk=user_id).first()
        if user:
            return user
    matri_id = str(notes.get('matri_id') or '').strip()
    if matri_id:
        return User.objects.filter(matri_id=matri_id).first()
    return None


def _resolve_plan(notes: dict) -> Plan | None:
    plan_id = str(notes.get('plan_id') or '').strip()
    if not plan_id:
        return None
    return Plan.objects.filter(pk=plan_id).first()


def _apply_status(obj: RazorpayOrder, new_status: str) -> bool:
    if obj.status == RazorpayOrder.STATUS_FULFILLED:
        return False
    if new_status == RazorpayOrder.STATUS_FULFILLED:
        obj.status = new_status
        return True
    if _STATUS_RANK.get(new_status, 0) >= _STATUS_RANK.get(obj.status, 0):
        obj.status = new_status
        return True
    return False


def persist_created_order(out: dict, *, notes: dict | None = None) -> RazorpayOrder | None:
    """Save a local RazorpayOrder after a successful Razorpay create-order call."""
    notes = _stringify_notes(notes)
    order_id = str(out.get('order_id') or '').strip()
    if not order_id:
        return None
    try:
        obj, _created = RazorpayOrder.objects.update_or_create(
            razorpay_order_id=order_id,
            defaults={
                'receipt': str(out.get('receipt') or '')[:64],
                'amount_paise': int(out.get('amount') or 0),
                'currency': str(out.get('currency') or 'INR')[:8],
                'purpose': str(notes.get('purpose') or '')[:40],
                'user': _resolve_user(notes),
                'plan': _resolve_plan(notes),
                'notes': notes,
            },
        )
        return obj
    except Exception:
        logger.exception('Failed to persist Razorpay order %s locally', order_id)
        return None


def _upsert_order_from_payload(
    *,
    order: dict,
    payment_id: str = '',
    status: str,
    transaction: Transaction | None = None,
    user: User | None = None,
    plan: Plan | None = None,
) -> RazorpayOrder | None:
    order_id = str(order.get('id') or order.get('order_id') or '').strip()
    if not order_id:
        return None
    notes = order.get('notes') if isinstance(order.get('notes'), dict) else {}
    notes = _stringify_notes(notes)
    resolved_user = user or _resolve_user(notes)
    resolved_plan = plan or _resolve_plan(notes)
    amount = order.get('amount')
    try:
        amount_paise = int(amount or 0)
    except (TypeError, ValueError):
        amount_paise = 0

    obj = RazorpayOrder.objects.filter(razorpay_order_id=order_id).first()
    if obj is None:
        obj = RazorpayOrder(
            razorpay_order_id=order_id,
            receipt=str(order.get('receipt') or '')[:64],
            amount_paise=amount_paise,
            currency=str(order.get('currency') or 'INR')[:8],
            purpose=str(notes.get('purpose') or '')[:40],
            user=resolved_user,
            plan=resolved_plan,
            notes=notes,
            status=status,
            razorpay_payment_id=(payment_id or '')[:64],
            transaction=transaction,
        )
        obj.save()
        return obj

    changed: list[str] = []
    if amount_paise and obj.amount_paise != amount_paise:
        obj.amount_paise = amount_paise
        changed.append('amount_paise')
    receipt = str(order.get('receipt') or '')[:64]
    if receipt and obj.receipt != receipt:
        obj.receipt = receipt
        changed.append('receipt')
    if notes and obj.notes != notes:
        obj.notes = notes
        changed.append('notes')
    purpose = str(notes.get('purpose') or '')[:40]
    if purpose and obj.purpose != purpose:
        obj.purpose = purpose
        changed.append('purpose')
    if resolved_user and obj.user_id is None:
        obj.user = resolved_user
        changed.append('user')
    if resolved_plan and obj.plan_id is None:
        obj.plan = resolved_plan
        changed.append('plan')
    if payment_id and obj.razorpay_payment_id != payment_id:
        obj.razorpay_payment_id = payment_id[:64]
        changed.append('razorpay_payment_id')
    if transaction is not None and obj.transaction_id != transaction.pk:
        obj.transaction = transaction
        changed.append('transaction')
    if _apply_status(obj, status):
        changed.append('status')
    if changed:
        obj.save(update_fields=changed + ['updated_at'])
    return obj


def record_order_outcome(
    *,
    order: dict,
    payment_id: str,
    result: Any = None,
    skipped_code: str | None = None,
    status: str | None = None,
) -> RazorpayOrder | None:
    """Update or stub a local RazorpayOrder after capture / fulfillment."""
    try:
        txn = getattr(result, 'transaction', None) if result is not None else None
        user = getattr(result, 'user', None) if result is not None else None
        plan = getattr(result, 'plan', None) if result is not None else None
        if status:
            new_status = status
        elif txn is not None:
            new_status = RazorpayOrder.STATUS_FULFILLED
        else:
            new_status = RazorpayOrder.STATUS_SKIPPED
        return _upsert_order_from_payload(
            order=order,
            payment_id=payment_id,
            status=new_status,
            transaction=txn,
            user=user,
            plan=plan,
        )
    except Exception:
        logger.exception(
            'Failed to update RazorpayOrder for payment %s (skipped=%s)',
            payment_id,
            skipped_code,
        )
        return None


def record_webhook_event(log: dict) -> RazorpayWebhookEvent | None:
    """Append a RazorpayWebhookEvent. Never raises to the caller."""
    try:
        order_id = str(log.get('razorpay_order_id') or '').strip()[:64]
        payment_id = str(log.get('razorpay_payment_id') or '').strip()[:64]
        order_obj = log.get('order')
        if order_obj is None and order_id:
            order_obj = RazorpayOrder.objects.filter(razorpay_order_id=order_id).first()
        txn = log.get('transaction')
        if txn is None and payment_id:
            txn = (
                Transaction.objects.filter(
                    transaction_id=payment_id,
                    payment_status=Transaction.STATUS_SUCCESS,
                )
                .order_by('-id')
                .first()
            )
        payload = log.get('payload')
        if payload is not None and not isinstance(payload, (dict, list)):
            payload = None
        summary = log.get('response_summary')
        if summary is not None and not isinstance(summary, (dict, list)):
            summary = {'value': str(summary)[:2000]}
        return RazorpayWebhookEvent.objects.create(
            event=str(log.get('event') or '')[:64],
            signature_valid=bool(log.get('signature_valid')),
            status=str(log.get('status') or RazorpayWebhookEvent.STATUS_FAILED)[:32],
            http_status=int(log.get('http_status') or 0),
            razorpay_order_id=order_id,
            razorpay_payment_id=payment_id,
            order=order_obj,
            transaction=txn,
            payload=payload,
            response_summary=summary,
            error_message=str(log.get('error_message') or '')[:4000],
        )
    except Exception:
        logger.exception('Failed to persist Razorpay webhook event')
        return None
