"""
Set AdminUser.branch from StaffProfile.branch when it was NULL (e.g. old bug or missing master.Branch at create time).

Usage:
  python manage.py sync_admin_user_branch_from_staff
  python manage.py sync_admin_user_branch_from_staff --dry-run
"""

from django.core.management.base import BaseCommand

from admin_panel.auth.models import AdminUser
from admin_panel.staff_mgmt.branch_sync import ensure_master_branch_from_admin_branch
from admin_panel.staff_mgmt.models import StaffProfile


class Command(BaseCommand):
    help = "Backfill AdminUser.branch from linked StaffProfile.branch code → master.Branch"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would change without saving",
        )

    def handle(self, *args, **options):
        dry = options["dry_run"]
        fixed = 0
        skipped = 0

        qs = (
            StaffProfile.objects.filter(is_deleted=False)
            .select_related("branch", "admin_user")
            .filter(admin_user__branch__isnull=True)
        )

        for sp in qs:
            au: AdminUser = sp.admin_user
            if not sp.branch_id:
                self.stdout.write(self.style.WARNING(f"Skip staff id={sp.pk}: no StaffProfile.branch"))
                skipped += 1
                continue
            mb = ensure_master_branch_from_admin_branch(sp.branch)
            if not mb:
                self.stdout.write(self.style.WARNING(f"Skip admin_user id={au.pk}: could not ensure master.Branch"))
                skipped += 1
                continue
            if dry:
                self.stdout.write(f"Would set AdminUser id={au.pk} branch_id={mb.pk} ({mb.name})")
            else:
                AdminUser.objects.filter(pk=au.pk).update(branch_id=mb.pk)
                self.stdout.write(self.style.SUCCESS(f"Updated AdminUser id={au.pk} → master.Branch id={mb.pk}"))
            fixed += 1

        self.stdout.write(self.style.NOTICE(f"Done. updated={fixed} skipped={skipped} dry_run={dry}"))
