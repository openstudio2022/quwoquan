"""Canonical CAS → immutable release media manifest 契约。"""
from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core.io import read_json, write_json  # noqa: E402
from core.media_asset_url import (  # noqa: E402
    is_cas_media_object_key,
    materialize_release_media,
    sha256_file,
)


def _seed_canonical() -> tuple[Path, str, str]:
    root = Path(tempfile.mkdtemp(prefix="media_asset_url_"))
    payload = b"canonical-cas-asset"
    digest = hashlib.sha256(payload).hexdigest()
    object_key = f"media/objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}.png"
    physical = root / object_key
    physical.parent.mkdir(parents=True)
    physical.write_bytes(payload)
    post_ref = "posts/article/攻略/毕棚沟攻略/1"
    post = root / post_ref
    write_json(
        post / "asset.refs.json",
        {
            "assets": [
                {
                    "assetId": "cover",
                    "objectKey": object_key,
                    "sha256": "sha256:" + digest,
                }
            ]
        },
    )
    return root, post_ref, object_key


def test_materialize_release_media_reads_closed_cas_only() -> None:
    canonical, post_ref, object_key = _seed_canonical()
    release_root = Path(tempfile.mkdtemp(prefix="release_media_"))
    report = materialize_release_media(
        release_id="release-a",
        post_refs=[post_ref],
        entity_refs=[],
        publish_root=canonical,
        release_root=release_root,
    )
    assert report["issues"] == []
    assert report["assets"][0]["objectKey"] == object_key
    path = release_root / "release-a/payload/media_manifest.json"
    assert read_json(path)["assets"] == report["assets"]
    assert (release_root / "release-a/payload" / object_key).read_bytes() == b"canonical-cas-asset"
    assert not (canonical / post_ref / "manifest.json").exists()


def test_release_media_manifest_is_create_once() -> None:
    canonical, post_ref, _ = _seed_canonical()
    release_root = Path(tempfile.mkdtemp(prefix="release_media_once_"))
    first = materialize_release_media(
        release_id="release-a",
        post_refs=[post_ref],
        entity_refs=[],
        publish_root=canonical,
        release_root=release_root,
    )
    second = materialize_release_media(
        release_id="release-a",
        post_refs=[post_ref],
        entity_refs=[],
        publish_root=canonical,
        release_root=release_root,
    )
    assert first == second


def test_invalid_or_dangling_asset_ref_fails_closed() -> None:
    canonical, post_ref, _ = _seed_canonical()
    write_json(
        canonical / post_ref / "asset.refs.json",
        {"assets": [{"objectKey": "../escape.png", "sha256": "sha256:" + "0" * 64}]},
    )
    release_root = Path(tempfile.mkdtemp(prefix="release_media_bad_"))
    report = materialize_release_media(
        release_id="release-bad",
        post_refs=[post_ref],
        entity_refs=[],
        publish_root=canonical,
        release_root=release_root,
    )
    assert report["issues"]
    assert not (release_root / "release-bad/payload/media_manifest.json").exists()


def test_cas_key_and_hash_contract() -> None:
    canonical, _, object_key = _seed_canonical()
    assert is_cas_media_object_key(object_key)
    assert not is_cas_media_object_key("../escape.png")
    assert sha256_file(canonical / object_key) == "sha256:" + object_key.split("/")[-1].split(".")[0]
