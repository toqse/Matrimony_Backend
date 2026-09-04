"""Razorpay webhook: fulfill captured payments when client verify is missed."""
from __future__ import annotations

import json
import logging

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from plans.models import RazorpayOrder, RazorpayWebhookEvent
from plans.razorpay_client import (
    RazorpayApiError,
    RazorpayNotConfiguredError,
    fetch_order,
    fetch_payment,
    verify_webhook_signature,
)
from plans.razorpay_fulfillment import FulfillmentError, fulfill_from_captured_payment
from plans.razorpay_records import record_order_outcome, record_webhook_event

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
        log: dict = {
            'signature_valid': False,
            'status': RazorpayWebhookEvent.STATUS_FAILED,
            'http_status': 500,
            'event': '',
            'payload': None,
            'razorpay_order_id': '',
            'razorpay_payment_id': '',
            'order': None,
            'transaction': None,
            'response_summary': None,
            'error_message': '',
        }
        self._prime_log_from_body(raw_body, log)
        try:
            response = self._handle(raw_body, signature, log)
        except Exception:
            logger.exception('Unexpected Razorpay webhook error')
            log['status'] = RazorpayWebhookEvent.STATUS_FAILED
            log['error_message'] = log.get('error_message') or 'Unhandled webhook error.'
            response = Response(
                {'success': False, 'error': {'code': 500, 'message': 'Fulfillment failed.'}},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        log['http_status'] = response.status_code
        if log.get('response_summary') is None:
            data = getattr(response, 'data', None)
            if isinstance(data, (dict, list)):
                log['response_summary'] = data
        record_webhook_event(log)
        return response

    def _prime_log_from_body(self, raw_body: bytes, log: dict) -> None:
        try:
            payload = json.loads((raw_body or b'').decode('utf-8') or '{}')
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        log['payload'] = payload
        event = str(payload.get('event') or '').strip()
        log['event'] = event
        entity = _extract_payment_entity(payload, event)
        if entity:
            log['razorpay_payment_id'] = str(entity.get('id') or '').strip()
            log['razorpay_order_id'] = str(entity.get('order_id') or '').strip()

    def _handle(self, raw_body: bytes, signature: str, log: dict) -> Response:
        try:
            sig_ok = verify_webhook_signature(raw_body, signature)
        except RazorpayNotConfiguredError:
            logger.error('Razorpay webhook rejected: webhook secret not configured')
            log['status'] = RazorpayWebhookEvent.STATUS_NOT_CONFIGURED
            log['error_message'] = 'Webhook secret not configured.'
            return Response(
                {'success': False, 'error': {'code': 503, 'message': 'Webhook not configured.'}},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        log['signature_valid'] = bool(sig_ok)
        if not sig_ok:
            log['status'] = RazorpayWebhookEvent.STATUS_INVALID_SIGNATURE
            log['error_message'] = 'Invalid webhook signature.'
            return Response(
                {'success': False, 'error': {'code': 400, 'message': 'Invalid webhook signature.'}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = log.get('payload')
        if payload is None:
            try:
                payload = json.loads(raw_body.decode('utf-8') or '{}')
            except (UnicodeDecodeError, json.JSONDecodeError):
                log['status'] = RazorpayWebhookEvent.STATUS_MALFORMED
                log['error_message'] = 'Malformed webhook body.'
                return Response(
                    {'success': False, 'error': {'code': 400, 'message': 'Malformed webhook body.'}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if isinstance(payload, dict):
                log['payload'] = payload
                log['event'] = str(payload.get('event') or '').strip()
            else:
                log['status'] = RazorpayWebhookEvent.STATUS_MALFORMED
                log['error_message'] = 'Malformed webhook body.'
                return Response(
                    {'success': False, 'error': {'code': 400, 'message': 'Malformed webhook body.'}},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        event = str(log.get('event') or '').strip()
        if event and event not in WEBHOOK_EVENTS:
            log['status'] = RazorpayWebhookEvent.STATUS_IGNORED
            return Response({'success': True, 'ignored': True, 'event': event}, status=status.HTTP_200_OK)

        payment_entity = _extract_payment_entity(payload, event)
        if not payment_entity:
            log['status'] = RazorpayWebhookEvent.STATUS_IGNORED
            return Response(
                {'success': True, 'ignored': True, 'reason': 'no_payment_entity'},
                status=status.HTTP_200_OK,
            )

        payment_id = str(payment_entity.get('id') or '').strip()
        order_id = str(payment_entity.get('order_id') or '').strip()
        log['razorpay_payment_id'] = payment_id
        log['razorpay_order_id'] = order_id
        if not payment_id or not order_id:
            log['status'] = RazorpayWebhookEvent.STATUS_IGNORED
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
            log['status'] = RazorpayWebhookEvent.STATUS_FAILED
            log['error_message'] = 'Razorpay not configured.'
            return Response(
                {'success': False, 'error': {'code': 503, 'message': 'Razorpay not configured.'}},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except RazorpayApiError as exc:
            logger.warning('Razorpay API error on webhook: %s', exc)
            log['status'] = RazorpayWebhookEvent.STATUS_FAILED
            log['error_message'] = str(exc)[:4000]
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
            log['status'] = RazorpayWebhookEvent.STATUS_IGNORED
            return Response({'success': True, 'ignored': True, 'reason': 'order_mismatch'}, status=200)

        if payment.get('status') != 'captured':
            log['status'] = RazorpayWebhookEvent.STATUS_IGNORED
            return Response(
                {'success': True, 'ignored': True, 'reason': 'not_captured'},
                status=status.HTTP_200_OK,
            )

        try:
            result = fulfill_from_captured_payment(payment=payment, order=order)
        except FulfillmentError as exc:
            logger.warning(
                'Webhook fulfillment skipped for %s: %s (%s)',
                payment_id,
                exc.message,
                exc.code,
            )
            log['status'] = RazorpayWebhookEvent.STATUS_SKIPPED
            log['error_message'] = f'{exc.code}: {exc.message}'
            log['order'] = RazorpayOrder.objects.filter(razorpay_order_id=order_id).first()
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
            log['status'] = RazorpayWebhookEvent.STATUS_FAILED
            log['error_message'] = 'Fulfillment failed.'
            record_order_outcome(
                order=order,
                payment_id=payment_id,
                status=RazorpayOrder.STATUS_PAID,
            )
            return Response(
                {'success': False, 'error': {'code': 500, 'message': 'Fulfillment failed.'}},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        log['order'] = RazorpayOrder.objects.filter(razorpay_order_id=order_id).first()
        if result is None:
            log['status'] = RazorpayWebhookEvent.STATUS_IGNORED
            return Response(
                {'success': True, 'ignored': True, 'reason': 'unknown_purpose'},
                status=status.HTTP_200_OK,
            )

        if result.transaction is not None:
            log['transaction'] = result.transaction
        if result.created:
            log['status'] = RazorpayWebhookEvent.STATUS_FULFILLED
        else:
            log['status'] = RazorpayWebhookEvent.STATUS_DUPLICATE

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
