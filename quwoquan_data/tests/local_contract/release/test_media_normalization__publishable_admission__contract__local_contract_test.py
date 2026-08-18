"""Publishable media is bounded by the variant contract, not by intent.

The widest profile the product serves is the widest body a release can usefully
hold, so an acquisition original must be refused at the surface where it would
first become published content.  These cases pin the rule to the contract rather
than to a copied constant, so widening a profile widens admission too.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

SCRIPTS_ROOT = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core.article_package import copy_asset_files
from core.media_asset_url import IMAGE_VARIANT_PROFILES
from core.media_normalization import (
    PUBLISHABLE_MAX_WIDTH,
    publishable_image_issue,
    publishable_media_issue,
)

PIL = pytest.importorskip("PIL.Image")


def _jpeg(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    PIL.new("RGB", (width, height), (120, 130, 140)).save(buffer, format="JPEG", quality=80)
    return buffer.getvalue()


def test_the_admission_ceiling_is_the_widest_served_profile() -> None:
    assert PUBLISHABLE_MAX_WIDTH == max(
        int(row["width"]) for row in IMAGE_VARIANT_PROFILES.values()
    )


def test_a_body_within_every_profile_is_publishable() -> None:
    assert publishable_image_issue(_jpeg(1024, 768), label="within") is None


def test_a_camera_original_is_refused() -> None:
    issue = publishable_image_issue(_jpeg(PUBLISHABLE_MAX_WIDTH + 1, 1200), label="original")
    assert issue is not None
    assert str(PUBLISHABLE_MAX_WIDTH) in issue


def test_an_undecodable_body_cannot_be_proven_normalized(tmp_path: Path) -> None:
    """Absent decoding capability is a refusal, never a silent pass."""
    body = tmp_path / "broken.jpg"
    body.write_bytes(b"not an image")
    assert publishable_media_issue(body, label="broken") is not None


def test_non_image_media_is_out_of_scope(tmp_path: Path) -> None:
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    assert publishable_media_issue(clip, label="clip") is None


def test_post_asset_binding_refuses_an_un_normalized_original(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(_jpeg(PUBLISHABLE_MAX_WIDTH + 400, 900))
    with pytest.raises(ValueError, match="not publishable"):
        copy_asset_files(
            [{"assetId": "a1", "fileName": "a1.jpg", "sourcePath": str(source)}],
            tmp_path / "assets",
        )


def test_post_asset_binding_accepts_a_normalized_body(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(_jpeg(1200, 800))
    out = copy_asset_files(
        [{"assetId": "a1", "fileName": "a1.jpg", "sourcePath": str(source)}],
        tmp_path / "assets",
    )
    assert out[0]["sha256"].startswith("sha256:")
    assert (tmp_path / "assets" / "a1.jpg").is_file()
