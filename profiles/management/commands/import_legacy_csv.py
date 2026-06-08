"""Management command: bulk-load the legacy matrimony CSV export.

Usage:
  python manage.py import_legacy_csv "txt (1).csv" \
      [--dry-run] [--limit 100] [--branch CODE] [--report PATH] \
      [--skip-existing|--no-skip-existing] [--no-auto-create-masters]

The heavy lifting lives in profiles.legacy_import; this command just wires
CLI options to the importer and writes a per-row CSV report.
"""
from __future__ import annotations

import csv
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from master.models import Branch
from profiles.legacy_import import LegacyImporter, parse_legacy_csv, read_legacy_csv_text
from profiles.legacy_import.normalize import clean

REPORT_FIELDS = ["row", "status", "reason", "name", "phone"]


class Command(BaseCommand):
    help = "Import old Matrimony CSV export into users, profiles, and horoscope rows."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", help="Path to the legacy export (CSV)")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate rows and write the report without touching the database.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Process only the first N data rows (handy for staging smoke tests).",
        )
        parser.add_argument(
            "--branch",
            default=None,
            help="Branch.code to assign to imported users (default: no branch).",
        )
        parser.add_argument(
            "--report",
            default="legacy_import_report.csv",
            help="Output CSV report path (row, status, reason, name, phone).",
        )
        parser.add_argument(
            "--skip-existing",
            dest="skip_existing",
            action="store_true",
            default=True,
            help="Skip rows whose mobile or email already exist in the DB (default).",
        )
        parser.add_argument(
            "--no-skip-existing",
            dest="skip_existing",
            action="store_false",
            help="Do not skip rows that conflict with existing users.",
        )
        parser.add_argument(
            "--no-auto-create-masters",
            action="store_true",
            help="Do not auto-create unknown master records; leave those FKs NULL.",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["csv_path"])
        if not csv_path.exists():
            raise CommandError(f"CSV file not found: {csv_path}")

        branch = self._resolve_branch(options.get("branch"))
        importer = LegacyImporter(
            dry_run=options["dry_run"],
            branch=branch,
            skip_existing=options["skip_existing"],
            auto_create_masters=not options["no_auto_create_masters"],
        )

        report_path = Path(options["report"])
        limit = options.get("limit")

        try:
            csv_text = read_legacy_csv_text(csv_path)
            _, reader = parse_legacy_csv(csv_text)
        except ValueError as exc:
            raise CommandError(str(exc))

        imported = skipped = failed = warnings = 0
        with report_path.open("w", encoding="utf-8", newline="") as report_file:
            report = csv.DictWriter(report_file, fieldnames=REPORT_FIELDS)
            report.writeheader()

            for index, row in enumerate(reader, start=2):
                if limit is not None and index > limit + 1:
                    break

                payload, reason = importer.build_payload(index, row)
                if payload is None:
                    skipped += 1
                    report.writerow(
                        {
                            "row": index,
                            "status": "skipped",
                            "reason": reason,
                            "name": clean(row.get("name")),
                            "phone": row.get("phone number", ""),
                        }
                    )
                    continue

                try:
                    with transaction.atomic():
                        importer.save(payload)
                except (IntegrityError, ValidationError, ValueError) as exc:
                    failed += 1
                    report.writerow(
                        {
                            "row": index,
                            "status": "failed",
                            "reason": str(exc),
                            "name": payload["name"],
                            "phone": payload["phone"] or "",
                        }
                    )
                    continue

                imported += 1
                row_reason = (
                    f"unmapped_star:{payload['star_warning']}"
                    if payload["star_warning"]
                    else ""
                )
                if row_reason:
                    warnings += 1
                report.writerow(
                    {
                        "row": index,
                        "status": "valid" if options["dry_run"] else "imported",
                        "reason": row_reason,
                        "name": payload["name"],
                        "phone": payload["phone"] or "",
                    }
                )

        action = "Validated" if options["dry_run"] else "Imported"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action} {imported}; skipped {skipped}; failed {failed}; "
                f"warnings {warnings}; report {report_path}"
            )
        )

    @staticmethod
    def _resolve_branch(code: str | None):
        if not code:
            return None
        branch = Branch.objects.filter(code=code, is_active=True).first()
        if not branch:
            raise CommandError(f"Active branch not found for code: {code}")
        return branch
