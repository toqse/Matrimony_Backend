"""Legacy matrimony CSV migration helpers.

Public entry points:
- LegacyImporter: row-level orchestrator (build_payload + save).
- read_legacy_csv_text / parse_legacy_csv: CSV decoding and row iteration.
- EXPECTED_COLUMNS: header layout the importer enforces on the legacy export.
"""
from .importer import LegacyImporter
from .parser import EXPECTED_COLUMNS, parse_legacy_csv, read_legacy_csv_text

__all__ = [
    "EXPECTED_COLUMNS",
    "LegacyImporter",
    "parse_legacy_csv",
    "read_legacy_csv_text",
]
