from rest_framework import serializers

from .models import MobileAppConfig


class MobileAppConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = MobileAppConfig
        fields = (
            "android_version",
            "ios_version",
            "android_force_update",
            "ios_force_update",
            "updated_at",
        )
        read_only_fields = ("updated_at",)

    def validate_android_version(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Android version cannot be empty.")
        return value

    def validate_ios_version(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("iOS version cannot be empty.")
        return value
