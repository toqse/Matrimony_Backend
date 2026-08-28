from rest_framework import serializers

from core.phone import normalize_phone_input, to_e164_display

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

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["phone"] = to_e164_display(instance.phone)
        return data

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
        return normalize_phone_input(value)

    def validate_source(self, value):
        valid = ["website", "walk-in", "phone", "whatsapp", "email"]
        if value not in valid:
            raise serializers.ValidationError(
                f"Invalid source. Must be one of: {', '.join(valid)}."
            )
        return value


class PublicEnquiryCreateSerializer(serializers.Serializer):
    name = serializers.CharField()
    phone = serializers.CharField()
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    subject = serializers.CharField(required=False, allow_blank=True, max_length=200)
    message = serializers.CharField()

    def validate_name(self, value):
        if not value or not str(value).strip():
            raise serializers.ValidationError("Name is required.")
        return str(value).strip()

    def validate_phone(self, value):
        return normalize_phone_input(value)

    def validate_email(self, value):
        return (value or "").strip().lower() or None

    def validate_subject(self, value):
        return (value or "").strip()

    def validate_message(self, value):
        if not value or not str(value).strip():
            raise serializers.ValidationError("Message is required.")
        return str(value).strip()


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
    # Accepts either a numeric AdminUser id (e.g. 2) or an employee code
    # (e.g. "EMP005"). Normalizes to the AdminUser pk in validated_data.
    staff_id = serializers.CharField(
        error_messages={
            "blank": "Staff is required.",
            "required": "Staff is required.",
            "null": "Staff is required.",
        }
    )

    def validate_staff_id(self, value):
        from admin_panel.auth.models import AdminUser
        from admin_panel.staff_mgmt.models import StaffProfile

        raw = str(value).strip()
        if not raw:
            raise serializers.ValidationError("Staff is required.")

        admin_user = None

        if raw.isdigit():
            admin_user = AdminUser.objects.filter(id=int(raw), is_active=True).first()

        if admin_user is None:
            sp = (
                StaffProfile.objects.select_related("admin_user")
                .filter(emp_code__iexact=raw, is_deleted=False)
                .first()
            )
            if sp and sp.admin_user_id and sp.admin_user.is_active:
                admin_user = sp.admin_user

        if admin_user is None:
            raise serializers.ValidationError("Staff not found or inactive.")

        return admin_user.pk


class EnquiryNoteCreateSerializer(serializers.Serializer):
    text = serializers.CharField(
        min_length=1,
        error_messages={
            "blank": "Note text is required.",
            "required": "Note text is required.",
        },
    )
