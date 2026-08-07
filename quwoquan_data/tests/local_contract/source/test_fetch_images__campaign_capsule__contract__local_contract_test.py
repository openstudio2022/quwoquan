from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from content.source import fetch_images


def _jpeg() -> bytes:
    output = io.BytesIO()
    Image.effect_noise((256, 256), 100).convert("RGB").save(output, format="JPEG")
    return output.getvalue()


def test_campaign_capsule_image_is_a_permitted_immutable_file_input(
    tmp_path: Path,
    monkeypatch,
) -> None:
    capsules = tmp_path / "content-addressed-capsules"
    image = capsules / "capsule/external-inputs/image/cas/sha256/ab/photo.jpg"
    image.parent.mkdir(parents=True)
    image.write_bytes(_jpeg())
    monkeypatch.setattr(fetch_images, "CONTENT_CAMPAIGN_CAPSULES_ROOT", capsules)

    payload = fetch_images.fetch_image_payload(image.as_uri())

    assert payload is not None
    assert payload["sha256"]


def test_non_capsule_runtime_cache_file_remains_blocked(
    tmp_path: Path,
    monkeypatch,
) -> None:
    capsules = tmp_path / "content-addressed-capsules"
    image = tmp_path / "mutable-cache/photo.jpg"
    image.parent.mkdir(parents=True)
    image.write_bytes(_jpeg())
    monkeypatch.setattr(fetch_images, "CONTENT_CAMPAIGN_CAPSULES_ROOT", capsules)
    monkeypatch.setattr(fetch_images, "DATA_ROOT", tmp_path / "repo-data")
    monkeypatch.setattr(fetch_images, "SOURCE_ACQUISITION_ROOT", tmp_path / "acquisition")

    assert fetch_images.fetch_image_payload(image.as_uri()) is None
