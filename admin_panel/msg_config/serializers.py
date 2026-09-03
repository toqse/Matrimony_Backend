from rest_framework import serializers

from .models import MsgConfig


def _mask_auth_key(key: str) -> str:
    key = (key or "").strip()
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}{'*' * max(4, len(key) - 8)}{key[-4:]}"


class MsgConfigSerializer(serializers.ModelSerializer):
    auth_key_set = serializers.SerializerMethodField()
    auth_key_masked = serializers.SerializerMethodField()
    using_env_fallback = serializers.SerializerMethodField()
    # Write-only: omit or blank keeps existing; send empty string with clear_auth_key to wipe
    auth_key = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
        max_length=255,
    )
    clear_auth_key = serializers.BooleanField(required=False, write_only=True, default=False)

    class Meta:
        model = MsgConfig
        fields = (
            "development_mode",
            "auth_key",
            "clear_auth_key",
            "auth_key_set",
            "auth_key_masked",
            "using_env_fallback",
            "integrated_number",
            "namespace",
            "updated_at",
        )
        read_only_fields = (
            "auth_key_set",
            "auth_key_masked",
            "using_env_fallback",
            "updated_at",
        )

    def get_auth_key_set(self, obj):
        return bool((obj.auth_key or "").strip() or obj.resolve_auth_key())

    def get_auth_key_masked(self, obj):
        stored = (obj.auth_key or "").strip()
        if stored:
            return _mask_auth_key(stored)
        resolved = obj.resolve_auth_key()
        if resolved:
            return _mask_auth_key(resolved)
        return ""

    def get_using_env_fallback(self, obj):
        return not bool((obj.auth_key or "").strip()) and bool(obj.resolve_auth_key())

    def validate_integrated_number(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Integrated number cannot be empty.")
        digits = "".join(c for c in value if c.isdigit())
        if len(digits) < 10:
            raise serializers.ValidationError("Integrated number must be a valid MSISDN.")
        return digits

    def validate_namespace(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Namespace cannot be empty.")
        return value

    def update(self, instance, validated_data):
        clear_auth_key = validated_data.pop("clear_auth_key", False)
        auth_key = validated_data.pop("auth_key", None)

        if clear_auth_key:
            instance.auth_key = ""
        elif auth_key is not None and auth_key.strip():
            instance.auth_key = auth_key.strip()

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance
