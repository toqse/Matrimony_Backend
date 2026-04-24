"""Absolute signed URLs for South Indian horoscope chart PNGs (grahanila-based)."""
from __future__ import annotations

from urllib.parse import urlencode

from django.urls import reverse

from .public_url_signing import sign_chart_access


def build_horoscope_chart_absolute_url(
    request,
    profile_id: int,
    style: str = 'south',
    lang: str = 'ml',
) -> str:
    rel = reverse('astrology:horoscope_chart', kwargs={'profile_id': profile_id})
    query = urlencode({'sig': sign_chart_access(profile_id), 'style': style, 'lang': lang})
    return request.build_absolute_uri(f'{rel}?{query}')
