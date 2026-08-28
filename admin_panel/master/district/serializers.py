from django.db.models import Count, Q
from rest_framework import serializers

from master.models import District, State


class DistrictListSerializer(serializers.ModelSerializer):
    state_name = serializers.CharField(source="state.name", read_only=True)

    class Meta:
        model = District
        fields = ["id", "name", "state", "state_name", "is_active"]
        read_only_fields = ["id", "is_active", "state_name"]


class DistrictWriteSerializer(serializers.ModelSerializer):
    state = serializers.PrimaryKeyRelatedField(
        queryset=State.objects.filter(is_active=True),
        error_messages={
            "does_not_exist": "Selected state is inactive or not found.",
            "incorrect_type": "Selected state is inactive or not found.",
            "required": "Selected state is inactive or not found.",
            "null": "Selected state is inactive or not found.",
        },
    )

    class Meta:
        model = District
        fields = ["id", "name", "state"]
        read_only_fields = ["id"]

    def validate_name(self, value: str) -> str:
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("District name is required.")
        if len(name) < 2:
            raise serializers.ValidationError("District name must be at least 2 characters.")
        if len(name) > 100:
            raise serializers.ValidationError("District name must not exceed 100 characters.")
        return name

    def validate_state(self, value: State) -> State:
        if not value or not value.is_active:
            raise serializers.ValidationError("Selected state is inactive or not found.")
        return value

    def validate(self, attrs):
        name = attrs.get("name")
        state = attrs.get("state")
        instance = getattr(self, "instance", None)
        if name is None and instance is not None:
            name = instance.name
        if state is None and instance is not None:
            state = instance.state
        if name and state:
            qs = District.objects.filter(name__iexact=name, state=state)
            if instance is not None:
                qs = qs.exclude(pk=instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"name": f"District '{name}' already exists under '{state.name}'."}
                )
        return attrs

    def create(self, validated_data):
        validated_data["name"] = validated_data["name"].strip()
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "name" in validated_data:
            validated_data["name"] = validated_data["name"].strip()
        return super().update(instance, validated_data)


class DistrictStateTabSerializer(serializers.ModelSerializer):
    district_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = State
        fields = ["id", "name", "district_count"]

    @staticmethod
    def setup_eager_loading(queryset):
        return queryset.annotate(
            district_count=Count("districts", filter=Q(districts__is_active=True))
        )
