"""Razorpay webhook: fulfill captured payments when client verify is missed."""
from __future__ import annotations

import json
import logging

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from plans.razorpay_client import (
    RazorpayApiError,
    RazorpayNotConfiguredError,
    fetch_order,
    fetch_payment,
    verify_webhook_signature,
)
from plans.razorpay_fulfillment import FulfillmentError, fulfill_from_captured_payment

logger = logging.getLogger(__name__)

WEBHOOK_EVENTS = frozenset({'payment.captured', 'order.paid'})


class RazorpayWebhookView(APIView):
    """
    POST /api/v1/payments/razorpay/webhook/

    Configure this URL in Razorpay Dashboard → Webhooks.
    Subscribes to payment.captured (and optionally order.paid).
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        raw_body = request.body or b''
        signature = request.headers.get('X-Razorpay-Signature') or request.META.get(
            'HTTP_X_RAZORPAY_SIGNATURE', ''
        )

        try:
            sig_ok = verify_webhook_signature(raw_body, signature)
        except RazorpayNotConfiguredError:
            logger.error('Razorpay webhook rejected: webhook secret not configured')
            return Response(
                {'success': False, 'error': {'code': 503, 'message': 'Webhook not configured.'}},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        if not sig_ok:
            return Response(
                {'success': False, 'error': {'code': 400, 'message': 'Invalid webhook signature.'}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payload = json.loads(raw_body.decode('utf-8') or '{}')
        except (UnicodeDecodeError, json.JSONDecodeError):
            return Response(
                {'success': False, 'error': {'code': 400, 'message': 'Malformed webhook body.'}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        event = str(payload.get('event') or '').strip()
        if event and event not in WEBHOOK_EVENTS:
            return Response({'success': True, 'ignored': True, 'event': event}, status=status.HTTP_200_OK)

        payment_entity = _extract_payment_entity(payload, event)
        if not payment_entity:
            return Response(
                {'success': True, 'ignored': True, 'reason': 'no_payment_entity'},
                status=status.HTTP_200_OK,
            )

        payment_id = str(payment_entity.get('id') or '').strip()
        order_id = str(payment_entity.get('order_id') or '').strip()
        if not payment_id or not order_id:
            return Response(
                {'success': True, 'ignored': True, 'reason': 'missing_ids'},
                status=status.HTTP_200_OK,
            )

        try:
            # Prefer live fetch so we do not trust webhook body alone for status/amount
            payment = fetch_payment(payment_id)
            order = fetch_order(order_id)
        except RazorpayNotConfiguredError:
            logger.exception('Razorpay not configured during webhook fulfill')
            return Response(
                {'success': False, 'error': {'code': 503, 'message': 'Razorpay not configured.'}},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except RazorpayApiError as exc:
            logger.warning('Razorpay API error on webhook: %s', exc)
            # Transient upstream — 500 so Razorpay retries
            return Response(
                {'success': False, 'error': {'code': 502, 'message': 'Upstream payment fetch failed.'}},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if payment.get('order_id') and payment.get('order_id') != order_id:
            logger.warning(
                'Webhook payment %s order mismatch: %s vs %s',
                payment_id,
                payment.get('order_id'),
                order_id,
            )
            return Response({'success': True, 'ignored': True, 'reason': 'order_mismatch'}, status=200)

        if payment.get('status') != 'captured':
            return Response(
                {'success': True, 'ignored': True, 'reason': 'not_captured'},
                status=status.HTTP_200_OK,
            )

        try:
            result = fulfill_from_captured_payment(payment=payment, order=order)
        except FulfillmentError as exc:
            # Business failures: acknowledge so Razorpay does not retry forever
            logger.warning(
                'Webhook fulfillment skipped for %s: %s (%s)',
                payment_id,
                exc.message,
                exc.code,
            )
            return Response(
                {
                    'success': True,
                    'fulfilled': False,
                    'code': exc.code,
                    'message': exc.message,
                },
                status=status.HTTP_200_OK,
            )
        except Exception:
            logger.exception('Unexpected webhook fulfillment error for %s', payment_id)
            return Response(
                {'success': False, 'error': {'code': 500, 'message': 'Fulfillment failed.'}},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if result is None:
            return Response(
                {'success': True, 'ignored': True, 'reason': 'unknown_purpose'},
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                'success': True,
                'fulfilled': True,
                'created': result.created,
                'purpose': result.purpose,
                'transaction_id': result.transaction.id if result.transaction else None,
            },
            status=status.HTTP_200_OK,
        )


def _extract_payment_entity(payload: dict, event: str) -> dict | None:
    container = payload.get('payload') or {}
    if event == 'payment.captured' or 'payment' in container:
        payment = container.get('payment') or {}
        entity = payment.get('entity') if isinstance(payment, dict) else None
        if isinstance(entity, dict) and entity.get('id'):
            return entity
    if event == 'order.paid':
        # order.paid may nest payment under payload.payment or only order
        payment = container.get('payment') or {}
        entity = payment.get('entity') if isinstance(payment, dict) else None
        if isinstance(entity, dict) and entity.get('id'):
            return entity
    return None
