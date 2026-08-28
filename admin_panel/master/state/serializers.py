from django.db.models import Count, Q
from rest_framework import serializers

from master.models import Country, State


class StateListSerializer(serializers.ModelSerializer):
    country_name = serializers.CharField(source="country.name", read_only=True)

    class Meta:
        model = State
        fields = ["id", "name", "code", "country", "country_name", "is_active"]
        read_only_fields = ["id", "is_active", "country_name"]


class StateWriteSerializer(serializers.ModelSerializer):
    country = serializers.PrimaryKeyRelatedField(
        queryset=Country.objects.filter(is_active=True),
        error_messages={
            "does_not_exist": "Selected country is inactive or not found.",
            "incorrect_type": "Selected country is inactive or not found.",
            "required": "Selected country is inactive or not found.",
            "null": "Selected country is inactive or not found.",
        },
    )

    class Meta:
        model = State
        fields = ["id", "name", "code", "country"]
        read_only_fields = ["id"]
        extra_kwargs = {"code": {"required": False, "allow_blank": True}}

    def validate_name(self, value: str) -> str:
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("State name is required.")
        if len(name) < 2:
            raise serializers.ValidationError("State name must be at least 2 characters.")
        if len(name) > 100:
            raise serializers.ValidationError("State name must not exceed 100 characters.")
        return name

    def validate_code(self, value: str) -> str:
        code = (value or "").strip()
        if len(code) > 20:
            raise serializers.ValidationError("State code must not exceed 20 characters.")
        return code

    def validate_country(self, value: Country) -> Country:
        if not value or not value.is_active:
            raise serializers.ValidationError("Selected country is inactive or not found.")
        return value

    def validate(self, attrs):
        name = attrs.get("name")
        country = attrs.get("country")
        instance = getattr(self, "instance", None)
        if name is None and instance is not None:
            name = instance.name
        if country is None and instance is not None:
            country = instance.country
        if name and country:
            qs = State.objects.filter(name__iexact=name, country=country)
            if instance is not None:
                qs = qs.exclude(pk=instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"name": f"State '{name}' already exists under '{country.name}'."}
                )
        return attrs

    def create(self, validated_data):
        validated_data["name"] = validated_data["name"].strip()
        if "code" in validated_data:
            validated_data["code"] = (validated_data["code"] or "").strip()
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "name" in validated_data:
            validated_data["name"] = validated_data["name"].strip()
        if "code" in validated_data:
            validated_data["code"] = (validated_data["code"] or "").strip()
        return super().update(instance, validated_data)


class StateCountryTabSerializer(serializers.ModelSerializer):
    state_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Country
        fields = ["id", "name", "state_count"]

    @staticmethod
    def setup_eager_loading(queryset):
        return queryset.annotate(state_count=Count("states", filter=Q(states__is_active=True)))
