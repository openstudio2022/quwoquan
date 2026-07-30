"""The creator-avatar crop reuses one deterministic canonical image derivative."""

from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image

DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core.image_variants import (
    WEBP_METHOD,
    build_center_square_cover_derivative,
)
from core.media_asset_url import (
    IMAGE_VARIANT_POLICY_VERSION,
    IMAGE_VARIANT_PROFILES,
)


def _source_image(*, width: int, height: int, mode: str = "RGBA") -> bytes:
    image = Image.new(mode, (width, height), (36, 102, 150, 190))
    for x in range(width):
        image.putpixel(
            (x, height // 2),
            (x % 256, (x // 2) % 256, (x // 3) % 256, 255),
        )
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_center_square_cover_derivative_is_repeatable_and_policy_bound() -> None:
    source = _source_image(width=1600, height=1400)

    first = build_center_square_cover_derivative(source)
    second = build_center_square_cover_derivative(source)

    assert first is not None
    assert second is not None
    assert first["bytes"] == second["bytes"]
    assert first["sha256"] == second["sha256"]
    assert first["cropBox"] == [100, 0, 1500, 1400]
    assert first["sourceWidth"] == 1600
    assert first["sourceHeight"] == 1400
    assert first["width"] == first["height"] == 1280
    assert first["colorMode"] == "RGB"
    assert first["format"] == "webp"
    assert first["mimeType"] == "image/webp"
    assert first["quality"] == IMAGE_VARIANT_PROFILES["cover"]["quality"]
    assert first["method"] == WEBP_METHOD
    assert first["policyVersion"] == IMAGE_VARIANT_POLICY_VERSION
    with Image.open(io.BytesIO(first["bytes"])) as rendered:
        assert rendered.size == (1280, 1280)
        assert rendered.mode == "RGB"
        assert rendered.format == "WEBP"


def test_center_square_cover_derivative_refuses_upscale() -> None:
    source = _source_image(width=1279, height=1800)

    assert build_center_square_cover_derivative(source) is None
