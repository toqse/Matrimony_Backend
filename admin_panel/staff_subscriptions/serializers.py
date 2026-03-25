from rest_framework import serializers

from .services import STAFF_PAYMENT_MODES


class StaffSubscriptionCreateSerializer(serializers.Serializer):
    customer_matri_id = serializers.CharField(
        required=True,
        allow_blank=True,
        error_messages={
            "required": "customer_matri_id is required.",
        },
    )

    def validate_customer_matri_id(self, value):
        if value is None or not str(value).strip():
            raise serializers.ValidationError("customer_matri_id is required.")
        return str(value).strip()
    plan_id = serializers.IntegerField(
        required=True,
        error_messages={"required": "plan_id is required."},
    )
    payment_mode = serializers.ChoiceField(
        choices=sorted(STAFF_PAYMENT_MODES),
        required=True,
        error_messages={
            "required": "payment_mode is required.",
            "invalid_choice": (
                "Invalid payment mode. Must be: cash, upi, card, netbanking."
            ),
        },
    )
    payment_reference = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, default=""
    )
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=True,
        error_messages={"required": "amount is required."},
    )


class StaffSubscriptionRenewSerializer(serializers.Serializer):
    payment_mode = serializers.ChoiceField(
        choices=sorted(STAFF_PAYMENT_MODES),
        required=True,
        error_messages={
            "required": "payment_mode is required.",
            "invalid_choice": (
                "Invalid payment mode. Must be: cash, upi, card, netbanking."
            ),
        },
    )
    payment_reference = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, default=""
    )
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=True,
        error_messages={"required": "amount is required."},
    )
