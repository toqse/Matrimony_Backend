from __future__ import annotations

import re
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


_METHOD_ACTION = {
    "POST": AuditLog.ACTION_CREATE,
    "PUT": AuditLog.ACTION_UPDATE,
    "PATCH": AuditLog.ACTION_UPDATE,
    "DELETE": AuditLog.ACTION_DELETE,
}

_METHOD_VERB = {
    "POST": "Created",
    "PUT": "Updated",
    "PATCH": "Updated",
    "DELETE": "Deleted",
}


def _looks_like_identifier(seg: str) -> bool:
    # Numeric ids or matri-id style tokens (contain a digit), not sub-route words.
    return bool(re.search(r"\d", seg or ""))


def build_generic_audit(path: str, method: str) -> tuple[str, str, str]:
    """
    Derive a clean (action, resource, details) tuple for a mutating request when a
    view did not log an explicit, richer audit row. Never stores raw URLs/query strings
    so the frontend renders a friendly label.
    """
    m = (method or "").upper()
    action = _METHOD_ACTION.get(m, AuditLog.ACTION_OTHER)

    parts = [p for p in (path or "").strip("/").split("/") if p]
    if parts and parts[0] == "api":
        parts = parts[1:]
    if parts and re.match(r"^v\d+$", parts[0], re.IGNORECASE):
        parts = parts[1:]
    # parts now: [role, resource, ...]
    rest = parts[1:] if len(parts) > 1 else []

    resource_noun = (rest[0] if rest else (parts[0] if parts else "resource")).replace("-", "_")
    identifier = ""
    for seg in rest[1:]:
        if _looks_like_identifier(seg):
            identifier = seg
            break

    resource = f"{resource_noun}:{identifier}" if identifier else resource_noun
    verb = _METHOD_VERB.get(m, m.title())
    noun_label = resource_noun.replace("_", " ").strip()
    details = f"{verb} {noun_label}" + (f" (id {identifier})" if identifier else "")
    return action, resource, details


def create_audit_log(
    request,
    action: str,
    resource: str,
    details: str,
    *,
    actor: AdminUser | None = None,
    branch_name: str | None = None,
    staff_name: str | None = None,
    target_profile_name: str | None = None,
    action_type: str | None = None,
    old_value: Any = None,
    new_value: Any = None,
) -> None:
    """
    Create an immutable audit row. request.user is the actor when they are an AdminUser
    (admin / staff / branch manager). For endpoints with no authenticated actor on the
    request (e.g. the login/OTP-verify view), pass `actor` explicitly. Member app users are
    not AdminUser instances, so they produce no rows.
    """
    action_norm = _normalize_action(action)
    user = getattr(request, "user", None)
    resolved_actor: AdminUser | None = None
    actor_name = ""

    if isinstance(user, AdminUser) and getattr(user, "is_authenticated", False):
        resolved_actor = user
    elif isinstance(actor, AdminUser):
        resolved_actor = actor

    if resolved_actor:
        actor_name = _actor_full_name(resolved_actor)

    # Persist admin-panel actor logs only (admin / staff / branch manager). Member app users
    # are not AdminUser instances, so they produce no rows. Prefer the actor's own role over
    # the URL prefix so logins on the shared /admin/auth endpoint record the true role.
    role = (getattr(resolved_actor, "role", "") or "").strip() if resolved_actor else ""
    if not role and resolved_actor:
        role = _role_from_request(request)
    if role not in {
        AdminUser.ROLE_ADMIN,
        AdminUser.ROLE_STAFF,
        AdminUser.ROLE_BRANCH_MANAGER,
    }:
        return

    actor_role_display = (
        "Admin"
        if role == AdminUser.ROLE_ADMIN
        else "Staff"
        if role == AdminUser.ROLE_STAFF
        else "Branch Manager"
        if role == AdminUser.ROLE_BRANCH_MANAGER
        else ""
    )

    resolved_branch = (
        (branch_name or "").strip()
        if branch_name is not None
        else _branch_name_from_actor(resolved_actor)
    )

    resolved_staff = (staff_name or "").strip() if staff_name is not None else ""
    if not resolved_staff and resolved_actor:
        resolved_staff = actor_name

    resolved_target = (target_profile_name or "").strip() if target_profile_name is not None else ""

    resolved_action_type = (action_type or "").strip() if action_type is not None else ""
    if not resolved_action_type:
        resolved_action_type = infer_action_type(action_norm)

    AuditLog.objects.create(
        actor=resolved_actor,
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

    # Mark the underlying request so the audit middleware does not also emit a
    # generic catch-all row for this same request (avoids duplicate entries).
    django_request = getattr(request, "_request", None) or request
    try:
        django_request._audit_explicit_logged = True
    except Exception:
        pass
