"""Resolve Place of Birth text to lat/lng during legacy bulk import.

Validate never calls this. Import uses an instance-level cache so duplicate
place strings in one CSV chunk hit OpenStreetMap at most once. Nominatim is
throttled to ~1 request/second. Failures leave coordinates unset.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from .normalize import clean

logger = logging.getLogger(__name__)

NOMINATIM_DELAY_SECONDS = 1.0

POB_HEADER_ALIASES = (
    "place of birth",
    "place_of_birth",
    "pob",
    "birth place",
)


def place_of_birth_from_row(row: dict) -> str:
    """Return the first non-empty Place of Birth alias from a parsed CSV row."""
    for key in POB_HEADER_ALIASES:
        value = clean(row.get(key))
        if value:
            return value[:255]
    return ""


class PlaceGeocoder:
    """Cache + throttle wrapper around the existing Nominatim helpers."""

    def __init__(self, *, nominatim_delay_seconds: float = NOMINATIM_DELAY_SECONDS):
        self._cache: dict[str, Optional[tuple[float, float]]] = {}
        self._last_nominatim_at: float = 0.0
        self._nominatim_delay_seconds = nominatim_delay_seconds

    def resolve(self, place: str) -> Optional[tuple[float, float]]:
        text = clean(place)
        if not text:
            return None

        cache_key = text.casefold()
        if cache_key in self._cache:
            return self._cache[cache_key]

        from astrology.services.horoscope_service import _fallback_lat_lon, _geocode_place

        fallback = _fallback_lat_lon(text)
        if fallback is not None:
            self._cache[cache_key] = fallback
            return fallback

        coords = self._nominatim(text, _geocode_place)
        self._cache[cache_key] = coords
        return coords

    def _nominatim(self, text: str, geocode_fn) -> Optional[tuple[float, float]]:
        delay = self._nominatim_delay_seconds
        if delay > 0 and self._last_nominatim_at:
            wait = delay - (time.monotonic() - self._last_nominatim_at)
            if wait > 0:
                time.sleep(wait)
        try:
            coords = geocode_fn(text)
            self._last_nominatim_at = time.monotonic()
            if not coords:
                return None
            lat, lon = float(coords[0]), float(coords[1])
            return lat, lon
        except Exception as exc:  # noqa: BLE001 - fail-soft per row
            self._last_nominatim_at = time.monotonic()
            logger.warning("legacy bulk geocode failed for place=%r: %s", text, exc)
            return None
