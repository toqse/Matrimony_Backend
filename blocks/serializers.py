from rest_framework import serializers


class BlockedProfileSerializer(serializers.Serializer):
    """One profile entry in the blocked-users list (wishlist-style card)."""

    matri_id = serializers.CharField()
    name = serializers.CharField()
    age = serializers.IntegerField(allow_null=True)
    location = serializers.CharField(allow_null=True)
    education = serializers.CharField(allow_null=True)
    occupation = serializers.CharField(allow_null=True)
    profile_photo = serializers.CharField(allow_null=True)
    match_percentage = serializers.IntegerField(allow_null=True)
    is_online = serializers.BooleanField()
    last_seen = serializers.CharField(allow_null=True)
