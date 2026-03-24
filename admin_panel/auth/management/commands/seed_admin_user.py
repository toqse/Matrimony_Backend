from django.core.management.base import BaseCommand

from admin_panel.auth.models import AdminUser
from admin_panel.auth.serializers import normalize_indian_mobile_10_to_e164


class Command(BaseCommand):
    help = "Seed an AdminUser for admin-panel OTP login (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("mobile", type=str, help="10 digit Indian mobile number (e.g. 9999999999)")
        parser.add_argument("--role", type=str, default=AdminUser.ROLE_ADMIN, help="admin|branch_manager|staff")
        parser.add_argument("--name", type=str, default="Seed Admin", help="Admin user's display name")
        parser.add_argument("--inactive", action="store_true", help="Create/update as inactive (is_active=False)")

    def handle(self, *args, **options):
        mobile_10 = (options["mobile"] or "").strip()
        role = (options["role"] or "").strip().lower()
        name = (options["name"] or "").strip() or "Seed Admin"
        is_active = not bool(options["inactive"])

        if role not in {c[0] for c in AdminUser.ROLE_CHOICES}:
            self.stderr.write(self.style.ERROR("Invalid role. Use: admin | branch_manager | staff"))
            return

        try:
            mobile_e164 = normalize_indian_mobile_10_to_e164(mobile_10)
        except Exception:
            self.stderr.write(self.style.ERROR("Mobile number must be 10 digits"))
            return

        user, created = AdminUser.objects.get_or_create(
            mobile=mobile_e164,
            defaults={"role": role, "name": name, "is_active": is_active},
        )
        if not created:
            user.role = role
            user.name = name
            user.is_active = is_active
            user.save(update_fields=["role", "name", "is_active", "updated_at"])

        action = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action} AdminUser: mobile={user.mobile}, role={user.role}, name={user.name}, is_active={user.is_active}"
            )
        )
