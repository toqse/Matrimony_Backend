"""Absolute signed URLs for South Indian horoscope chart PNGs (grahanila-based)."""


def build_horoscope_chart_absolute_url(
    request,
    profile_id: int,
    style: str = 'south',
    lang: str = 'ml',
) -> str:
    """Chart PNG URLs are disabled; return empty string."""
    return ''
