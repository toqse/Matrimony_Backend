"""Bridge from the admin Bulk Upload UI to profiles.legacy_import.

The legacy matrimony export uses different column names, dirty data, and
extra horoscope fields that the strict bulk-upload template rejects. Rather
than relax the modern validators (and risk accepting bad new data), this
module reuses LegacyImporter to validate / import legacy CSV bytes that
were uploaded through the same admin UI.

Cache layout (keyed by validation_token):
    {
        "admin_user_id": int,
        "job_id": int,
        "csv_text": str,            # raw decoded CSV the user uploaded
        "legacy": True,             # marker so the import view picks this path
        "errors": list[dict],       # row-level validation errors
        "valid_rows": int,
        "error_rows": int,
        "total_rows": int,
    }
"""
from __future__ import annotations

import io
import secrets
from typing import Any

from django.core.cache import cache
from django.db import transaction

from profiles.legacy_import import LegacyImporter, parse_legacy_csv
from profiles.legacy_import.normalize import clean

LEGACY_CACHE_PREFIX = "bulk_upload:legacy:v1:"
LEGACY_CACHE_TTL = 60 * 60  # 1 hour, same as the modern path
LEGACY_ASYNC_ROW_THRESHOLD = 50


def cache_legacy_payload(payload: dict[str, Any]) -> str:
    token = secrets.token_urlsafe(32)
    cache.set(LEGACY_CACHE_PREFIX + token, payload, LEGACY_CACHE_TTL)
    return token


def get_cached_legacy_payload(token: str) -> dict[str, Any] | None:
    return cache.get(LEGACY_CACHE_PREFIX + token)


def delete_cached_legacy_payload(token: str) -> None:
    cache.delete(LEGACY_CACHE_PREFIX + token)


def _row_error(row_num: int, reason: str) -> dict[str, Any]:
    return {"row": row_num, "field": "non_field_error", "message": reason}


def validate_legacy_csv_text(csv_text: str) -> dict[str, Any]:
    """Run the legacy importer in dry-run mode against decoded CSV text.

    Returns the same shape the strict path returns so the UI can render
    errors/total/valid/error counts identically.
    """
    importer = LegacyImporter(dry_run=True)
    try:
        _, reader = parse_legacy_csv(csv_text)
    except ValueError as exc:
        return {
            "total_rows": 0,
            "valid_rows": 0,
            "error_rows": 0,
            "errors": [{"row": 1, "field": "headers", "message": str(exc)}],
        }

    total_rows = 0
    valid_rows = 0
    error_rows = 0
    errors: list[dict[str, Any]] = []

    for index, row in enumerate(reader, start=2):
        if not any((v or "").strip() for v in row.values()):
            continue
        total_rows += 1
        payload, reason = importer.build_payload(index, row)
        if payload is None:
            error_rows += 1
            errors.append(_row_error(index, reason))
            continue
        valid_rows += 1

    return {
        "total_rows": total_rows,
        "valid_rows": valid_rows,
        "error_rows": error_rows,
        "errors": errors,
    }


def import_legacy_csv_text(
    csv_text: str,
    *,
    branch=None,
) -> dict[str, Any]:
    """Run the real legacy import against decoded CSV text.

    Returns {"imported": int, "failed": list[{"row","field","message"}]}.
    """
    importer = LegacyImporter(branch=branch)
    _, reader = parse_legacy_csv(csv_text)

    imported = 0
    failed: list[dict[str, Any]] = []

    for index, row in enumerate(reader, start=2):
        if not any((v or "").strip() for v in row.values()):
            continue
        payload, reason = importer.build_payload(index, row)
        if payload is None:
            failed.append(_row_error(index, reason))
            continue
        try:
            with transaction.atomic():
                importer.save(payload)
            imported += 1
        except Exception as exc:  # noqa: BLE001 - report and continue per row
            failed.append({"row": index, "field": "non_field_error", "message": str(exc)})

    return {"imported": imported, "failed": failed}


def decode_uploaded_csv(uploaded_file) -> str:
    """Return CSV text for an uploaded legacy file. XLSX is converted upstream."""
    name = (getattr(uploaded_file, "name", "") or "").lower()
    data = uploaded_file.read()
    if name.endswith(".xlsx"):
        # Avoid a circular import: parser already knows how to convert XLSX.
        from .parser import _xlsx_to_csv_text

        text, _ = _xlsx_to_csv_text(data)
        return text
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


__all__ = [
    "LEGACY_ASYNC_ROW_THRESHOLD",
    "cache_legacy_payload",
    "clean",
    "decode_uploaded_csv",
    "delete_cached_legacy_payload",
    "get_cached_legacy_payload",
    "import_legacy_csv_text",
    "validate_legacy_csv_text",
]
