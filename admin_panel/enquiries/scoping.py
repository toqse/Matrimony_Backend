"""Map AdminUser (master Branch) to admin_panel.branches.Branch by code."""

from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response

from admin_panel.auth.models import AdminUser
from admin_panel.auth.serializers import normalize_admin_role
from admin_panel.branches.models import Branch
from admin_panel.staff_mgmt.models import StaffProfile
from master.models import Branch as MasterBranch


def manager_branch_code(user: AdminUser) -> str | None:
    return (
        MasterBranch.objects.filter(pk=getattr(user, "branch_id", None))
        .values_list("code", flat=True)
        .first()
    )


def admin_branch_for_manager(user: AdminUser) -> Branch | None:
    code = manager_branch_code(user)
    if not code:
        return None
    return Branch.objects.filter(code=code, is_deleted=False).first()


def staff_profile_for(user: AdminUser) -> StaffProfile | None:
    return (
        StaffProfile.objects.select_related("branch")
        .filter(admin_user=user, is_deleted=False)
        .first()
    )


def branch_manager_branch_enquiry_scope(request):
    """
    Branch Manager only: returns (admin_panel.branches.Branch | None, error Response | None).
    Optional ?branch_id= must match AdminUser.branch_id (master PK).
    """
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return None, Response(
            {"success": False, "error": {"code": 401, "message": "Unauthorized"}},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    if normalize_admin_role(getattr(user, "role", "")) != AdminUser.ROLE_BRANCH_MANAGER:
        return None, Response(
            {"success": False, "error": {"code": 403, "message": "Insufficient permissions."}},
            status=status.HTTP_403_FORBIDDEN,
        )
    master_bid = getattr(user, "branch_id", None)
    if not master_bid:
        return None, Response(
            {
                "success": False,
                "error": {
                    "code": 400,
                    "message": "No branch assigned to your account. Contact admin.",
                },
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    raw = request.query_params.get("branch_id")
    if raw not in (None, ""):
        try:
            requested = int(raw)
        except (TypeError, ValueError):
            return None, Response(
                {"success": False, "error": {"code": 400, "message": "Invalid branch_id"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if requested != master_bid:
            return None, Response(
                {"success": False, "error": {"code": 403, "message": "Access denied"}},
                status=status.HTTP_403_FORBIDDEN,
            )

    mb = admin_branch_for_manager(user)
    return mb, None
