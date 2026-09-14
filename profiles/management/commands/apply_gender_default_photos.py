"""Fill gender default photos on existing members missing profile/full files.

Usage:
  python manage.py apply_gender_default_photos [--dry-run] [--limit N]
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from accounts.models import User
from profiles.default_photos import apply_gender_default_photos, users_needing_default_photos


class Command(BaseCommand):
    help = "Apply Aiswarya gender default photos to existing profiles with empty photo files."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count matching profiles without writing files.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Max number of profiles to process.",
        )

    def handle(self, *args, **options):
        qs = users_needing_default_photos().order_by("pk")
        limit = options.get("limit")
        if limit is not None:
            qs = qs[: max(0, int(limit))]
        pks = list(qs.values_list("pk", flat=True))
        total = len(pks)
        if options.get("dry_run"):
            self.stdout.write(f"Would update {total} profile(s).")
            return

        updated = 0
        for user in User.objects.filter(pk__in=pks).iterator():
            if apply_gender_default_photos(user):
                updated += 1
        self.stdout.write(self.style.SUCCESS(f"Updated {updated} of {total} profile(s)."))
