"""Resolve and load bundled bulk-upload templates."""
from __future__ import annotations

import csv
import io
from pathlib import Path

from django.conf import settings
from openpyxl import Workbook

from .parser import TEMPLATE_COLUMNS

TEMPLATE_FILENAME = "Matrimony_Bulk_Upload_Template.xlsx"
LEGACY_IMPORT_TEMPLATE_FILENAME = "matrimony_import_template_with_reg_no.csv"
_LEGACY_IMPORT_TEMPLATE_ALIASES = (
    LEGACY_IMPORT_TEMPLATE_FILENAME,
    "matrimony_import_template.csv",
)

# Extra columns included in the curated modern workbook (optional on upload).
_TEMPLATE_OPTIONAL_COLUMNS = (
    "Father's Status (Alive / Late)",
    "Mother's Status (Alive / Late)",
)


def _module_dir() -> Path:
    return Path(__file__).resolve().parent


def _base_dir() -> Path:
    return Path(getattr(settings, "BASE_DIR", _module_dir().parent.parent))


def legacy_import_template_candidates() -> list[Path]:
    module_dir = _module_dir()
    base = _base_dir()
    paths: list[Path] = [
        base.parent / LEGACY_IMPORT_TEMPLATE_FILENAME,
        base / "profiles" / "legacy_import" / "legacy_bulk_upload_template.csv",
    ]
    for name in _LEGACY_IMPORT_TEMPLATE_ALIASES:
        paths.append(base.parent / name)
        paths.append(module_dir / "templates" / name)
    # Keep order stable while dropping duplicates from alias overlap.
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        unique.append(path)
    return unique


def resolve_legacy_import_template_path() -> Path | None:
    for path in legacy_import_template_candidates():
        if path.is_file():
            return path
    return None


def _read_legacy_template_text() -> str:
    path = resolve_legacy_import_template_path()
    if path is None:
        raise FileNotFoundError("Legacy bulk upload template CSV not found")
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def get_legacy_template_columns() -> list[str]:
    """Return the header row from the bundled legacy import template."""
    text = _read_legacy_template_text()
    reader = csv.reader(io.StringIO(text))
    try:
        row = next(reader)
    except StopIteration:
        return []
    return [cell.strip() for cell in row if cell.strip()]


def load_legacy_import_template_csv() -> tuple[bytes, str]:
    """Return (file_bytes, filename) for the legacy matrimony import CSV."""
    text = _read_legacy_template_text()
    return text.encode("utf-8"), LEGACY_IMPORT_TEMPLATE_FILENAME


def generate_legacy_import_template_xlsx() -> bytes:
    """Build an XLSX workbook from the legacy template header + sample rows."""
    text = _read_legacy_template_text()
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return out.read()


def bulk_upload_template_candidates() -> list[Path]:
    module_dir = _module_dir()
    base = _base_dir()
    return [
        module_dir / TEMPLATE_FILENAME,
        base / TEMPLATE_FILENAME,
        base.parent / TEMPLATE_FILENAME,
        module_dir / "templates" / TEMPLATE_FILENAME,
    ]


def resolve_bulk_upload_template_path() -> Path | None:
    for path in bulk_upload_template_candidates():
        if path.is_file():
            return path
    return None


def _generate_fallback_xlsx_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append([*TEMPLATE_COLUMNS, *_TEMPLATE_OPTIONAL_COLUMNS])
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return out.read()


def load_bulk_upload_template_xlsx() -> tuple[bytes, str]:
    """Return (file_bytes, filename). Never raises — falls back to generated workbook."""
    path = resolve_bulk_upload_template_path()
    if path is not None:
        return path.read_bytes(), TEMPLATE_FILENAME
    return _generate_fallback_xlsx_bytes(), TEMPLATE_FILENAME
