from __future__ import annotations

from admin_panel.auth.authentication import AdminJWTAuthentication

from .utils import create_audit_log


class AuditLogMiddleware:
    """
    Auto-log mutating admin-panel requests.
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
        )

        if should_track and (not getattr(request, "user", None) or not getattr(request.user, "is_authenticated", False)):
            try:
                auth_result = AdminJWTAuthentication().authenticate(request)
                if auth_result:
                    request.user, _ = auth_result
            except Exception:
                pass

        response = self.get_response(request)

        if should_track and response.status_code < 500:
            action = {
                "POST": "create",
                "PATCH": "update",
                "DELETE": "delete",
            }.get(request.method, "other")
            details = f"{request.method} {request.path} responded {response.status_code}"
            create_audit_log(request, action=action, resource=request.path, details=details)

        return response

