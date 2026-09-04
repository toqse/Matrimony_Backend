"""
Date of birth parsing and validation for matrimony registration.

Reusable age calculation and strict DD-MM-YYYY / DD/MM/YYYY parsing.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Final

__all__ = [
    "PROFILE_AGE_ERROR",
    "calculate_age",
    "parse_registration_dob_string",
    "validate_matrimony_registration_dob",
    "validate_profile_age",
]

# Earliest realistic DOB for the platform (rejects placeholder years like 1900).
MIN_REALISTIC_DOB: Final[date] = date(1920, 1, 1)

# Completed years: 18 <= age < 80 (18 through 79 inclusive).
_MIN_AGE_INCLUSIVE: Final[int] = 18
_MAX_AGE_EXCLUSIVE: Final[int] = 80
PROFILE_AGE_ERROR: Final[str] = "Age must be at least 18 and less than 80 years"

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


def validate_profile_age(dob: date, *, today: date | None = None) -> None:
    """
    Enforce future / realistic bounds and 18 <= age < 80 for member profiles.

    Raises:
        ValueError: with a stable, API-safe message string.
    """
    today = today or date.today()

    if dob > today:
        raise ValueError("DOB cannot be in the future")

    if dob < MIN_REALISTIC_DOB:
        raise ValueError("Date of birth is not realistic.")

    age = calculate_age(dob, today=today)
    if not (_MIN_AGE_INCLUSIVE <= age < _MAX_AGE_EXCLUSIVE):
        raise ValueError(PROFILE_AGE_ERROR)


def validate_matrimony_registration_dob(
    dob: date, gender: str | None = None, *, today: date | None = None
) -> None:
    """
    Registration DOB rules. Gender is accepted for call-site compatibility;
    age limits are the same for all genders (18 <= age < 80).
    """
    validate_profile_age(dob, today=today)
