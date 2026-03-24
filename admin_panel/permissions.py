from rest_framework.permissions import BasePermission

from admin_panel.auth.models import AdminUser
from admin_panel.auth.serializers import normalize_admin_role


def _normalized_role(user) -> str:
    return normalize_admin_role(getattr(user, "role", ""))


def _panel_user(request):
    return getattr(request, "admin_user", None) or getattr(request, "user", None)


def _is_authenticated_active_panel_user(user) -> bool:
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", True)
    )


class IsStaffOrAbove(BasePermission):
    """Admin, Branch Manager, or Staff."""

    def has_permission(self, request, view):
        user = request.user
        if not getattr(user, "is_authenticated", False):
            return False
        return _normalized_role(user) in (
            AdminUser.ROLE_ADMIN,
            AdminUser.ROLE_BRANCH_MANAGER,
            AdminUser.ROLE_STAFF,
        )


class IsBranchManager(BasePermission):
    """
    Allows Admin and Branch Manager. Denies Staff.

    Prefer ``request.admin_user`` when set (e.g. after ``AdminUserBindingMixin``); falls back to ``request.user``.
    """

    def has_permission(self, request, view):
        user = _panel_user(request)
        if not _is_authenticated_active_panel_user(user):
            return False
        return _normalized_role(user) in (
            AdminUser.ROLE_ADMIN,
            AdminUser.ROLE_BRANCH_MANAGER,
        )


class IsBranchManagerOnly(BasePermission):
    """Allows only Branch Manager (not admin, not staff)."""

    def has_permission(self, request, view):
        user = _panel_user(request)
        if not _is_authenticated_active_panel_user(user):
            return False
        return _normalized_role(user) == AdminUser.ROLE_BRANCH_MANAGER


class IsAdminUser(BasePermission):
    """Super-admin role (admin_panel role name `admin`)."""

    def has_permission(self, request, view):
        user = request.user
        if not getattr(user, "is_authenticated", False):
            return False
        return _normalized_role(user) == AdminUser.ROLE_ADMIN


class IsAdminOrBranchManager(BasePermission):
    """Same access rule as ``IsBranchManager`` (admin or branch manager)."""

    def has_permission(self, request, view):
        return IsBranchManager().has_permission(request, view)
