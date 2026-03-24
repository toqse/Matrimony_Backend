"""
Shared API mixins for admin_panel (branch scoping, admin_user on request).
"""
from __future__ import annotations

from rest_framework.exceptions import PermissionDenied

from admin_panel.auth.models import AdminUser
from admin_panel.auth.serializers import normalize_admin_role


def bind_admin_user(request) -> None:
    """Attach request.admin_user to the authenticated panel user (same as request.user for Admin JWT)."""
    u = getattr(request, "user", None)
    if u is not None and getattr(u, "is_authenticated", False):
        request.admin_user = u


class AdminUserBindingMixin:
    """Sets request.admin_user after authentication so permissions and mixins can use a consistent attribute."""

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        bind_admin_user(request)


class BranchScopedMixin(AdminUserBindingMixin):
    """
    Auto-filters queryset to the logged-in panel user's branch (FK to master.Branch).

    - Admin: no branch filter (sees all).
    - Branch manager: filters queryset where ``branch_field`` equals ``user.branch`` (master.Branch).
      Raises PermissionDenied if the manager has no branch assigned.

    Override ``branch_field`` if the model uses a different FK name. For models keyed to
    ``admin_panel.branches.Branch`` instead of ``master.Branch``, subclass and override
    ``get_branch_scope_filter``.
    """

    branch_field = "branch"

    def get_branch_scope_filter(self, user):
        return {self.branch_field: user.branch}

    def get_queryset(self):
        qs = super().get_queryset()
        user = getattr(self.request, "admin_user", None) or getattr(self.request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return qs
        role = normalize_admin_role(getattr(user, "role", ""))
        if role == AdminUser.ROLE_ADMIN:
            return qs
        if role == AdminUser.ROLE_BRANCH_MANAGER:
            if not getattr(user, "branch_id", None):
                raise PermissionDenied("No branch assigned to your account.")
            return qs.filter(**self.get_branch_scope_filter(user))
        return qs.none()
