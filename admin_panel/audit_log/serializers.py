from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    timestamp = serializers.SerializerMethodField()
    action_display = serializers.CharField(source="get_action_display", read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "timestamp",
            "actor_name",
            "actor_role",
            "branch_name",
            "staff_name",
            "target_profile_name",
            "action",
            "action_display",
            "action_type",
            "resource",
            "details",
        ]

    def get_timestamp(self, obj):
        return obj.created_at.strftime("%d-%m-%Y %H:%M")
