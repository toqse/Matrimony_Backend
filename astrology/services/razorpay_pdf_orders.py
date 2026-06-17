"""Razorpay order creation and payment verification for astrology PDF products."""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings

from plans.models import Transaction
from plans.razorpay_client import (
    RazorpayApiError,
    RazorpayNotConfiguredError,
    create_razorpay_order,
    fetch_payment,
    inr_to_paise,
    verify_payment_signature,
)

from ..models import AstrologyPdfCredit

# Re-export for astrology views
__all__ = [
    'RazorpayApiError',
    'RazorpayNotConfiguredError',
    'amount_paise',
    'catalog_price_inr',
    'create_order',
    'fetch_payment',
    'transaction_type_for_product',
    'verify_payment_signature',
]


def catalog_price_inr(product: str) -> Decimal:
    if product == AstrologyPdfCredit.PRODUCT_JATHAKAM:
        return Decimal(str(getattr(settings, 'ASTROLOGY_JATHAKAM_PRICE_INR', '175')))
    if product == AstrologyPdfCredit.PRODUCT_THALAKURI:
        return Decimal(str(getattr(settings, 'ASTROLOGY_THALAKURI_PRICE_INR', '20')))
    raise ValueError('Invalid product.')


def amount_paise(product: str) -> int:
    return inr_to_paise(catalog_price_inr(product))


def transaction_type_for_product(product: str) -> str:
    if product == AstrologyPdfCredit.PRODUCT_JATHAKAM:
        return Transaction.TYPE_JATHAKAM_PDF
    if product == AstrologyPdfCredit.PRODUCT_THALAKURI:
        return Transaction.TYPE_THALAKURI_PDF
    raise ValueError('Invalid product.')


def create_order(*, user_matri_id: str, product: str) -> dict:
    """Create a Razorpay order for an astrology PDF product."""
    amt = amount_paise(product)
    receipt = f'{product[:2]}{uuid.uuid4().hex}'[:40]
    return create_razorpay_order(
        amount_paise=amt,
        receipt=receipt,
        notes={
            'product': product,
            'matri_id': user_matri_id or '',
            'purpose': 'astrology_pdf',
        },
    )
