from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

DATA_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(DATA_SCRIPTS))

from content.release.canonical.content_pool_record import (  # noqa: E402
    pool_payload_digest,
)

COVER_BYTES = b"\xff\xd8\xff\xe0cover-bytes"
DETAIL_BYTES = b"\xff\xd8\xff\xe0detail-bytes"


def _asset_row(asset_id: str, payload: bytes) -> dict[str, object]:
    digest = hashlib.sha256(payload).hexdigest()
    return {
        "assetId": asset_id,
        "bytes": len(payload),
        "sha256": f"sha256:{digest}",
        "objectKey": (
            f"media/objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}.jpg"
        ),
    }


def _structured_object(root: Path, *, assets: list[dict[str, object]]) -> Path:
    root.mkdir(parents=True)
    (root / "manifest.json").write_text(
        json.dumps({"contentId": "content-a", "version": 1}, ensure_ascii=False),
        encoding="utf-8",
    )
    (root / "article.md").write_text("# body\n", encoding="utf-8")
    (root / "asset.refs.json").write_text(
        json.dumps({"assets": assets}, ensure_ascii=False), encoding="utf-8"
    )
    return root


def test_media_bytes_do_not_enter_the_object_payload_digest(tmp_path: Path) -> None:
    """REQ-003 records media by digest only, so bytes never shift the digest.

    A produced object still carries its bytes inside the execution package, while
    canonical publish receives the same object without them.  Both sides must
    therefore agree on one payload digest, otherwise every object that owns
    media is permanently unadmittable after promotion.
    """

    assets = [
        _asset_row("cover", COVER_BYTES),
        _asset_row("detail", DETAIL_BYTES),
    ]
    package = _structured_object(tmp_path / "package/object", assets=assets)
    canonical = _structured_object(
        tmp_path / "publish/posts/article/a/1", assets=assets
    )
    package_assets = package / "assets"
    package_assets.mkdir()
    (package_assets / "cover.jpg").write_bytes(COVER_BYTES)
    (package_assets / "detail.jpg").write_bytes(DETAIL_BYTES)

    assert pool_payload_digest(package) == pool_payload_digest(canonical)


def test_media_reference_drift_still_changes_the_payload_digest(
    tmp_path: Path,
) -> None:
    """Excluding bytes must not weaken the closure over media references."""

    canonical = _structured_object(
        tmp_path / "publish/posts/article/a/1",
        assets=[_asset_row("cover", COVER_BYTES)],
    )
    before = pool_payload_digest(canonical)
    (canonical / "asset.refs.json").write_text(
        json.dumps(
            {"assets": [_asset_row("cover", DETAIL_BYTES)]}, ensure_ascii=False
        ),
        encoding="utf-8",
    )

    assert pool_payload_digest(canonical) != before
