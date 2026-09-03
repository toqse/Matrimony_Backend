"""Shared Razorpay REST client (orders, payments, signature verification)."""
from __future__ import annotations

import hashlib
import hmac
import logging
from decimal import Decimal

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

RAZORPAY_API = 'https://api.razorpay.com/v1'


class RazorpayNotConfiguredError(Exception):
    """Missing RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET."""


class RazorpayApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def razorpay_credentials() -> tuple[str, str]:
    key_id = (getattr(settings, 'RAZORPAY_KEY_ID', '') or '').strip()
    key_secret = (getattr(settings, 'RAZORPAY_KEY_SECRET', '') or '').strip()
    if not key_id or not key_secret:
        raise RazorpayNotConfiguredError('Razorpay is not configured.')
    return key_id, key_secret


def inr_to_paise(amount_inr: Decimal) -> int:
    paise = (amount_inr * Decimal('100')).quantize(Decimal('1'))
    return int(paise)


def create_razorpay_order(*, amount_paise: int, receipt: str, notes: dict) -> dict:
    """Create a Razorpay order. Returns order_id, amount, currency, receipt, key_id."""
    key_id, key_secret = razorpay_credentials()
    payload = {
        'amount': amount_paise,
        'currency': 'INR',
        'receipt': receipt,
        'notes': {k: str(v) for k, v in notes.items()},
    }
    url = f'{RAZORPAY_API}/orders'
    try:
        r = requests.post(url, json=payload, auth=(key_id, key_secret), timeout=30)
    except requests.RequestException as exc:
        logger.exception('Razorpay order request failed')
        raise RazorpayApiError(f'Razorpay unreachable: {exc}') from exc
    if not r.ok:
        logger.warning('Razorpay order error %s: %s', r.status_code, r.text[:500])
        raise RazorpayApiError(r.text or 'Razorpay order failed', status_code=r.status_code)
    data = r.json()
    return {
        'order_id': data.get('id'),
        'amount': data.get('amount'),
        'currency': data.get('currency', 'INR'),
        'receipt': data.get('receipt', receipt),
        'key_id': key_id,
    }


def verify_payment_signature(order_id: str, payment_id: str, signature: str) -> bool:
    _, key_secret = razorpay_credentials()
    message = f'{order_id}|{payment_id}'.encode('utf-8')
    expected = hmac.new(
        key_secret.encode('utf-8'),
        message,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, (signature or '').strip())


def verify_webhook_signature(body: bytes, signature: str) -> bool:
    """
    Verify Razorpay webhook HMAC (X-Razorpay-Signature).
    Uses RAZORPAY_WEBHOOK_SECRET (Dashboard webhook secret), not the API key secret.
    """
    secret = (getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', '') or '').strip()
    if not secret:
        raise RazorpayNotConfiguredError('Razorpay webhook secret is not configured.')
    expected = hmac.new(
        secret.encode('utf-8'),
        body if isinstance(body, (bytes, bytearray)) else str(body).encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, (signature or '').strip())


def fetch_payment(payment_id: str) -> dict:
    key_id, key_secret = razorpay_credentials()
    url = f'{RAZORPAY_API}/payments/{payment_id}'
    try:
        r = requests.get(url, auth=(key_id, key_secret), timeout=30)
    except requests.RequestException as exc:
        logger.exception('Razorpay payment fetch failed')
        raise RazorpayApiError(f'Razorpay unreachable: {exc}') from exc
    if not r.ok:
        raise RazorpayApiError(r.text or 'Payment fetch failed', status_code=r.status_code)
    return r.json()


def fetch_order(order_id: str) -> dict:
    key_id, key_secret = razorpay_credentials()
    url = f'{RAZORPAY_API}/orders/{order_id}'
    try:
        r = requests.get(url, auth=(key_id, key_secret), timeout=30)
    except requests.RequestException as exc:
        logger.exception('Razorpay order fetch failed')
        raise RazorpayApiError(f'Razorpay unreachable: {exc}') from exc
    if not r.ok:
        raise RazorpayApiError(r.text or 'Order fetch failed', status_code=r.status_code)
    return r.json()
