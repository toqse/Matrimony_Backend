"""
Date of birth parsing and validation for matrimony registration.

Reusable age calculation and strict DD-MM-YYYY / DD/MM/YYYY parsing.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Final

__all__ = [
    "calculate_age",
    "parse_registration_dob_string",
    "validate_matrimony_registration_dob",
]

# Earliest realistic DOB for the platform (rejects placeholder years like 1900).
MIN_REALISTIC_DOB: Final[date] = date(1920, 1, 1)

_MAX_AGE: Final[int] = 80
_MIN_AGE_MALE: Final[int] = 21
_MIN_AGE_FEMALE: Final[int] = 18
_MIN_AGE_OTHER: Final[int] = 18

_RE_DD_MM_YYYY_DASH: Final[re.Pattern[str]] = re.compile(
    r"^(?P<d>\d{2})-(?P<m>\d{2})-(?P<y>\d{4})$"
)
_RE_DD_MM_YYYY_SLASH: Final[re.Pattern[str]] = re.compile(
    r"^(?P<d>\d{2})/(?P<m>\d{2})/(?P<y>\d{4})$"
)


def calculate_age(dob: date, *, today: date | None = None) -> int:
    """
    Completed years since DOB (birthday not yet reached this year => one less).
    """
    today = today or date.today()
    return today.year - dob.year - (
        (today.month, today.day) < (dob.month, dob.day)
    )


def parse_registration_dob_string(dob_str: str | None) -> date:
    """
    Parse DOB for registration: only DD-MM-YYYY or DD/MM/YYYY.

    Raises:
        ValueError: with a stable, API-safe message string.
    """
    if dob_str is None:
        raise ValueError("Date of birth is required.")
    s = str(dob_str).strip()
    if not s:
        raise ValueError("Date of birth is required.")

    has_dash = "-" in s
    has_slash = "/" in s
    if has_dash and has_slash:
        raise ValueError("Invalid date format. Use DD-MM-YYYY or DD/MM/YYYY")
    if not has_dash and not has_slash:
        raise ValueError("Invalid date format. Use DD-MM-YYYY or DD/MM/YYYY")

    if has_dash:
        if not _RE_DD_MM_YYYY_DASH.match(s):
            raise ValueError("Invalid date format. Use DD-MM-YYYY or DD/MM/YYYY")
        fmt = "%d-%m-%Y"
    else:
        if not _RE_DD_MM_YYYY_SLASH.match(s):
            raise ValueError("Invalid date format. Use DD-MM-YYYY or DD/MM/YYYY")
        fmt = "%d/%m/%Y"

    try:
        return datetime.strptime(s, fmt).date()
    except ValueError:
        raise ValueError(
            "Invalid date. Check day, month, and year (including leap years)."
        ) from None


def validate_matrimony_registration_dob(dob: date, gender: str, *, today: date | None = None) -> None:
    """
    Enforce future / realistic bounds and gender-based age rules for registration.

    Raises:
        ValueError: with a stable, API-safe message string.
    """
    today = today or date.today()
    g = (gender or "").strip().upper()

    if dob > today:
        raise ValueError("DOB cannot be in the future")

    if dob < MIN_REALISTIC_DOB:
        raise ValueError("Date of birth is not realistic.")

    age = calculate_age(dob, today=today)

    if age > _MAX_AGE:
        raise ValueError("Maximum age allowed is 80 years")

    if g == "M":
        if age < _MIN_AGE_MALE:
            raise ValueError("Minimum age for male is 21 years")
    elif g == "F":
        if age < _MIN_AGE_FEMALE:
            raise ValueError("Minimum age for female is 18 years")
    elif g == "O":
        if age < _MIN_AGE_OTHER:
            raise ValueError("Minimum age is 18 years")
