from rest_framework.permissions import BasePermission

from admin_panel.auth.models import AdminUser
from admin_panel.auth.serializers import normalize_admin_role


class IsPanelStaff(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        if not getattr(u, "is_authenticated", False) or not getattr(u, "is_active", True):
            return False
        return normalize_admin_role(getattr(u, "role", "")) == AdminUser.ROLE_STAFF

