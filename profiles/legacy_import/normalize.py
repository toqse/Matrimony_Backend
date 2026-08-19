"""Cell-level normalization for legacy matrimony rows.

The old export uses noisy free-text values (`No Info`, suffixed phone numbers,
slashed dates, occasional negative counts). These helpers convert those into
clean Python primitives the importer can safely persist.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Optional

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

NO_INFO = {"", "no info", "n/a", "na", "nil", "none", "null", "-"}
PARENT_NAME_PLACEHOLDERS = {"FATHER", "MOTHER"}

TOB_HEADER_ALIASES = (
    "time of birth",
    "time_of_birth",
    "tob",
    "birth time",
)

TOB_PARSE_FORMATS = ("%H:%M:%S", "%H:%M")


def norm_header(value: object) -> str:
    """Lowercase + collapse whitespace for header matching."""
    return " ".join((str(value) if value is not None else "").strip().split()).lower()


def clean(value: object, *, zero_is_blank: bool = False) -> str:
    """Strip noise from a CSV cell.

    `No Info` style placeholders collapse to ''. When `zero_is_blank` is set,
    literal `0` / `0.0` is also treated as missing data (used for height,
    sibling counts, etc., where 0 carries no meaning in the legacy data).
    """
    text = " ".join((str(value) if value is not None else "").strip().split())
    if text.lower() in NO_INFO:
        return ""
    if zero_is_blank and text in {"0", "0.0", "-0", "-1"}:
        return ""
    return text


def parse_phone(value: object) -> Optional[str]:
    """Pull the first plausible 10-digit Indian mobile out of a noisy cell.

    Handles trailing 'W', extra suffixed numbers, leading 91/0, and rejects
    landlines (anything not starting with 6/7/8/9 after normalization).
    """
    text = str(value or "")
    for group in re.findall(r"\d{10,12}", text):
        digits = group
        if len(digits) == 12 and digits.startswith("91"):
            digits = digits[-10:]
        if len(digits) == 11 and digits.startswith("0"):
            digits = digits[-10:]
        if len(digits) == 10 and digits[0] in "6789":
            return digits
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) >= 10:
        candidate = digits[:10]
        if candidate[0] in "6789":
            return candidate
    return None


def parse_dob(value: object) -> Optional[date]:
    """Parse legacy `DD/MM/YYYY` dates; also accept `DD-MM-YYYY` and ISO."""
    text = clean(value)
    if not text:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_tob(value: object) -> Optional[time]:
    """Parse legacy birth-time cells (HH:MM or HH:MM:SS). Invalid input -> None."""
    text = clean(value)
    if not text:
        return None
    for fmt in TOB_PARSE_FORMATS:
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def time_of_birth_from_row(row: dict) -> Optional[time]:
    """Return the first non-empty Time of Birth alias from a parsed CSV row."""
    for key in TOB_HEADER_ALIASES:
        parsed = parse_tob(row.get(key))
        if parsed is not None:
            return parsed
    return None


def parse_int(value: object, *, min_value: int = 0) -> int:
    """Coerce to non-negative int; treat 'No Info'/blank/negative as 0."""
    text = clean(value, zero_is_blank=True)
    if not text:
        return 0
    try:
        number = int(Decimal(text))
    except (InvalidOperation, ValueError):
        return 0
    return max(min_value, number)


def parse_decimal(value: object) -> Optional[Decimal]:
    """Coerce to Decimal or None when the cell is empty/non-numeric."""
    text = clean(value, zero_is_blank=True)
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def parse_email(value: object) -> Optional[str]:
    """Lowercased valid email or None. Silent on bad input (legacy is dirty)."""
    text = clean(value)
    if not text:
        return None
    try:
        validate_email(text)
    except ValidationError:
        return None
    return text.lower()


def parse_bool(value: object) -> bool:
    """Yes/No/True/False/1/0 → bool. Defaults to False on noise."""
    text = clean(value).lower()
    if text in {"yes", "y", "true", "1"}:
        return True
    return False


def parse_gender(value: object) -> str:
    """Return 'M', 'F', 'O' or '' for invalid input."""
    text = clean(value).upper()
    if text in {"M", "MALE", "MAN", "BOY"}:
        return "M"
    if text in {"F", "FEMALE", "WOMAN", "GIRL"}:
        return "F"
    if text in {"O", "OTHER", "OTHERS"}:
        return "O"
    return ""


def parent_name(value: object) -> str:
    """Drop placeholder labels like 'FATHER'/'MOTHER' that mean 'unknown'."""
    text = clean(value)
    if text.upper() in PARENT_NAME_PLACEHOLDERS:
        return ""
    return text
