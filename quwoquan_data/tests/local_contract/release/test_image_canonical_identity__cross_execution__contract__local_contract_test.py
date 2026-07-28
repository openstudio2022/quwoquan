# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/image-commercial-scale-closure/spec.md#gwt-002
from __future__ import annotations

import sys
from pathlib import Path

import pytest

DATA_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data"
)
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from core.io import write_json  # noqa: E402
from core.image_deduplication import perceptual_hash_distance  # noqa: E402
from content.release.canonical import post_promotion as subject  # noqa: E402
from content.release.canonical.object_transaction_contract import (  # noqa: E402
    ObjectTransactionError,
)


def _manifest(*, digest: str, perceptual_hash: str) -> dict[str, object]:
    return {
        "contentType": "image",
        "assets": [
            {
                "assetId": "image-1",
                "kind": "image",
                "sha256": digest,
                "perceptualHash": perceptual_hash,
            }
        ],
    }


def test_perceptual_hash_distance_is_hex_hamming_distance() -> None:
    assert perceptual_hash_distance("0000000000000000", "0000000000000003") == 2
    with pytest.raises(ValueError, match="same-width hexadecimal"):
        perceptual_hash_distance("invalid", "0000")


def test_cross_execution_exact_image_identity_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish = tmp_path / "publish"
    package = tmp_path / "package"
    existing = publish / "posts/image/摄影/既有图片/1"
    write_json(
        existing / "manifest.json",
        _manifest(digest="sha256:" + "a" * 64, perceptual_hash="0" * 16),
    )
    write_json(
        package / "object/manifest.json",
        _manifest(digest="sha256:" + "a" * 64, perceptual_hash="f" * 16),
    )
    monkeypatch.setattr(subject, "PUBLISH_ROOT", publish)

    with pytest.raises(ObjectTransactionError, match="duplicated by sha256"):
        subject._assert_cross_publish_image_unique(
            package_root=package,
            canonical_post=publish / "posts/image/摄影/新图片/1",
        )


def test_cross_execution_perceptual_duplicate_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish = tmp_path / "publish"
    package = tmp_path / "package"
    write_json(
        publish / "posts/image/摄影/既有图片/1/manifest.json",
        _manifest(digest="sha256:" + "a" * 64, perceptual_hash="0" * 16),
    )
    write_json(
        package / "object/manifest.json",
        _manifest(digest="sha256:" + "b" * 64, perceptual_hash="0" * 15 + "3"),
    )
    monkeypatch.setattr(subject, "PUBLISH_ROOT", publish)

    with pytest.raises(ObjectTransactionError, match="duplicated by perceptualHash"):
        subject._assert_cross_publish_image_unique(
            package_root=package,
            canonical_post=publish / "posts/image/摄影/新图片/1",
        )


def test_commercial_image_requires_perceptual_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish = tmp_path / "publish"
    package = tmp_path / "package"
    write_json(
        package / "object/manifest.json",
        _manifest(digest="sha256:" + "b" * 64, perceptual_hash=""),
    )
    monkeypatch.setattr(subject, "PUBLISH_ROOT", publish)

    with pytest.raises(ObjectTransactionError, match="requires perceptualHash"):
        subject._assert_cross_publish_image_unique(
            package_root=package,
            canonical_post=publish / "posts/image/摄影/新图片/1",
        )
