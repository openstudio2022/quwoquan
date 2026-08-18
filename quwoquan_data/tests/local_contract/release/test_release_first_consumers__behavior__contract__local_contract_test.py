from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from core.schema import assert_valid
from core.media_asset_url import materialize_release_media
from core.release_media_binding import bind_release_object_media_assets
from content.release.canonical.build_lookup_indexes import build_publish_lookup_indexes
from content.release.environment.consistency import scan_release_contract
from support.media_fixture import admit_media_body


def _write(path: Path, payload: dict | str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, dict):
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    elif isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_bytes(payload)


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    canonical = tmp_path / "publish"
    release = tmp_path / "release/release-a"
    payload = b"asset"
    digest = hashlib.sha256(payload).hexdigest()
    key = f"media/objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}.jpg"
    admit_media_body(payload)
    post = canonical / "posts/article/攻略/甲/1"
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
    _write(post / "article.md", "# 甲")
    _write(post / "evidence/source_catalog.json", {"sources": [{"url": "https://example.com"}]})
    _write(post / "evidence/rights.json", {"rights": {"mode": "licensed"}})
    _write(post / "creator.refs.json", {"creatorRefs": ["creator-a"]})
    _write(post / "tag.refs.json", {"tagRefs": ["Topic/旅行"]})
    _write(
        post / "asset.refs.json",
        {
            "assets": [
                {
                    "assetId": "asset-a",
                    "kind": "image",
                    "mimeType": "image/jpeg",
                    "objectKey": key,
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
    creator_header = {
        "schema": "quwoquan_data.creator_object",
        "creatorId": "creator-a",
        "profileRef": "profile.json",
        "assetsRef": "assets.refs.json",
        "worksRefsRef": "works.refs.ndjson",
        "tagRefs": [],
        "entityRefs": [],
    }
    _write(canonical / "creators/creator-a/_creator.json", creator_header)
    _write(canonical / "creators/creator-a/profile.json", {"userId": "creator-a"})
    _write(canonical / "creators/creator-a/assets.refs.json", {"assets": []})
    _write(canonical / "creators/creator-a/works.refs.ndjson", "")
    tag_snapshot = {
        "label": "旅行",
        "labelEn": "travel",
        "createdAt": "2026-07-13T00:00:00Z",
        "updatedAt": "2026-07-13T00:00:00Z",
    }
    _write(canonical / "tags/Topic/旅行/_definition.json", tag_snapshot)
    desired = {
        "schema": "quwoquan_data.release_desired_state",
        "releaseId": "release-a",
        "desiredRefs": {
            "posts": ["posts/article/攻略/甲/1"],
            "entities": [],
            "creators": ["creator-a"],
            "tags": ["Topic/旅行"],
        },
    }
    for name, payload_doc in {
        "release.json": {"schema": "quwoquan_data.release", "releaseId": "release-a", "sourceOwner": "qwq_data", "releaseKind": "content", "executionIds": ["20260715--travel-homepage-coverage--test-region-a--scale-001"]},
        "desired_state.json": desired,
        "sample_bundle.json": {"schema": "quwoquan_data.release_sample", "tags": ["Topic/旅行"]},
        "index/objects.json": {
            "posts": ["posts/article/攻略/甲/1"],
            "entities": [],
            "creators": ["creator-a"],
            "tags": ["Topic/旅行"],
        },
    }.items():
        _write(release / "payload" / name, payload_doc)
    shutil.copytree(post, release / "payload/objects/posts/article/攻略/甲/1")
    shutil.copytree(
        canonical / "creators/creator-a",
        release / "payload/objects/creators/creator-a",
    )
    shutil.copytree(
        canonical / "tags/Topic/旅行",
        release / "payload/objects/tags/Topic/旅行",
    )
    media_manifest = materialize_release_media(
        release_id="release-a",
        post_refs=["posts/article/攻略/甲/1"],
        entity_refs=[],
        publish_root=canonical,
        release_root=tmp_path / "release",
    )
    bind_release_object_media_assets(
        objects_root=release / "payload/objects",
        manifest=media_manifest,
    )
    return canonical, release


def test_release_first_consumer_closure_and_deterministic_index(tmp_path: Path) -> None:
    canonical, release = _fixture(tmp_path)
    # Nothing to strip: canonical publish never held the body in the first place.
    assert not (canonical / "media").exists()
    desired = json.loads((release / "payload" / "desired_state.json").read_text(encoding="utf-8"))
    report = scan_release_contract(
        desired,
        publish_root=canonical,
        release_root=release,
    )
    assert report["status"] == "passed"
    unrelated = canonical / "posts/article/攻略/无关/1"
    _write(
        unrelated / "manifest.json",
        {
            "contentType": "article",
            "publishTitle": "不属于 release",
            "tagRefs": ["Topic/旅行"],
        },
    )
    canonical_before = _tree_bytes(canonical)
    first = build_publish_lookup_indexes(
        release_id="release-a",
        canonical_root=canonical,
        release_root=tmp_path / "release",
    )
    second = build_publish_lookup_indexes(
        release_id="release-a",
        canonical_root=canonical,
        release_root=tmp_path / "release",
    )
    assert first["indexHash"] == second["indexHash"]
    assert first["posts"] == 1
    lookup_root = release / "payload/index/lookups"
    first_bytes = _tree_bytes(lookup_root)
    build_publish_lookup_indexes(
        release_id="release-a",
        canonical_root=canonical,
        release_root=tmp_path / "release",
    )
    assert _tree_bytes(lookup_root) == first_bytes
    assert _tree_bytes(canonical) == canonical_before
    assert not (release / "index").exists()
    manifest = json.loads(
        (lookup_root / "manifest.json").read_text(encoding="utf-8")
    )
    assert_valid(
        manifest,
        "release",
        "release_lookup_index",
        label="release lookup manifest",
    )
    media = json.loads((release / "payload" / "media_manifest.json").read_text(encoding="utf-8"))
    assert "cdnUrl" not in json.dumps(media)
    assert "objectKey" not in json.dumps(media)
    assert media["assets"][0]["publicSliceKey"].startswith("media/image/s/asset/")


def test_release_consumer_rejects_noncanonical_schema_and_create_once_drift(tmp_path: Path) -> None:
    canonical, release = _fixture(tmp_path)
    noncanonical = {"schema": "invalid.release", "environment": "gamma"}
    report = scan_release_contract(noncanonical, publish_root=canonical, release_root=release)
    assert report["status"] == "failed"
    assert report["blockingIssues"][0]["code"] == "release_contract_schema_invalid"

    build_publish_lookup_indexes(
        release_id="release-a",
        canonical_root=canonical,
        release_root=tmp_path / "release",
    )
    (release / "payload/index/lookups/posts.ndjson").write_text("drift\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        build_publish_lookup_indexes(
            release_id="release-a",
            canonical_root=canonical,
            release_root=tmp_path / "release",
        )


def test_release_lookup_rejects_extra_file_and_path_escape(tmp_path: Path) -> None:
    canonical, release = _fixture(tmp_path)
    build_publish_lookup_indexes(
        release_id="release-a",
        canonical_root=canonical,
        release_root=tmp_path / "release",
    )
    _write(release / "payload/index/lookups/unexpected.txt", "drift\n")
    with pytest.raises(FileExistsError, match="immutable release index conflict"):
        build_publish_lookup_indexes(
            release_id="release-a",
            canonical_root=canonical,
            release_root=tmp_path / "release",
        )

    with pytest.raises(ValueError, match="release_id"):
        build_publish_lookup_indexes(
            release_id="../escape",
            canonical_root=canonical,
            release_root=tmp_path / "release",
        )

    desired_path = release / "payload/desired_state.json"
    desired = json.loads(desired_path.read_text(encoding="utf-8"))
    desired["desiredRefs"]["posts"] = ["../escape"]
    _write(desired_path, desired)
    shutil.rmtree(release / "payload/index/lookups")
    with pytest.raises(ValueError, match="desiredRefs.posts"):
        build_publish_lookup_indexes(
            release_id="release-a",
            canonical_root=canonical,
            release_root=tmp_path / "release",
        )


def test_release_lookup_missing_desired_state_and_partial_write_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical, release = _fixture(tmp_path)
    desired_path = release / "payload/desired_state.json"
    desired_bytes = desired_path.read_bytes()
    desired_path.unlink()
    with pytest.raises(FileNotFoundError, match="desired_state missing"):
        build_publish_lookup_indexes(
            release_id="release-a",
            canonical_root=canonical,
            release_root=tmp_path / "release",
        )

    desired_path.write_bytes(desired_bytes)
    original_write_bytes = Path.write_bytes

    def _fail_posts(path: Path, payload: bytes) -> int:
        if path.name == "posts.ndjson":
            raise OSError("injected lookup write failure")
        return original_write_bytes(path, payload)

    monkeypatch.setattr(Path, "write_bytes", _fail_posts)
    with pytest.raises(OSError, match="injected lookup write failure"):
        build_publish_lookup_indexes(
            release_id="release-a",
            canonical_root=canonical,
            release_root=tmp_path / "release",
        )
    assert not (release / "payload/index/lookups").exists()


def test_release_lookup_rejects_first_write_after_attestation(
    tmp_path: Path,
) -> None:
    canonical, release = _fixture(tmp_path)
    _write(
        release / "attestations/release.json",
        {"schema": "quwoquan_data.release_attestation"},
    )

    with pytest.raises(ValueError, match="attested release"):
        build_publish_lookup_indexes(
            release_id="release-a",
            canonical_root=canonical,
            release_root=tmp_path / "release",
        )
    assert not (release / "payload/index/lookups").exists()


def test_release_consumer_rejects_unrelated_canonical_media(tmp_path: Path) -> None:
    canonical, release = _fixture(tmp_path)
    payload = b"unrelated"
    digest = hashlib.sha256(payload).hexdigest()
    key = f"media/objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}.jpg"
    _write(canonical / key, payload)
    media_path = release / "payload/media_manifest.json"
    media = json.loads(media_path.read_text(encoding="utf-8"))
    media["assets"].append(
        {
            "assetId": "unrelated",
            "kind": "image",
            "version": 1,
            "contentType": "image/jpeg",
            "publicSliceKey": "media/image/s/asset/unrelated/v1/source.jpg",
            "sha256": f"sha256:{digest}",
            "bytes": len(payload),
            "ownerRefs": ["posts/article/攻略/无关/1"],
            "rightsSnapshotRefs": [],
        }
    )
    _write(
        release / "payload/media/image/s/asset/unrelated/v1/source.jpg",
        payload,
    )
    media["counts"]["assets"] += 1
    _write(media_path, media)

    report = scan_release_contract(
        json.loads((release / "payload/desired_state.json").read_text(encoding="utf-8")),
        publish_root=canonical,
        release_root=release,
    )

    assert report["status"] == "failed"
    assert any(issue["code"] == "release_media_closure_mismatch" for issue in report["blockingIssues"])


def test_release_consumer_rejects_public_slice_identity_drift(tmp_path: Path) -> None:
    canonical, release = _fixture(tmp_path)
    media_path = release / "payload/media_manifest.json"
    media = json.loads(media_path.read_text(encoding="utf-8"))
    media["assets"][0]["kind"] = "video"
    _write(media_path, media)

    report = scan_release_contract(
        json.loads((release / "payload/desired_state.json").read_text(encoding="utf-8")),
        publish_root=canonical,
        release_root=release,
    )

    assert report["status"] == "failed"
    assert any(
        issue["code"] == "release_media_public_slice_identity_mismatch"
        for issue in report["blockingIssues"]
    )


def test_release_consumer_rejects_private_cas_in_object_snapshot(tmp_path: Path) -> None:
    canonical, release = _fixture(tmp_path)
    asset_refs_path = release / "payload/objects/posts/article/攻略/甲/1/asset.refs.json"
    asset_refs = json.loads(asset_refs_path.read_text(encoding="utf-8"))
    asset_refs["assets"][0]["objectKey"] = (
        "media/objects/sha256/aa/bb/" + "a" * 64 + ".jpg"
    )
    _write(asset_refs_path, asset_refs)

    report = scan_release_contract(
        json.loads((release / "payload/desired_state.json").read_text(encoding="utf-8")),
        publish_root=canonical,
        release_root=release,
    )

    assert report["status"] == "failed"
    assert any(
        issue["code"] == "release_object_private_storage_leak"
        for issue in report["blockingIssues"]
    )
