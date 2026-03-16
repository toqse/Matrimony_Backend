"""
Match list item: basic profile fields only (no phone, email, family).
"""
from rest_framework import serializers
from django.utils import timezone
from datetime import timedelta


class MatchListProfileSerializer(serializers.Serializer):
    """One profile in match list: matri_id, name, age, height, education, occupation, profile_photo, is_online, last_seen, is_new, match_percentage, can_view_details, can_send_interest, can_chat."""
    matri_id = serializers.CharField()
    name = serializers.CharField()
    age = serializers.IntegerField(allow_null=True)
    height = serializers.IntegerField(allow_null=True)
    education = serializers.CharField(allow_null=True)
    occupation = serializers.CharField(allow_null=True)
    profile_photo = serializers.URLField(allow_null=True)
    is_online = serializers.BooleanField()
    last_seen = serializers.CharField(allow_null=True)
    is_new = serializers.BooleanField()
    match_percentage = serializers.IntegerField(allow_null=True)
    can_view_details = serializers.BooleanField()
    can_send_interest = serializers.BooleanField()
    can_chat = serializers.BooleanField()


def format_last_seen(dt):
    if not dt:
        return None
    now = timezone.now()
    delta = now - dt
    if delta < timedelta(minutes=15):
        return "Available Online"
    if delta < timedelta(hours=1):
        m = int(delta.total_seconds() / 60)
        return f"{m} minutes ago"
    if delta < timedelta(hours=24):
        h = int(delta.total_seconds() / 3600)
        return f"{h} hours ago"
    if delta < timedelta(days=7):
        d = delta.days
        return f"{d} days ago"
    return None
