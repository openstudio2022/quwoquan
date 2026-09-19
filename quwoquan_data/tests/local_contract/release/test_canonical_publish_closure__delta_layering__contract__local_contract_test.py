"""Canonical publish closure 必须分层：热路径 O(Δ)，全量 orphan 只在 release 边界。

per-object 事务不得把 closure 结论写成硬编码 passed，也不得为了拿到结论去扫全树；
全量 orphan 扫描仍然只属于 release 与 verify 门。
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from content.release.canonical import object_transaction_audit as audit_module
from content.release.canonical.canonical_inventory import load_or_bootstrap_inventory
from content.release.canonical.object_transaction_audit import (
    audit_object_transaction,
    validate_publish_delta,
    validate_publish_invariants,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
)
from support.media_fixture import admit_media_body
from support import object_transaction_fixtures as shared_fixtures
from support.object_transaction_fixtures import TRANSACTION_ID

_CAS_PREFIX = "media/objects/sha256"


def _object_key(payload: bytes, suffix: str = "jpg") -> str:
    digest = hashlib.sha256(payload).hexdigest()
    return f"{_CAS_PREFIX}/{digest[:2]}/{digest[2:4]}/{digest}.{suffix}"


_ENTITY_REF = "地点/中国/浙江省/杭州市/西湖区/景区/真实地点/1"
_ENTITY_PATH = "entities/地点/中国/浙江省/杭州市/西湖区/景区/p0001/真实地点/1"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def build_canonical(root: Path) -> Path:
    """把共享 canonical 树绑定为隔离的 current publish repository。"""
    publish = shared_fixtures.build_canonical(root)
    (publish / ".git").mkdir(exist_ok=True)
    _write_json(
        publish / "repository.json",
        {
            "schema": "quwoquan_data.publish_repository.v2",
            "repositoryId": "canonical-publish-closure-test",
            "layoutVersion": 2,
        },
    )
    return publish


def build_package(
    root: Path,
    canonical: Path,
    *,
    entity_extra: dict | None = None,
) -> Path:
    """把共享输入投影成现役 logical identity 与 layout-v2 package。"""
    previous_ref = shared_fixtures.OBJECT_REF
    previous_closure_digest = shared_fixtures.transaction._closure_digest
    shared_fixtures.OBJECT_REF = _ENTITY_REF
    shared_fixtures.transaction._closure_digest = lambda **_kwargs: "pending"
    try:
        package = shared_fixtures.build_package(root, canonical)
    finally:
        shared_fixtures.OBJECT_REF = previous_ref
        shared_fixtures.transaction._closure_digest = previous_closure_digest

    object_root = package / "object"
    (object_root / "_entity.json").unlink()
    for retired in ("evidence", "evidence_index.json"):
        target = object_root / retired
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink(missing_ok=True)
    media = object_root / "media/cover.jpg"
    media.parent.mkdir(parents=True)
    media.write_bytes((package / "cas/image.jpg").read_bytes())
    digest = "sha256:" + hashlib.sha256(media.read_bytes()).hexdigest()
    evidence = b"fixture source evidence\n"
    evidence_path = object_root / "sources/s001/evidence.txt"
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_bytes(evidence)
    source_ref = "sources/s001/source.json"
    _write_json(
        object_root / source_ref,
        {
            "schema": "quwoquan_data.publish_source",
            "sourceId": "s001",
            "sourceUrl": "https://zh.wikipedia.org/wiki/真实地点",
            "sourceUseMode": "licensed_adaptation",
            "fetchedAt": "2026-07-11T00:00:00Z",
            "metadata": {},
            "assets": [{"assetId": "cover"}],
            "evidence": [{
                "path": "evidence.txt",
                "sha256": "sha256:" + hashlib.sha256(evidence).hexdigest(),
                "bytes": len(evidence),
                "kind": "source_snapshot",
            }],
        },
    )
    manifest = {
        "schema": "quwoquan_data.entity_object",
        "entityId": "entity:canonical-publish-closure-test",
        "entityRef": "/entity/" + _ENTITY_REF,
        "version": 1,
        "label": "真实地点",
        "domain": "地点",
        "type": "景区",
        "geographyMode": "administrative",
        "geoTagRef": "Topic/地理/行政区/中国/浙江省/杭州市/西湖区",
        "contentType": "homepage",
        "publishMediaMode": "not_applicable",
        "creatorProfileId": shared_fixtures.CREATOR_ID,
        "tagRefs": [shared_fixtures.TAG_REF],
        "sourceRefs": [source_ref],
        "sourceUrls": ["https://zh.wikipedia.org/wiki/真实地点"],
        "finalContentRef": "page.md",
        "assets": [{
            "assetId": "cover",
            "kind": "image",
            "path": "media/cover.jpg",
            "objectKey": _object_key(media.read_bytes()),
            "sha256": digest,
            "bytes": media.stat().st_size,
            "sourceRefs": [source_ref],
        }],
        **(entity_extra or {}),
    }
    _write_json(object_root / "manifest.json", manifest)

    package_document = json.loads(
        (package / "object_transaction_package.json").read_text(encoding="utf-8")
    )
    package_document["target"].update(
        objectRef=_ENTITY_REF,
        objectPath=_ENTITY_PATH,
    )
    package_document["closure"].pop("sourceCatalogRef", None)
    package_document["closure"].pop("rightsRef", None)
    package_document["closure"]["sourceRefs"] = [source_ref]
    package_document["closure"]["casRefs"] = [{
        "sourceRef": "object/media/cover.jpg",
        "objectKey": manifest["assets"][0]["objectKey"],
        "sha256": digest,
        "bytes": media.stat().st_size,
    }]
    review = {"contentReviewRef": "content_review.json"}
    review_binding = shared_fixtures.transaction._review_binding(
        object_root, {"review": review}
    )
    package_document["semanticBinding"] = {
        key: review_binding[key]
        for key in ("protocol", "objectRevision", "dispositionsDigest")
    }
    package_document["objectClosureDigest"] = (
        shared_fixtures.transaction._closure_digest(
            object_root=object_root,
            object_kind="entities",
            object_ref=_ENTITY_REF,
            target_schema="quwoquan_data.entity_object",
            source_policy_revision=shared_fixtures.SOURCE_POLICY,
            closure=package_document["closure"],
            cas_rows=[dict(package_document["closure"]["casRefs"][0])],
            review=review_binding,
        )
    )
    _write_json(package / "object_transaction_package.json", package_document)
    return package


def _entry(run_root: Path, destination: str, payload: object) -> dict[str, object]:
    """在事务 delta blob store 里落一个候选文件，并返回它的 delta entry。"""
    if isinstance(payload, bytes):
        data = payload
    else:
        data = (
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
        ).encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    ref = Path("delta/blobs/sha256") / digest[:2] / digest
    blob = run_root / ref
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(data)
    return {
        "destination": destination,
        "operation": "create",
        "blobRef": ref.as_posix(),
        "sha256": f"sha256:{digest}",
        "bytes": len(data),
    }


def _codes(report: dict) -> set[str]:
    return {str(issue["code"]) for issue in report["issues"]}


def test_delta_closure_blocks_environment_media_url(
    tmp_path: Path,
) -> None:
    publish = build_canonical(tmp_path)
    run_root = tmp_path / "run"
    cover = b"cover-bytes"
    object_key = _object_key(cover)
    entries = [
        _entry(run_root, object_key, cover),
        _entry(
            run_root,
            "posts/image/摄影/作品/1/manifest.json",
            {
                "schema": "quwoquan_data.post_object",
                "contentType": "image",
                "assets": [
                    {
                        "assetId": "cover",
                        "kind": "image",
                        "objectKey": object_key,
                        "cdnUrl": "https://cdn.example.com/cover.jpg",
                    }
                ],
            },
        ),
    ]

    report = validate_publish_delta(
        publish_root=publish,
        run_root=run_root,
        entries=entries,
    )

    assert report["status"] == "failed"
    assert "environment_media_url_in_canonical" in _codes(report)


def test_delta_closure_resolves_media_from_library_and_blocks_dangling(
    tmp_path: Path,
) -> None:
    publish = build_canonical(tmp_path)
    run_root = tmp_path / "run"
    cover = b"cover-bytes"
    object_key = _object_key(cover)
    admit_media_body(cover)

    def _manifest(key: str) -> dict[str, object]:
        return {
            "schema": "quwoquan_data.post_object",
            "contentType": "image",
            "assets": [{"assetId": "cover", "kind": "image", "objectKey": key}],
        }

    # The delta carries the manifest alone; the body it cites is already held by
    # the library, which is where the reference closes.
    closed = validate_publish_delta(
        publish_root=publish,
        run_root=run_root,
        entries=[
            _entry(run_root, "posts/image/摄影/作品/1/manifest.json", _manifest(object_key)),
        ],
    )
    assert closed["status"] == "passed", closed["issues"]
    assert closed["deltaFileCount"] == 1

    missing = _object_key(b"never-ingested")
    dangling = validate_publish_delta(
        publish_root=publish,
        run_root=run_root,
        entries=[
            _entry(run_root, "posts/image/摄影/作品/2/manifest.json", _manifest(missing)),
        ],
    )
    assert dangling["status"] == "failed"
    assert "dangling_asset_ref" in _codes(dangling)

    non_cas = validate_publish_delta(
        publish_root=publish,
        run_root=run_root,
        entries=[
            _entry(
                run_root,
                "posts/image/摄影/作品/3/manifest.json",
                _manifest("media/legacy/cover.jpg"),
            ),
        ],
    )
    assert non_cas["status"] == "failed"
    assert "non_cas_asset_ref" in _codes(non_cas)


def test_delta_rejects_a_noncanonical_file_under_a_canonical_root(
    tmp_path: Path,
) -> None:
    publish = build_canonical(tmp_path)
    run_root = tmp_path / "run"

    report = validate_publish_delta(
        publish_root=publish,
        run_root=run_root,
        entries=[
            _entry(run_root, "posts/image/摄影/作品/1/assets/cover.jpg", b"cover-bytes"),
        ],
    )

    assert report["status"] == "failed"
    assert "noncanonical_file" in _codes(report)


def test_delta_closure_blocks_video_poster_closure_gap(tmp_path: Path) -> None:
    publish = build_canonical(tmp_path)
    run_root = tmp_path / "run"
    movie = b"movie-bytes"
    video_key = _object_key(movie, suffix="mp4")

    report = validate_publish_delta(
        publish_root=publish,
        run_root=run_root,
        entries=[
            _entry(run_root, video_key, movie),
            _entry(
                run_root,
                "posts/video/纪录/作品/1/manifest.json",
                {
                    "schema": "quwoquan_data.post_object",
                    "contentType": "video",
                    "assets": [
                        {
                            "assetId": "movie",
                            "kind": "video",
                            "objectKey": video_key,
                            "posterAssetId": "cover",
                        }
                    ],
                },
            ),
        ],
    )

    assert report["status"] == "failed"
    assert "video_poster_closure_invalid" in _codes(report)


def test_delta_closure_leaves_stray_media_bytes_to_release_invariants(
    tmp_path: Path,
) -> None:
    publish = build_canonical(tmp_path)
    stray = publish / _object_key(b"stray-bytes")
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_bytes(b"stray-bytes")
    run_root = tmp_path / "run"

    delta = validate_publish_delta(
        publish_root=publish,
        run_root=run_root,
        entries=[
            _entry(
                run_root,
                "tags/Topic/旅行/_definition.json",
                {"schema": "quwoquan_data.tag_definition"},
            )
        ],
    )
    # Delta validation remains O(Δ), while the repository-wide scanner rejects
    # an undeclared root before interpreting any object documents beneath it.
    assert "noncanonical_root" not in _codes(delta)
    with pytest.raises(ValueError, match="DATA.REPOSITORY.ROOT_ENTRY_INVALID: media"):
        validate_publish_invariants(publish)


def test_audit_blocks_entity_creator_closure_gap(tmp_path: Path) -> None:
    publish = build_canonical(tmp_path)
    package = build_package(
        tmp_path,
        publish,
        entity_extra={"creatorProfileId": "creator_not_in_refs"},
    )

    with pytest.raises(ObjectTransactionError) as failure:
        audit_object_transaction(
            publish_root=publish,
            output_root=tmp_path / ".qwq_output",
            package_root=package,
            transaction_id=TRANSACTION_ID,
            expected_canonical_merkle=load_or_bootstrap_inventory(publish)["stats"][
                "merkleRoot"
            ],
        )

    assert "dangling_creator_ref" in str(failure.value)


def test_audit_reports_delta_scoped_closure_without_full_tree_scan(
    monkeypatch,
    tmp_path: Path,
) -> None:
    publish = build_canonical(tmp_path)
    package = build_package(tmp_path, publish)

    def _unexpected_full_scan(_root: Path) -> dict:
        raise AssertionError("per-object transaction called the release invariants scan")

    monkeypatch.setattr(
        audit_module, "validate_publish_invariants", _unexpected_full_scan
    )
    report = audit_object_transaction(
        publish_root=publish,
        output_root=tmp_path / ".qwq_output",
        package_root=package,
        transaction_id=TRANSACTION_ID,
        expected_canonical_merkle=load_or_bootstrap_inventory(publish)["stats"][
            "merkleRoot"
        ],
    )

    assert report["closure"]["status"] == "passed"
    assert report["closure"]["validationScope"] == "delta"
    assert report["closure"]["deltaFileCount"] == report["deltaFileCount"]
