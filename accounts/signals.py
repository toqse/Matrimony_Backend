"""
Keep the admin-panel login model (admin_panel.auth.AdminUser) in sync with
admin-capable accounts.User rows.

Background: the OTP admin panel (/api/v1/admin/auth/) authenticates against the
separate AdminUser table, NOT accounts.User. So a Django superuser alone cannot
log in to the admin panel. This signal bridges that gap: whenever a superuser
(or a user with role='admin') is saved with a mobile number, a matching
AdminUser is created/updated automatically.
"""
import re

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User


def _to_e164_india(raw: str) -> str | None:
    """Normalize an Indian mobile to +91XXXXXXXXXX, or None if not 10 digits."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"+91{digits}"
    return None


@receiver(post_save, sender=User, dispatch_uid="sync_admin_panel_user")
def sync_admin_panel_user(sender, instance: User, **kwargs):
    # Only mirror admin-capable accounts; skip ordinary members for performance.
    is_admin_account = bool(getattr(instance, "is_superuser", False)) or (
        getattr(instance, "role", "") == "admin"
    )
    if not is_admin_account:
        return

    mobile_e164 = _to_e164_india(getattr(instance, "mobile", "") or "")
    if not mobile_e164:
        # No usable phone yet (e.g. superuser created without one). Nothing to do
        # until a phone number is added to the account.
        return

    name = (instance.name or "").strip() or (instance.email or "").strip() or "Admin User"
    email = (instance.email or "").strip()

    def _upsert():
        from admin_panel.auth.models import AdminUser

        AdminUser.objects.update_or_create(
            mobile=mobile_e164,
            defaults={
                "role": AdminUser.ROLE_ADMIN,
                "name": name,
                "email": email,
                "is_active": True,
            },
        )

    # Run after the surrounding transaction commits (e.g. Django admin save),
    # so we never create an AdminUser for a User row that gets rolled back.
    transaction.on_commit(_upsert)
