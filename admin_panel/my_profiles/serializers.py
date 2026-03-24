from rest_framework import serializers


class MyProfileListSerializer(serializers.Serializer):
    """Used for the paginated table list."""

    matri_id = serializers.CharField()
    name = serializers.CharField()
    gender = serializers.CharField()
    age = serializers.IntegerField(allow_null=True)
    religion = serializers.CharField(allow_null=True)
    caste = serializers.CharField(allow_null=True)
    subscription_plan = serializers.CharField(allow_null=True)
    is_verified = serializers.BooleanField()
    completeness = serializers.IntegerField()
    profile_status = serializers.CharField()
    is_wishlisted = serializers.BooleanField()
    profile_photo = serializers.URLField(allow_null=True)


class MyProfileSummarySerializer(serializers.Serializer):
    total_profiles = serializers.IntegerField()
    verified = serializers.IntegerField()
    unverified = serializers.IntegerField()
    subscribed = serializers.IntegerField()
    incomplete_count = serializers.IntegerField()
    incomplete_message = serializers.CharField(allow_null=True)
