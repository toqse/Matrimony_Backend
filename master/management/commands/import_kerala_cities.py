"""
Import Kerala municipal cities under India -> Kerala -> district.

Data source: master/fixtures/kerala_cities.json
(city name + district name). Idempotent via get_or_create;
existing matches are activated if inactive.

Usage:
  python manage.py import_kerala_cities
  python manage.py import_kerala_cities --file path/to/kerala_cities.json
  python manage.py import_kerala_cities --deactivate-others
  docker compose exec django python manage.py import_kerala_cities
  docker compose exec django python manage.py import_kerala_cities --deactivate-others
"""
from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from master.models import City, Country, District, State


class Command(BaseCommand):
    help = "Import Kerala municipal cities under India -> Kerala districts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default=None,
            help="Path to JSON fixture (default: master/fixtures/kerala_cities.json)",
        )
        parser.add_argument(
            "--deactivate-others",
            action="store_true",
            help=(
                "Deactivate Kerala cities that are not in this import list "
                "(useful after junk bulk data)."
            ),
        )

    def _resolve_file(self, file_path: str | None) -> Path:
        if file_path:
            return Path(file_path)
        base = Path(__file__).resolve().parent.parent.parent
        return base / "fixtures" / "kerala_cities.json"

    def handle(self, *args, **options):
        file_path = self._resolve_file(options.get("file"))
        deactivate_others = bool(options.get("deactivate_others"))

        if not file_path.exists():
            self.stdout.write(self.style.ERROR(f"File not found: {file_path}"))
            return

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        country_name = (data.get("country") or "India").strip()
        state_name = (data.get("state") or "Kerala").strip()
        cities_data = data.get("cities") or []
        if not isinstance(cities_data, list) or not cities_data:
            self.stdout.write(self.style.ERROR('JSON must contain a non-empty "cities" array.'))
            return

        country = Country.objects.filter(name__iexact=country_name).first()
        if not country:
            self.stdout.write(
                self.style.ERROR(
                    f'Country "{country_name}" not found. '
                    "Run load_india_locations first."
                )
            )
            return

        state = State.objects.filter(country=country, name__iexact=state_name).first()
        if not state:
            self.stdout.write(
                self.style.ERROR(
                    f'State "{state_name}" under "{country.name}" not found. '
                    "Run load_india_locations first."
                )
            )
            return

        # Ensure Kerala (and India) are active for registration dropdowns.
        if not country.is_active:
            country.is_active = True
            country.save(update_fields=["is_active", "updated_at"])
        if not state.is_active:
            state.is_active = True
            state.save(update_fields=["is_active", "updated_at"])

        district_cache: dict[str, District | None] = {}
        created = existing = activated = skipped = 0
        keep_city_ids: list[int] = []

        with transaction.atomic():
            for row in cities_data:
                if not isinstance(row, dict):
                    skipped += 1
                    continue
                city_name = (row.get("name") or "").strip()
                district_name = (row.get("district") or "").strip()
                if not city_name or not district_name:
                    skipped += 1
                    self.stdout.write(
                        self.style.WARNING(f"Skipping incomplete row: {row!r}")
                    )
                    continue

                cache_key = district_name.lower()
                if cache_key not in district_cache:
                    district = District.objects.filter(
                        state=state, name__iexact=district_name
                    ).first()
                    district_cache[cache_key] = district
                    if district is None:
                        self.stdout.write(
                            self.style.ERROR(
                                f'District "{district_name}" not found under '
                                f"{state.name}; skipping cities for it."
                            )
                        )
                    elif not district.is_active:
                        district.is_active = True
                        district.save(update_fields=["is_active", "updated_at"])

                district = district_cache[cache_key]
                if district is None:
                    skipped += 1
                    continue

                # Prefer case-insensitive match so KERALA-style rows are reused.
                city = City.objects.filter(
                    district=district, name__iexact=city_name
                ).first()
                if city:
                    existing += 1
                    keep_city_ids.append(city.id)
                    if not city.is_active:
                        city.is_active = True
                        city.save(update_fields=["is_active", "updated_at"])
                        activated += 1
                else:
                    city = City.objects.create(
                        district=district,
                        name=city_name,
                        is_active=True,
                    )
                    created += 1
                    keep_city_ids.append(city.id)

            deactivated = 0
            if deactivate_others:
                qs = City.objects.filter(district__state=state).exclude(
                    id__in=keep_city_ids
                )
                deactivated = qs.update(is_active=False)

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Created {created}, already existed {existing} "
                f"(reactivated {activated}), skipped {skipped}."
            )
        )
        if deactivate_others:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Deactivated {deactivated} other Kerala cities not in the list."
                )
            )
        active_count = City.objects.filter(
            district__state=state, is_active=True
        ).count()
        self.stdout.write(
            f"Active cities under {country.name} / {state.name}: {active_count}"
        )
