"""Resolve and load the bundled bulk-upload Excel template."""
from __future__ import annotations

import io
from pathlib import Path

from django.conf import settings
from openpyxl import Workbook

from .parser import TEMPLATE_COLUMNS

TEMPLATE_FILENAME = "Matrimony_Bulk_Upload_Template.xlsx"

# Extra columns included in the curated workbook (optional on upload).
_TEMPLATE_OPTIONAL_COLUMNS = (
    "Father's Status (Alive / Late)",
    "Mother's Status (Alive / Late)",
)


def bulk_upload_template_candidates() -> list[Path]:
    module_dir = Path(__file__).resolve().parent
    base = Path(getattr(settings, "BASE_DIR", module_dir.parent.parent))
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
