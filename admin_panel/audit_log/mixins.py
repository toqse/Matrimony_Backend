from .models import AuditLog


def _get_client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class AuditLogMixin:
    def log_action(self, action, resource, details, old_value=None, new_value=None):
        user = getattr(self.request, "user", None)
        actor = user if getattr(user, "is_authenticated", False) else None
        AuditLog.objects.create(
            actor=actor,
            actor_name=(getattr(actor, "name", "") or "").strip(),
            actor_role=(getattr(actor, "role", "") or "").strip(),
            action=action,
            resource=resource,
            details=details or "",
            old_value=old_value,
            new_value=new_value,
            ip_address=_get_client_ip(self.request),
        )
