"""A profile's declared width is an upper bound on delivery, not an upscale target."""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from PIL import Image

DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core.image_variants import LOCAL_VARIANT_PROFILES, build_local_variants
from core.media_asset_url import IMAGE_VARIANT_PROFILES, effective_delivery_width

WIDEST_PROFILE = max(
    IMAGE_VARIANT_PROFILES,
    key=lambda name: IMAGE_VARIANT_PROFILES[name]["width"],
)


def _source_image(*, width: int, height: int) -> bytes:
    image = Image.new("RGB", (width, height), (36, 102, 150))
    for x in range(width):
        image.putpixel((x, height // 2), (x % 256, (x // 2) % 256, (x // 3) % 256))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


# spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-006.t5
def test_widest_profile_delivers_declared_width_or_stored_width() -> None:
    declared = IMAGE_VARIANT_PROFILES[WIDEST_PROFILE]["width"]
    wider = declared * 2
    narrower = declared - 448

    assert effective_delivery_width(WIDEST_PROFILE, stored_width=wider) == declared
    assert effective_delivery_width(WIDEST_PROFILE, stored_width=declared) == declared
    assert effective_delivery_width(WIDEST_PROFILE, stored_width=narrower) == narrower


# spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-006.t5
def test_no_profile_ever_projects_above_the_stored_width() -> None:
    for name, profile in IMAGE_VARIANT_PROFILES.items():
        declared = profile["width"]
        for stored_width in (1, declared // 2, declared - 1, declared, declared + 1):
            effective = effective_delivery_width(name, stored_width=stored_width)

            assert effective == min(declared, stored_width)
            assert effective <= stored_width
            assert effective <= declared


# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/absent-empty-failure-nullability/spec.md#gwt-002.t1
def test_unknown_profile_or_unusable_stored_width_raises() -> None:
    with pytest.raises(ValueError):
        effective_delivery_width("original", stored_width=1024)
    with pytest.raises(ValueError):
        effective_delivery_width("", stored_width=1024)
    for stored_width in (0, -1, True, 1024.0, "1024", None):
        with pytest.raises(ValueError):
            effective_delivery_width(WIDEST_PROFILE, stored_width=stored_width)


# spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-006.t5
def test_local_variants_consume_the_projection_without_upscaling() -> None:
    narrowest = min(
        IMAGE_VARIANT_PROFILES[name]["width"] for name in LOCAL_VARIANT_PROFILES
    )
    source_width = narrowest + 1
    variants = build_local_variants(
        _source_image(width=source_width, height=source_width // 2),
        base_name="000_narrow-source",
    )

    assert {variant["profile"] for variant in variants} == set(LOCAL_VARIANT_PROFILES)
    for variant in variants:
        declared = IMAGE_VARIANT_PROFILES[variant["profile"]]["width"]

        assert variant["width"] == min(declared, source_width)
        assert variant["width"] <= source_width
        with Image.open(io.BytesIO(variant["bytes"])) as rendered:
            assert rendered.width == min(declared, source_width)
