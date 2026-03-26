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


def create_audit_log(request, action: str, resource: str, details: str):
    """
    Reusable global helper to create immutable audit log rows.
    """
    user = getattr(request, "user", None)
    actor = user if isinstance(user, AdminUser) and getattr(user, "is_authenticated", False) else None
    actor_name = (getattr(actor, "name", "") or "").strip()
    role = _role_from_request(request)
    AuditLog.objects.create(
        actor=actor,
        actor_name=actor_name,
        actor_role=role,
        role=role,
        action=(action or "other").strip(),
        resource=(resource or "").strip(),
        details=details or "",
        ip_address=_get_client_ip(request),
    )

