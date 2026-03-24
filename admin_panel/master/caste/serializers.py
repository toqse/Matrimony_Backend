from django.db.models import Count, Q
from rest_framework import serializers

from master.models import Caste, Religion


class CasteListSerializer(serializers.ModelSerializer):
    religion_name = serializers.CharField(source="religion.name", read_only=True)

    class Meta:
        model = Caste
        fields = ["id", "name", "religion", "religion_name", "is_active"]
        read_only_fields = ["id", "is_active", "religion_name"]


class CasteWriteSerializer(serializers.ModelSerializer):
    religion = serializers.PrimaryKeyRelatedField(
        queryset=Religion.objects.filter(is_active=True),
        error_messages={
            "does_not_exist": "Selected religion is inactive or not found.",
            "incorrect_type": "Selected religion is inactive or not found.",
            "required": "Selected religion is inactive or not found.",
            "null": "Selected religion is inactive or not found.",
        },
    )

    class Meta:
        model = Caste
        fields = ["id", "name", "religion"]
        read_only_fields = ["id"]

    def validate_name(self, value: str) -> str:
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("Caste name is required.")
        if len(name) < 2:
            raise serializers.ValidationError("Caste name must be at least 2 characters.")
        if len(name) > 100:
            raise serializers.ValidationError("Caste name must not exceed 100 characters.")
        return name

    def validate_religion(self, value: Religion) -> Religion:
        if not value or not value.is_active:
            raise serializers.ValidationError("Selected religion is inactive or not found.")
        return value

    def validate(self, attrs):
        name = attrs.get("name")
        religion = attrs.get("religion")
        if name and religion:
            qs = Caste.objects.filter(name__iexact=name, religion=religion)
            instance = getattr(self, "instance", None)
            if instance is not None:
                qs = qs.exclude(pk=instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"name": f"Caste '{name}' already exists under '{religion.name}'."}
                )
        return attrs

    def create(self, validated_data):
        validated_data["name"] = validated_data["name"].strip()
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "name" in validated_data:
            validated_data["name"] = validated_data["name"].strip()
        return super().update(instance, validated_data)


class CasteReligionTabSerializer(serializers.ModelSerializer):
    caste_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Religion
        fields = ["id", "name", "caste_count"]

    @staticmethod
    def setup_eager_loading(queryset):
        return queryset.annotate(caste_count=Count("castes", filter=Q(castes__is_active=True)))
