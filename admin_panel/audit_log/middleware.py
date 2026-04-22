from __future__ import annotations

import re

from admin_panel.auth.authentication import AdminJWTAuthentication

# Avoid duplicate rows: these handlers call create_audit_log with full context.
_ADMIN_PROFILE_EXPLICIT = re.compile(
    r"^/api/v1/admin/profiles/(merge/?|[^/]+/(basic|location|religion|personal|education|about|photos|verify|assign-staff|block)/?|[^/]+/?)$",
    re.IGNORECASE,
)


def _skip_middleware_audit(path: str, method: str) -> bool:
    p = (path or "").lower()
    m = (method or "").upper()
    if m not in {"POST", "PATCH", "DELETE"}:
        return False
    if _ADMIN_PROFILE_EXPLICIT.match(p or "/"):
        return True
    if p.endswith("/api/v1/staff/profiles/create/") and m == "POST":
        return True
    if p.endswith("/api/v1/branch/my-profiles/create/") and m == "POST":
        return True
    return False


class AuditLogMiddleware:
    """
    Resolve panel auth for downstream logs.

    Note: We intentionally DO NOT auto-create audit rows here, because:
    - Requirement: do not store URLs
    - Requirement: ignore admin logs; only staff/branch manager logs should be created explicitly
    """

    TRACKED_METHODS = {"POST", "PATCH", "DELETE"}
    TRACKED_PREFIXES = ("/api/v1/admin/", "/api/v1/staff/", "/api/v1/branch/")
    SKIP_PREFIXES = ("/api/v1/admin/audit-log/",)

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = (request.path or "").lower()
        should_track = (
            request.method in self.TRACKED_METHODS
            and any(path.startswith(p) for p in self.TRACKED_PREFIXES)
            and not any(path.startswith(p) for p in self.SKIP_PREFIXES)
            and not _skip_middleware_audit(path, request.method)
        )

        if should_track and (not getattr(request, "user", None) or not getattr(request.user, "is_authenticated", False)):
            try:
                auth_result = AdminJWTAuthentication().authenticate(request)
                if auth_result:
                    request.user, _ = auth_result
            except Exception:
                pass

        return self.get_response(request)

