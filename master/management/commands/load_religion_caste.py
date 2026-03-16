"""
Load religions and castes from JSON fixture into master tables.

Usage:
  python manage.py load_religion_caste
  python manage.py load_religion_caste --file path/to/religions_castes.json
  python manage.py load_religion_caste --clear   # Delete existing religion/caste data first
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from master.models import Religion, Caste


class Command(BaseCommand):
    help = 'Load religions and castes from a JSON fixture.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            default=None,
            help='Path to JSON fixture (default: master/fixtures/religions_castes.json)',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete existing Caste and Religion data before loading.',
        )

    def handle(self, *args, **options):
        file_path = options.get('file')
        clear_first = options.get('clear', False)

        if file_path is None:
            base = Path(__file__).resolve().parent.parent.parent
            file_path = base / 'fixtures' / 'religions_castes.json'
        else:
            file_path = Path(file_path)

        if not file_path.exists():
            self.stdout.write(self.style.ERROR(f'File not found: {file_path}'))
            return

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        religions_data = data.get('religions') or data
        if not isinstance(religions_data, list):
            self.stdout.write(self.style.ERROR('JSON must contain a "religions" array.'))
            return

        with transaction.atomic():
            if clear_first:
                self.stdout.write('Clearing existing religion and caste data...')
                Caste.objects.all().delete()
                Religion.objects.all().delete()
                self.stdout.write(self.style.WARNING('Cleared Religion and Caste.'))

            religions_created = 0
            castes_created = 0

            for r in religions_data:
                name = (r.get('name') or '').strip()
                if not name:
                    continue
                religion, created = Religion.objects.get_or_create(
                    name=name,
                    defaults={'is_active': True},
                )
                if created:
                    religions_created += 1

                for c in r.get('castes') or []:
                    cname = (c if isinstance(c, str) else c.get('name', '')).strip()
                    if not cname:
                        continue
                    _, created = Caste.objects.get_or_create(
                        religion=religion,
                        name=cname,
                        defaults={'is_active': True},
                    )
                    if created:
                        castes_created += 1

            self.stdout.write(self.style.SUCCESS(
                f'Done. Created: {religions_created} religions, {castes_created} castes.'
            ))
