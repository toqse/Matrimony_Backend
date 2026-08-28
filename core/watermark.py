from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Iterable

from django.core.files.base import ContentFile
from django.db.models import ImageField
from PIL import Image

# Cap longest edge before watermark to cut CPU/RAM on phone-camera originals.
_MAX_SOURCE_EDGE = 1920
_AADHAAR_MAX_EDGE = 2000
_WEBP_QUALITY = 85
_WEBP_QUALITY_MIN = 60
_WEBP_METHOD = 4
_MAX_OUTPUT_BYTES = 2 * 1024 * 1024


def _is_newly_assigned_file(file_value) -> bool:
    """
    Return True when a File/ImageField was newly assigned in this save cycle.
    """
    if not file_value:
        return False
    return bool(getattr(file_value, "_committed", False) is False)


@lru_cache(maxsize=4)
def _load_logo_rgba(watermark_path_str: str) -> Image.Image | None:
    path = Path(watermark_path_str)
    if not path.exists():
        return None
    try:
        return Image.open(path).convert("RGBA")
    except Exception:
        return None


def _downscale_rgba(base: Image.Image, max_edge: int = _MAX_SOURCE_EDGE) -> Image.Image:
    w, h = base.size
    longest = max(w, h)
    if longest <= max_edge:
        return base
    scale = max_edge / float(longest)
    tw = max(1, int(w * scale))
    th = max(1, int(h * scale))
    return base.resize((tw, th), Image.LANCZOS)


def _webp_filename(name: str | None) -> str:
    stem = Path(name or "photo").stem or "photo"
    return f"{stem}.webp"


def _encode_webp_capped(image_rgb: Image.Image) -> bytes:
    """
    Encode RGB image as WebP. Start at high quality; if over 2MB, step quality
    down without resizing so watermark pixels stay in place.
    """
    quality = _WEBP_QUALITY
    last = b""
    while quality >= _WEBP_QUALITY_MIN:
        out = BytesIO()
        image_rgb.save(out, format="WEBP", quality=quality, method=_WEBP_METHOD)
        last = out.getvalue()
        if len(last) <= _MAX_OUTPUT_BYTES:
            return last
        quality -= 5
    return last


def _save_webp(file_value, image_rgb: Image.Image) -> None:
    payload = _encode_webp_capped(image_rgb)
    file_value.save(_webp_filename(file_value.name), ContentFile(payload), save=False)


def _overlay_logo(base: Image.Image, logo_src: Image.Image) -> Image.Image:
    """Bottom-right logo overlay. Placement math must stay unchanged."""
    logo = logo_src.copy()
    target_width = max(int(base.width * 0.26), 1)
    scale = target_width / max(logo.width, 1)
    target_height = max(int(logo.height * scale), 1)
    logo = logo.resize((target_width, target_height), Image.LANCZOS)

    # Keep logo visible but not overwhelming.
    alpha = logo.split()[3].point(lambda p: int(p * 0.72))
    logo.putalpha(alpha)

    margin = max(12, int(min(base.width, base.height) * 0.03))
    x = max(base.width - logo.width - margin, 0)
    y = max(base.height - logo.height - margin, 0)

    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    layer.paste(logo, (x, y), logo)
    return Image.alpha_composite(base, layer)


def apply_logo_watermark(file_value, watermark_path: Path) -> None:
    """
    Overlay the configured logo watermark at bottom-right of an uploaded image,
    then store as WebP (max 2MB). If the logo file is missing, still compress.
    """
    if not file_value:
        return

    try:
        file_value.open("rb")
        source_img = Image.open(file_value)
        base = _downscale_rgba(source_img.convert("RGBA"))

        logo_src = _load_logo_rgba(str(watermark_path))
        if logo_src is not None:
            base = _overlay_logo(base, logo_src)

        _save_webp(file_value, base.convert("RGB"))
    except Exception:
        # Keep upload flow resilient; if processing fails we keep original upload.
        return
    finally:
        try:
            file_value.close()
        except Exception:
            pass


def compress_image_field_to_webp(file_value, *, max_edge: int = _AADHAAR_MAX_EDGE) -> None:
    """Downscale and encode a newly uploaded image as WebP with no overlay."""
    if not file_value:
        return
    try:
        file_value.open("rb")
        source_img = Image.open(file_value)
        base = _downscale_rgba(source_img.convert("RGBA"), max_edge=max_edge)
        _save_webp(file_value, base.convert("RGB"))
    except Exception:
        return
    finally:
        try:
            file_value.close()
        except Exception:
            pass


def watermark_model_images(instance, *, watermark_path: Path, exclude_fields: Iterable[str] = ()) -> None:
    """
    Watermark newly assigned ImageFields on a model instance.
    """
    excluded = set(exclude_fields)
    for field in instance._meta.concrete_fields:
        if not isinstance(field, ImageField) or field.name in excluded:
            continue
        file_value = getattr(instance, field.name, None)
        if _is_newly_assigned_file(file_value):
            apply_logo_watermark(file_value, watermark_path)


def compress_assigned_images(
    instance,
    field_names: Iterable[str],
    *,
    max_edge: int = _AADHAAR_MAX_EDGE,
) -> None:
    """Compress newly assigned ImageFields to WebP without a watermark overlay."""
    names = set(field_names)
    for field in instance._meta.concrete_fields:
        if not isinstance(field, ImageField) or field.name not in names:
            continue
        file_value = getattr(instance, field.name, None)
        if _is_newly_assigned_file(file_value):
            compress_image_field_to_webp(file_value, max_edge=max_edge)
