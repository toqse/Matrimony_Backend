"""
Helpers for building absolute URLs for media files in API responses.

We often get relative URLs from Django storages (e.g. "media/..." or "/media/...").
These helpers normalize them into full URLs using the incoming request.
"""

from __future__ import annotations

from typing import Any, Optional


def absolute_media_url(request, file_or_url: Any) -> Optional[str]:
    """
    Convert a FileField/ImageField value (or a string path/url) into an absolute URL.

    - Returns None for falsy values
    - Returns input if it's already an absolute http(s) URL
    - Uses `request.build_absolute_uri()` when available
    - Normalizes relative "media/..." into "/media/..." before building
    """
    if not file_or_url:
        return None

    # Resolve to a string URL/path
    try:
        url = file_or_url.url  # FileField/ImageField
    except Exception:
        url = str(file_or_url)

    if not url:
        return None

    u = str(url)
    if u.startswith("http://") or u.startswith("https://"):
        return u

    # Normalize common relative forms: "media/x.jpg" -> "/media/x.jpg"
    if not u.startswith("/"):
        u = "/" + u

    try:
        return request.build_absolute_uri(u) if request is not None else u
    except Exception:
        return u

