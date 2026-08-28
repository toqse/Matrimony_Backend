"""WebP encode + bottom-right watermark placement."""
from io import BytesIO
from pathlib import Path
import tempfile
import unittest

from django.test import SimpleTestCase
from PIL import Image, features

from core.watermark import (
    _MAX_OUTPUT_BYTES,
    apply_logo_watermark,
    compress_image_field_to_webp,
)


def _jpeg_bytes(size=(1200, 800), color=(0, 0, 220)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _png_logo_bytes(size=(200, 80), color=(255, 0, 0, 255)) -> bytes:
    img = Image.new("RGBA", size, color)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class FakeImageFile:
    """Minimal FieldFile stand-in: readable after open(), writable via save()."""

    def __init__(self, data: bytes, name: str = "photo.jpg"):
        self._buffer = BytesIO(data)
        self.name = name
        self._committed = False

    def open(self, mode="rb"):
        self._buffer.seek(0)
        return self

    def read(self, *args, **kwargs):
        return self._buffer.read(*args, **kwargs)

    def seek(self, *args, **kwargs):
        return self._buffer.seek(*args, **kwargs)

    def tell(self):
        return self._buffer.tell()

    def close(self):
        self._buffer.seek(0)

    def save(self, name, content, save=False):
        self.name = name
        if hasattr(content, "seek"):
            content.seek(0)
        raw = content.read() if hasattr(content, "read") else bytes(content)
        self._buffer = BytesIO(raw)
        self._committed = False
        self._data = raw

    @property
    def _data(self):
        pos = self._buffer.tell()
        self._buffer.seek(0)
        data = self._buffer.read()
        self._buffer.seek(pos)
        return data

    @_data.setter
    def _data(self, value: bytes):
        self._buffer = BytesIO(value)


@unittest.skipUnless(features.check("webp"), "Pillow was built without WebP")
class WatermarkWebpTests(SimpleTestCase):
    def test_watermarked_output_is_webp_under_2mb_logo_bottom_right(self):
        photo = FakeImageFile(_jpeg_bytes((1600, 1000), color=(0, 0, 220)))
        with tempfile.TemporaryDirectory() as tmp:
            logo_path = Path(tmp) / "logo.png"
            logo_path.write_bytes(_png_logo_bytes())
            apply_logo_watermark(photo, logo_path)

        self.assertTrue(str(photo.name).lower().endswith(".webp"))
        self.assertLessEqual(len(photo._data), _MAX_OUTPUT_BYTES)
        self.assertGreater(len(photo._data), 0)

        result = Image.open(BytesIO(photo._data))
        self.assertEqual(result.format, "WEBP")
        rgb = result.convert("RGB")
        w, h = rgb.size
        top_left = rgb.getpixel((8, 8))
        # Logo is ~26% wide at bottom-right with a ~3% margin; sample inside that box.
        bottom_right = rgb.getpixel((int(w * 0.90), int(h * 0.92)))
        # Source is blue; logo is red at bottom-right after overlay.
        # WebP chroma can mute primaries, so compare regions rather than exact RGB.
        self.assertGreater(top_left[2], top_left[0] + 40)
        self.assertGreater(bottom_right[0], top_left[0] + 40)
        self.assertGreater(bottom_right[0], rgb.getpixel((8, h - 8))[0] + 20)

    def test_missing_logo_still_encodes_webp(self):
        photo = FakeImageFile(_jpeg_bytes())
        apply_logo_watermark(photo, Path("/nonexistent/logo.png"))
        self.assertTrue(str(photo.name).lower().endswith(".webp"))
        self.assertEqual(Image.open(BytesIO(photo._data)).format, "WEBP")
        self.assertLessEqual(len(photo._data), _MAX_OUTPUT_BYTES)

    def test_aadhaar_compress_is_webp_without_requiring_logo(self):
        photo = FakeImageFile(_jpeg_bytes((3000, 1200), color=(40, 40, 40)), name="aadhaar.jpg")
        compress_image_field_to_webp(photo, max_edge=2000)
        self.assertTrue(str(photo.name).lower().endswith(".webp"))
        result = Image.open(BytesIO(photo._data))
        self.assertEqual(result.format, "WEBP")
        self.assertLessEqual(max(result.size), 2000)
        self.assertLessEqual(len(photo._data), _MAX_OUTPUT_BYTES)
