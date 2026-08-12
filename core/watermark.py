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
_JPEG_QUALITY = 85


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


def apply_logo_watermark(file_value, watermark_path: Path) -> None:
    """
    Overlay the configured logo watermark at bottom-right of an uploaded image.
    """
    if not file_value:
        return

    logo_src = _load_logo_rgba(str(watermark_path))
    if logo_src is None:
        return

    try:
        file_value.open("rb")
        source_img = Image.open(file_value)
        source_format = (source_img.format or "PNG").upper()
        exif = source_img.info.get("exif")
        base = _downscale_rgba(source_img.convert("RGBA"))

        # Copy cached logo so per-image resize/alpha does not mutate the cache.
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
        watermarked = Image.alpha_composite(base, layer)

        out = BytesIO()
        save_kwargs: dict = {}
        fmt = "JPEG" if source_format in {"JPG", "JPEG"} else source_format

        if fmt == "JPEG":
            watermarked = watermarked.convert("RGB")
            save_kwargs["quality"] = _JPEG_QUALITY
            if exif:
                save_kwargs["exif"] = exif
        elif fmt == "PNG":
            # Prefer JPEG for photo uploads after watermark (smaller, faster).
            fmt = "JPEG"
            watermarked = watermarked.convert("RGB")
            save_kwargs["quality"] = _JPEG_QUALITY

        watermarked.save(out, format=fmt, **save_kwargs)

        name = file_value.name or "photo.jpg"
        if fmt == "JPEG" and not name.lower().endswith((".jpg", ".jpeg")):
            stem = Path(name).stem or "photo"
            name = f"{stem}.jpg"

        file_value.save(name, ContentFile(out.getvalue()), save=False)
    except Exception:
        # Keep upload flow resilient; if watermark fails we keep original upload.
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
