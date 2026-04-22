from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    timestamp = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "timestamp",
            "actor_name",
            "actor_role",
            "branch_name",
            "target_profile_name",
            "action_type",
            "details",
        ]

    def get_timestamp(self, obj):
        return obj.created_at.strftime("%d-%m-%Y %H:%M")
