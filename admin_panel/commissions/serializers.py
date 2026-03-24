from decimal import Decimal

from rest_framework import serializers

from accounts.models import User
from admin_panel.auth.models import AdminUser
from admin_panel.staff_mgmt.models import StaffProfile
from master.models import Branch as MasterBranch
from plans.models import Plan, UserPlan

from .models import Commission


def _manager_branch_code(user):
    return (
        MasterBranch.objects.filter(pk=getattr(user, "branch_id", None))
        .values_list("code", flat=True)
        .first()
    )


def _plan_display_name(obj: Commission) -> str:
    if obj.subscription_id and getattr(obj.subscription, "plan", None):
        return obj.subscription.plan.name or ""
    if obj.plan_id and obj.plan:
        return obj.plan.name or ""
    return ""


class CommissionSerializer(serializers.ModelSerializer):
    staff = serializers.CharField(source="staff.name", read_only=True)
    branch = serializers.CharField(source="branch.name", read_only=True)
    customer = serializers.CharField(source="customer.name", read_only=True)
    matri_id = serializers.CharField(source="customer.matri_id", read_only=True)
    plan = serializers.SerializerMethodField()
    amount = serializers.DecimalField(source="sale_amount", max_digits=12, decimal_places=2, read_only=True)
    rate = serializers.DecimalField(source="commission_rate", max_digits=5, decimal_places=2, read_only=True)
    commission = serializers.DecimalField(source="commission_amt", max_digits=12, decimal_places=2, read_only=True)
    sale_amt = serializers.DecimalField(source="sale_amount", max_digits=12, decimal_places=2, read_only=True)
    date = serializers.SerializerMethodField()
    status_label = serializers.SerializerMethodField()
    slip_url = serializers.SerializerMethodField()
    can_approve = serializers.SerializerMethodField()
    can_mark_paid = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()
    can_view = serializers.SerializerMethodField()
    can_download_slip = serializers.SerializerMethodField()
    approve_url = serializers.SerializerMethodField()
    mark_paid_url = serializers.SerializerMethodField()
    cancel_url = serializers.SerializerMethodField()
    detail_url = serializers.SerializerMethodField()

    def get_date(self, obj):
        if not obj.created_at:
            return None
        return obj.created_at.date().isoformat()

    def get_plan(self, obj):
        return _plan_display_name(obj)

    def get_status_label(self, obj):
        return obj.get_status_display()

    def _branch_path(self, obj, suffix: str = "") -> str:
        return f"/api/v1/branch/commissions/{obj.pk}/{suffix}" if suffix else f"/api/v1/branch/commissions/{obj.pk}/"

    def get_slip_url(self, obj):
        return self._branch_path(obj, "slip/")

    def get_can_approve(self, obj):
        return obj.status == Commission.STATUS_PENDING

    def get_can_mark_paid(self, obj):
        # Branch endpoint exists but returns 403 by design; keep explicit false for UI.
        return False

    def get_can_cancel(self, obj):
        return obj.status == Commission.STATUS_PENDING

    def get_can_view(self, obj):
        return True

    def get_can_download_slip(self, obj):
        return True

    def get_approve_url(self, obj):
        return self._branch_path(obj, "approve/")

    def get_mark_paid_url(self, obj):
        return self._branch_path(obj, "mark-paid/")

    def get_cancel_url(self, obj):
        return self._branch_path(obj, "cancel/")

    def get_detail_url(self, obj):
        return self._branch_path(obj)

    class Meta:
        model = Commission
        fields = [
            "id",
            "date",
            "staff",
            "branch",
            "customer",
            "matri_id",
            "plan",
            "amount",
            "sale_amt",
            "rate",
            "commission",
            "status",
            "status_label",
            "can_approve",
            "can_mark_paid",
            "can_cancel",
            "can_view",
            "can_download_slip",
            "approve_url",
            "mark_paid_url",
            "cancel_url",
            "detail_url",
            "slip_url",
            "paid_at",
            "created_at",
        ]


class CommissionCreateSerializer(serializers.Serializer):
    """
    Manual add commission (Admin or Branch Manager for own branch).
    Either:
      - staff_id + matri_id + plan_id + sale_amount [+ commission_rate]
      - staff_id + user_plan_id + sale_amount [+ commission_rate]
    """

    staff_id = serializers.IntegerField(required=True)
    matri_id = serializers.CharField(required=False, allow_blank=True)
    plan_id = serializers.IntegerField(required=False, allow_null=True)
    user_plan_id = serializers.IntegerField(required=False, allow_null=True)
    sale_amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=True)
    commission_rate = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)

    def validate_sale_amount(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError("Sale amount must be a positive number")
        return value

    def validate_staff_id(self, value):
        try:
            s = StaffProfile.objects.get(pk=value, is_deleted=False)
        except StaffProfile.DoesNotExist:
            raise serializers.ValidationError("Staff not found")
        if not s.is_active:
            raise serializers.ValidationError("Staff is inactive")
        return value

    def validate(self, attrs):
        matri = (attrs.get("matri_id") or "").strip()
        plan_id = attrs.get("plan_id")
        up_id = attrs.get("user_plan_id")
        has_manual = bool(matri and plan_id is not None)
        has_sub = bool(up_id)
        if has_manual and has_sub:
            raise serializers.ValidationError(
                "Do not combine user_plan_id with matri_id/plan_id."
            )
        if not has_manual and not has_sub:
            raise serializers.ValidationError(
                "Provide either (matri_id + plan_id) for a manual sale, or user_plan_id for an existing subscription."
            )

        request = self.context.get("request")
        if request:
            role = getattr(request.user, "role", None)
            if role == AdminUser.ROLE_STAFF:
                raise serializers.ValidationError("Insufficient permissions")
            staff = StaffProfile.objects.select_related("branch").get(pk=attrs["staff_id"])
            if role == AdminUser.ROLE_BRANCH_MANAGER:
                code = _manager_branch_code(request.user)
                if not code or staff.branch.code != code:
                    raise serializers.ValidationError(
                        {"staff_id": "You can only add commissions for staff in your branch."}
                    )
        return attrs

    def validate_matri_id(self, value):
        if value is None:
            return value
        v = (value or "").strip()
        if not v:
            return None
        if not User.objects.filter(matri_id__iexact=v).exists():
            raise serializers.ValidationError("No customer found with this matri_id")
        return v

    def validate_plan_id(self, value):
        if value is None:
            return value
        if not Plan.objects.filter(pk=value, is_active=True).exists():
            raise serializers.ValidationError("Invalid or inactive plan")
        return value

    def validate_user_plan_id(self, value):
        if value is None:
            return value
        if not UserPlan.objects.filter(pk=value).exists():
            raise serializers.ValidationError("Subscription not found")
        return value

    def create(self, validated_data):
        staff = StaffProfile.objects.select_related("branch").get(pk=validated_data["staff_id"])
        sale = Decimal(validated_data["sale_amount"])
        rate = validated_data.get("commission_rate")
        if rate is None:
            rate = Decimal(staff.commission_rate or 0)
        else:
            rate = Decimal(rate)
        if rate < 0 or rate > 100:
            raise serializers.ValidationError({"commission_rate": "Commission rate must be between 0 and 100"})
        commission_amt = (sale * rate) / Decimal("100")

        if validated_data.get("user_plan_id"):
            up = UserPlan.objects.select_related("user", "plan").get(pk=validated_data["user_plan_id"])
            customer = up.user
            subscription = up
            branch = staff.branch
            plan_fk = None
        else:
            customer = User.objects.get(matri_id__iexact=validated_data["matri_id"].strip())
            plan_fk = Plan.objects.get(pk=validated_data["plan_id"])
            subscription = None
            branch = staff.branch

        return Commission.objects.create(
            staff=staff,
            subscription=subscription,
            plan=plan_fk,
            customer=customer,
            branch=branch,
            sale_amount=sale,
            commission_rate=rate,
            commission_amt=commission_amt,
            status=Commission.STATUS_PENDING,
        )
