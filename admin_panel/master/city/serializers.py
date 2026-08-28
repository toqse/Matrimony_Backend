from django.db.models import Count, Q
from rest_framework import serializers

from master.models import City, District


class CityListSerializer(serializers.ModelSerializer):
    district_name = serializers.CharField(source="district.name", read_only=True)

    class Meta:
        model = City
        fields = ["id", "name", "district", "district_name", "is_active"]
        read_only_fields = ["id", "is_active", "district_name"]


class CityWriteSerializer(serializers.ModelSerializer):
    district = serializers.PrimaryKeyRelatedField(
        queryset=District.objects.filter(is_active=True),
        error_messages={
            "does_not_exist": "Selected district is inactive or not found.",
            "incorrect_type": "Selected district is inactive or not found.",
            "required": "Selected district is inactive or not found.",
            "null": "Selected district is inactive or not found.",
        },
    )

    class Meta:
        model = City
        fields = ["id", "name", "district"]
        read_only_fields = ["id"]

    def validate_name(self, value: str) -> str:
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("City name is required.")
        if len(name) < 2:
            raise serializers.ValidationError("City name must be at least 2 characters.")
        if len(name) > 100:
            raise serializers.ValidationError("City name must not exceed 100 characters.")
        return name

    def validate_district(self, value: District) -> District:
        if not value or not value.is_active:
            raise serializers.ValidationError("Selected district is inactive or not found.")
        return value

    def validate(self, attrs):
        name = attrs.get("name")
        district = attrs.get("district")
        instance = getattr(self, "instance", None)
        if name is None and instance is not None:
            name = instance.name
        if district is None and instance is not None:
            district = instance.district
        if name and district:
            qs = City.objects.filter(name__iexact=name, district=district)
            if instance is not None:
                qs = qs.exclude(pk=instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"name": f"City '{name}' already exists under '{district.name}'."}
                )
        return attrs

    def create(self, validated_data):
        validated_data["name"] = validated_data["name"].strip()
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "name" in validated_data:
            validated_data["name"] = validated_data["name"].strip()
        return super().update(instance, validated_data)


class CityDistrictTabSerializer(serializers.ModelSerializer):
    city_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = District
        fields = ["id", "name", "city_count"]

    @staticmethod
    def setup_eager_loading(queryset):
        return queryset.annotate(city_count=Count("cities", filter=Q(cities__is_active=True)))
