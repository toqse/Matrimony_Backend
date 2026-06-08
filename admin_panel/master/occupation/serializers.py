from rest_framework import serializers

from master.models import Occupation


class OccupationListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Occupation
        fields = ["id", "name", "is_active", "created_at", "updated_at"]
        read_only_fields = fields


class OccupationWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Occupation
        fields = ["id", "name"]
        read_only_fields = ["id"]

    def validate_name(self, value: str) -> str:
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("Occupation name is required.")
        if len(name) < 2:
            raise serializers.ValidationError("Occupation name must be at least 2 characters.")
        if len(name) > 150:
            raise serializers.ValidationError("Occupation name must not exceed 150 characters.")

        qs = Occupation.objects.filter(name__iexact=name)
        instance = getattr(self, "instance", None)
        if instance is not None:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError(f"Occupation '{name}' already exists.")
        return name

    def create(self, validated_data):
        validated_data["name"] = validated_data["name"].strip()
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "name" in validated_data:
            validated_data["name"] = validated_data["name"].strip()
        return super().update(instance, validated_data)
