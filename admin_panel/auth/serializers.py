import re

from django.utils import timezone
from rest_framework import serializers

from .models import AdminUser


ROLE_CHOICES = {AdminUser.ROLE_ADMIN, AdminUser.ROLE_BRANCH_MANAGER, AdminUser.ROLE_STAFF}


def normalize_admin_role(value: str) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return ""
    compressed = raw.replace("-", "_").replace(" ", "_")
    compact = compressed.replace("_", "")

    aliases = {
        "admin": AdminUser.ROLE_ADMIN,
        "branch_manager": AdminUser.ROLE_BRANCH_MANAGER,
        "branchmanager": AdminUser.ROLE_BRANCH_MANAGER,
        "staff": AdminUser.ROLE_STAFF,
    }
    return aliases.get(compressed) or aliases.get(compact) or raw


def normalize_indian_mobile_10_to_e164(mobile_10: str) -> str:
    from core.phone import normalize_phone_input
    return normalize_phone_input(mobile_10)


def mobile_to_display(mobile_e164: str) -> str:
    from core.phone import to_display_spaced
    return to_display_spaced(mobile_e164)


class SendOTPSerializer(serializers.Serializer):
    mobile = serializers.CharField(required=True)
    role = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_role(self, value: str) -> str:
        raw = (value or "").strip()
        if not raw:
            return ""
        v = normalize_admin_role(raw)
        if v not in ROLE_CHOICES:
            raise serializers.ValidationError("Please select a valid role")
        return v

    def validate_mobile(self, value: str) -> str:
        return normalize_indian_mobile_10_to_e164(value)


class VerifyOTPSerializer(serializers.Serializer):
    mobile = serializers.CharField(required=True)
    role = serializers.CharField(required=False, allow_blank=True, default="")
    otp = serializers.CharField(required=True)

    def validate_role(self, value: str) -> str:
        raw = (value or "").strip()
        if not raw:
            return ""
        v = normalize_admin_role(raw)
        if v not in ROLE_CHOICES:
            raise serializers.ValidationError("Please select a valid role")
        return v

    def validate_mobile(self, value: str) -> str:
        return normalize_indian_mobile_10_to_e164(value)

    def validate_otp(self, value: str) -> str:
        v = (value or "").strip()
        if not re.fullmatch(r"\d{6}", v):
            raise serializers.ValidationError("OTP must be 6 digits")
        return v


class TokenRefreshSerializer(serializers.Serializer):
    refresh_token = serializers.CharField(required=True)


class LogoutSerializer(serializers.Serializer):
    refresh_token = serializers.CharField(required=True)


class AdminProfileSerializer(serializers.ModelSerializer):
    mobile_display = serializers.SerializerMethodField()
    role_display = serializers.SerializerMethodField()

    class Meta:
        model = AdminUser
        fields = [
            "id",
            "name",
            "email",
            "mobile",
            "mobile_display",
            "role",
            "role_display",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        from core.phone import to_e164_display
        data["mobile"] = to_e164_display(instance.mobile)
        data["mobile_display"] = mobile_to_display(instance.mobile)
        return data

    def get_mobile_display(self, obj):
        return mobile_to_display(obj.mobile)

    def get_role_display(self, obj):
        return obj.get_role_display()


class AdminProfileUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(required=True, allow_blank=True)
    email = serializers.EmailField(required=True)

    def validate_name(self, value):
        v = (value or "").strip()
        if not v:
            raise serializers.ValidationError("Name is required.")
        if len(v) < 2:
            raise serializers.ValidationError("Name must be at least 2 characters.")
        if len(v) > 100:
            raise serializers.ValidationError("Name must not exceed 100 characters.")
        return v

    def validate_email(self, value):
        email = (value or "").strip().lower()
        user = self.context.get("user")
        qs = AdminUser.objects.filter(email__iexact=email)
        if user is not None:
            qs = qs.exclude(pk=user.pk)
        if qs.exists():
            raise serializers.ValidationError("This email is already registered to another account.")
        return email


class ChangePhoneSendOTPSerializer(serializers.Serializer):
    new_mobile = serializers.CharField(required=True)

    def validate_new_mobile(self, value):
        from core.phone import normalize_phone_input, personal_mobile_in_use

        mobile = normalize_phone_input(value)
        user = self.context.get("user")
        err = personal_mobile_in_use(
            mobile,
            exclude_admin_user_id=user.pk if user is not None else None,
        )
        if err:
            raise serializers.ValidationError(err)
        return mobile


class ChangePhoneVerifyOTPSerializer(serializers.Serializer):
    new_mobile = serializers.CharField(required=True)
    otp = serializers.CharField(required=True)

    def validate_new_mobile(self, value):
        from core.phone import normalize_phone_input

        return normalize_phone_input(value)

    def validate_otp(self, value):
        v = (value or "").strip()
        if not re.fullmatch(r"\d{6}", v):
            raise serializers.ValidationError("OTP must be 6 digits.")
        return v


def admin_permissions_for_role(role: str) -> list[str]:
    role = normalize_admin_role(role)
    if role == AdminUser.ROLE_ADMIN:
        return ["manage_branches", "manage_staff", "view_reports"]
    if role == AdminUser.ROLE_BRANCH_MANAGER:
        return ["manage_staff", "view_reports"]
    if role == AdminUser.ROLE_STAFF:
        return ["view_reports"]
    return []


def branch_payload(user: AdminUser):
    if not getattr(user, "branch_id", None) or not getattr(user, "branch", None):
        return None
    return {"id": user.branch.id, "name": user.branch.name}

