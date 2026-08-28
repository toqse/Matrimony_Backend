import os

from django.db.models import Q
from rest_framework import serializers

from .models import Testimonial


PHOTO_ERROR = "Photo must be JPEG/PNG/WEBP under 5MB"


class TestimonialSerializer(serializers.ModelSerializer):
    class Meta:
        model = Testimonial
        fields = [
            "id",
            "name",
            "role",
            "review",
            "rating",
            "avatar",
            "status",
            "sort_order",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def validate_name(self, value):
        name = (value or "").strip()
        if not name:
            raise serializers.ValidationError("Name is required")
        return name

    def validate_role(self, value):
        role = (value or "").strip()
        if not role:
            raise serializers.ValidationError("Role is required")
        return role

    def validate_review(self, value):
        text = (value or "").strip()
        if not text:
            raise serializers.ValidationError("Review is required")
        return text

    def validate_rating(self, value):
        if value is None:
            return 5
        if not 1 <= int(value) <= 5:
            raise serializers.ValidationError("Rating must be between 1 and 5")
        return int(value)

    def validate_avatar(self, value):
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

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        avatar_url = data.get("avatar")
        if avatar_url and request is not None:
            data["avatar"] = request.build_absolute_uri(avatar_url)
        return data


class TestimonialListSerializer(serializers.ModelSerializer):
    avatar = serializers.SerializerMethodField()

    class Meta:
        model = Testimonial
        fields = [
            "id",
            "name",
            "role",
            "review",
            "rating",
            "avatar",
            "status",
            "sort_order",
            "created_at",
        ]

    def get_avatar(self, obj):
        if not obj.avatar:
            return None
        request = self.context.get("request")
        url = obj.avatar.url
        return request.build_absolute_uri(url) if request is not None else url


def apply_testimonial_filters(queryset, request):
    qs = queryset
    status_param = (request.query_params.get("status") or "").strip().lower()
    if status_param:
        if status_param not in {Testimonial.STATUS_DRAFT, Testimonial.STATUS_PUBLISHED}:
            raise serializers.ValidationError("Invalid status filter")
        qs = qs.filter(status=status_param)

    search = (request.query_params.get("search") or "").strip()
    if search:
        qs = qs.filter(
            Q(name__icontains=search)
            | Q(role__icontains=search)
            | Q(review__icontains=search)
        )
    return qs
