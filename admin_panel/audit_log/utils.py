from __future__ import annotations

from typing import Any

from admin_panel.auth.models import AdminUser

from .models import AuditLog


def _get_client_ip(request) -> str | None:
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _role_from_request(request) -> str:
    user = getattr(request, "user", None)
    role = (getattr(user, "role", "") or "").strip()
    if role:
        return role
    path = (getattr(request, "path", "") or "").lower()
    if path.startswith("/api/v1/staff/"):
        return AdminUser.ROLE_STAFF
    if path.startswith("/api/v1/branch/"):
        return AdminUser.ROLE_BRANCH_MANAGER
    if path.startswith("/api/v1/admin/"):
        return AdminUser.ROLE_ADMIN
    return ""

def _actor_full_name(actor: AdminUser | None) -> str:
    if not actor:
        return ""
    # Prefer full_name if present; fallback to name.
    fn = (getattr(actor, "full_name", "") or "").strip()
    if fn:
        return fn
    return (getattr(actor, "name", "") or "").strip()


def _branch_name_from_actor(actor: AdminUser | None) -> str:
    if not actor:
        return ""
    branch = getattr(actor, "branch", None)
    if branch is not None:
        return (getattr(branch, "name", "") or "").strip()
    bid = getattr(actor, "branch_id", None)
    if not bid:
        return ""
    from master.models import Branch

    b = Branch.objects.filter(pk=bid).values_list("name", flat=True).first()
    return (b or "").strip()


def _normalize_action(action: str) -> str:
    a = (action or "").strip() or AuditLog.ACTION_OTHER
    valid = {c[0] for c in AuditLog.ACTION_CHOICES}
    return a if a in valid else AuditLog.ACTION_OTHER


def infer_action_type(action: str) -> str:
    """Map granular action codes to create_profile / update_profile."""
    a = (action or "").strip()
    if a == AuditLog.ACTION_CREATE_PROFILE:
        return AuditLog.ACTION_TYPE_CREATE_PROFILE
    return AuditLog.ACTION_TYPE_UPDATE_PROFILE


def create_audit_log(
    request,
    action: str,
    resource: str,
    details: str,
    *,
    branch_name: str | None = None,
    staff_name: str | None = None,
    target_profile_name: str | None = None,
    action_type: str | None = None,
    old_value: Any = None,
    new_value: Any = None,
) -> None:
    """
    Create an immutable audit row. request.user is the actor when they are an AdminUser
    (admin / staff / branch manager). Member app users are recorded via actor_name only.
    """
    action_norm = _normalize_action(action)
    user = getattr(request, "user", None)
    actor: AdminUser | None = None
    actor_name = ""

    if isinstance(user, AdminUser) and getattr(user, "is_authenticated", False):
        actor = user
        actor_name = _actor_full_name(actor)

    # Save only staff / branch manager logs (ignore admin and member logs).
    role = _role_from_request(request) if actor else ""
    if role not in {AdminUser.ROLE_STAFF, AdminUser.ROLE_BRANCH_MANAGER}:
        return

    actor_role_display = (
        "Staff" if role == AdminUser.ROLE_STAFF else "Branch Manager" if role == AdminUser.ROLE_BRANCH_MANAGER else ""
    )

    resolved_branch = (
        (branch_name or "").strip()
        if branch_name is not None
        else _branch_name_from_actor(actor)
    )

    resolved_staff = (staff_name or "").strip() if staff_name is not None else ""
    if not resolved_staff and actor:
        resolved_staff = actor_name

    resolved_target = (target_profile_name or "").strip() if target_profile_name is not None else ""

    resolved_action_type = (action_type or "").strip() if action_type is not None else ""
    if not resolved_action_type:
        resolved_action_type = infer_action_type(action_norm)

    AuditLog.objects.create(
        actor=actor,
        actor_name=actor_name,
        actor_role=actor_role_display,
        role=role,
        action=action_norm,
        resource=(resource or "").strip(),
        details=details or "",
        old_value=old_value,
        new_value=new_value,
        ip_address=_get_client_ip(request),
        branch_name=resolved_branch,
        staff_name=resolved_staff,
        target_profile_name=resolved_target,
        action_type=resolved_action_type,
    )
