"""
Change an AdminUser mobile number (admin panel OTP login).

Usage (10-digit Indian numbers):
  python manage.py change_admin_mobile 9496954772 9876543210

Inside Docker:
  docker compose exec django python manage.py change_admin_mobile 9496954772 9876543210

You may pass E164 (+91XXXXXXXXXX) for the old number if you prefer.
"""
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from admin_panel.auth.models import AdminUser
from admin_panel.auth.serializers import normalize_indian_mobile_10_to_e164


def _to_e164(mobile_raw: str) -> str:
    s = (mobile_raw or "").strip().replace(" ", "")
    if not s:
        raise ValueError("empty")
    if s.startswith("+91") and len(s) == 13 and s[3:].isdigit():
        return s
    if re.fullmatch(r"\d{10}", s):
        return normalize_indian_mobile_10_to_e164(s)
    raise ValueError("invalid")


class Command(BaseCommand):
    help = "Change AdminUser mobile (admin panel). Args: old_mobile new_mobile (10-digit Indian numbers)."

    def add_arguments(self, parser):
        parser.add_argument("old_mobile", type=str, help="Current number: 10 digits or +91XXXXXXXXXX")
        parser.add_argument("new_mobile", type=str, help="New number: 10 digits only")

    def handle(self, *args, **options):
        try:
            old_e164 = _to_e164(options["old_mobile"])
        except ValueError:
            self.stderr.write(self.style.ERROR("Old mobile must be 10 digits or +91XXXXXXXXXX."))
            return
        try:
            new_e164 = _to_e164(options["new_mobile"])
        except ValueError:
            self.stderr.write(self.style.ERROR("New mobile must be exactly 10 digits."))
            return

        if old_e164 == new_e164:
            self.stderr.write(self.style.ERROR("Old and new mobile are the same."))
            return

        user = AdminUser.objects.filter(mobile=old_e164).first()
        if not user:
            self.stderr.write(
                self.style.ERROR(f"No AdminUser found with mobile {old_e164}.")
            )
            return

        conflict = AdminUser.objects.exclude(pk=user.pk).filter(mobile=new_e164).first()
        if conflict:
            self.stderr.write(
                self.style.ERROR(
                    f"Another AdminUser (id={conflict.pk}) already uses {new_e164}. Remove or change that account first."
                )
            )
            return

        with transaction.atomic():
            user.mobile = new_e164
            user.save(update_fields=["mobile", "updated_at"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Updated AdminUser id={user.pk} ({user.name}): mobile {old_e164} -> {new_e164}"
            )
        )
