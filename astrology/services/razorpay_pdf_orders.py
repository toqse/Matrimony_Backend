"""Razorpay order creation and payment verification for astrology PDF products."""
from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from decimal import Decimal

import requests
from django.conf import settings

from plans.models import Transaction

from ..models import AstrologyPdfCredit

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


def catalog_price_inr(product: str) -> Decimal:
    if product == AstrologyPdfCredit.PRODUCT_JATHAKAM:
        return Decimal(str(getattr(settings, 'ASTROLOGY_JATHAKAM_PRICE_INR', '175')))
    if product == AstrologyPdfCredit.PRODUCT_THALAKURI:
        return Decimal(str(getattr(settings, 'ASTROLOGY_THALAKURI_PRICE_INR', '20')))
    raise ValueError('Invalid product.')


def amount_paise(product: str) -> int:
    paise = (catalog_price_inr(product) * Decimal('100')).quantize(Decimal('1'))
    return int(paise)


def transaction_type_for_product(product: str) -> str:
    if product == AstrologyPdfCredit.PRODUCT_JATHAKAM:
        return Transaction.TYPE_JATHAKAM_PDF
    if product == AstrologyPdfCredit.PRODUCT_THALAKURI:
        return Transaction.TYPE_THALAKURI_PDF
    raise ValueError('Invalid product.')


def create_order(*, user_matri_id: str, product: str) -> dict:
    """
    Create a Razorpay order. Returns dict with id, amount, currency, receipt (and caller adds key_id).
    """
    key_id, key_secret = razorpay_credentials()
    amt = amount_paise(product)
    receipt = f'{product[:2]}{uuid.uuid4().hex}'[:40]
    payload = {
        'amount': amt,
        'currency': 'INR',
        'receipt': receipt,
        'notes': {
            'product': product,
            'matri_id': user_matri_id or '',
        },
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
