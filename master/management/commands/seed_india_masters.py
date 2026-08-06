"""
Seed India locations (country → states → districts → HQ cities) and
religion/caste masters in one command.

Locations:
  - Fetched from the internet by default (India only).
  - Falls back to master/fixtures/india_locations.json if the fetch fails.

Religion / caste:
  - Loaded from local SQLite (default: Backend/db.sqlite3), or
  - from a JSON file exported from that SQLite.

Usage:
  python manage.py seed_india_masters
  python manage.py seed_india_masters --sqlite db.sqlite3
  python manage.py seed_india_masters --religion-file master/fixtures/religions_castes_from_sqlite.json
  python manage.py seed_india_masters --no-fetch
  python manage.py seed_india_masters --clear-locations --clear-religion
  docker compose exec django python manage.py seed_india_masters \\
      --religion-file master/fixtures/religions_castes_from_sqlite.json
"""
from __future__ import annotations

import json
import sqlite3
import urllib.error
import urllib.request
from collections import OrderedDict
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from master.models import Caste, City, Country, District, Religion, State

# Complete India states + districts (~784). Source: igod.gov.in via community JSON.
DEFAULT_LOCATIONS_URL = (
    "https://raw.githubusercontent.com/sanjaynishad/Indian-States-And-Districts/"
    "main/dist/Indian-states-districts.json"
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures"


class Command(BaseCommand):
    help = (
        "Seed India (country/state/district) from the internet and "
        "religion/caste from local SQLite (or JSON)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--sqlite",
            type=str,
            default=None,
            help="SQLite DB path for religion/caste (default: BASE_DIR/db.sqlite3).",
        )
        parser.add_argument(
            "--religion-file",
            type=str,
            default=None,
            help="JSON religions file instead of reading SQLite.",
        )
        parser.add_argument(
            "--locations-url",
            type=str,
            default=DEFAULT_LOCATIONS_URL,
            help="URL to fetch India states/districts JSON.",
        )
        parser.add_argument(
            "--no-fetch",
            action="store_true",
            help="Skip internet fetch; use bundled india_locations.json.",
        )
        parser.add_argument(
            "--skip-locations",
            action="store_true",
            help="Do not seed country/state/district.",
        )
        parser.add_argument(
            "--skip-religion",
            action="store_true",
            help="Do not seed religion/caste.",
        )
        parser.add_argument(
            "--clear-locations",
            action="store_true",
            help="Clear India's states/districts/cities before loading.",
        )
        parser.add_argument(
            "--clear-religion",
            action="store_true",
            help="Clear all religions/castes before loading.",
        )
        parser.add_argument(
            "--export-religion-fixture",
            type=str,
            default=None,
            help="Also write religions/castes JSON to this path (from SQLite).",
        )

    def handle(self, *args, **options):
        if not options["skip_locations"]:
            self._seed_locations(
                fetch=not options["no_fetch"],
                url=options["locations_url"],
                clear=options["clear_locations"],
            )
        else:
            self.stdout.write("Skipping locations.")

        if not options["skip_religion"]:
            religions = self._load_religions_payload(
                sqlite_path=options["sqlite"],
                religion_file=options["religion_file"],
                export_path=options["export_religion_fixture"],
            )
            self._seed_religions(religions, clear=options["clear_religion"])
        else:
            self.stdout.write("Skipping religion/caste.")

        self.stdout.write(self.style.SUCCESS("seed_india_masters finished."))

    # ------------------------------------------------------------------
    # Locations
    # ------------------------------------------------------------------

    def _seed_locations(self, *, fetch: bool, url: str, clear: bool) -> None:
        states_payload = None
        source = "fixture"

        if fetch:
            try:
                self.stdout.write(f"Fetching India locations from:\n  {url}")
                states_payload = self._fetch_online_states(url)
                source = "internet"
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Fetched {len(states_payload)} states/UTs, "
                        f"{sum(len(s['districts']) for s in states_payload)} districts."
                    )
                )
            except Exception as exc:
                self.stdout.write(
                    self.style.WARNING(f"Fetch failed ({exc}); falling back to fixture.")
                )

        if states_payload is None:
            states_payload = self._load_fixture_states()
            source = "fixture"
            self.stdout.write(
                f"Using bundled fixture: {len(states_payload)} states/UTs, "
                f"{sum(len(s['districts']) for s in states_payload)} districts."
            )

        with transaction.atomic():
            country, _ = Country.objects.get_or_create(
                name="India",
                defaults={"code": "IN", "is_active": True},
            )
            if country.code != "IN":
                country.code = "IN"
                country.is_active = True
                country.save(update_fields=["code", "is_active", "updated_at"])

            if clear:
                self.stdout.write("Clearing existing India location data...")
                City.objects.filter(district__state__country=country).delete()
                District.objects.filter(state__country=country).delete()
                State.objects.filter(country=country).delete()

            states_created = districts_created = cities_created = 0
            for item in states_payload:
                state_name = (item.get("name") or "").strip()
                if not state_name:
                    continue
                state, created = State.objects.get_or_create(
                    country=country,
                    name=state_name,
                    defaults={
                        "code": (item.get("code") or "")[:20],
                        "is_active": True,
                    },
                )
                states_created += int(created)
                if not created and item.get("code") and not state.code:
                    state.code = (item.get("code") or "")[:20]
                    state.save(update_fields=["code", "updated_at"])

                for district_name in item.get("districts") or []:
                    district_name = (district_name or "").strip()
                    if not district_name:
                        continue
                    district, created = District.objects.get_or_create(
                        state=state,
                        name=district_name,
                        defaults={"is_active": True},
                    )
                    districts_created += int(created)
                    _, city_created = City.objects.get_or_create(
                        district=district,
                        name=district_name,
                        defaults={"is_active": True},
                    )
                    cities_created += int(city_created)

        india_states = State.objects.filter(country=country).count()
        india_districts = District.objects.filter(state__country=country).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Locations ({source}): +{states_created} states, "
                f"+{districts_created} districts, +{cities_created} cities. "
                f"India totals: {india_states} states, {india_districts} districts."
            )
        )

    def _fetch_online_states(self, url: str) -> list[dict]:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "AiswaryaMatrimony-seed/1.0"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        if not isinstance(data, list) or not data:
            raise ValueError("Expected a non-empty JSON array of states.")

        out: list[dict] = []
        for row in data:
            if not isinstance(row, dict):
                continue
            name = (row.get("name") or row.get("state") or "").strip()
            code = (row.get("code") or row.get("stateCode") or "").strip()
            districts = row.get("districts") or []
            if isinstance(districts, dict):
                districts = list(districts.keys())
            cleaned = [str(d).strip() for d in districts if str(d).strip()]
            if not name or not cleaned:
                continue
            out.append({"name": name, "code": code, "districts": cleaned})

        if len(out) < 28:
            raise ValueError(f"Too few states in payload ({len(out)}).")
        total_districts = sum(len(s["districts"]) for s in out)
        if total_districts < 500:
            raise ValueError(f"Too few districts in payload ({total_districts}).")
        return out

    def _load_fixture_states(self) -> list[dict]:
        path = FIXTURES_DIR / "india_locations.json"
        if not path.exists():
            raise FileNotFoundError(f"Fixture not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        countries = data.get("countries") if isinstance(data, dict) else data
        india = next(
            (c for c in countries if (c.get("name") or "").strip().lower() == "india"),
            None,
        )
        if not india:
            raise ValueError("india_locations.json has no India entry.")
        out: list[dict] = []
        for s in india.get("states") or []:
            districts = []
            for d in s.get("districts") or []:
                if isinstance(d, str):
                    districts.append(d.strip())
                elif isinstance(d, dict) and d.get("name"):
                    districts.append(str(d["name"]).strip())
            out.append(
                {
                    "name": (s.get("name") or "").strip(),
                    "code": (s.get("code") or "").strip(),
                    "districts": [x for x in districts if x],
                }
            )
        return out

    # ------------------------------------------------------------------
    # Religion / caste
    # ------------------------------------------------------------------

    def _default_sqlite_path(self) -> Path:
        return Path(settings.BASE_DIR) / "db.sqlite3"

    def _load_religions_payload(
        self,
        *,
        sqlite_path: str | None,
        religion_file: str | None,
        export_path: str | None,
    ) -> list[dict]:
        if religion_file:
            path = Path(religion_file)
            if not path.exists():
                raise FileNotFoundError(f"Religion file not found: {path}")
            data = json.loads(path.read_text(encoding="utf-8"))
            religions = data.get("religions") if isinstance(data, dict) else data
            if not isinstance(religions, list):
                raise ValueError('Religion JSON must contain a "religions" array.')
            self.stdout.write(f"Loaded religions from JSON: {path}")
            return religions

        db_path = Path(sqlite_path) if sqlite_path else self._default_sqlite_path()
        if not db_path.exists():
            # Prefer exported fixture if SQLite is missing (e.g. production container).
            fallback = FIXTURES_DIR / "religions_castes_from_sqlite.json"
            if fallback.exists():
                self.stdout.write(
                    self.style.WARNING(
                        f"SQLite not found at {db_path}; using {fallback}"
                    )
                )
                data = json.loads(fallback.read_text(encoding="utf-8"))
                return data.get("religions") or []
            raise FileNotFoundError(
                f"SQLite not found: {db_path}. Pass --sqlite or --religion-file."
            )

        religions = self._read_religions_from_sqlite(db_path)
        self.stdout.write(
            f"Loaded {len(religions)} religions / "
            f"{sum(len(r.get('castes') or []) for r in religions)} castes from {db_path}"
        )

        if export_path:
            target = Path(export_path)
        else:
            target = FIXTURES_DIR / "religions_castes_from_sqlite.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps({"religions": religions}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        self.stdout.write(f"Wrote religion fixture: {target}")

        return religions

    def _read_religions_from_sqlite(self, db_path: Path) -> list[dict]:
        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute(
                """
                SELECT r.name, c.name
                FROM master_religion r
                LEFT JOIN master_caste c
                  ON c.religion_id = r.id AND IFNULL(c.is_active, 1) = 1
                WHERE IFNULL(r.is_active, 1) = 1
                ORDER BY r.name, c.name
                """
            ).fetchall()
        finally:
            conn.close()

        grouped: OrderedDict[str, list[str]] = OrderedDict()
        for religion_name, caste_name in rows:
            religion_name = (religion_name or "").strip()
            if not religion_name:
                continue
            grouped.setdefault(religion_name, [])
            caste_name = (caste_name or "").strip()
            if caste_name and caste_name not in grouped[religion_name]:
                grouped[religion_name].append(caste_name)

        return [{"name": name, "castes": castes} for name, castes in grouped.items()]

    def _seed_religions(self, religions: list[dict], *, clear: bool) -> None:
        with transaction.atomic():
            if clear:
                self.stdout.write("Clearing existing religion and caste data...")
                Caste.objects.all().delete()
                Religion.objects.all().delete()

            religions_created = castes_created = 0
            for item in religions:
                name = (item.get("name") or "").strip()
                if not name:
                    continue
                religion, created = Religion.objects.get_or_create(
                    name=name,
                    defaults={"is_active": True},
                )
                religions_created += int(created)
                if not religion.is_active:
                    religion.is_active = True
                    religion.save(update_fields=["is_active", "updated_at"])

                for caste in item.get("castes") or []:
                    cname = (caste if isinstance(caste, str) else caste.get("name", "")).strip()
                    if not cname:
                        continue
                    _, created = Caste.objects.get_or_create(
                        religion=religion,
                        name=cname,
                        defaults={"is_active": True},
                    )
                    castes_created += int(created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Religion/caste: +{religions_created} religions, +{castes_created} castes. "
                f"Totals: {Religion.objects.filter(is_active=True).count()} religions, "
                f"{Caste.objects.filter(is_active=True).count()} castes."
            )
        )
