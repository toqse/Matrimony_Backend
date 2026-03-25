import re

from rest_framework import serializers

from admin_panel.branches.models import Branch

SOURCE_CHOICES = ["website", "walk-in", "phone", "whatsapp", "email"]


class StaffEnquiryCreateSerializer(serializers.Serializer):
    name = serializers.CharField(
        required=True,
        error_messages={"required": "Name is required."},
    )
    phone = serializers.CharField(
        required=True,
        error_messages={"required": "Phone number is required."},
    )
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    source = serializers.ChoiceField(
        choices=SOURCE_CHOICES,
        error_messages={
            "required": "source is required.",
            "invalid_choice": (
                "Invalid source. Must be: website, walk-in, phone, whatsapp, email."
            ),
        },
    )
    branch = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.filter(is_deleted=False),
        required=False,
        allow_null=True,
    )

    def validate_name(self, value):
        if not value or not str(value).strip():
            raise serializers.ValidationError("Name is required.")
        return str(value).strip()

    def validate_phone(self, value):
        if not value:
            raise serializers.ValidationError("Phone number is required.")
        cleaned = re.sub(r"\D", "", str(value))
        if len(cleaned) != 10:
            raise serializers.ValidationError("Enter a valid 10-digit phone number.")
        return cleaned


class StaffEnquiryNoteCreateSerializer(serializers.Serializer):
    text = serializers.CharField(required=True, allow_blank=True)

    def validate_text(self, value):
        if value is None or not str(value).strip():
            raise serializers.ValidationError("Note text is required.")
        return str(value).strip()
