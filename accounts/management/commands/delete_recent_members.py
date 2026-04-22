"""
Remove the most recently created member accounts (role=user, not staff/superuser).

Typical use: undo a mistaken bulk upload. By default this is a dry run; pass --execute
to actually delete.

Examples:
  python manage.py delete_recent_members 35
  python manage.py delete_recent_members 35 --execute
  python manage.py delete_recent_members --last-bulk-job
  python manage.py delete_recent_members --last-bulk-job --execute

Note: Deletes may fail if another table references the user with PROTECT (e.g. some
commission rows). Fix or remove those rows first, then re-run.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

User = get_user_model()


def _member_queryset():
    return User.objects.filter(role="user", is_staff=False, is_superuser=False)


class Command(BaseCommand):
    help = "Delete the newest member accounts by created_at (dry run unless --execute)."

    def add_arguments(self, parser):
        parser.add_argument(
            "count",
            nargs="?",
            type=int,
            default=None,
            help="How many of the newest members to remove.",
        )
        parser.add_argument(
            "--last-bulk-job",
            action="store_true",
            dest="last_bulk_job",
            help="Set count from the latest completed bulk-upload job (imported_count).",
        )
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Perform deletion. Without this flag, only lists candidates.",
        )

    def handle(self, *args, **options):
        count = options["count"]
        execute = options["execute"]
        last_bulk = options["last_bulk_job"]

        if last_bulk:
            from admin_panel.bulk_upload.models import BulkUploadJob

            job = (
                BulkUploadJob.objects.filter(
                    status=BulkUploadJob.STATUS_COMPLETED,
                    imported_count__gt=0,
                )
                .order_by("-completed_at", "-id")
                .first()
            )
            if not job:
                self.stderr.write(
                    self.style.ERROR(
                        "No completed bulk upload job with imported_count > 0 found."
                    )
                )
                return
            count = int(job.imported_count)
            self.stdout.write(
                f"Last bulk job: id={job.id} file={job.file_name!r} "
                f"imported_count={count} completed_at={job.completed_at}"
            )

        if count is None or count < 1:
            self.stderr.write(
                self.style.ERROR(
                    "Provide a positive integer count, or use --last-bulk-job "
                    "(e.g. delete_recent_members 20 or delete_recent_members --last-bulk-job)."
                )
            )
            return

        users = list(_member_queryset().order_by("-created_at")[:count])
        if not users:
            self.stdout.write(self.style.WARNING("No matching member users found."))
            return
        if len(users) < count:
            self.stdout.write(
                self.style.WARNING(
                    f"Only {len(users)} member(s) match (requested {count})."
                )
            )

        self.stdout.write(f"Candidates ({len(users)}):")
        for u in users:
            self.stdout.write(
                f"  {u.matri_id or '-'}  name={u.name!r}  mobile={u.mobile}  "
                f"created_at={u.created_at}"
            )

        if not execute:
            self.stdout.write(
                self.style.WARNING("Dry run only. Re-run with --execute to delete.")
            )
            return

        deleted = 0
        for u in users:
            matri = u.matri_id
            uid = str(u.pk)
            try:
                with transaction.atomic():
                    u.delete()
                deleted += 1
                self.stdout.write(self.style.SUCCESS(f"Deleted {matri} ({uid})"))
            except Exception as exc:
                self.stderr.write(
                    self.style.ERROR(f"Failed to delete {matri} ({uid}): {exc}")
                )

        self.stdout.write(self.style.SUCCESS(f"Finished. Deleted {deleted} of {len(users)}."))
