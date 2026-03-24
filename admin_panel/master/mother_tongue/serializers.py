from rest_framework import serializers

from master.models import MotherTongue


class MotherTongueSerializer(serializers.ModelSerializer):
    class Meta:
        model = MotherTongue
        fields = ["id", "name", "is_active"]
        read_only_fields = ["id", "is_active"]

    def validate_name(self, value: str) -> str:
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("Mother tongue name is required.")
        if len(name) < 2:
            raise serializers.ValidationError("Mother tongue name must be at least 2 characters.")
        if len(name) > 100:
            raise serializers.ValidationError("Mother tongue name must not exceed 100 characters.")

        qs = MotherTongue.objects.filter(name__iexact=name)
        instance = getattr(self, "instance", None)
        if instance is not None:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError(f"Mother tongue '{name}' already exists.")
        return name
