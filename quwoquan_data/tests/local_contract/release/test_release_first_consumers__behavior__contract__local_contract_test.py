from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from core.media_asset_url import materialize_release_media
from content.release.canonical.build_lookup_indexes import build_publish_lookup_indexes
from content.release.environment.consistency import scan_release_contract


def _write(path: Path, payload: dict | str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, dict):
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    elif isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_bytes(payload)


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    canonical = tmp_path / "publish"
    release = tmp_path / "release/release-a"
    payload = b"asset"
    digest = hashlib.sha256(payload).hexdigest()
    key = f"media/objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}.jpg"
    _write(canonical / key, payload)
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
    _write(post / "asset.refs.json", {"assets": [{"objectKey": key, "sha256": f"sha256:{digest}"}]})
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
        "release.json": {"schema": "quwoquan_data.release", "releaseId": "release-a", "releaseKind": "content", "executionIds": ["20260715--travel-homepage-coverage--test-region-a--scale-001"]},
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
    materialize_release_media(
        release_id="release-a",
        post_refs=["posts/article/攻略/甲/1"],
        entity_refs=[],
        publish_root=canonical,
        release_root=tmp_path / "release",
    )
    return canonical, release


def test_release_first_consumer_closure_and_deterministic_index(tmp_path: Path) -> None:
    canonical, release = _fixture(tmp_path)
    shutil.rmtree(canonical / "media")
    desired = json.loads((release / "payload" / "desired_state.json").read_text(encoding="utf-8"))
    report = scan_release_contract(
        desired,
        publish_root=canonical,
        release_root=release,
    )
    assert report["status"] == "passed"
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
    media = json.loads((release / "payload" / "media_manifest.json").read_text(encoding="utf-8"))
    assert "cdnUrl" not in json.dumps(media)


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


def test_release_consumer_rejects_unrelated_canonical_media(tmp_path: Path) -> None:
    canonical, release = _fixture(tmp_path)
    payload = b"unrelated"
    digest = hashlib.sha256(payload).hexdigest()
    key = f"media/objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}.jpg"
    _write(canonical / key, payload)
    media_path = release / "payload/media_manifest.json"
    media = json.loads(media_path.read_text(encoding="utf-8"))
    media["assets"].append({"objectKey": key, "sha256": f"sha256:{digest}", "bytes": len(payload)})
    _write(media_path, media)

    report = scan_release_contract(
        json.loads((release / "payload/desired_state.json").read_text(encoding="utf-8")),
        publish_root=canonical,
        release_root=release,
    )

    assert report["status"] == "failed"
    assert any(issue["code"] == "release_media_closure_mismatch" for issue in report["blockingIssues"])
