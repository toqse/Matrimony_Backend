from __future__ import annotations

from rest_framework import serializers

from admin_panel.commissions.models import Commission


def plan_display_name(obj: Commission) -> str:
    if obj.subscription_id and getattr(obj.subscription, "plan", None):
        return obj.subscription.plan.name or ""
    if obj.plan_id and obj.plan:
        return obj.plan.name or ""
    return ""


class StaffCommissionListSerializer(serializers.ModelSerializer):
    date = serializers.SerializerMethodField()
    customer = serializers.CharField(source="customer.name", read_only=True)
    plan = serializers.SerializerMethodField()
    rate = serializers.SerializerMethodField()
    commission = serializers.DecimalField(
        source="commission_amt", max_digits=12, decimal_places=2, read_only=True
    )

    class Meta:
        model = Commission
        fields = ["id", "date", "customer", "plan", "sale_amount", "rate", "commission", "status"]

    def get_date(self, obj: Commission) -> str | None:
        if not obj.created_at:
            return None
        return obj.created_at.date().isoformat()

    def get_plan(self, obj: Commission) -> str:
        return plan_display_name(obj)

    def get_rate(self, obj: Commission) -> float:
        return float(obj.commission_rate or 0)


class StaffCommissionDetailSerializer(StaffCommissionListSerializer):
    matri_id = serializers.CharField(source="customer.matri_id", read_only=True)

    class Meta:
        model = Commission
        fields = StaffCommissionListSerializer.Meta.fields + ["matri_id"]
