"""CSV decoding and header validation for the legacy matrimony export."""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Iterator

from .normalize import norm_header

EXPECTED_COLUMNS = [
    "name",
    "phone number",
    "email",
    "date of birth",
    "gender",
    "partner preference",
    "country",
    "state",
    "district",
    "city",
    "address",
    "religion",
    "caste",
    "mother toungue",
    "marital status",
    "has children",
    "number of children",
    "height (cm)",
    "weight (kg)",
    "complexion",
    "highest education",
    "education subject",
    "employment",
    "occupation",
    "annual income",
    "about me",
    "family type",
    "father's name",
    "father's occupation",
    "mother's name",
    "mother's occupation",
    "family status",
    "number of brothers",
    "number of married brothers",
    "number of sisters",
    "number of married sisters",
    "about my family",
    "horochart",
    "amsachart",
    "bhavchart",
    "sishta_dur",
    "star",
    "padam",
]


def read_legacy_csv_text(path: Path) -> str:
    """Read the source file, falling back to latin-1 when the export contains
    bytes that aren't valid UTF-8 (the legacy file has 0xD1 etc. mid-row).
    """
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def parse_legacy_csv(text: str) -> tuple[list[str], Iterator[dict[str, str]]]:
    """Return normalized headers + an iterator of dict rows.

    Raises ValueError if the headers do not begin with EXPECTED_COLUMNS so that
    we don't silently misalign columns from a different export.
    """
    reader = csv.DictReader(io.StringIO(text))
    headers = [norm_header(h) for h in (reader.fieldnames or [])]
    if headers[: len(EXPECTED_COLUMNS)] != EXPECTED_COLUMNS:
        raise ValueError("CSV headers do not match the expected legacy export format.")
    reader.fieldnames = headers
    return headers, reader
