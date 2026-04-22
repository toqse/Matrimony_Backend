from rest_framework import serializers
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
        value = value.strip()
        if not value.isdigit() or len(value) < 10:
            raise serializers.ValidationError("Enter a valid phone number")
        qs = Branch.objects.filter(phone=value, is_deleted=False)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "Phone number already registered to another branch"
            )
        return value

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