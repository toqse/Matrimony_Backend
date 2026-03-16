from rest_framework import serializers
from .models import UserSettings


class ProfileVisibilitySerializer(serializers.Serializer):
    profile_visibility = serializers.ChoiceField(
        choices=[c[0] for c in UserSettings.PROFILE_VISIBILITY_CHOICES],
    )


class InterestPermissionSerializer(serializers.Serializer):
    interest_permission = serializers.ChoiceField(
        choices=[c[0] for c in UserSettings.INTEREST_PERMISSION_CHOICES],
    )


class NotificationSettingsSerializer(serializers.Serializer):
    interest_request = serializers.BooleanField(required=False)
    chat = serializers.BooleanField(required=False)
    profile_views = serializers.BooleanField(required=False)
    new_matches = serializers.BooleanField(required=False)


class AccountUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(min_length=8, write_only=True)
