import os

from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers

from .models import SuccessStory


PHOTO_ERROR = "Photo must be JPEG/PNG/WEBP under 5MB"


class SuccessStorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SuccessStory
        fields = [
            "id",
            "couple_name_1",
            "couple_name_2",
            "wedding_date",
            "location",
            "story_text",
            "couple_photo",
            "status",
            "is_featured",
            "views_count",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "views_count", "created_by", "created_at", "updated_at"]

    def validate_wedding_date(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("Wedding date cannot be in the future")
        return value

    def validate_location(self, value):
        if not (value or "").strip():
            raise serializers.ValidationError("Location is required")
        return value.strip()

    def validate_story_text(self, value):
        text = (value or "").strip()
        if len(text) < 50:
            raise serializers.ValidationError("Story must be at least 50 characters")
        return text

    def validate_couple_photo(self, value):
        if not value:
            return value
        max_size = 5 * 1024 * 1024
        ext = os.path.splitext(getattr(value, "name", "") or "")[1].lower()
        content_type = (getattr(value, "content_type", "") or "").lower()
        valid_ext = {".jpg", ".jpeg", ".png", ".webp"}
        valid_types = {"image/jpeg", "image/png", "image/webp"}
        if value.size > max_size:
            raise serializers.ValidationError(PHOTO_ERROR)
        if ext not in valid_ext and content_type not in valid_types:
            raise serializers.ValidationError(PHOTO_ERROR)
        return value

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        name1 = attrs.get("couple_name_1", getattr(instance, "couple_name_1", ""))
        name2 = attrs.get("couple_name_2", getattr(instance, "couple_name_2", ""))
        if not (name1 or "").strip() or not (name2 or "").strip():
            raise serializers.ValidationError({"non_field_errors": ["Both partner names are required"]})

        if self.partial:
            # If status is explicitly updated to published via PATCH, allow only for draft records.
            next_status = attrs.get("status")
            if next_status == SuccessStory.STATUS_PUBLISHED and instance and instance.status == SuccessStory.STATUS_PUBLISHED:
                raise serializers.ValidationError({"status": ["Story is already published"]})
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        photo_url = data.get("couple_photo")
        if photo_url and request is not None:
            data["couple_photo"] = request.build_absolute_uri(photo_url)
        data["description"] = data.get("story_text", "")
        return data


class SuccessStoryListSerializer(serializers.ModelSerializer):
    couple_names = serializers.SerializerMethodField()
    couple_photo = serializers.SerializerMethodField()
    description = serializers.CharField(source="story_text", read_only=True)

    class Meta:
        model = SuccessStory
        fields = [
            "id",
            "couple_name_1",
            "couple_name_2",
            "couple_names",
            "wedding_date",
            "location",
            "couple_photo",
            "description",
            "status",
            "is_featured",
            "views_count",
            "created_at",
        ]

    def get_couple_names(self, obj):
        return f"{obj.couple_name_1} & {obj.couple_name_2}"

    def get_couple_photo(self, obj):
        if not obj.couple_photo:
            return None
        request = self.context.get("request")
        url = obj.couple_photo.url
        return request.build_absolute_uri(url) if request is not None else url


def apply_success_story_filters(queryset, request):
    qs = queryset
    status_param = (request.query_params.get("status") or "").strip().lower()
    if status_param:
        if status_param not in {SuccessStory.STATUS_DRAFT, SuccessStory.STATUS_PUBLISHED}:
            raise serializers.ValidationError("Invalid status filter")
        qs = qs.filter(status=status_param)

    search = (request.query_params.get("search") or "").strip()
    if search:
        qs = qs.filter(
            Q(couple_name_1__icontains=search)
            | Q(couple_name_2__icontains=search)
            | Q(location__icontains=search)
            | Q(story_text__icontains=search)
        )
    return qs
