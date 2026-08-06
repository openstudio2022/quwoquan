"""Canonical publish closure 必须分层：热路径 O(Δ)，全量 orphan 只在 release 边界。

per-object 事务不得把 closure 结论写成硬编码 passed，也不得为了拿到结论去扫全树；
全量 orphan 扫描仍然只属于 release 与 verify 门。
"""
from __future__ import annotations

import hashlib
import json
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
from support.object_transaction_fixtures import (
    TRANSACTION_ID,
    build_canonical,
    build_package,
)

_CAS_PREFIX = "media/objects/sha256"


def _object_key(payload: bytes, suffix: str = "jpg") -> str:
    digest = hashlib.sha256(payload).hexdigest()
    return f"{_CAS_PREFIX}/{digest[:2]}/{digest[2:4]}/{digest}.{suffix}"


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


def test_delta_closure_blocks_environment_media_url_and_non_work_identity(
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
                "contentIdentity": "draft",
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
    assert "post_content_identity_invalid" in _codes(report)
    assert "environment_media_url_in_canonical" in _codes(report)


def test_delta_closure_resolves_cas_from_same_delta_and_blocks_dangling(
    tmp_path: Path,
) -> None:
    publish = build_canonical(tmp_path)
    run_root = tmp_path / "run"
    cover = b"cover-bytes"
    object_key = _object_key(cover)

    def _manifest(key: str) -> dict[str, object]:
        return {
            "schema": "quwoquan_data.post_object",
            "contentIdentity": "work",
            "contentType": "image",
            "assets": [{"assetId": "cover", "kind": "image", "objectKey": key}],
        }

    closed = validate_publish_delta(
        publish_root=publish,
        run_root=run_root,
        entries=[
            _entry(run_root, object_key, cover),
            _entry(run_root, "posts/image/摄影/作品/1/manifest.json", _manifest(object_key)),
        ],
    )
    assert closed["status"] == "passed", closed["issues"]
    assert closed["deltaFileCount"] == 2

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
                    "contentIdentity": "work",
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


def test_delta_closure_leaves_global_orphans_to_release_invariants(
    tmp_path: Path,
) -> None:
    publish = build_canonical(tmp_path)
    orphan = publish / _object_key(b"orphan-bytes")
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_bytes(b"orphan-bytes")
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
    invariants = validate_publish_invariants(publish)

    assert "orphan_media" not in _codes(delta)
    assert "orphan_media" in _codes(invariants)
    assert invariants["status"] == "failed"


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

    assert "entity_creator_closure_missing" in str(failure.value)


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
