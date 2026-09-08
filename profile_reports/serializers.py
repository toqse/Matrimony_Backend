from rest_framework import serializers

from .models import ProfileReport


class ProfileReportCreateSerializer(serializers.Serializer):
    matri_id = serializers.CharField(max_length=32)
    message = serializers.CharField(max_length=2000, min_length=1, trim_whitespace=True)


class ProfileReportStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[
        ProfileReport.STATUS_PENDING,
        ProfileReport.STATUS_REVIEWED,
        ProfileReport.STATUS_DISMISSED,
    ])
