from __future__ import annotations

import re

from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, transaction
from rest_framework import serializers

from admin_panel.auth.models import AdminUser
from admin_panel.auth.serializers import normalize_admin_role
from master.models import Branch as MasterBranch

from .branch_sync import ensure_master_branch_from_admin_branch
from .models import StaffProfile


def _to_e164(mobile_10: str) -> str:
    return f"+91{mobile_10}"


def _next_emp_code() -> str:
    last = StaffProfile.objects.order_by("-id").values_list("emp_code", flat=True).first()
    if not last:
        return "EMP001"
    m = re.search(r"(\d+)$", last or "")
    n = int(m.group(1)) if m else 0
    return f"EMP{n + 1:03d}"


def _get_admin_user_branch_code(user):
    return (
        MasterBranch.objects.filter(pk=getattr(user, "branch_id", None))
        .values_list("code", flat=True)
        .first()
    )


class StaffSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField(read_only=True)
    target_progress = serializers.SerializerMethodField(read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    # Write: login role (staff | branch_manager). Read: actual AdminUser.role (mirrored as account_role).
    role = serializers.ChoiceField(
        choices=[AdminUser.ROLE_STAFF, AdminUser.ROLE_BRANCH_MANAGER],
        write_only=True,
    )
    account_role = serializers.CharField(source="admin_user.role", read_only=True)

    class Meta:
        model = StaffProfile
        fields = [
            "id",
            "emp_code",
            "name",
            "mobile",
            "email",
            "profile_photo",
            "branch",
            "branch_name",
            "designation",
            "department",
            "joining_date",
            "basic_salary",
            "commission_rate",
            "monthly_target",
            "achieved_target",
            "pf_number",
            "esi_number",
            "street_address",
            "city",
            "state",
            "pincode",
            "bank_name",
            "account_number",
            "ifsc_code",
            "upi_id",
            "login_username",
            "password",
            "role",
            "account_role",
            "is_active",
            "status",
            "target_progress",
            "created_at",
        ]
        read_only_fields = ["emp_code", "status", "target_progress", "created_at", "branch_name", "account_role"]
        extra_kwargs = {
            "name": {"required": True},
            "mobile": {"required": True},
            "designation": {"required": True},
            "basic_salary": {"required": True},
            "commission_rate": {"required": False},
            "monthly_target": {"required": True},
            "branch": {"required": True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Create must send explicit role (avoids accidental default "staff" when UI omits the field).
        if self.instance is None:
            self.fields["role"].required = True
        else:
            self.fields["role"].required = False

    def get_status(self, obj):
        return "active" if obj.is_active else "inactive"

    def get_target_progress(self, obj):
        return {"achieved": int(obj.achieved_target or 0), "target": int(obj.monthly_target or 0)}

    def validate_name(self, value):
        v = (value or "").strip()
        if not v:
            raise serializers.ValidationError("Staff name is required")
        return v

    def validate_mobile(self, value):
        v = (value or "").strip()
        if not re.fullmatch(r"\d{10}", v):
            raise serializers.ValidationError("Mobile must be 10 digits")
        qs = StaffProfile.objects.filter(mobile=v, is_deleted=False)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Mobile already registered to another staff member")
        return v

    def validate_email(self, value):
        if not value:
            return None
        qs = StaffProfile.objects.filter(email__iexact=value, is_deleted=False)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Email already in use")
        return value

    def validate_branch(self, value):
        if not value or not value.is_active:
            raise serializers.ValidationError("Selected branch is inactive or does not exist")
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user and normalize_admin_role(getattr(user, "role", "")) == AdminUser.ROLE_BRANCH_MANAGER:
            manager_code = _get_admin_user_branch_code(user)
            if not manager_code or manager_code != value.code:
                raise serializers.ValidationError("Access denied")
        return value

    def validate_designation(self, value):
        v = (value or "").strip()
        if not v:
            raise serializers.ValidationError("Designation is required")
        return v

    def validate_basic_salary(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError("Salary must be a positive number")
        return value

    def validate_commission_rate(self, value):
        if value is None:
            return 0
        if value < 0 or value > 100:
            raise serializers.ValidationError("Commission rate must be between 0 and 100")
        return value

    def validate_monthly_target(self, value):
        if value is None or int(value) <= 0:
            raise serializers.ValidationError("Target must be a positive number")
        return int(value)

    def validate_role(self, value):
        v = normalize_admin_role(value or "")
        if v not in (AdminUser.ROLE_STAFF, AdminUser.ROLE_BRANCH_MANAGER):
            raise serializers.ValidationError("Role must be staff or branch_manager")
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        actor_role = normalize_admin_role(getattr(actor, "role", ""))
        if v == AdminUser.ROLE_BRANCH_MANAGER and actor_role != AdminUser.ROLE_ADMIN:
            raise serializers.ValidationError("Only admin can assign branch manager role")
        return v

    def _create_admin_user(self, validated_data, admin_role):
        # AdminUser.branch → master.Branch; ensure row exists (same code as admin branch).
        staff_branch = validated_data["branch"]
        master_branch = ensure_master_branch_from_admin_branch(staff_branch)
        if not master_branch:
            raise serializers.ValidationError(
                {"branch": "Cannot resolve master branch for this selection."}
            )
        return AdminUser.objects.create(
            mobile=_to_e164(validated_data["mobile"]),
            role=admin_role,
            name=validated_data["name"],
            branch=master_branch,
            is_active=validated_data.get("is_active", True),
        )

    def create(self, validated_data):
        raw_password = validated_data.pop("password", "")
        admin_role = normalize_admin_role(validated_data.pop("role"))
        with transaction.atomic():
            for _ in range(5):
                try:
                    admin_user = self._create_admin_user(validated_data, admin_role)
                    validated_data["admin_user"] = admin_user
                    validated_data["emp_code"] = _next_emp_code()
                    if raw_password:
                        validated_data["login_password_hash"] = make_password(raw_password)
                    return StaffProfile.objects.create(**validated_data)
                except IntegrityError:
                    continue
        raise serializers.ValidationError("Unable to generate unique employee code. Please try again.")

    def update(self, instance, validated_data):
        raw_password = validated_data.pop("password", None)
        admin_user = instance.admin_user
        if "role" in validated_data:
            admin_user.role = normalize_admin_role(validated_data.pop("role"))
        if "name" in validated_data:
            admin_user.name = validated_data["name"]
        if "branch" in validated_data:
            master_branch = ensure_master_branch_from_admin_branch(validated_data["branch"])
            if not master_branch:
                raise serializers.ValidationError(
                    {"branch": "Cannot resolve master branch for this selection."}
                )
            admin_user.branch = master_branch
        if "is_active" in validated_data:
            admin_user.is_active = validated_data["is_active"]
        if "mobile" in validated_data:
            admin_user.mobile = _to_e164(validated_data["mobile"])
        admin_user.save()

        if raw_password:
            validated_data["login_password_hash"] = make_password(raw_password)
        return super().update(instance, validated_data)

