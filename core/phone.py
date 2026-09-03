"""
Indian mobile phone normalization and display helpers.

Canonical storage/display format: +91XXXXXXXXXX (10 digits, first digit 6-9).
"""
from __future__ import annotations

import re

from rest_framework import serializers

# Indian mobile: 10 digits starting with 6-9
_INDIAN_MOBILE_RE = re.compile(r"^[6-9]\d{9}$")
# Non-phone placeholders (soft-delete, merge markers) — pass through on display
_PLACEHOLDER_RE = re.compile(r"^(del|x|merged|inactive)[-_]?", re.I)


def _digits_only(value: str) -> str:
    return "".join(c for c in (value or "") if c.isdigit())


def extract_indian_mobile_10(value: str | None) -> str | None:
    """
    Extract a 10-digit Indian mobile from arbitrary input.
    Returns None if not a valid Indian mobile pattern.
    """
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if _PLACEHOLDER_RE.match(raw):
        return None

    digits = _digits_only(raw)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    elif len(digits) == 13 and digits.startswith("091"):
        digits = digits[3:]
    elif len(digits) > 10:
        # Last 10 digits if prefixed with country code variants
        if digits.endswith(digits[-10:]) and _INDIAN_MOBILE_RE.match(digits[-10:]):
            digits = digits[-10:]

    if len(digits) != 10 or not _INDIAN_MOBILE_RE.match(digits):
        return None
    return digits


def normalize_phone_input(value: str | None, *, required: bool = True) -> str:
    """
    Normalize user input to E.164 +91XXXXXXXXXX.
    Auto-prefixes +91 when only 10 digits are provided.
    """
    if value is None or str(value).strip() == "":
        if required:
            raise serializers.ValidationError("Phone number is required.")
        return ""

    mobile_10 = extract_indian_mobile_10(value)
    if not mobile_10:
        raise serializers.ValidationError(
            "Invalid phone number. Enter a valid 10-digit Indian mobile number (starting with 6-9)."
        )
    return f"+91{mobile_10}"


def to_e164_display(stored: str | None) -> str:
    """
    Format stored phone for API/display as +91XXXXXXXXXX.
    Non-phone placeholders are returned unchanged.
    """
    if stored is None:
        return ""
    raw = str(stored).strip()
    if not raw:
        return ""
    if _PLACEHOLDER_RE.match(raw):
        return raw

    mobile_10 = extract_indian_mobile_10(raw)
    if mobile_10:
        return f"+91{mobile_10}"
    return raw


def to_display_spaced(stored: str | None) -> str:
    """Format as +91 XXXXXXXXXX for human-readable display."""
    e164 = to_e164_display(stored)
    if e164.startswith("+91") and len(e164) == 13:
        return f"+91 {e164[3:]}"
    return e164


def phone_variants(value: str | None) -> tuple[str, str, str]:
    """
    Return (+91XXXXXXXXXX, 91XXXXXXXXXX, XXXXXXXXXX) for uniqueness lookups.
    """
    e164 = normalize_phone_input(value, required=True)
    mobile_10 = e164[3:]
    return e164, f"91{mobile_10}", mobile_10


def mobile_10_from_stored(stored: str | None) -> str:
    """Extract bare 10-digit mobile from any stored variant."""
    mobile_10 = extract_indian_mobile_10(stored)
    return mobile_10 or ""


def personal_mobile_in_use(
    value: str | None,
    *,
    exclude_staff_profile_id: int | None = None,
    exclude_admin_user_id: int | None = None,
    exclude_member_user_id=None,
) -> str | None:
    """
    Return a user-facing error message if this personal mobile is already registered
    to another staff profile, admin login, or member user. Otherwise None.
    """
    from django.contrib.auth import get_user_model

    from admin_panel.auth.models import AdminUser
    from admin_panel.staff_mgmt.models import StaffProfile

    User = get_user_model()

    try:
        e164, prefixed, bare = phone_variants(value)
    except serializers.ValidationError:
        return None

    variants = {e164, prefixed, bare}

    staff_qs = StaffProfile.objects.filter(mobile__in=variants, is_deleted=False)
    if exclude_staff_profile_id:
        staff_qs = staff_qs.exclude(pk=exclude_staff_profile_id)
    if staff_qs.exists():
        return "This mobile number is already registered to another staff member."

    # Ignore AdminUsers whose linked staff profile was soft-deleted (defense for
    # legacy rows that still hold the real mobile after soft-delete).
    admin_qs = AdminUser.objects.filter(mobile__in=variants).exclude(
        staff_profile__is_deleted=True
    )
    if exclude_admin_user_id:
        admin_qs = admin_qs.exclude(pk=exclude_admin_user_id)
    if admin_qs.exists():
        return "This mobile number is already registered to another admin panel account."

    member_qs = User.objects.filter(mobile__in=variants)
    if exclude_member_user_id is not None:
        member_qs = member_qs.exclude(pk=exclude_member_user_id)
    if member_qs.exists():
        return "This mobile number is already registered to a member profile."

    return None
