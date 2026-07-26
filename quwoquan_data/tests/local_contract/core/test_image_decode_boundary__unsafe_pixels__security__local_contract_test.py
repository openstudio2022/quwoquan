"""The shared image boundary must reject Pillow decompression-bomb inputs."""
from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image


DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core.image_decode import ImageDecodeFailure, probe_image_bytes  # noqa: E402
from core.image_variants import build_local_variants, image_dimensions  # noqa: E402


def _jpeg_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (100, 100), color=(8, 16, 32)).save(buffer, format="JPEG")
    return buffer.getvalue()


def test_pillow_pixel_limit_is_a_typed_rejection_without_a_runtime_warning():
    payload = _jpeg_bytes()
    original_limit = Image.MAX_IMAGE_PIXELS
    try:
        Image.MAX_IMAGE_PIXELS = 10
        probe = probe_image_bytes(payload)
        dimensions = image_dimensions(payload)
        variants = build_local_variants(payload, base_name="test")
    finally:
        Image.MAX_IMAGE_PIXELS = original_limit

    assert probe.failure is ImageDecodeFailure.PIXEL_LIMIT_EXCEEDED
    assert dimensions is None
    assert variants == []
