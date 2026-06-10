from __future__ import annotations

from admin_panel.auth.authentication import AdminJWTAuthentication
from admin_panel.auth.models import AdminUser

from .utils import build_generic_audit, create_audit_log


class AuditLogMiddleware:
    """
    Capture every state-changing action performed by admin-panel users
    (admin / branch manager / staff).

    Behaviour:
    - Views that call create_audit_log() themselves record rich, explicit rows. Those
      requests are flagged (request._audit_explicit_logged) so we skip them here and avoid
      duplicates.
    - Every other successful mutating request (POST / PUT / PATCH / DELETE) under the panel
      prefixes gets a generic catch-all row derived from the method + resource path (no raw
      URLs are stored).
    - Login / logout are logged explicitly in the auth views, so the auth subtree is excluded
      from generic logging.
    """

    TRACKED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
    TRACKED_PREFIXES = ("/api/v1/admin/", "/api/v1/staff/", "/api/v1/branch/")
    # Read-only / self-referential surfaces that must never generate generic rows.
    SKIP_PREFIXES = ("/api/v1/admin/audit-log/",)
    # Explicitly-logged subtrees (login/logout/profile) — skip generic catch-all only.
    GENERIC_SKIP_PREFIXES = ("/api/v1/admin/auth/",)

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = (request.path or "").lower()
        should_track = (
            request.method in self.TRACKED_METHODS
            and any(path.startswith(p) for p in self.TRACKED_PREFIXES)
            and not any(path.startswith(p) for p in self.SKIP_PREFIXES)
        )

        # Resolve panel auth up-front so request.user is available both to the view and to
        # our post-response generic logging.
        if should_track and (
            not getattr(request, "user", None)
            or not getattr(request.user, "is_authenticated", False)
            or not isinstance(getattr(request, "user", None), AdminUser)
        ):
            try:
                auth_result = AdminJWTAuthentication().authenticate(request)
                if auth_result:
                    request.user, _ = auth_result
            except Exception:
                pass

        response = self.get_response(request)

        if should_track:
            try:
                self._maybe_log_generic(request, response, path)
            except Exception:
                # Audit logging must never break the actual request/response.
                pass

        return response

    def _maybe_log_generic(self, request, response, path: str) -> None:
        # A view already wrote a richer, explicit row for this request.
        if getattr(request, "_audit_explicit_logged", False):
            return
        if any(path.startswith(p) for p in self.GENERIC_SKIP_PREFIXES):
            return
        status_code = getattr(response, "status_code", 200)
        if status_code >= 400:
            return
        user = getattr(request, "user", None)
        if not isinstance(user, AdminUser) or not getattr(user, "is_authenticated", False):
            return

        action, resource, details = build_generic_audit(request.path, request.method)
        create_audit_log(request, action=action, resource=resource, details=details)
