"""Razorpay order creation and payment fulfillment for astrology PDF products."""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import transaction as db_transaction

from plans.models import Transaction
from plans.razorpay_client import (
    RazorpayApiError,
    RazorpayNotConfiguredError,
    create_razorpay_order,
    fetch_payment,
    inr_to_paise,
    verify_payment_signature,
)
from plans.razorpay_fulfillment import (
    RAZORPAY_PURPOSE_ASTROLOGY_PDF,
    FulfillmentError,
    FulfillmentResult,
    get_success_txn_by_payment_id,
    resolve_user_from_notes,
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
    'fulfill_pdf_payment',
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


def create_order(*, user_matri_id: str, product: str, user_id: str | int | None = None) -> dict:
    """Create a Razorpay order for an astrology PDF product."""
    amt = amount_paise(product)
    receipt = f'{product[:2]}{uuid.uuid4().hex}'[:40]
    notes = {
        'product': product,
        'matri_id': user_matri_id or '',
        'purpose': RAZORPAY_PURPOSE_ASTROLOGY_PDF,
    }
    if user_id is not None and str(user_id).strip():
        notes['user_id'] = str(user_id)
    return create_razorpay_order(
        amount_paise=amt,
        receipt=receipt,
        notes=notes,
    )


def fulfill_pdf_payment(
    *,
    payment_id: str,
    order: dict,
    expected_paise: int | None = None,
    expected_product: str | None = None,
) -> FulfillmentResult:
    """
    Grant AstrologyPdfCredit for a captured Razorpay payment.
    Idempotent on payment_id.
    """
    notes = order.get('notes') or {}
    if notes.get('purpose') != RAZORPAY_PURPOSE_ASTROLOGY_PDF:
        raise FulfillmentError('Order is not for astrology PDF.', code='WRONG_PURPOSE')

    product = str(notes.get('product') or '').strip()
    if expected_product and product != expected_product:
        raise FulfillmentError('Order product does not match request.', code='PRODUCT_MISMATCH')
    if product not in (
        AstrologyPdfCredit.PRODUCT_JATHAKAM,
        AstrologyPdfCredit.PRODUCT_THALAKURI,
    ):
        raise FulfillmentError('Invalid PDF product on order.', code='INVALID_PRODUCT')

    expected_type = transaction_type_for_product(product)
    price = catalog_price_inr(product)
    paise = amount_paise(product)
    if expected_paise is not None and int(expected_paise) != paise:
        raise FulfillmentError('Payment amount does not match product price.', code='AMOUNT_MISMATCH')

    existing = get_success_txn_by_payment_id(payment_id)
    if existing:
        if existing.transaction_type != expected_type:
            raise FulfillmentError('Payment does not match this product.', code='TYPE_MISMATCH')
        with db_transaction.atomic():
            credit, _ = AstrologyPdfCredit.objects.get_or_create(
                transaction=existing,
                defaults={'user': existing.user, 'product': product},
            )
        if credit.product != product:
            raise FulfillmentError('Credit product mismatch.', code='CREDIT_MISMATCH')
        return FulfillmentResult(
            created=False,
            purpose=RAZORPAY_PURPOSE_ASTROLOGY_PDF,
            transaction=existing,
            user=existing.user,
            credit=credit,
            message='PDF credit already granted for this payment.',
        )

    user = resolve_user_from_notes(notes)

    with db_transaction.atomic():
        locked = (
            Transaction.objects.select_for_update()
            .filter(transaction_id=payment_id)
            .first()
        )
        if locked:
            if locked.payment_status != Transaction.STATUS_SUCCESS:
                raise FulfillmentError(
                    'Payment transaction is not successful.', code='TXN_NOT_SUCCESS'
                )
            if locked.transaction_type != expected_type:
                raise FulfillmentError(
                    'Payment does not match this product.', code='TYPE_MISMATCH'
                )
            credit, _ = AstrologyPdfCredit.objects.get_or_create(
                transaction=locked,
                defaults={'user': locked.user, 'product': product},
            )
            if credit.product != product:
                raise FulfillmentError('Credit product mismatch.', code='CREDIT_MISMATCH')
            return FulfillmentResult(
                created=False,
                purpose=RAZORPAY_PURPOSE_ASTROLOGY_PDF,
                transaction=locked,
                user=locked.user,
                credit=credit,
                message='PDF credit already granted for this payment.',
            )

        txn = Transaction.objects.create(
            user=user,
            plan=None,
            amount=price,
            service_charge=Decimal('0'),
            total_amount=price,
            payment_method=Transaction.PAYMENT_RAZORPAY,
            payment_status=Transaction.STATUS_SUCCESS,
            transaction_type=expected_type,
            transaction_id=payment_id,
        )
        credit = AstrologyPdfCredit.objects.create(
            user=user,
            product=product,
            transaction=txn,
        )

    return FulfillmentResult(
        created=True,
        purpose=RAZORPAY_PURPOSE_ASTROLOGY_PDF,
        transaction=txn,
        user=user,
        credit=credit,
        message='PDF credit granted.',
    )
