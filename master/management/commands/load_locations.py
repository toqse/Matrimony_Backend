"""
Load countries, states, districts, and cities from a JSON fixture into master tables.

Usage:
  python manage.py load_locations
  python manage.py load_locations --file path/to/locations.json
  python manage.py load_locations --clear   # Delete existing location data first

JSON format:
  {
    "countries": [
      {
        "name": "India",
        "code": "IN",
        "states": [
          {
            "name": "Kerala",
            "code": "KL",
            "districts": [
              {
                "name": "Thiruvananthapuram",
                "cities": ["Thiruvananthapuram", "Neyyattinkara"]
              }
            ]
          }
        ]
      }
    ]
  }
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from master.models import Country, State, District, City


class Command(BaseCommand):
    help = 'Load countries, states, districts, and cities from a JSON fixture.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            default=None,
            help='Path to JSON fixture (default: master/fixtures/locations.json)',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete existing Country/State/District/City data before loading (order-safe).',
        )

    def handle(self, *args, **options):
        file_path = options.get('file')
        clear_first = options.get('clear', False)

        if file_path is None:
            base = Path(__file__).resolve().parent.parent.parent
            file_path = base / 'fixtures' / 'locations.json'
        else:
            file_path = Path(file_path)

        if not file_path.exists():
            self.stdout.write(self.style.ERROR(f'File not found: {file_path}'))
            return

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        countries_data = data.get('countries') or data
        if not isinstance(countries_data, list):
            self.stdout.write(self.style.ERROR('JSON must contain a "countries" array.'))
            return

        with transaction.atomic():
            if clear_first:
                self.stdout.write('Clearing existing location data...')
                City.objects.all().delete()
                District.objects.all().delete()
                State.objects.all().delete()
                Country.objects.all().delete()
                self.stdout.write(self.style.WARNING('Cleared Country, State, District, City.'))

            countries_created = 0
            states_created = 0
            districts_created = 0
            cities_created = 0

            for c in countries_data:
                country, created = Country.objects.get_or_create(
                    name=c['name'].strip(),
                    defaults={'code': (c.get('code') or '')[:10], 'is_active': True},
                )
                if created:
                    countries_created += 1

                for s in c.get('states') or []:
                    state, created = State.objects.get_or_create(
                        country=country,
                        name=s['name'].strip(),
                        defaults={'code': (s.get('code') or '')[:20], 'is_active': True},
                    )
                    if created:
                        states_created += 1

                    for d in s.get('districts') or []:
                        district, created = District.objects.get_or_create(
                            state=state,
                            name=d['name'].strip(),
                            defaults={'is_active': True},
                        )
                        if created:
                            districts_created += 1

                        for city_name in d.get('cities') or []:
                            city_name = (city_name or '').strip()
                            if not city_name:
                                continue
                            _, created = City.objects.get_or_create(
                                district=district,
                                name=city_name,
                                defaults={'is_active': True},
                            )
                            if created:
                                cities_created += 1

            self.stdout.write(self.style.SUCCESS(
                f'Done. Created: {countries_created} countries, {states_created} states, '
                f'{districts_created} districts, {cities_created} cities.'
            ))
