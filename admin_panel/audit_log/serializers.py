from rest_framework import serializers
import re

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    timestamp = serializers.SerializerMethodField()
    user = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()
    details = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "timestamp",
            "user",
            "role",
            "action",
            "resource",
            "details",
            "ip_address",
        ]

    def get_timestamp(self, obj):
        return obj.created_at.strftime("%d-%m-%Y %H:%M")

    def get_user(self, obj):
        # Prefer real actor identity; avoid role-like placeholders as usernames.
        role_like_values = {
            "admin",
            "staff",
            "branch_manager",
            "branch manager",
            "super admin",
        }

        actor = getattr(obj, "actor", None)
        actor_name = (getattr(actor, "name", "") or "").strip() if actor else ""
        if actor_name and actor_name.lower() not in role_like_values:
            return actor_name

        # Fallback to snapshot if it looks like a real name.
        name = (obj.actor_name or "").strip()
        if name and name.lower() not in role_like_values:
            return name

        # Final fallback to unique actor identifiers when name is generic.
        actor_email = (getattr(actor, "email", "") or "").strip() if actor else ""
        if actor_email:
            return actor_email
        actor_mobile = (getattr(actor, "mobile", "") or "").strip() if actor else ""
        if actor_mobile:
            return actor_mobile

        return "System"

    def get_role(self, obj):
        return obj.role or obj.actor_role

    def get_details(self, obj):
        details = (obj.details or "").strip()
        if not details:
            action = (obj.action or "action").replace("_", " ").strip()
            return f"{action.capitalize()} performed."

        # Middleware pattern (API call trace) should not be shown to UI users.
        # Example hidden: "POST /api/v1/admin/auth/token/refresh/ responded 200"
        m = re.match(r"^(POST|PATCH|DELETE)\s+(\S+)\s+responded\s+(\d{3})$", details)
        if m:
            action = (obj.action or "action").replace("_", " ").strip()
            return f"{action.capitalize()} action completed successfully."

        # Keep existing custom event messages, ensure sentence formatting.
        if details and not details.endswith("."):
            return f"{details}."
        return details
