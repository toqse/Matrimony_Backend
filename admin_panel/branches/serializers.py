from rest_framework import serializers

from core.phone import extract_indian_mobile_10, mobile_10_from_stored, normalize_phone_input, to_e164_display

from .models import Branch
from .services import generate_branch_code

class BranchSerializer(serializers.ModelSerializer):
    profiles_count = serializers.IntegerField(read_only=True)
    revenue = serializers.FloatField(read_only=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = Branch
        fields = "__all__"
        extra_kwargs = {
            # Generated automatically; not required in input
            "code": {"required": False, "read_only": True},
        }

    def get_status(self, obj):
        return "active" if obj.is_active else "inactive"

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["phone"] = to_e164_display(instance.phone)
        return data

    def validate_name(self, value):
        if len(value) < 3:
            raise serializers.ValidationError("Name too short")
        qs = Branch.objects.filter(name__iexact=value.strip(), is_deleted=False)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Branch with this name already exists")
        return value

    def validate_phone(self, value):
        e164 = normalize_phone_input(value)
        mobile_10 = mobile_10_from_stored(e164)
        qs = Branch.objects.filter(is_deleted=False)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        for branch in qs.only("phone"):
            if mobile_10_from_stored(branch.phone) == mobile_10:
                raise serializers.ValidationError(
                    "Phone number already registered to another branch"
                )
        return e164

    def validate_email(self, value):
        value = (value or "").strip().lower()
        qs = Branch.objects.filter(email__iexact=value, is_deleted=False)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Email already registered to another branch")
        return value

    def create(self, validated_data):
        if not validated_data.get("code"):
            validated_data["code"] = generate_branch_code(validated_data["city"])
        return super().create(validated_data)