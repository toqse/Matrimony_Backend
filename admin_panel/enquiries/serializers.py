import re

from rest_framework import serializers

from .models import Enquiry, EnquiryNote


class EnquiryNoteSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.name", read_only=True)

    class Meta:
        model = EnquiryNote
        fields = ["id", "text", "created_by_name", "created_at"]


class EnquirySerializer(serializers.ModelSerializer):
    assigned_to_name = serializers.CharField(source="assigned_to.name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    enquiry_notes = EnquiryNoteSerializer(many=True, read_only=True)

    class Meta:
        model = Enquiry
        fields = [
            "id",
            "name",
            "phone",
            "email",
            "source",
            "status",
            "assigned_to",
            "assigned_to_name",
            "branch",
            "branch_name",
            "notes",
            "enquiry_notes",
            "created_at",
            "updated_at",
        ]


class EnquiryCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Enquiry
        fields = ["name", "phone", "email", "source", "branch", "assigned_to"]

    def validate_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Name is required.")
        return value.strip()

    def validate_phone(self, value):
        if not value:
            raise serializers.ValidationError("Phone number is required.")
        cleaned = re.sub(r"\D", "", value)
        if len(cleaned) != 10:
            raise serializers.ValidationError("Enter a valid 10-digit phone number.")
        return cleaned

    def validate_source(self, value):
        valid = ["website", "walk-in", "phone", "whatsapp", "email"]
        if value not in valid:
            raise serializers.ValidationError(
                f"Invalid source. Must be one of: {', '.join(valid)}."
            )
        return value


class EnquiryMoveSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=["contacted", "interested", "converted", "lost"],
        error_messages={
            "invalid_choice": "Invalid status. Must be: contacted, interested, converted, or lost."
        },
    )

    def validate(self, attrs):
        enquiry = self.context.get("enquiry")
        if enquiry and enquiry.status in ("converted", "lost"):
            raise serializers.ValidationError(
                "Cannot revert a converted or lost enquiry."
            )
        return attrs

    def validate_status(self, value):
        return value


class EnquiryAssignSerializer(serializers.Serializer):
    staff_id = serializers.IntegerField()

    def validate_staff_id(self, value):
        from admin_panel.auth.models import AdminUser

        try:
            AdminUser.objects.get(id=value, is_active=True)
        except AdminUser.DoesNotExist:
            raise serializers.ValidationError("Staff not found or inactive.")
        return value


class EnquiryNoteCreateSerializer(serializers.Serializer):
    text = serializers.CharField(
        min_length=1,
        error_messages={
            "blank": "Note text is required.",
            "required": "Note text is required.",
        },
    )
