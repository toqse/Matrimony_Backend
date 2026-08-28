from django.db.models import Count, Q
from rest_framework import serializers

from master.models import Country


class CountryListSerializer(serializers.ModelSerializer):
    state_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Country
        fields = ["id", "name", "code", "is_active", "state_count"]
        read_only_fields = ["id", "is_active", "state_count"]

    @staticmethod
    def setup_eager_loading(queryset):
        return queryset.annotate(state_count=Count("states", filter=Q(states__is_active=True)))


class CountryWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ["id", "name", "code"]
        read_only_fields = ["id"]
        extra_kwargs = {"code": {"required": False, "allow_blank": True}}

    def validate_name(self, value: str) -> str:
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("Country name is required.")
        if len(name) < 2:
            raise serializers.ValidationError("Country name must be at least 2 characters.")
        if len(name) > 100:
            raise serializers.ValidationError("Country name must not exceed 100 characters.")

        qs = Country.objects.filter(name__iexact=name)
        instance = getattr(self, "instance", None)
        if instance is not None:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError(f"Country '{name}' already exists.")
        return name

    def validate_code(self, value: str) -> str:
        code = (value or "").strip()
        if len(code) > 10:
            raise serializers.ValidationError("Country code must not exceed 10 characters.")
        return code
