# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/design.md#dec-031
"""DEC-031：research release 媒体以 CAS objectKey 私有交付，commercial 保留公开切片。"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from content.release.environment.release_runtime import release_media_public_slices
from core.media_asset_url import (
    build_release_media_manifest,
    copy_release_media_objects,
)
from core.schema import assert_valid
from support.media_fixture import admit_media_body

_POST_REF = "posts/article/攻略/甲/1"
_PUBLIC_SLICE_SEGMENT_RE = re.compile(r"^media/(avatar|image|video)/s/")


def _write(path: Path, payload: dict | str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, dict):
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    elif isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_bytes(payload)


def _canonical_fixture(tmp_path: Path) -> tuple[Path, str, str]:
    """构造持有一个 image 资产的 canonical post，返回 (publish_root, cas_key, sha256)。"""
    canonical = tmp_path / "publish"
    body = b"private-delivery-asset"
    digest = hashlib.sha256(body).hexdigest()
    cas_key = f"media/objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}.jpg"
    admit_media_body(body)
    post = canonical / _POST_REF
    _write(
        post / "manifest.json",
        {
            "schema": "quwoquan_data.post_object",
            "contentType": "article",
            "finalContentRef": "article.md",
            "sourceCatalogRef": "evidence/source_catalog.json",
            "rightsRef": "evidence/rights.json",
            "creatorRefsRef": "creator.refs.json",
            "tagRefsRef": "tag.refs.json",
            "assetRefsRef": "asset.refs.json",
        },
    )
    _write(
        post / "asset.refs.json",
        {
            "assets": [
                {
                    "assetId": "asset-a",
                    "kind": "image",
                    "mimeType": "image/jpeg",
                    "objectKey": cas_key,
                    "sha256": f"sha256:{digest}",
                }
            ]
        },
    )
    _write(
        post / "rights_snapshots/asset-a.json",
        {
            "assetId": "asset-a",
            "manifestAsset": {
                "assetId": "asset-a",
                "sha256": f"sha256:{digest}",
            },
        },
    )
    return canonical, cas_key, f"sha256:{digest}"


def _manifest(tmp_path: Path, release_class: str) -> tuple[dict, str, str]:
    canonical, cas_key, sha256 = _canonical_fixture(tmp_path)
    manifest = build_release_media_manifest(
        release_id="release-a",
        post_refs=[_POST_REF],
        entity_refs=[],
        publish_root=canonical,
        release_class=release_class,
    )
    assert manifest["issues"] == []
    return manifest, cas_key, sha256


def test_research_manifest_uses_private_object_key(tmp_path: Path) -> None:
    manifest, cas_key, _ = _manifest(tmp_path, "research")
    (row,) = manifest["assets"]
    assert row["privateObjectKey"] == cas_key
    assert "publicSliceKey" not in row
    # 探针两项判定的负例：非公开 slice 路径段、非绝对 URL。
    assert not _PUBLIC_SLICE_SEGMENT_RE.match(row["privateObjectKey"])
    assert not row["privateObjectKey"].startswith(("http://", "https://"))


def test_commercial_manifest_keeps_public_slice(tmp_path: Path) -> None:
    manifest, _, _ = _manifest(tmp_path, "commercial")
    (row,) = manifest["assets"]
    assert "privateObjectKey" not in row
    assert _PUBLIC_SLICE_SEGMENT_RE.match(row["publicSliceKey"])


def test_manifest_build_rejects_unknown_release_class(tmp_path: Path) -> None:
    canonical, _, _ = _canonical_fixture(tmp_path)
    with pytest.raises(ValueError, match="release class"):
        build_release_media_manifest(
            release_id="release-a",
            post_refs=[_POST_REF],
            entity_refs=[],
            publish_root=canonical,
            release_class="prod-gray",
        )


def test_manifest_schema_rejects_dual_or_absent_delivery_keys(tmp_path: Path) -> None:
    manifest, cas_key, _ = _manifest(tmp_path, "commercial")
    dual = json.loads(json.dumps(manifest))
    dual["assets"][0]["privateObjectKey"] = cas_key
    with pytest.raises(ValueError):
        assert_valid(dual, "release", "media_manifest", label="dual-delivery")
    absent = json.loads(json.dumps(manifest))
    del absent["assets"][0]["publicSliceKey"]
    with pytest.raises(ValueError):
        assert_valid(absent, "release", "media_manifest", label="absent-delivery")


def test_copy_places_research_bodies_at_private_object_key(tmp_path: Path) -> None:
    manifest, cas_key, sha256 = _manifest(tmp_path, "research")
    release_root = tmp_path / "release/release-a"
    copy_release_media_objects(manifest=manifest, release_root=release_root)
    body = release_root / "payload" / cas_key
    assert body.is_file()
    assert f"sha256:{hashlib.sha256(body.read_bytes()).hexdigest()}" == sha256


def _release_dir(tmp_path: Path, release_class: str, manifest: dict) -> Path:
    release = tmp_path / "release/release-a"
    _write(release / "payload/release.json", {"releaseClass": release_class})
    _write(release / "payload/media_manifest.json", manifest)
    return release


def test_sync_slices_follow_release_class(tmp_path: Path) -> None:
    manifest, cas_key, sha256 = _manifest(tmp_path, "research")
    release = _release_dir(tmp_path, "research", manifest)
    assert release_media_public_slices(release) == {cas_key: sha256}


def test_sync_slices_fail_closed_on_class_form_mismatch(tmp_path: Path) -> None:
    research_manifest, _, _ = _manifest(tmp_path, "research")
    commercial_release = _release_dir(tmp_path, "commercial", research_manifest)
    with pytest.raises(SystemExit, match="commercial release 不得携带私有交付 key"):
        release_media_public_slices(commercial_release)

    commercial_manifest, _, _ = _manifest(tmp_path / "second", "commercial")
    research_release = _release_dir(tmp_path / "second", "research", commercial_manifest)
    with pytest.raises(SystemExit, match="research release 不得携带公开交付 slice"):
        release_media_public_slices(research_release)
