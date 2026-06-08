from rest_framework import serializers

from master.models import Education, EducationSubject


class EducationSubjectListSerializer(serializers.ModelSerializer):
    education_ids = serializers.PrimaryKeyRelatedField(
        source="educations",
        many=True,
        read_only=True,
    )

    class Meta:
        model = EducationSubject
        fields = [
            "id",
            "name",
            "is_active",
            "created_at",
            "updated_at",
            "education_ids",
        ]
        read_only_fields = fields


class EducationSubjectWriteSerializer(serializers.ModelSerializer):
    educations = serializers.PrimaryKeyRelatedField(
        queryset=Education.objects.filter(is_active=True),
        many=True,
        required=False,
    )

    class Meta:
        model = EducationSubject
        fields = ["id", "name", "educations"]
        read_only_fields = ["id"]

    def validate_name(self, value: str) -> str:
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("Education subject name is required.")
        if len(name) < 2:
            raise serializers.ValidationError(
                "Education subject name must be at least 2 characters."
            )
        if len(name) > 150:
            raise serializers.ValidationError(
                "Education subject name must not exceed 150 characters."
            )

        qs = EducationSubject.objects.filter(name__iexact=name)
        instance = getattr(self, "instance", None)
        if instance is not None:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError(f"Education subject '{name}' already exists.")
        return name

    def create(self, validated_data):
        educations = validated_data.pop("educations", None)
        validated_data["name"] = validated_data["name"].strip()
        obj = super().create(validated_data)
        if educations is not None:
            obj.educations.set(educations)
        return obj

    def update(self, instance, validated_data):
        educations = validated_data.pop("educations", None)
        if "name" in validated_data:
            validated_data["name"] = validated_data["name"].strip()
        obj = super().update(instance, validated_data)
        if educations is not None:
            obj.educations.set(educations)
        return obj
