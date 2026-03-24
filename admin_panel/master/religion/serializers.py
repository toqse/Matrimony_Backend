from django.db.models import Count, Q
from rest_framework import serializers

from master.models import Religion


class ReligionListSerializer(serializers.ModelSerializer):
    caste_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Religion
        fields = ["id", "name", "is_active", "caste_count"]
        read_only_fields = ["id", "is_active", "caste_count"]

    @staticmethod
    def setup_eager_loading(queryset):
        return queryset.annotate(caste_count=Count("castes", filter=Q(castes__is_active=True)))


class ReligionWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Religion
        fields = ["id", "name"]
        read_only_fields = ["id"]

    def validate_name(self, value: str) -> str:
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("Religion name is required.")
        if len(name) < 2:
            raise serializers.ValidationError("Religion name must be at least 2 characters.")
        if len(name) > 100:
            raise serializers.ValidationError("Religion name must not exceed 100 characters.")

        qs = Religion.objects.filter(name__iexact=name)
        instance = getattr(self, "instance", None)
        if instance is not None:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError(f"Religion '{name}' already exists.")
        return name
