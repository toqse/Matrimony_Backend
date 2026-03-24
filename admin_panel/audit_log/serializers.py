from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    timestamp = serializers.SerializerMethodField()
    action_display = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "timestamp",
            "actor_name",
            "actor_role",
            "action",
            "action_display",
            "resource",
            "details",
            "ip_address",
        ]

    def get_timestamp(self, obj):
        return obj.created_at.strftime("%d-%m-%Y %H:%M")

    def get_action_display(self, obj):
        return obj.get_action_display()
