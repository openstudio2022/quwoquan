"""The storage baseline is the input to CDN transformation, never its output.

A body frozen into an immutable release is what the four declared profiles
transform *from*. Each declared width is therefore an upper bound on delivery, not
a ceiling on storage: capping the stored body at the widest declared width is what
guarantees that profile can never deliver the width it declares. The long edge is
a second, unrelated axis — normalizing on it pushes a portrait body whose width is
already inside every profile even further down.

So this admission surface keeps exactly one per-asset judgement: can the stored
body be decoded. Rights and quality admission happen earlier; object-level byte
volume is the single-object storage budget, measured on the whole object closure
somewhere else entirely.
"""

from __future__ import annotations

import hashlib
import io
import sys
from pathlib import Path

import pytest

DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core.article_package import copy_asset_files  # noqa: E402
from core.media_asset_url import IMAGE_VARIANT_PROFILES  # noqa: E402
from core.media_normalization import publishable_media_issue  # noqa: E402

Image = pytest.importorskip("PIL.Image")

WIDEST_DECLARED_WIDTH = max(
    int(row["width"]) for row in IMAGE_VARIANT_PROFILES.values()
)


def _png(*, width: int, height: int) -> bytes:
    """A real, decodable body; PNG keeps the bytes stable across encoders."""

    image = Image.new("RGB", (width, height), (36, 102, 150))
    for x in range(width):
        image.putpixel((x, height // 2), (x % 256, (x // 2) % 256, (x // 3) % 256))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _source(tmp_path: Path, name: str, body: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(body)
    return path


def _wider_than_every_profile(tmp_path: Path) -> Path:
    return _source(
        tmp_path,
        "wider.png",
        _png(width=WIDEST_DECLARED_WIDTH + 640, height=WIDEST_DECLARED_WIDTH // 2),
    )


def _narrow_but_long_edged(tmp_path: Path) -> Path:
    """Width inside every profile, long edge beyond the widest declared width."""

    return _source(
        tmp_path,
        "portrait.png",
        _png(width=WIDEST_DECLARED_WIDTH - 448, height=WIDEST_DECLARED_WIDTH + 320),
    )


# spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-006.t1
def test_a_body_wider_than_every_declared_profile_is_admitted(tmp_path: Path) -> None:
    source = _wider_than_every_profile(tmp_path)

    assert publishable_media_issue(source, label="wider") is None, (
        "the widest declared width is a delivery output width; using it as a "
        "storage ceiling stops that profile from ever delivering it"
    )


# spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-006.t1
def test_admission_is_not_judged_on_the_long_edge(tmp_path: Path) -> None:
    source = _narrow_but_long_edged(tmp_path)

    assert publishable_media_issue(source, label="portrait") is None, (
        "the long edge is not the axis instant transformation constrains, so a "
        "body already inside every declared width must not be refused on it"
    )


# spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-006.t2
def test_the_admitted_storage_body_is_the_source_body_byte_for_byte(
    tmp_path: Path,
) -> None:
    """Passthrough is what keeps the rights snapshot digest and the release body one digest."""

    sources = [
        _wider_than_every_profile(tmp_path),
        _narrow_but_long_edged(tmp_path),
    ]

    admitted = copy_asset_files(
        [
            {
                "assetId": f"asset-{index}",
                "fileName": source.name,
                "sourcePath": str(source),
            }
            for index, source in enumerate(sources, start=1)
        ],
        tmp_path / "assets",
    )

    for row, source in zip(admitted, sources, strict=True):
        published = tmp_path / "assets" / source.name
        expected = source.read_bytes()

        assert published.read_bytes() == expected
        assert row["sha256"] == "sha256:" + hashlib.sha256(expected).hexdigest()


# spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-006.t1
def test_a_body_narrower_than_a_declared_width_is_not_upscaled(
    tmp_path: Path,
) -> None:
    source = _narrow_but_long_edged(tmp_path)
    with Image.open(io.BytesIO(source.read_bytes())) as decoded:
        source_width = decoded.width

    copy_asset_files(
        [
            {
                "assetId": "asset-1",
                "fileName": source.name,
                "sourcePath": str(source),
            }
        ],
        tmp_path / "assets",
    )

    with Image.open(tmp_path / "assets" / source.name) as published:
        assert published.width == source_width, (
            "upscaling adds bytes without adding information"
        )


# spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-006.t3
def test_an_undecodable_body_is_a_failure_rather_than_a_returned_verdict(
    tmp_path: Path,
) -> None:
    """Absent decoding capability and "no problem found" must not share one carrier.

    A nullable problem string makes the two indistinguishable at the call site: an
    empty result means both "this body is fine" and "nothing could be measured".
    The spec names no exception type here, only that the outcome must reach the
    caller as a failure rather than as an in-band verdict.
    """

    source = _source(tmp_path, "broken.png", b"not an image")

    with pytest.raises(Exception):  # noqa: B017
        publishable_media_issue(source, label="broken")
