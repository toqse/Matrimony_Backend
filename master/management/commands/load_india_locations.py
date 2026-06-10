"""
Seed India as a Country with all states/UTs, their districts, and a default
HQ city per district, into the master tables.

Data source: bundled fixture master/fixtures/india_locations.json
(country -> states -> districts). Each district name may be a plain string or
an object {"name": "...", "cities": ["..."]}. When a district has no explicit
"cities", its headquarters city is auto-created using the district's own name.

Idempotent: re-running only adds what's missing (uses get_or_create).

Usage:
  python manage.py load_india_locations
  python manage.py load_india_locations --file path/to/india_locations.json
  python manage.py load_india_locations --clear   # remove India's data first
  docker-compose exec django python manage.py load_india_locations
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from master.models import Country, State, District, City


class Command(BaseCommand):
    help = "Seed India (country -> states/UTs -> districts -> HQ city) from a bundled JSON fixture."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default=None,
            help="Path to JSON fixture (default: master/fixtures/india_locations.json)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete India's existing State/District/City data before loading.",
        )

    def _resolve_file(self, file_path):
        if file_path:
            return Path(file_path)
        base = Path(__file__).resolve().parent.parent.parent
        return base / "fixtures" / "india_locations.json"

    def handle(self, *args, **options):
        file_path = self._resolve_file(options.get("file"))
        clear_first = options.get("clear", False)

        if not file_path.exists():
            self.stdout.write(self.style.ERROR(f"File not found: {file_path}"))
            return

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        countries_data = data.get("countries") if isinstance(data, dict) else data
        if not isinstance(countries_data, list):
            self.stdout.write(self.style.ERROR('JSON must contain a "countries" array.'))
            return

        states_created = districts_created = cities_created = 0

        with transaction.atomic():
            for c in countries_data:
                country, _ = Country.objects.get_or_create(
                    name=(c["name"] or "").strip(),
                    defaults={"code": (c.get("code") or "")[:10], "is_active": True},
                )

                if clear_first:
                    self.stdout.write(f"Clearing existing location data for {country.name}...")
                    City.objects.filter(district__state__country=country).delete()
                    District.objects.filter(state__country=country).delete()
                    State.objects.filter(country=country).delete()

                for s in c.get("states") or []:
                    state, created = State.objects.get_or_create(
                        country=country,
                        name=(s["name"] or "").strip(),
                        defaults={"code": (s.get("code") or "")[:20], "is_active": True},
                    )
                    states_created += int(created)

                    for d in s.get("districts") or []:
                        if isinstance(d, str):
                            district_name, city_names = d.strip(), []
                        else:
                            district_name = (d.get("name") or "").strip()
                            city_names = list(d.get("cities") or [])
                        if not district_name:
                            continue

                        district, created = District.objects.get_or_create(
                            state=state,
                            name=district_name,
                            defaults={"is_active": True},
                        )
                        districts_created += int(created)

                        # No explicit cities -> seed the district HQ (same name).
                        if not city_names:
                            city_names = [district_name]

                        for city_name in city_names:
                            city_name = (city_name or "").strip()
                            if not city_name:
                                continue
                            _, created = City.objects.get_or_create(
                                district=district,
                                name=city_name,
                                defaults={"is_active": True},
                            )
                            cities_created += int(created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Created {states_created} states/UTs, {districts_created} districts, "
                f"{cities_created} cities. Totals now: "
                f"{State.objects.count()} states, {District.objects.count()} districts, "
                f"{City.objects.count()} cities."
            )
        )
