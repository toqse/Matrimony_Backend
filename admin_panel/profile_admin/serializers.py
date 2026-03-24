from datetime import date
from typing import Optional

from rest_framework import serializers


def _age_from_dob(dob) -> Optional[int]:
    if not dob:
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


class AdminProfileListSerializer(serializers.Serializer):
    """Single row for GET /api/v1/admin/profiles/."""

    matri_id = serializers.CharField()
    name = serializers.CharField()
    gender = serializers.CharField()
    age = serializers.IntegerField(allow_null=True)
    religion = serializers.CharField(allow_blank=True)
    caste = serializers.CharField(allow_blank=True)
    marital_status = serializers.CharField(allow_blank=True)
    plan = serializers.CharField(allow_blank=True)
    assigned_staff = serializers.CharField(allow_blank=True, allow_null=True)
    verified = serializers.BooleanField()
    completion_percent = serializers.IntegerField()
    horoscope_available = serializers.BooleanField()
    is_active = serializers.BooleanField()
    is_blocked = serializers.BooleanField()
