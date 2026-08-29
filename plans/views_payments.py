"""Razorpay order/verify endpoints for plan purchase and service charge."""
from __future__ import annotations

import uuid

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Plan, Transaction, UserPlan
from .razorpay_client import (
    RazorpayApiError,
    RazorpayNotConfiguredError,
    create_razorpay_order,
    fetch_order,
    fetch_payment,
    inr_to_paise,
    verify_payment_signature,
)
from .serializers import PlanOrderSerializer, PlanVerifySerializer, ServiceChargeVerifySerializer
from .services import (
    RAZORPAY_PURPOSE_PLAN_PURCHASE,
    RAZORPAY_PURPOSE_SERVICE_CHARGE,
    SamePlanAlreadyActiveError,
    activate_plan_purchase,
    active_same_plan_error_body,
    compute_plan_purchase_amounts,
    compute_service_charge_remaining,
    pay_remaining_service_charge,
    plan_purchase_response_data,
    user_same_plan_active_preflight,
)


def _validation_error(details):
    return Response(
        {'success': False, 'error': {'code': 400, 'message': 'Validation failed.', 'details': details}},
        status=status.HTTP_400_BAD_REQUEST,
    )


def _razorpay_not_configured(exc):
    return Response(
        {'success': False, 'error': {'code': 503, 'message': str(exc)}},
        status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def _razorpay_api_error(exc):
    return Response(
        {'success': False, 'error': {'code': 502, 'message': str(exc)}},
        status=status.HTTP_502_BAD_GATEWAY,
    )


def _same_plan_conflict(message: str):
    return Response(
        active_same_plan_error_body(message),
        status=status.HTTP_409_CONFLICT,
    )


def _user_matri_id(user) -> str:
    return (getattr(user, 'matri_id', '') or '').strip()


def _notes_match_user(notes: dict, user) -> bool:
    notes = notes or {}
    matri_id = _user_matri_id(user)
    if matri_id and notes.get('matri_id', '').strip() != matri_id:
        return False
    user_id = str(user.pk)
    if notes.get('user_id', '').strip() and notes.get('user_id', '').strip() != user_id:
        return False
    return True


def _verify_captured_payment(*, order_id: str, payment_id: str, signature: str, expected_paise: int):
    try:
        sig_ok = verify_payment_signature(order_id, payment_id, signature)
    except RazorpayNotConfiguredError as exc:
        return _razorpay_not_configured(exc)
    if not sig_ok:
        return Response(
            {'success': False, 'error': {'code': 400, 'message': 'Invalid payment signature.'}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        pay = fetch_payment(payment_id)
    except RazorpayNotConfiguredError as exc:
        return _razorpay_not_configured(exc)
    except RazorpayApiError as exc:
        return _razorpay_api_error(exc)

    if pay.get('order_id') != order_id:
        return Response(
            {'success': False, 'error': {'code': 400, 'message': 'Order id does not match payment.'}},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if pay.get('status') != 'captured':
        return Response(
            {'success': False, 'error': {'code': 400, 'message': 'Payment is not captured.'}},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if int(pay.get('amount', 0)) != expected_paise:
        return Response(
            {'success': False, 'error': {'code': 400, 'message': 'Payment amount mismatch.'}},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return None


class PlanOrderView(APIView):
    """POST /api/v1/plans/order/ — create Razorpay order for plan purchase."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = PlanOrderSerializer(data=request.data)
        if not ser.is_valid():
            return _validation_error(ser.errors)

        plan = Plan.objects.get(pk=ser.validated_data['plan_id'])
        payment_option = ser.validated_data['payment_option']
        blocked_msg = user_same_plan_active_preflight(request.user, plan)
        if blocked_msg:
            return _same_plan_conflict(blocked_msg)
        amount_inr, _, _, _ = compute_plan_purchase_amounts(request.user, plan, payment_option)
        if amount_inr <= 0:
            return Response(
                {'success': False, 'error': {'code': 400, 'message': 'Nothing to pay for this plan option.'}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        amount_paise = inr_to_paise(amount_inr)
        receipt = f'pl{uuid.uuid4().hex}'[:40]
        notes = {
            'purpose': RAZORPAY_PURPOSE_PLAN_PURCHASE,
            'matri_id': _user_matri_id(request.user),
            'user_id': str(request.user.pk),
            'plan_id': str(plan.pk),
            'payment_option': payment_option,
        }
        try:
            out = create_razorpay_order(amount_paise=amount_paise, receipt=receipt, notes=notes)
        except RazorpayNotConfiguredError as exc:
            return _razorpay_not_configured(exc)
        except RazorpayApiError as exc:
            return _razorpay_api_error(exc)

        return Response(
            {
                'success': True,
                'data': {
                    'plan_id': plan.pk,
                    'payment_option': payment_option,
                    'amount_inr': float(amount_inr),
                    'order_id': out['order_id'],
                    'amount': out['amount'],
                    'currency': out['currency'],
                    'key_id': out['key_id'],
                },
            },
            status=status.HTTP_200_OK,
        )


class PlanVerifyView(APIView):
    """POST /api/v1/plans/verify/ — verify Razorpay payment and activate plan."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = PlanVerifySerializer(data=request.data)
        if not ser.is_valid():
            return _validation_error(ser.errors)

        plan = Plan.objects.get(pk=ser.validated_data['plan_id'])
        payment_option = ser.validated_data['payment_option']
        order_id = ser.validated_data['razorpay_order_id'].strip()
        payment_id = ser.validated_data['razorpay_payment_id'].strip()
        signature = ser.validated_data['razorpay_signature'].strip()

        amount_inr, _, _, _ = compute_plan_purchase_amounts(request.user, plan, payment_option)
        expected_paise = inr_to_paise(amount_inr)

        existing_txn = Transaction.objects.filter(transaction_id=payment_id).first()
        if existing_txn:
            if existing_txn.user_id != request.user.id:
                return Response(
                    {'success': False, 'error': {'code': 403, 'message': 'Payment belongs to another account.'}},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if existing_txn.transaction_type != Transaction.TYPE_PLAN_PURCHASE:
                return Response(
                    {'success': False, 'error': {'code': 400, 'message': 'Payment does not match plan purchase.'}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            extra = {
                'payment_option': payment_option,
                'amount_paid': float(existing_txn.amount),
                'service_charge_remaining': float(
                    max((existing_txn.service_charge or 0) - (getattr(request.user.user_plan, 'service_charge_paid', 0) or 0), 0)
                ),
                'valid_until': (
                    request.user.user_plan.valid_until.isoformat()
                    if hasattr(request.user, 'user_plan') and request.user.user_plan.valid_until
                    else None
                ),
                'carry_forward': {},
            }
            return Response(
                {
                    'success': True,
                    'message': 'Plan already activated for this payment.',
                    'data': plan_purchase_response_data(existing_txn, plan, extra),
                },
                status=status.HTTP_200_OK,
            )

        pay_err = _verify_captured_payment(
            order_id=order_id,
            payment_id=payment_id,
            signature=signature,
            expected_paise=expected_paise,
        )
        if pay_err is not None:
            return pay_err

        try:
            order = fetch_order(order_id)
        except RazorpayNotConfiguredError as exc:
            return _razorpay_not_configured(exc)
        except RazorpayApiError as exc:
            return _razorpay_api_error(exc)

        notes = order.get('notes') or {}
        if notes.get('purpose') != RAZORPAY_PURPOSE_PLAN_PURCHASE:
            return Response(
                {'success': False, 'error': {'code': 400, 'message': 'Order is not for plan purchase.'}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not _notes_match_user(notes, request.user):
            return Response(
                {'success': False, 'error': {'code': 403, 'message': 'Order belongs to another account.'}},
                status=status.HTTP_403_FORBIDDEN,
            )
        if str(notes.get('plan_id', '')).strip() != str(plan.pk):
            return Response(
                {'success': False, 'error': {'code': 400, 'message': 'Order plan does not match request.'}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if notes.get('payment_option', payment_option) != payment_option:
            return Response(
                {'success': False, 'error': {'code': 400, 'message': 'Order payment option mismatch.'}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            _, txn, extra = activate_plan_purchase(
                user=request.user,
                plan=plan,
                payment_option=payment_option,
                payment_method=Transaction.PAYMENT_RAZORPAY,
                razorpay_payment_id=payment_id,
            )
        except SamePlanAlreadyActiveError as exc:
            return _same_plan_conflict(str(exc))
        return Response(
            {
                'success': True,
                'message': extra.pop('message'),
                'data': plan_purchase_response_data(txn, plan, extra),
            },
            status=status.HTTP_201_CREATED,
        )


class ServiceChargeOrderView(APIView):
    """POST /api/v1/plans/pay-remaining-service/order/ — Razorpay order for remaining service charge."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            user_plan, remaining = compute_service_charge_remaining(request.user)
        except UserPlan.DoesNotExist:
            return Response(
                {'success': False, 'error': {'code': 404, 'message': 'No active plan found. Purchase a plan first.'}},
                status=status.HTTP_404_NOT_FOUND,
            )
        if remaining <= 0:
            return Response(
                {
                    'success': True,
                    'message': 'No remaining service charge to pay.',
                    'data': {'amount_inr': 0, 'amount_paid': 0, 'service_charge_remaining': 0},
                },
                status=status.HTTP_200_OK,
            )

        amount_paise = inr_to_paise(remaining)
        receipt = f'sc{uuid.uuid4().hex}'[:40]
        notes = {
            'purpose': RAZORPAY_PURPOSE_SERVICE_CHARGE,
            'matri_id': _user_matri_id(request.user),
            'user_id': str(request.user.pk),
            'plan_id': str(user_plan.plan_id),
        }
        try:
            out = create_razorpay_order(amount_paise=amount_paise, receipt=receipt, notes=notes)
        except RazorpayNotConfiguredError as exc:
            return _razorpay_not_configured(exc)
        except RazorpayApiError as exc:
            return _razorpay_api_error(exc)

        return Response(
            {
                'success': True,
                'data': {
                    'amount_inr': float(remaining),
                    'order_id': out['order_id'],
                    'amount': out['amount'],
                    'currency': out['currency'],
                    'key_id': out['key_id'],
                },
            },
            status=status.HTTP_200_OK,
        )


class ServiceChargeVerifyView(APIView):
    """POST /api/v1/plans/pay-remaining-service/verify/ — verify and mark service charge paid."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = ServiceChargeVerifySerializer(data=request.data)
        if not ser.is_valid():
            return _validation_error(ser.errors)

        order_id = ser.validated_data['razorpay_order_id'].strip()
        payment_id = ser.validated_data['razorpay_payment_id'].strip()
        signature = ser.validated_data['razorpay_signature'].strip()

        try:
            user_plan, remaining = compute_service_charge_remaining(request.user)
        except UserPlan.DoesNotExist:
            return Response(
                {'success': False, 'error': {'code': 404, 'message': 'No active plan found. Purchase a plan first.'}},
                status=status.HTTP_404_NOT_FOUND,
            )

        existing_txn = Transaction.objects.filter(transaction_id=payment_id).first()
        if existing_txn:
            if existing_txn.user_id != request.user.id:
                return Response(
                    {'success': False, 'error': {'code': 403, 'message': 'Payment belongs to another account.'}},
                    status=status.HTTP_403_FORBIDDEN,
                )
            return Response(
                {
                    'success': True,
                    'message': 'Service charge already paid for this payment.',
                    'data': {
                        'transaction_id': existing_txn.id,
                        'amount_paid': float(existing_txn.amount),
                        'service_charge_remaining': 0,
                    },
                },
                status=status.HTTP_200_OK,
            )

        if remaining <= 0:
            return Response(
                {
                    'success': True,
                    'message': 'No remaining service charge to pay.',
                    'data': {'amount_paid': 0, 'service_charge_remaining': 0},
                },
                status=status.HTTP_200_OK,
            )

        expected_paise = inr_to_paise(remaining)
        pay_err = _verify_captured_payment(
            order_id=order_id,
            payment_id=payment_id,
            signature=signature,
            expected_paise=expected_paise,
        )
        if pay_err is not None:
            return pay_err

        try:
            order = fetch_order(order_id)
        except RazorpayNotConfiguredError as exc:
            return _razorpay_not_configured(exc)
        except RazorpayApiError as exc:
            return _razorpay_api_error(exc)

        notes = order.get('notes') or {}
        if notes.get('purpose') != RAZORPAY_PURPOSE_SERVICE_CHARGE:
            return Response(
                {'success': False, 'error': {'code': 400, 'message': 'Order is not for service charge payment.'}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not _notes_match_user(notes, request.user):
            return Response(
                {'success': False, 'error': {'code': 403, 'message': 'Order belongs to another account.'}},
                status=status.HTTP_403_FORBIDDEN,
            )

        user_plan, txn, amount_paid = pay_remaining_service_charge(
            user=request.user,
            payment_method=Transaction.PAYMENT_RAZORPAY,
            razorpay_payment_id=payment_id,
        )
        if txn is None:
            return Response(
                {
                    'success': True,
                    'message': 'No remaining service charge to pay.',
                    'data': {'amount_paid': 0, 'service_charge_remaining': 0},
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                'success': True,
                'message': 'Remaining service charge paid successfully.',
                'data': {
                    'transaction_id': txn.id,
                    'amount_paid': float(amount_paid),
                    'service_charge_remaining': 0,
                },
            },
            status=status.HTTP_201_CREATED,
        )
