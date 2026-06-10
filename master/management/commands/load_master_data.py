"""
Seed matrimony reference/master data into the master tables from a bundled
JSON fixture (master/fixtures/master_data.json).

Covers:
  - Religions and their Castes
  - Mother tongues
  - Education (highest qualification) and Education Subjects
  - Occupations
  - Income ranges
  - Marital statuses
  - Employment statuses

Idempotent: uses get_or_create, so re-running only adds what's missing and
never duplicates existing rows (safe alongside the seed data migrations).

Usage:
  python manage.py load_master_data
  python manage.py load_master_data --file path/to/master_data.json
  python manage.py load_master_data --only religions,mother_tongues
  docker-compose exec django python manage.py load_master_data
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from master.models import (
    Religion,
    Caste,
    MotherTongue,
    Education,
    EducationSubject,
    Occupation,
    IncomeRange,
    MaritalStatus,
    EmploymentStatus,
)


# Simple "name + is_active" lookups keyed by their JSON section.
SIMPLE_SECTIONS = {
    "mother_tongues": MotherTongue,
    "educations": Education,
    "education_subjects": EducationSubject,
    "occupations": Occupation,
    "income_ranges": IncomeRange,
    "marital_statuses": MaritalStatus,
    "employment_statuses": EmploymentStatus,
}


class Command(BaseCommand):
    help = "Seed religions, castes, mother tongues, education, subjects, occupations, etc. from a JSON fixture."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default=None,
            help="Path to JSON fixture (default: master/fixtures/master_data.json)",
        )
        parser.add_argument(
            "--only",
            type=str,
            default=None,
            help="Comma-separated sections to load (e.g. religions,mother_tongues). Default: all.",
        )

    def _resolve_file(self, file_path):
        if file_path:
            return Path(file_path)
        base = Path(__file__).resolve().parent.parent.parent
        return base / "fixtures" / "master_data.json"

    def handle(self, *args, **options):
        file_path = self._resolve_file(options.get("file"))
        only = options.get("only")
        selected = {s.strip() for s in only.split(",")} if only else None

        if not file_path.exists():
            self.stdout.write(self.style.ERROR(f"File not found: {file_path}"))
            return

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        def wanted(section: str) -> bool:
            return selected is None or section in selected

        counts = {}

        with transaction.atomic():
            if wanted("religions"):
                counts["religions"], counts["castes"] = self._seed_religions(data.get("religions") or [])

            for section, model in SIMPLE_SECTIONS.items():
                if wanted(section):
                    counts[section] = self._seed_simple(model, data.get(section) or [])

        summary = ", ".join(f"{k}: +{v}" for k, v in counts.items())
        self.stdout.write(self.style.SUCCESS(f"Done. Created {summary or 'nothing (all sections skipped)'}."))

    def _seed_religions(self, religions_data):
        religions_created = castes_created = 0
        for r in religions_data:
            name = (r.get("name") if isinstance(r, dict) else r) or ""
            name = name.strip()
            if not name:
                continue
            religion, created = Religion.objects.get_or_create(name=name, defaults={"is_active": True})
            religions_created += int(created)

            castes = r.get("castes") if isinstance(r, dict) else []
            for c in castes or []:
                cname = (c if isinstance(c, str) else c.get("name", "")).strip()
                if not cname:
                    continue
                _, created = Caste.objects.get_or_create(
                    religion=religion, name=cname, defaults={"is_active": True}
                )
                castes_created += int(created)
        return religions_created, castes_created

    def _seed_simple(self, model, names):
        created_count = 0
        for raw in names:
            name = (raw if isinstance(raw, str) else raw.get("name", "")).strip()
            if not name:
                continue
            _, created = model.objects.get_or_create(name=name, defaults={"is_active": True})
            created_count += int(created)
        return created_count
