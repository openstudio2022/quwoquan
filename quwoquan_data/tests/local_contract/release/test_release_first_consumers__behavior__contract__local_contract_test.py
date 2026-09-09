"""Release 只消费随体对象，来源权限与原始证据不得被投影改写。

spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#req-009
"""

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
from content.release.canonical.release_consistency import scan_release_contract
from support.media_fixture import tiny_png_bytes


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
    payload = tiny_png_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    source_evidence = b"Fixture source: test author; rights unknown; no authorization granted.\n"
    source_ref = "sources/s001/source.json"
    post = canonical / "posts/article/攻略/甲/1"
    _write(
        post / "manifest.json",
        {
            "schema": "quwoquan_data.post_object",
            "objectRef": "article/攻略/甲/1",
            "contentId": "post-a",
            "version": 1,
            "contentType": "article",
            "finalContentRef": "article.md",
            "sourceRefs": [source_ref],
            "creatorProfileId": "creator-a",
            "tagRefs": ["Topic/旅行"],
            "assets": [{
                "assetId": "asset-a", "kind": "image", "mimeType": "image/png",
                "path": "media/asset-a.png", "sha256": f"sha256:{digest}",
                "bytes": len(payload), "sourceRefs": [source_ref],
            }],
        },
    )
    _write(post / "article.md", "# 甲")
    _write(post / "media/asset-a.png", payload)
    _write(post / "sources/s001/evidence.txt", source_evidence)
    source = {
        "schema": "quwoquan_data.publish_source",
        "sourceId": "s001",
        "sourceUrl": "https://example.com/source-a",
        "sourceUseMode": "factual_reference_only",
        "fetchedAt": "2026-09-09T00:00:00Z",
        "metadata": {
            "author": "Fixture Author",
            "license": "unknown",
            "accessPolicy": "tos_restricted",
        },
        "assets": [{
            "assetId": "asset-a",
            "sha256": f"sha256:{digest}",
            "rightsStatus": "unknown",
            "authorizationRequired": True,
        }],
        "evidence": [{
            "path": "evidence.txt",
            "sha256": "sha256:" + hashlib.sha256(source_evidence).hexdigest(),
            "bytes": len(source_evidence),
            "kind": "source_excerpt",
        }],
    }
    assert_valid(source, "publish", "source", label="release-first source fixture")
    _write(post / source_ref, source)
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
    _write(canonical / "creators/creator-a/profile.json", {"userId": "creator-a", "assets": []})
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
        "release.json": {"schema": "quwoquan_data.release", "releaseId": "release-a", "sourceOwner": "qwq_data", "releaseKind": "content", "releaseClass": "production", "executionIds": ["20260715--travel-homepage-coverage--test-region-a--scale-001"]},
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
    assert media_manifest["issues"] == []
    release_source = release / "payload/objects/posts/article/攻略/甲/1/sources/s001"
    source_files = (release_source / "source.json", release_source / "evidence.txt")
    for path in source_files:
        path.chmod(0o444)
    source_before = {path: (path.read_bytes(), path.stat().st_mode) for path in source_files}
    bind_release_object_media_assets(
        objects_root=release / "payload/objects",
        manifest=media_manifest,
    )
    assert {path: (path.read_bytes(), path.stat().st_mode) for path in source_files} == source_before
    return canonical, release


def test_release_first_consumer_closure_and_deterministic_index(tmp_path: Path) -> None:
    canonical, release = _fixture(tmp_path)
    # 媒体只在所选对象包随体携带，不需要全局 CAS 或原库。
    assert (canonical / "posts/article/攻略/甲/1/media/asset-a.png").read_bytes() == tiny_png_bytes()
    assert not (canonical / "media").exists()
    source_ref = "posts/article/攻略/甲/1/sources/s001/source.json"
    source_before = (canonical / source_ref).read_bytes()
    assert (release / "payload/objects" / source_ref).read_bytes() == source_before
    desired = json.loads((release / "payload" / "desired_state.json").read_text(encoding="utf-8"))
    report = scan_release_contract(
        desired,
        publish_root=canonical,
        release_root=release,
    )
    assert report["status"] == "passed", report["blockingIssues"]
    unrelated = canonical / "posts/article/攻略/无关/1"
    _write(
        unrelated / "manifest.json",
        {
            "objectRef": "article/攻略/无关/1",
            "version": 1,
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


@pytest.mark.parametrize("corruption", ["missing_source", "evidence_drift", "asset_identity_drift", "legacy_rights_ref"])
def test_release_consumer_rejects_invalid_carried_source(tmp_path: Path, corruption: str) -> None:
    canonical, release = _fixture(tmp_path)
    source_root = release / "payload/objects/posts/article/攻略/甲/1/sources/s001"
    source_path = source_root / "source.json"
    if corruption == "missing_source":
        source_path.unlink()
    elif corruption == "evidence_drift":
        evidence = source_root / "evidence.txt"
        evidence.chmod(0o644)
        evidence.write_bytes(b"changed source evidence")
    elif corruption == "asset_identity_drift":
        source = json.loads(source_path.read_text(encoding="utf-8"))
        source["assets"][0]["sha256"] = "sha256:" + "0" * 64
        source_path.chmod(0o644)
        _write(source_path, source)
    else:
        media_path = release / "payload/media_manifest.json"
        media = json.loads(media_path.read_text(encoding="utf-8"))
        media["assets"][0]["rightsSnapshotRefs"] = ["objects/posts/article/攻略/甲/1/rights_snapshots/asset-a.json"]
        _write(media_path, media)
    before = _tree_bytes(release)
    report = scan_release_contract(
        json.loads((release / "payload/desired_state.json").read_text(encoding="utf-8")),
        publish_root=canonical,
        release_root=release,
    )
    assert report["status"] == "failed"
    codes = {issue["code"] for issue in report["blockingIssues"]}
    expected = {
        "missing_source": "object_evidence_missing",
        "evidence_drift": "release_media_rights_snapshot_invalid",
        "asset_identity_drift": "release_media_rights_identity_mismatch",
        "legacy_rights_ref": "release_media_rights_refs_invalid",
    }
    assert expected[corruption] in codes
    assert _tree_bytes(release) == before


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
    asset_refs_path = release / "payload/objects/posts/article/攻略/甲/1/manifest.json"
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
