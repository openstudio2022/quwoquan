from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from content.release.canonical import canonical_inventory as inventory_subject
from content.release.canonical.canonical_inventory import (
    apply_inventory_delta,
    assert_canonical_image_unique,
    canonical_inventory_path,
    load_or_bootstrap_inventory,
    write_inventory,
)
from content.release.canonical.object_transaction_contract import ObjectTransactionError


def _manifest(index: int, *, perceptual_hash: str | None = None) -> dict[str, object]:
    return {
        "contentType": "image",
        "assets": [
            {
                "assetId": f"asset-{index}",
                "kind": "image",
                "sha256": "sha256:"
                + hashlib.sha256(f"asset-{index}".encode()).hexdigest(),
                "perceptualHash": perceptual_hash
                or hashlib.sha256(f"phash-{index}".encode()).hexdigest()[:16],
            }
        ],
    }


def test_image_duplicate_hot_index_is_linear_and_complete_at_one_thousand(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish = tmp_path / "publish"
    publish.mkdir()
    inventory = load_or_bootstrap_inventory(publish)
    original_glob = Path.glob

    def reject_hot_scan(path: Path, pattern: str):
        if path == publish / "posts" and pattern == "**/manifest.json":
            raise AssertionError("hot duplicate lookup scanned canonical manifests")
        return original_glob(path, pattern)

    monkeypatch.setattr(Path, "glob", reject_hot_scan)

    def reject_general_inventory_scan(_root: Path):
        raise AssertionError("hot duplicate lookup scanned the canonical tree")

    monkeypatch.setattr(inventory_subject, "_files", reject_general_inventory_scan)
    size_at_one_hundred = 0
    manifests: list[dict[str, object]] = []
    for index in range(1_000):
        manifest = _manifest(index)
        manifests.append(manifest)
        relative = f"posts/image/load/{index}/manifest.json"
        assert_canonical_image_unique(
            publish_root=publish,
            manifest=manifest,
            excluded_manifest_path=relative,
        )
        payload = (json.dumps(manifest, sort_keys=True) + "\n").encode()
        destination = publish / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        inventory = apply_inventory_delta(
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
        write_inventory(publish, inventory)
        inventory = load_or_bootstrap_inventory(publish)
        if index == 99:
            size_at_one_hundred = canonical_inventory_path(publish).stat().st_size

    database = canonical_inventory_path(publish)
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM image_identities"
        ).fetchone()[0] == 1_000
        assert connection.execute(
            "SELECT COUNT(*) FROM image_perceptual_bands"
        ).fetchone()[0] == 6_000
        assert connection.execute(
            "SELECT inventory_digest FROM image_index_state"
        ).fetchone()[0] == inventory["inventoryDigest"]
    assert database.stat().st_size < size_at_one_hundred * 15

    exact = _manifest(0, perceptual_hash="f" * 16)
    with pytest.raises(ObjectTransactionError, match="duplicated by sha256"):
        assert_canonical_image_unique(
            publish_root=publish,
            manifest=exact,
            excluded_manifest_path="posts/image/load/exact/manifest.json",
        )

    first_hash = str(manifests[0]["assets"][0]["perceptualHash"])  # type: ignore[index]
    near_hash = f"{int(first_hash, 16) ^ 0b11111:016x}"
    near = _manifest(1_001, perceptual_hash=near_hash)
    with pytest.raises(ObjectTransactionError, match="duplicated by perceptualHash"):
        assert_canonical_image_unique(
            publish_root=publish,
            manifest=near,
            excluded_manifest_path="posts/image/load/near/manifest.json",
        )


def test_duplicate_manifest_rolls_back_inventory_and_image_index_together(
    tmp_path: Path,
) -> None:
    publish = tmp_path / "publish"
    publish.mkdir()
    inventory = load_or_bootstrap_inventory(publish)
    manifest = _manifest(7)
    payload = (json.dumps(manifest, sort_keys=True) + "\n").encode()

    first = "posts/image/atomic/first/manifest.json"
    first_path = publish / first
    first_path.parent.mkdir(parents=True)
    first_path.write_bytes(payload)
    inventory = apply_inventory_delta(
        inventory,
        [
            {
                "destination": first,
                "operation": "create",
                "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
            }
        ],
        publish_root=publish,
    )
    write_inventory(publish, inventory)
    before = load_or_bootstrap_inventory(publish)

    duplicate = "posts/image/atomic/duplicate/manifest.json"
    duplicate_path = publish / duplicate
    duplicate_path.parent.mkdir(parents=True)
    duplicate_path.write_bytes(payload)
    pending = apply_inventory_delta(
        before,
        [
            {
                "destination": duplicate,
                "operation": "create",
                "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
            }
        ],
        publish_root=publish,
    )
    with pytest.raises(ObjectTransactionError, match="duplicated by sha256"):
        write_inventory(publish, pending)

    assert load_or_bootstrap_inventory(publish) == before
    with sqlite3.connect(canonical_inventory_path(publish)) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM entries WHERE path = ?", (duplicate,)
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM image_identities"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT inventory_digest FROM image_index_state"
        ).fetchone()[0] == before["inventoryDigest"]


def test_image_index_follows_inverse_and_replay_delta(
    tmp_path: Path,
) -> None:
    publish = tmp_path / "publish"
    publish.mkdir()
    before = load_or_bootstrap_inventory(publish)
    manifest = _manifest(42)
    payload = (json.dumps(manifest, sort_keys=True) + "\n").encode()
    relative = "posts/image/replay/work/manifest.json"
    entry = {
        "destination": relative,
        "operation": "create",
        "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
    }
    destination = publish / relative
    destination.parent.mkdir(parents=True)
    destination.write_bytes(payload)
    applied = apply_inventory_delta(
        before,
        [entry],
        publish_root=publish,
    )
    write_inventory(publish, applied)

    destination.unlink()
    restored = apply_inventory_delta(
        load_or_bootstrap_inventory(publish),
        [entry],
        publish_root=publish,
        reverse=True,
    )
    write_inventory(publish, restored)
    assert_canonical_image_unique(
        publish_root=publish,
        manifest=manifest,
        excluded_manifest_path=relative,
    )

    destination.write_bytes(payload)
    replayed = apply_inventory_delta(
        load_or_bootstrap_inventory(publish),
        [entry],
        publish_root=publish,
    )
    write_inventory(publish, replayed)
    with sqlite3.connect(canonical_inventory_path(publish)) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM image_identities WHERE manifest_path = ?",
            (relative,),
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT inventory_digest FROM image_index_state"
        ).fetchone()[0] == replayed["inventoryDigest"]


def test_image_query_fails_closed_when_sidecar_structure_is_incomplete(
    tmp_path: Path,
) -> None:
    publish = tmp_path / "publish"
    publish.mkdir()
    load_or_bootstrap_inventory(publish)
    database = canonical_inventory_path(publish)
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE image_perceptual_bands")

    with pytest.raises(ObjectTransactionError, match="structure drift"):
        assert_canonical_image_unique(
            publish_root=publish,
            manifest=_manifest(99),
            excluded_manifest_path="posts/image/incomplete/work/manifest.json",
        )


def test_cold_bootstrap_rejects_preexisting_cross_post_duplicate(
    tmp_path: Path,
) -> None:
    publish = tmp_path / "publish"
    payload = (json.dumps(_manifest(88), sort_keys=True) + "\n").encode()
    for name in ("first", "duplicate"):
        manifest_path = publish / f"posts/image/bootstrap/{name}/manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_bytes(payload)

    with pytest.raises(ObjectTransactionError, match="duplicated by sha256"):
        load_or_bootstrap_inventory(publish)
    assert not canonical_inventory_path(publish).exists()
