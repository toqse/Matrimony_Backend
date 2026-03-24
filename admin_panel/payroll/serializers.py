from django.urls import reverse
from rest_framework import serializers

from admin_panel.auth.models import AdminUser

from .models import SalaryRecord


class SalaryRecordSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source="staff.name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    month_display = serializers.SerializerMethodField()

    def get_month_display(self, obj):
        if not obj.month:
            return None
        return obj.month.strftime("%Y-%m")

    class Meta:
        model = SalaryRecord
        fields = [
            "id",
            "staff_name",
            "branch_name",
            "month",
            "month_display",
            "basic",
            "commission",
            "allowances",
            "deductions",
            "gross",
            "net",
            "status",
            "approved_by",
            "paid_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class SalaryRecordListSerializer(serializers.ModelSerializer):
    """Table row: Staff, Branch, Month, Basic, Commission, Allowances, Deductions, Gross, Net, Status."""

    staff = serializers.CharField(source="staff.name", read_only=True)
    branch = serializers.CharField(source="branch.name", read_only=True)
    month = serializers.SerializerMethodField()

    def get_month(self, obj):
        if not obj.month:
            return None
        return obj.month.strftime("%B %Y")

    class Meta:
        model = SalaryRecord
        fields = [
            "id",
            "staff",
            "branch",
            "month",
            "basic",
            "commission",
            "allowances",
            "deductions",
            "gross",
            "net",
            "status",
        ]


def _role_can_generate(user) -> bool:
    return getattr(user, "role", None) == AdminUser.ROLE_ADMIN


def _role_can_mark_paid(user) -> bool:
    return getattr(user, "role", None) == AdminUser.ROLE_ADMIN


def _role_can_approve(user) -> bool:
    r = getattr(user, "role", None)
    return r in (AdminUser.ROLE_ADMIN, AdminUser.ROLE_BRANCH_MANAGER)


def _branch_download_url(request, pk: int) -> str:
    if not request:
        return ""
    path = reverse("branch-payroll-download", kwargs={"pk": pk})
    return request.build_absolute_uri(path)


class BranchSalaryRecordListSerializer(serializers.ModelSerializer):
    """Branch Manager table row — includes download_url for slip."""

    staff = serializers.CharField(source="staff.name", read_only=True)
    month = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()
    download = serializers.SerializerMethodField()
    dections = serializers.DecimalField(source="deductions", max_digits=12, decimal_places=2, read_only=True)

    def get_month(self, obj):
        if not obj.month:
            return None
        return obj.month.strftime("%B %Y")

    def get_download_url(self, obj):
        return _branch_download_url(self.context.get("request"), obj.pk)

    def get_download(self, obj):
        return _branch_download_url(self.context.get("request"), obj.pk)

    class Meta:
        model = SalaryRecord
        fields = [
            "id",
            "staff",
            "month",
            "basic",
            "commission",
            "allowances",
            "deductions",
            "gross",
            "net",
            "status",
            "download_url",
            "download",
            "dections",
        ]


class BranchSalaryRecordDetailSerializer(serializers.ModelSerializer):
    staff = serializers.CharField(source="staff.name", read_only=True)
    month = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()
    download = serializers.SerializerMethodField()
    dections = serializers.DecimalField(source="deductions", max_digits=12, decimal_places=2, read_only=True)

    def get_month(self, obj):
        if not obj.month:
            return None
        return obj.month.strftime("%B %Y")

    def get_download_url(self, obj):
        return _branch_download_url(self.context.get("request"), obj.pk)

    def get_download(self, obj):
        return _branch_download_url(self.context.get("request"), obj.pk)

    class Meta:
        model = SalaryRecord
        fields = [
            "id",
            "staff",
            "month",
            "basic",
            "commission",
            "allowances",
            "deductions",
            "gross",
            "net",
            "status",
            "download_url",
            "download",
            "dections",
        ]
