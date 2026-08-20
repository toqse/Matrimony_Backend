"""Shared response envelopes for horoscope fetch endpoints."""

from __future__ import annotations

from typing import Any, Type

from rest_framework import serializers


def horoscope_not_found_response() -> dict[str, Any]:
    return {
        'success': False,
        'is_horoscope_generated': False,
        'error': {
            'code': 404,
            'message': 'Horoscope profile not found. Please update birth details first.',
        },
    }


def horoscope_not_generated_response() -> dict[str, Any]:
    return {
        'success': False,
        'is_horoscope_generated': False,
        'error': {
            'code': 400,
            'message': 'Horoscope has not been generated, Please Contact the Administrator',
        },
    }


def horoscope_generated_response(
    hp,
    *,
    serializer_class: Type[serializers.Serializer],
) -> dict[str, Any]:
    return {
        'success': True,
        'is_horoscope_generated': True,
        'data': serializer_class(hp).data,
    }


def horoscope_fetch_payload(
    hp,
    *,
    serializer_class: Type[serializers.Serializer],
) -> dict[str, Any]:
    """Return the appropriate envelope for a HoroscopeProfile row (or None)."""
    if hp is None:
        return horoscope_not_found_response()
    if not hp.is_exe_done():
        return horoscope_not_generated_response()
    return horoscope_generated_response(hp, serializer_class=serializer_class)


def horoscope_pdf_ready(hp) -> bool:
    """True when EXE output is complete enough to build Jathakam / Thalakuri PDFs."""
    if hp is None:
        return False
    return bool(hp.pr_rasi and len(hp.pr_rasi) >= 11 and hp.is_exe_done())


def horoscope_not_ready_for_pdf_response() -> dict[str, Any]:
    return {
        'success': False,
        'is_horoscope_generated': False,
        'error': {
            'code': 400,
            'message': (
                'Horoscope has not been generated yet. Please contact the administrator. '
                'PDF purchase will be available after your horoscope is calculated.'
            ),
        },
    }
