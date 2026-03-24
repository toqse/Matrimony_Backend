"""Mixins for admin_panel enquiries (branch-scoped branch manager APIs)."""

from __future__ import annotations

from rest_framework.permissions import IsAuthenticated

from admin_panel.auth.authentication import AdminJWTAuthentication

from .scoping import branch_manager_branch_enquiry_scope


class BranchScopedMixin:
    """
    Admin JWT + authenticated user; branch manager views call
    get_branch_manager_scope() to obtain admin Branch or an error Response.
    Sets request.admin_user when authenticated.
    """

    authentication_classes = [AdminJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        u = getattr(request, "user", None)
        if u is not None and getattr(u, "is_authenticated", False):
            request.admin_user = u

    def get_branch_manager_scope(self):
        return branch_manager_branch_enquiry_scope(self.request)
