"""
Horoscope decoder verification tool.

Compares the Windows EXE's house-by-house chart output (ground truth) against
Django's decode of the same raw strings, and prints a house-by-house mismatch
report plus overall accuracy.

Usage:
    python manage.py verify_horoscope_decoder
    python manage.py verify_horoscope_decoder --file path/to/ground_truth.json
    python manage.py verify_horoscope_decoder --strict   # exit 1 if < 100%

Ground-truth JSON shape::

    {
      "verified_against_exe": true,
      "records": [
        {
          "id": 1842,
          "pr_rasi": "BHEJGAFADJC",
          "pr_amsa": "DGDLBAFFGAL",
          "pr_bhav": "BHEJGLFADJC",
          "exe": {
            "rasi":  {"1": ["Ju", "Sa"], "2": ["La"], ...},
            "amsa":  {...},
            "bhava": {...}
          }
        }
      ]
    }

The EXE side ("exe") must be filled in from the actual Windows Horoscope
Generator output. The tool never infers EXE values; it only compares.
"""
from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from astrology.services.horoscope_verification import (
    overall_accuracy,
    render_report,
    verify_record,
)

DEFAULT_FIXTURE = (
    Path(settings.BASE_DIR)
    / 'astrology'
    / 'fixtures'
    / 'horoscope_exe_ground_truth.json'
)


class Command(BaseCommand):
    help = 'Verify Django horoscope decoding against EXE ground-truth house maps.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            dest='file',
            default=str(DEFAULT_FIXTURE),
            help='Path to EXE ground-truth JSON (default: astrology/fixtures/horoscope_exe_ground_truth.json).',
        )
        parser.add_argument(
            '--strict',
            action='store_true',
            help='Exit with code 1 if overall accuracy is below 100%%.',
        )

    def handle(self, *args, **options):
        path = Path(options['file'])
        if not path.exists():
            raise CommandError(f'Ground-truth file not found: {path}')

        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as exc:
            raise CommandError(f'Invalid JSON in {path}: {exc}')

        records = payload.get('records') or []
        if not records:
            raise CommandError(f'No "records" found in {path}.')

        verified_flag = bool(payload.get('verified_against_exe', False))
        if not verified_flag:
            self.stdout.write(
                self.style.WARNING(
                    'WARNING: "verified_against_exe" is false. The EXE side of this '
                    'fixture has NOT been confirmed against the real Windows EXE, so '
                    'a 100% result here does NOT certify EXE parity. Replace the "exe" '
                    'house maps with actual EXE output and set the flag to true.'
                )
            )

        all_results = []
        for record in records:
            results = verify_record(record)
            if not results:
                self.stdout.write(
                    self.style.WARNING(
                        f'id={record.get("id")}: no "exe" charts to compare, skipped.'
                    )
                )
                continue
            all_results.append(results)
            report = render_report(record.get('id'), results)
            failed = not all(r.passed for r in results.values())
            self.stdout.write(self.style.ERROR(report) if failed else report)

        acc = overall_accuracy(all_results)
        self.stdout.write('')
        summary = f'OVERALL DECODER ACCURACY: {acc:.2f}%'
        if acc >= 100.0:
            self.stdout.write(self.style.SUCCESS(summary))
        else:
            self.stdout.write(self.style.ERROR(summary))

        if options['strict'] and acc < 100.0:
            raise CommandError('Decoder accuracy is below 100%.')
