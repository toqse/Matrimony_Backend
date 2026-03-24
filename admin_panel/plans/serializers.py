from rest_framework import serializers

from plans.models import Plan, UserPlan


class AdminPlanSerializer(serializers.ModelSerializer):
    has_horoscope = serializers.SerializerMethodField(read_only=True)
    subscriber_count = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Plan
        fields = [
            "id",
            "name",
            "price",
            "duration_days",
            "interest_limit",
            "contact_view_limit",
            "chat_limit",
            "horoscope_match_limit",
            "profile_view_limit",
            "has_horoscope",
            "is_highlighted",
            "is_active",
            "subscriber_count",
            "description",
            "created_at",
        ]
        read_only_fields = ["subscriber_count", "has_horoscope", "created_at"]

    def get_has_horoscope(self, obj):
        return int(obj.horoscope_match_limit or 0) > 0

    def get_subscriber_count(self, obj):
        return int(getattr(obj, "subscriber_count", None) or UserPlan.objects.filter(plan=obj, is_active=True).count())

    def validate_name(self, value):
        v = (value or "").strip()
        if not v:
            raise serializers.ValidationError("Plan name is required")
        qs = Plan.objects.filter(name__iexact=v)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A plan with this name already exists")
        return v

    def validate_price(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError("Price must be a positive number")
        return value

    def validate_duration_days(self, value):
        if value is None or int(value) <= 0:
            raise serializers.ValidationError("Duration must be greater than 0")
        return int(value)

    def validate_interest_limit(self, value):
        if value is None or int(value) < 0:
            raise serializers.ValidationError("Interest limit is required")
        return int(value)

    def validate_contact_view_limit(self, value):
        if value is None or int(value) < 0:
            raise serializers.ValidationError("Contact view limit is required")
        return int(value)

    def validate_chat_limit(self, value):
        if value is None or int(value) < 0:
            raise serializers.ValidationError("Chat limit is required")
        return int(value)

    def validate_horoscope_match_limit(self, value):
        if value is None or int(value) < 0:
            raise serializers.ValidationError("Horoscope limit is required")
        return int(value)

    def validate_profile_view_limit(self, value):
        if value is None or int(value) < 0:
            raise serializers.ValidationError("Profile view limit is required")
        return int(value)
