"""Helpers for master vs user-entered city on UserLocation (no master City auto-create)."""
from __future__ import annotations

import re

from master.models import City, District, State

_MULTI_SPACE = re.compile(r'\s+')
_PUNCT = re.compile(r'[^\w\s]', re.UNICODE)


def sanitize_city_name(raw) -> str:
    """Trim, collapse spaces, strip control/odd punctuation; max 150 chars."""
    if raw is None:
        return ''
    s = str(raw).strip()
    if not s:
        return ''
    s = _MULTI_SPACE.sub(' ', s)
    # Keep letters/digits/spaces and common name punctuation (.'-)
    cleaned = []
    for ch in s:
        if ch.isalnum() or ch in (" ", ".", "'", "-", '\u2019'):
            cleaned.append(ch)
        elif ch.isspace():
            cleaned.append(' ')
    s = _MULTI_SPACE.sub(' ', ''.join(cleaned)).strip()
    return s[:150]


def normalize_city_key(raw: str) -> str:
    """Lowercase + sanitize for equality / fuzzy compare."""
    s = sanitize_city_name(raw).lower()
    s = _PUNCT.sub('', s)
    return _MULTI_SPACE.sub(' ', s).strip()


def resolve_location_city_fields(attrs: dict) -> dict:
    """
    Mutate/return attrs with consistent city_id + city_name.

    - city_id set → verify (optionally vs district), force city_name from master.
    - city_id null/absent + city_name → store sanitized name, city_id None.
    Never creates master.City rows.
    """
    attrs = dict(attrs)
    ciid = attrs.get('city_id', _MISSING)
    raw_name = attrs.get('city_name', _MISSING)

    if ciid is not _MISSING and ciid is not None:
        city = City.objects.filter(pk=ciid, is_active=True).select_related('district').first()
        if not city:
            # Existence already validated on field; leave for hierarchy errors
            pass
        else:
            did = attrs.get('district_id')
            if did is not None and city.district_id != did:
                raise ValueError('city_id does not belong to district_id or is inactive.')
            attrs['city_id'] = city.pk
            attrs['city_name'] = city.name
            return attrs

    if raw_name is not _MISSING:
        name = sanitize_city_name(raw_name)
        attrs['city_name'] = name
        if ciid is _MISSING or ciid is None:
            attrs['city_id'] = None
        return attrs

    if ciid is not _MISSING and ciid is None:
        attrs['city_id'] = None
        if 'city_name' not in attrs:
            attrs['city_name'] = ''
    return attrs


_MISSING = object()


def enforce_location_hierarchy(attrs: dict, *, require_active: bool = True) -> None:
    """Raise serializers.ValidationError-compatible dict of field errors."""
    from rest_framework.serializers import ValidationError

    cid = attrs.get('country_id')
    sid = attrs.get('state_id')
    did = attrs.get('district_id')
    ciid = attrs.get('city_id')
    errors = {}

    active = {'is_active': True} if require_active else {}

    if sid is not None and cid is not None:
        if not State.objects.filter(pk=sid, country_id=cid, **active).exists():
            errors['state_id'] = 'state_id does not belong to country_id or is inactive.'
    if did is not None and sid is not None:
        if not District.objects.filter(pk=did, state_id=sid, **active).exists():
            errors['district_id'] = 'district_id does not belong to state_id or is inactive.'
    if ciid is not None and did is not None:
        if not City.objects.filter(pk=ciid, district_id=did, **active).exists():
            errors['city_id'] = 'city_id does not belong to district_id or is inactive.'

    if errors:
        raise ValidationError(errors)


def location_defaults_from_validated(vd: dict) -> dict:
    """Build UserLocation update defaults including nullable city_id / city_name."""
    defaults = {}
    if 'address' in vd:
        defaults['address'] = vd.get('address') or ''
    for k in ('country_id', 'state_id', 'district_id'):
        if k in vd and vd.get(k) is not None:
            defaults[k] = vd[k]
    if 'city_id' in vd:
        defaults['city_id'] = vd.get('city_id')  # may be None for manual city
    if 'city_name' in vd:
        defaults['city_name'] = vd.get('city_name') or ''
    return defaults
