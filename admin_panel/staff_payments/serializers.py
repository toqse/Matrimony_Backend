from __future__ import annotations

from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from accounts.models import User
from plans.models import Plan


class PaymentFlowValidationError(serializers.ValidationError):
    def __init__(self, *, code: str, message: str, status_code: int = 400):
        super().__init__(
            {
                "code": code,
                "status": status_code,
                "message": message,
            }
        )


class StaffPaymentCreateSerializer(serializers.Serializer):
    MODE_CASH = "cash"
    MODE_GPAY_UPI = "gpay_upi"
    VALID_MODES = (MODE_CASH, MODE_GPAY_UPI)

    mode = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    customer_matri_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    plan_id = serializers.IntegerField(required=False, allow_null=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    discount_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    reference_no = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    physical_receipt_no = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    cashier_receipt_no = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    otp = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def _fail(self, *, code: str, message: str, status_code: int = 400):
        raise PaymentFlowValidationError(code=code, message=message, status_code=status_code)

    def validate(self, attrs):
        mode = (attrs.get("mode") or "").strip().lower()
        matri_id = (attrs.get("customer_matri_id") or "").strip()
        plan_id = attrs.get("plan_id")
        raw_amount = attrs.get("amount")
        raw_discount = attrs.get("discount_amount")

        if not mode or mode not in self.VALID_MODES:
            self._fail(code="INVALID_MODE", message='mode must be either "cash" or "gpay_upi".')
        if not matri_id:
            self._fail(code="CUSTOMER_NOT_FOUND", message="Customer not found.", status_code=404)
        if plan_id is None:
            self._fail(code="INVALID_PLAN", message="Invalid or inactive plan.")
        if raw_amount is None:
            self._fail(code="INVALID_AMOUNT", message="Invalid amount.")

        customer = User.objects.filter(matri_id__iexact=matri_id, role="user", is_active=True).first()
        if not customer:
            self._fail(code="CUSTOMER_NOT_FOUND", message="Customer not found.", status_code=404)

        plan = Plan.objects.filter(pk=plan_id, is_active=True).first()
        if not plan:
            self._fail(code="INVALID_PLAN", message="Invalid or inactive plan.")

        try:
            amount = Decimal(str(raw_amount))
        except (InvalidOperation, TypeError, ValueError):
            self._fail(code="INVALID_AMOUNT", message="Invalid amount.")

        try:
            discount = (
                Decimal(str(raw_discount))
                if raw_discount is not None and str(raw_discount).strip() != ""
                else Decimal("0")
            )
        except (InvalidOperation, TypeError, ValueError):
            self._fail(code="INVALID_DISCOUNT", message="Invalid discount amount.")

        if discount < Decimal("0"):
            self._fail(code="INVALID_DISCOUNT", message="Discount cannot be negative.")
        if discount >= plan.price:
            self._fail(
                code="INVALID_DISCOUNT",
                message=f"Discount must be less than plan price (₹{plan.price}).",
            )

        expected_total = (plan.price - discount).quantize(Decimal("0.01"))
        if amount <= Decimal("0"):
            self._fail(code="INVALID_AMOUNT", message="Amount must be greater than zero.")

        if amount != expected_total:
            self._fail(
                code="INVALID_AMOUNT",
                message=f"Amount must equal plan price minus discount (expected ₹{expected_total}).",
            )

        reference_no = (attrs.get("reference_no") or "").strip()
        physical_receipt_no = (attrs.get("physical_receipt_no") or "").strip()
        cashier_receipt_no = (attrs.get("cashier_receipt_no") or "").strip()
        otp = (attrs.get("otp") or "").strip()

        if mode == self.MODE_GPAY_UPI:
            if not reference_no:
                self._fail(code="REFERENCE_NO_REQUIRED", message="reference_no is required for UPI.")
        elif mode == self.MODE_CASH:
            if not physical_receipt_no:
                self._fail(
                    code="PHYSICAL_RECEIPT_NO_REQUIRED",
                    message="physical_receipt_no is required for cash payments.",
                )
            if not cashier_receipt_no:
                self._fail(
                    code="CASHIER_RECEIPT_NO_REQUIRED",
                    message="cashier_receipt_no is required for cash payments.",
                )
            if not otp:
                self._fail(code="OTP_REQUIRED", message="otp is required for cash confirmation.")

        attrs["mode"] = mode
        attrs["customer_matri_id"] = matri_id
        attrs["customer"] = customer
        attrs["plan"] = plan
        attrs["amount"] = amount
        attrs["discount_amount"] = discount
        attrs["reference_no"] = reference_no
        attrs["physical_receipt_no"] = physical_receipt_no
        attrs["cashier_receipt_no"] = cashier_receipt_no
        attrs["otp"] = otp
        attrs["notes"] = (attrs.get("notes") or "").strip()
        return attrs


class StaffPaymentPlanQuoteSerializer(serializers.Serializer):
    """POST body for /api/v1/staff/payments/quote/ — plan + discount preview."""

    plan_id = serializers.IntegerField(required=True)
    discount_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, default=Decimal("0")
    )


class StaffPaymentCustomerOtpSendSerializer(serializers.Serializer):
    customer_matri_id = serializers.CharField(required=True, max_length=30)


class StaffPaymentCustomerOtpVerifySerializer(serializers.Serializer):
    customer_matri_id = serializers.CharField(required=True, max_length=30)
    otp = serializers.CharField(required=True, max_length=12)
