from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from content.release.canonical import post_promotion
from content.release.canonical.canonical_inventory import (
    apply_inventory_delta,
    assert_canonical_video_unique,
    canonical_inventory_path,
    load_or_bootstrap_inventory,
    write_inventory,
)
from content.release.canonical.object_transaction_contract import ObjectTransactionError


def _sha(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode()).hexdigest()


def _manifest(
    execution_id: str,
    *,
    content: str,
    poster: str,
    poster_phash: str = "0123456789abcdef",
) -> dict[str, object]:
    video_id = f"video-{execution_id}"
    poster_id = f"poster-{execution_id}"
    return {
        "contentType": "video",
        "executionId": execution_id,
        "assets": [
            {
                "assetId": video_id,
                "kind": "video",
                "mimeType": "video/mp4",
                "fileName": "assets/video.mp4",
                "sha256": _sha(content),
                "posterAssetId": poster_id,
                "posterFileName": "assets/poster.webp",
                "posterSha256": _sha(poster),
            },
            {
                "assetId": poster_id,
                "kind": "image",
                "mimeType": "image/webp",
                "fileName": "assets/poster.webp",
                "sha256": _sha(poster),
                "perceptualHash": poster_phash,
            },
        ],
    }


def _write_manifest(publish: Path, relative: str, manifest: dict[str, object]) -> bytes:
    payload = (json.dumps(manifest, ensure_ascii=False, sort_keys=True) + "\n").encode()
    destination = publish / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return payload


def _apply_manifest(
    publish: Path,
    inventory: dict[str, object],
    relative: str,
    manifest: dict[str, object],
) -> dict[str, object]:
    payload = _write_manifest(publish, relative, manifest)
    pending = apply_inventory_delta(
        inventory,
        [
            {
                "destination": relative,
                "operation": "create",
                "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
            }
        ],
        publish_root=publish,
    )
    write_inventory(publish, pending)
    return load_or_bootstrap_inventory(publish)


def test_existing_canonical_video_rejects_exact_content_and_exact_poster(
    tmp_path: Path,
) -> None:
    publish = tmp_path / "publish"
    existing_ref = "posts/video/体验/既有视频/1/manifest.json"
    existing = _manifest("execution-old", content="content-old", poster="poster-old")
    _write_manifest(publish, existing_ref, existing)
    load_or_bootstrap_inventory(publish)

    with pytest.raises(ObjectTransactionError, match="content sha256"):
        assert_canonical_video_unique(
            publish_root=publish,
            manifest=_manifest(
                "execution-new-content",
                content="content-old",
                poster="poster-new-content",
                poster_phash="fedcba9876543210",
            ),
            excluded_manifest_path="posts/video/体验/新内容重复/1/manifest.json",
        )

    with pytest.raises(ObjectTransactionError, match="poster sha256"):
        assert_canonical_video_unique(
            publish_root=publish,
            manifest=_manifest(
                "execution-new-poster",
                content="content-new-poster",
                poster="poster-old",
            ),
            excluded_manifest_path="posts/video/体验/新海报重复/1/manifest.json",
        )


def test_post_promotion_gate_rejects_exact_video_before_transaction_apply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish = tmp_path / "publish"
    package = tmp_path / "package"
    existing = _manifest("execution-old", content="same-video", poster="poster-old")
    _write_manifest(
        publish,
        "posts/video/体验/既有视频/1/manifest.json",
        existing,
    )
    candidate = _manifest(
        "execution-new",
        content="same-video",
        poster="poster-new",
        poster_phash="fedcba9876543210",
    )
    _write_manifest(package, "object/manifest.json", candidate)
    monkeypatch.setattr(post_promotion, "PUBLISH_ROOT", publish)

    with pytest.raises(ObjectTransactionError, match="content sha256"):
        post_promotion._assert_cross_publish_video_unique(
            package_root=package,
            canonical_post=publish / "posts/video/体验/待发布视频/1",
        )


def test_same_execution_target_is_idempotent_but_another_target_is_not(
    tmp_path: Path,
) -> None:
    publish = tmp_path / "publish"
    relative = "posts/video/体验/幂等视频/1/manifest.json"
    manifest = _manifest("execution-idempotent", content="same", poster="same-poster")
    _write_manifest(publish, relative, manifest)
    load_or_bootstrap_inventory(publish)

    assert_canonical_video_unique(
        publish_root=publish,
        manifest=manifest,
        excluded_manifest_path=relative,
    )
    with pytest.raises(ObjectTransactionError, match="content sha256"):
        assert_canonical_video_unique(
            publish_root=publish,
            manifest=manifest,
            excluded_manifest_path="posts/video/体验/另一个对象/1/manifest.json",
        )


def test_duplicate_increment_rolls_back_inventory_and_both_indexes(
    tmp_path: Path,
) -> None:
    publish = tmp_path / "publish"
    publish.mkdir()
    inventory = load_or_bootstrap_inventory(publish)
    first = _manifest("execution-first", content="duplicate", poster="poster-first")
    first_ref = "posts/video/体验/原子视频一/1/manifest.json"
    inventory = _apply_manifest(publish, inventory, first_ref, first)

    duplicate = _manifest(
        "execution-duplicate",
        content="duplicate",
        poster="poster-second",
        poster_phash="fedcba9876543210",
    )
    duplicate_ref = "posts/video/体验/原子视频二/1/manifest.json"
    payload = _write_manifest(publish, duplicate_ref, duplicate)
    pending = apply_inventory_delta(
        inventory,
        [
            {
                "destination": duplicate_ref,
                "operation": "create",
                "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
            }
        ],
        publish_root=publish,
    )
    with pytest.raises(ObjectTransactionError, match="content sha256"):
        write_inventory(publish, pending)

    assert load_or_bootstrap_inventory(publish) == inventory
    with sqlite3.connect(canonical_inventory_path(publish)) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM entries WHERE path = ?", (duplicate_ref,)
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM image_identities"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM video_identities"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT inventory_digest FROM video_index_state"
        ).fetchone()[0] == inventory["inventoryDigest"]


def test_video_index_state_tamper_and_stale_inventory_fence_fail_closed(
    tmp_path: Path,
) -> None:
    publish = tmp_path / "publish"
    publish.mkdir()
    base = load_or_bootstrap_inventory(publish)

    stale_path = publish / "posts/video/体验/stale/1/note.md"
    stale_path.parent.mkdir(parents=True)
    stale_path.write_text("stale", encoding="utf-8")
    stale = apply_inventory_delta(
        base,
        [
            {
                "destination": "posts/video/体验/stale/1/note.md",
                "operation": "create",
                "sha256": _sha("stale"),
                "bytes": 5,
            }
        ],
        publish_root=publish,
    )
    winner_path = publish / "posts/video/体验/winner/1/note.md"
    winner_path.parent.mkdir(parents=True)
    winner_path.write_text("winner", encoding="utf-8")
    winner = apply_inventory_delta(
        base,
        [
            {
                "destination": "posts/video/体验/winner/1/note.md",
                "operation": "create",
                "sha256": _sha("winner"),
                "bytes": 6,
            }
        ],
        publish_root=publish,
    )
    write_inventory(publish, winner)
    with pytest.raises(ObjectTransactionError, match="write CAS drift"):
        write_inventory(publish, stale)

    with sqlite3.connect(canonical_inventory_path(publish)) as connection:
        connection.execute(
            "UPDATE video_index_state SET inventory_digest = ? WHERE singleton = 1",
            (_sha("tampered"),),
        )
    with pytest.raises(ObjectTransactionError, match="video inventory state drift"):
        assert_canonical_video_unique(
            publish_root=publish,
            manifest=_manifest("execution-probe", content="probe", poster="probe"),
            excluded_manifest_path="posts/video/体验/probe/1/manifest.json",
        )


def test_poster_binding_must_match_the_exact_manifest_asset(tmp_path: Path) -> None:
    publish = tmp_path / "publish"
    publish.mkdir()
    manifest = _manifest("execution-binding", content="binding", poster="poster")
    video = manifest["assets"][0]  # type: ignore[index]
    assert isinstance(video, dict)
    video["posterSha256"] = _sha("not-the-poster")

    with pytest.raises(ObjectTransactionError, match="poster identity binding drift"):
        assert_canonical_video_unique(
            publish_root=publish,
            manifest=manifest,
            excluded_manifest_path="posts/video/体验/binding/1/manifest.json",
        )
