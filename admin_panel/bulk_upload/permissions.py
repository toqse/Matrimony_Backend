from rest_framework.permissions import BasePermission

from admin_panel.auth.models import AdminUser


class IsAdminOrBranchManager(BasePermission):
    """Bulk upload: Admin (all branches) or Branch Manager (own branch only)."""

    def has_permission(self, request, view):
        user = request.user
        if not getattr(user, "is_authenticated", False):
            return False
        return getattr(user, "role", None) in (
            AdminUser.ROLE_ADMIN,
            AdminUser.ROLE_BRANCH_MANAGER,
        )
