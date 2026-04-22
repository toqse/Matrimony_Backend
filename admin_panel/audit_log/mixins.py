from .utils import create_audit_log


class AuditLogMixin:
    def log_action(self, action, resource, details, old_value=None, new_value=None, **kwargs):
        create_audit_log(
            self.request,
            action=action,
            resource=resource,
            details=details or "",
            old_value=old_value,
            new_value=new_value,
            **kwargs,
        )
