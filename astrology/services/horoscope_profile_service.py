"""
Horoscope support during profile creation.

This module is intentionally *future ready*: it only persists the birth inputs
required by the Horoscope Generator workflow (the Windows EXE bridge table,
``astrology.HoroscopeProfile``). It NEVER calculates a horoscope here. The
``HoroscopeProfile`` row is created with ``is_calculated=False`` and
``calculated_at=None`` so the generator can pick it up later.

Public API:
    - ``HoroscopeInputSerializer``: validates the horoscope-related fields added
      to the Profile Create API.
    - ``validate_horoscope_input``: convenience wrapper around the serializer.
    - ``create_horoscope_profile``: create/populate the bridge record.
    - ``apply_profile_creation_horoscope``: persist birth inputs on the member's
      ``UserProfile`` and create the bridge record when ``has_horoscope`` is set.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

from rest_framework import serializers

logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = 5.5

# Cleared when birth inputs change so GET horoscope/me is not_generated and
# the Windows EXE can rewrite the chart. Do not include EXE input fields.
EXE_OUTPUT_RESET: dict[str, Any] = {
    'pr_rasi': '',
    'pr_amsa': '',
    'pr_bhav': '',
    'pr_star': None,
    'pr_pada': None,
    'pr_dasabalance': None,
    'lagnam': '',
    'rasi_sign': '',
    'star_name': '',
    'nakshatra_pada': None,
    'gana': '',
    'yoni': '',
    'rajju': '',
}


def _float_close(left: Any, right: Any) -> bool:
    if left is None and right is None:
        return True
    if left is None or right is None:
        return False
    try:
        return abs(float(left) - float(right)) < 1e-4
    except (TypeError, ValueError):
        return False


def horoscope_chart_inputs_changed(
    hp,
    *,
    dob: date | None,
    birth_time: time | None,
    birth_latitude: float | None,
    birth_longitude: float | None,
    birth_timezone: float | None,
) -> bool:
    """True when EXE input fields that affect the chart differ from ``hp``."""
    tz = birth_timezone if birth_timezone is not None else DEFAULT_TIMEZONE
    return (
        hp.pr_dob != dob
        or hp.pr_tob != birth_time
        or not _float_close(hp.pr_lat, birth_latitude)
        or not _float_close(hp.pr_lon, birth_longitude)
        or not _float_close(hp.pr_tz, tz)
    )

# Frontend / legacy field names -> canonical serializer keys.
HOROSCOPE_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    'birth_place': ('place_of_birth', 'placeOfBirth', 'birthPlace', 'pob'),
    'birth_time': ('time_of_birth', 'timeOfBirth', 'birthTime', 'tob'),
    'birth_latitude': ('latitude', 'lat', 'birthLatitude'),
    'birth_longitude': ('longitude', 'lon', 'lng', 'birthLongitude'),
    'birth_timezone': ('timezone', 'time_zone', 'tz', 'birthTimezone'),
    'has_horoscope': ('hasHoroscope', 'has_horoscope_details'),
}


def normalize_horoscope_payload(data: dict[str, Any]) -> dict[str, Any]:
    """
    Map frontend alias keys to canonical horoscope field names.

    Canonical keys in the payload take precedence over aliases.
    """
    if not isinstance(data, dict):
        return data

    normalized = dict(data)
    for canonical, aliases in HOROSCOPE_FIELD_ALIASES.items():
        if canonical in normalized and normalized[canonical] not in (None, ''):
            continue
        for alias in aliases:
            if alias not in normalized:
                continue
            value = normalized[alias]
            if value is None or value == '':
                continue
            normalized[canonical] = value
            break
    return normalized


def parse_timezone_to_offset(value: Any) -> float | None:
    """
    Convert timezone input to UTC offset hours for ``pr_tz``.

    Accepts numeric offsets (5.5), IANA names (Asia/Kolkata), or offset
    strings (+05:30, UTC+5:30). Returns None when unparseable.
    """
    if value is None or value == '':
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    try:
        return float(text)
    except (TypeError, ValueError):
        pass

    # Offset strings: +05:30, UTC+5:30, GMT-4:00
    offset_match = re.match(
        r'^(?:UTC|GMT)?\s*([+-])\s*(\d{1,2})(?::(\d{2}))?$',
        text,
        re.IGNORECASE,
    )
    if offset_match:
        sign = 1 if offset_match.group(1) == '+' else -1
        hours = int(offset_match.group(2))
        minutes = int(offset_match.group(3) or 0)
        return sign * (hours + minutes / 60.0)

    # IANA timezone name
    try:
        tz = ZoneInfo(text)
        offset = tz.utcoffset(datetime(2020, 1, 1, 12, 0, tzinfo=timezone.utc))
        if offset is not None:
            return offset.total_seconds() / 3600.0
    except Exception:
        pass

    return None


def _coords_are_usable(lat: float | None, lon: float | None) -> bool:
    """True when both coordinates are present and not a placeholder (0, 0)."""
    if lat is None or lon is None:
        return False
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    if lat_f == 0 and lon_f == 0:
        return False
    return True


def _resolve_birth_coordinates(
    birth_place: str | None,
    birth_latitude: float | None,
    birth_longitude: float | None,
) -> tuple[float | None, float | None]:
    """
  Use request coordinates when valid; otherwise resolve from birth_place.

  Frontend often sends birth_latitude/birth_longitude as 0 before geocoding
  completes — those placeholders are treated as missing.
    """
    if _coords_are_usable(birth_latitude, birth_longitude):
        return float(birth_latitude), float(birth_longitude)

    place = (birth_place or '').strip()
    if not place:
        return None, None

    from astrology.services.horoscope_service import _fallback_lat_lon

    resolved = _fallback_lat_lon(place)
    if resolved:
        logger.info(
            'Resolved birth coordinates from place=%r -> lat=%r lon=%r',
            place,
            resolved[0],
            resolved[1],
        )
        return resolved[0], resolved[1]

    logger.warning(
        'Could not resolve birth coordinates for place=%r; lat/lon remain unset',
        place,
    )
    return None, None


class HoroscopeInputSerializer(serializers.Serializer):
    """
    Validates the horoscope-related fields accepted by the Profile Create API.

    When ``has_horoscope`` is true, ``date_of_birth`` (supplied via serializer
    context, since the core profile payload owns it), ``birth_time`` and
    ``birth_place`` are required.
    """

    has_horoscope = serializers.BooleanField(required=False, default=False)
    birth_time = serializers.TimeField(
        required=False,
        allow_null=True,
        input_formats=['%H:%M:%S', '%H:%M'],
    )
    birth_place = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=255
    )
    birth_latitude = serializers.FloatField(
        required=False, allow_null=True, min_value=-90, max_value=90
    )
    birth_longitude = serializers.FloatField(
        required=False, allow_null=True, min_value=-180, max_value=180
    )
    birth_timezone = serializers.FloatField(
        required=False, allow_null=True, min_value=-12, max_value=14
    )

    def to_internal_value(self, data):
        if isinstance(data, dict):
            normalized = normalize_horoscope_payload(data)
            tz_raw = normalized.get('birth_timezone')
            if tz_raw is not None and tz_raw != '':
                parsed_tz = parse_timezone_to_offset(tz_raw)
                if parsed_tz is not None:
                    normalized['birth_timezone'] = parsed_tz
                elif isinstance(tz_raw, str):
                    # Unparseable string — drop so FloatField does not reject IANA name.
                    normalized.pop('birth_timezone', None)
            data = normalized
        return super().to_internal_value(data)

    def validate(self, attrs):
        raw = getattr(self, 'initial_data', {}) or {}
        normalized_raw = normalize_horoscope_payload(raw) if isinstance(raw, dict) else {}
        logger.info(
            "HoroscopeInputSerializer raw vs parsed | "
            "Received Latitude raw=%r parsed=%r | "
            "Received Longitude raw=%r parsed=%r | "
            "Received Timezone raw=%r parsed=%r | "
            "Received Place raw=%r parsed=%r | has_horoscope=%r",
            normalized_raw.get('birth_latitude'), attrs.get('birth_latitude'),
            normalized_raw.get('birth_longitude'), attrs.get('birth_longitude'),
            normalized_raw.get('birth_timezone'), attrs.get('birth_timezone'),
            normalized_raw.get('birth_place'), attrs.get('birth_place'),
            attrs.get('has_horoscope'),
        )
        if not attrs.get('has_horoscope'):
            return attrs

        errors: dict[str, str] = {}
        if not self.context.get('date_of_birth'):
            errors['date_of_birth'] = (
                'Date of birth is required when has_horoscope is true.'
            )
        if not attrs.get('birth_time'):
            errors['birth_time'] = (
                'Birth time is required when has_horoscope is true.'
            )
        if not (attrs.get('birth_place') or '').strip():
            errors['birth_place'] = (
                'Birth place is required when has_horoscope is true.'
            )
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


def validate_horoscope_input(
    data: dict[str, Any], *, date_of_birth: Any = None
) -> dict[str, Any]:
    """
    Validate and normalize horoscope fields from a request payload.

    Raises ``rest_framework.serializers.ValidationError`` on invalid input.
    Returns the serializer's ``validated_data`` (with python ``time``/``float``
    values).
    """
    serializer = HoroscopeInputSerializer(
        data=data, context={'date_of_birth': date_of_birth}
    )
    serializer.is_valid(raise_exception=True)
    return dict(serializer.validated_data)


def create_horoscope_profile(
    *,
    user,
    name: str | None = None,
    dob: date | None = None,
    birth_time: time | None = None,
    birth_latitude: float | None = None,
    birth_longitude: float | None = None,
    birth_timezone: float | None = None,
):
    """
    Create or populate the ``horoscope_profile`` bridge record for ``user``.

    This does NOT calculate the horoscope. It only stores the EXE input fields
    (``pr_name``, ``pr_dob``, ``pr_tob``, ``pr_lat``, ``pr_lon``, ``pr_tz``) and
    resets the calculation status (``is_calculated=False``, ``calculated_at=None``)
    so the Horoscope Generator workflow can process it later.

    When an existing row's chart inputs change, EXE output and derived fields
    are cleared so ``is_exe_done()`` is false until the generator rewrites them.

    Returns the ``HoroscopeProfile`` instance.
    """
    from astrology.models import HoroscopeProfile

    tz = birth_timezone if birth_timezone is not None else DEFAULT_TIMEZONE
    resolved_dob = dob if dob is not None else getattr(user, 'dob', None)
    resolved_name = (name if name is not None else getattr(user, 'name', '')) or ''
    logger.info(
        "create_horoscope_profile user=%s | Received Latitude=%r | "
        "Received Longitude=%r | Received Timezone=%r (stored pr_tz=%r)",
        getattr(user, "pk", None),
        birth_latitude,
        birth_longitude,
        birth_timezone,
        tz,
    )
    existing = HoroscopeProfile.objects.filter(user=user).first()
    defaults: dict[str, Any] = {
        'pr_name': resolved_name,
        'pr_dob': resolved_dob,
        'pr_tob': birth_time,
        'pr_lat': birth_latitude,
        'pr_lon': birth_longitude,
        'pr_tz': tz,
        'is_calculated': False,
        'calculated_at': None,
    }
    if existing is not None and horoscope_chart_inputs_changed(
        existing,
        dob=resolved_dob,
        birth_time=birth_time,
        birth_latitude=birth_latitude,
        birth_longitude=birth_longitude,
        birth_timezone=tz,
    ):
        defaults.update(EXE_OUTPUT_RESET)

    horoscope_profile, _ = HoroscopeProfile.objects.update_or_create(
        user=user,
        defaults=defaults,
    )
    return horoscope_profile


def apply_profile_creation_horoscope(
    *,
    user,
    profile,
    horoscope_input: dict[str, Any],
    name: str | None = None,
    dob: date | None = None,
):
    """
    Persist birth inputs onto the member ``UserProfile`` and, when
    ``has_horoscope`` is set, create the ``horoscope_profile`` bridge record.

    ``horoscope_input`` is the validated data from ``HoroscopeInputSerializer``.
    Returns the created ``HoroscopeProfile`` or ``None`` when ``has_horoscope``
    is false.
    """
    has_horoscope = bool(horoscope_input.get('has_horoscope'))
    profile.has_horoscope = has_horoscope

    birth_place = horoscope_input.get('birth_place')
    resolved_lat, resolved_lon = _resolve_birth_coordinates(
        birth_place,
        horoscope_input.get('birth_latitude'),
        horoscope_input.get('birth_longitude'),
    )
    birth_timezone = horoscope_input.get('birth_timezone')

    logger.info(
        'apply_profile_creation_horoscope user=%s | '
        'Received Latitude=%r | Received Longitude=%r | Received Timezone=%r | '
        'resolved_lat=%r resolved_lon=%r',
        getattr(user, 'pk', None),
        horoscope_input.get('birth_latitude'),
        horoscope_input.get('birth_longitude'),
        birth_timezone,
        resolved_lat,
        resolved_lon,
    )

    update_fields = ['has_horoscope', 'updated_at']
    if horoscope_input.get('birth_time') is not None:
        profile.time_of_birth = horoscope_input['birth_time']
        update_fields.append('time_of_birth')
    if birth_place is not None:
        profile.place_of_birth = birth_place or ''
        update_fields.append('place_of_birth')
    if resolved_lat is not None:
        profile.birth_latitude = resolved_lat
        update_fields.append('birth_latitude')
    if resolved_lon is not None:
        profile.birth_longitude = resolved_lon
        update_fields.append('birth_longitude')
    if birth_timezone is not None:
        profile.birth_timezone = birth_timezone
        update_fields.append('birth_timezone')

    if profile.pk:
        profile.save(update_fields=update_fields)
    else:
        profile.save()

    if not has_horoscope:
        return None

    return create_horoscope_profile(
        user=user,
        name=name,
        dob=dob,
        birth_time=horoscope_input.get('birth_time'),
        birth_latitude=resolved_lat,
        birth_longitude=resolved_lon,
        birth_timezone=birth_timezone,
    )


# Top-level keys (canonical + aliases) that signal horoscope intent in an
# edit payload. Mirrors HOROSCOPE_FIELD_ALIASES plus the nested section key.
_HOROSCOPE_EDIT_KEYS: frozenset[str] = frozenset(
    {'has_horoscope', 'horoscope_details'}
    | set(HOROSCOPE_FIELD_ALIASES.keys())
    | {alias for aliases in HOROSCOPE_FIELD_ALIASES.values() for alias in aliases}
)

_HOROSCOPE_BIRTH_FIELDS = (
    'birth_time',
    'birth_place',
    'birth_latitude',
    'birth_longitude',
    'birth_timezone',
)


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ('true', '1', 'yes', 'on')
    return bool(value)


def apply_profile_edit_horoscope(user, profile, data: dict[str, Any]):
    """
    Apply horoscope birth-input edits coming from an admin/staff/branch PATCH.

    Reuses the same safe path as profile creation: validates with
    ``HoroscopeInputSerializer`` and persists via ``apply_profile_creation_horoscope``
    (which resets ``HoroscopeProfile.is_calculated`` to False and clears stale EXE
    output fields when birth inputs change). The member's current ``dob`` is used
    for validation.

    Accepts a nested ``horoscope_details`` object and/or top-level alias keys
    (e.g. ``time_of_birth``, ``place_of_birth``, ``latitude``). Returns the
    ``HoroscopeProfile`` instance, or ``None`` when no horoscope data is applied.
    """
    if not isinstance(data, dict):
        return None

    section = data.get('horoscope_details')
    if not (any(key in data for key in _HOROSCOPE_EDIT_KEYS) or isinstance(section, dict)):
        return None

    payload: dict[str, Any] = {}
    if isinstance(section, dict):
        payload.update(section)
    for key in _HOROSCOPE_EDIT_KEYS:
        if key == 'horoscope_details':
            continue
        if key in data and data[key] not in (None, ''):
            payload[key] = data[key]

    normalized = normalize_horoscope_payload(payload)
    has_birth_fields = any(
        normalized.get(field) not in (None, '') for field in _HOROSCOPE_BIRTH_FIELDS
    )

    has_flag = 'has_horoscope' in normalized
    if not has_birth_fields and not has_flag:
        return None

    # Plain flag toggle (no birth inputs supplied): preserve legacy behavior of
    # only flipping the availability badge without re-validating birth details.
    if not has_birth_fields:
        profile.has_horoscope = _coerce_bool(normalized.get('has_horoscope'))
        profile.save(update_fields=['has_horoscope', 'updated_at'])
        return None

    # Birth details supplied: default has_horoscope to True when omitted.
    if 'has_horoscope' not in normalized:
        normalized['has_horoscope'] = True

    dob = getattr(user, 'dob', None)
    horoscope_input = validate_horoscope_input(
        normalized,
        date_of_birth=dob.isoformat() if dob else None,
    )
    return apply_profile_creation_horoscope(
        user=user,
        profile=profile,
        horoscope_input=horoscope_input,
        name=getattr(user, 'name', None),
        dob=dob,
    )
