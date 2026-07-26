"""Small valid raster payloads for tests that cross a real media boundary."""
from __future__ import annotations

from io import BytesIO

from PIL import Image


_FIXTURE_SIZE = (320, 240)


def _color(seed: int) -> tuple[int, int, int]:
    return (
        (seed * 47) % 256,
        (seed * 83) % 256,
        (seed * 131) % 256,
    )


def jpeg_bytes(*, seed: int = 0) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", _FIXTURE_SIZE, color=_color(seed)).save(
        buffer,
        format="JPEG",
        quality=85,
    )
    return buffer.getvalue()


def png_bytes(*, seed: int = 0) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", _FIXTURE_SIZE, color=_color(seed)).save(buffer, format="PNG")
    return buffer.getvalue()


__all__ = ["jpeg_bytes", "png_bytes"]
