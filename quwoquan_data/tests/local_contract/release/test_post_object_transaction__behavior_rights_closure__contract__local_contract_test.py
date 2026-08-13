"""场景组：来源权利闭包、sourceUseMode 真值与 video poster CAS 闭包。

从 test_post_object_transaction__behavior__contract__local_contract_test.py
按场景拆出；测试逐字搬移。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from content.release.canonical.application import apply_object_transaction
from content.release.canonical.canonical_inventory import load_or_bootstrap_inventory
from content.release.canonical.object_transaction_audit import (
    audit_object_transaction,
    validate_publish_invariants,
)
from content.release.canonical.post_transaction import (
    ObjectTransactionError,
)
from core.schema import validate_result
from core.source_digest import (
    current_execution_bundle_identity,
    current_source_definition_snapshot,
)
from PIL import Image

from support.post_object_transaction_fixture import (
    CREATOR_REF,
    POST_REF,
    _admit_packaged_creator,
    _copy_creator_avatar_cas,
    _fixture,
    _force_commercial_lifecycle,
    _isolate_creator_avatar_cas,
    _source_attribution,
    _write_json,
    build_post_object_transaction_package,
)


def test_travel_commercial_asset_blocks_unverified_rights(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _force_commercial_lifecycle(monkeypatch)
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    manifest_path = execution / "posts" / POST_REF / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    asset = manifest["assets"][0]
    asset["creator"] = ""
    asset["license"] = ""
    asset["termsUrl"] = ""
    asset["authorizationProof"] = ""
    asset["rightsAuditStatus"] = "unverified"
    asset["rightsAuditIssues"] = [
        "imageRights: missing required field license",
        "imageRights: missing required field credit",
    ]
    _write_json(manifest_path, manifest)
    source_index_path = execution / "sources/commons/assets/index.json"
    source_index = json.loads(source_index_path.read_text(encoding="utf-8"))
    source_asset = source_index["assets"][0]
    source_asset["authorizationProof"] = ""
    source_asset["termsUrl"] = ""
    source_asset["creator"] = ""
    source_asset["license"] = ""
    source_asset["rightsAuditStatus"] = "unverified"
    source_asset["rightsAuditIssues"] = list(asset["rightsAuditIssues"])
    _write_json(source_index_path, source_index)

    with pytest.raises(
        ObjectTransactionError,
        match="权利审计仍有未关闭问题",
    ):
        build_post_object_transaction_package(
            execution_root=execution,
            object_ref=POST_REF,
            transaction_id=transaction_id,
            package_root=package,
        )


def test_travel_commercial_asset_blocks_unverified_collection_page_rights(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _force_commercial_lifecycle(monkeypatch)
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    manifest_path = execution / "posts" / POST_REF / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sourceUrls"] = ["https://content.example.test/article/landscape"]
    asset = manifest["assets"][0]
    asset.pop("sourceAssetId", None)
    asset["collectionPageUrl"] = "https://travel.example.test/article/landscape"
    asset["creator"] = ""
    asset["license"] = ""
    asset["termsUrl"] = ""
    asset["authorizationProof"] = ""
    asset["rightsAuditStatus"] = "unverified"
    asset["rightsAuditIssues"] = ["imageRights: source terms not yet verified"]
    _write_json(manifest_path, manifest)
    source_refs_path = execution / "posts" / POST_REF / "1.download/source_refs.json"
    source_refs = json.loads(source_refs_path.read_text(encoding="utf-8"))
    source_refs["sources"][0]["sourceUrl"] = (
        "https://content.example.test/article/landscape"
    )
    _write_json(source_refs_path, source_refs)
    source_index_path = execution / "sources/commons/assets/index.json"
    source_index = json.loads(source_index_path.read_text(encoding="utf-8"))
    source_asset = source_index["assets"][0]
    source_asset.update(
        {
            "authorizationProof": "",
            "termsUrl": "",
            "creator": "",
            "license": "",
            "rightsAuditStatus": "unverified",
            "rightsAuditIssues": ["imageRights: source terms not yet verified"],
        }
    )
    _write_json(source_index_path, source_index)

    with pytest.raises(
        ObjectTransactionError,
        match="权利审计仍有未关闭问题",
    ):
        build_post_object_transaction_package(
            execution_root=execution,
            object_ref=POST_REF,
            transaction_id=transaction_id,
            package_root=package,
        )


def test_canonical_source_catalog_preserves_factual_reference_only_truth(
    tmp_path: Path,
) -> None:
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    _write_json(
        execution / "sources/commons/meta.json",
        {
            "sourceUseMode": "factual_reference_only",
            "researchLane": "image",
        },
    )

    build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )

    catalog = json.loads(
        (package / "object/source_catalog.json").read_text(encoding="utf-8")
    )
    assert catalog["sources"] == [
        {
            "sourceUrl": "https://commons.wikimedia.org/wiki/File:Example.jpg",
            "sourceUseMode": "factual_reference_only",
        }
    ]
    rights = json.loads(
        (package / "object/rights.json").read_text(encoding="utf-8")
    )
    assert rights["assets"][0]["sourceUseMode"] == "factual_reference_only"
    assert validate_result(rights, "release", "asset_rights_closure") == []


def test_verified_research_asset_projects_final_editorial_rights(
    tmp_path: Path,
) -> None:
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    _write_json(
        execution / "sources/commons/meta.json",
        {
            "sourceUseMode": "rights_audit_only",
            "rightsMode": "rights_audit_only",
            "researchLane": "video",
        },
    )
    index_path = execution / "sources/commons/assets/index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["assets"][0]["usageScope"] = "internal_reference"
    _write_json(index_path, index)
    manifest_path = execution / "posts" / POST_REF / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["assets"][0]["usageScope"] = "internal_reference"
    _write_json(manifest_path, manifest)

    build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )

    rights = json.loads((package / "object/rights.json").read_text(encoding="utf-8"))
    assert rights["assets"][0]["sourceUseMode"] == "licensed_adaptation"
    assert rights["assets"][0]["usageScope"] == "editorial"
    assert validate_result(rights, "release", "asset_rights_closure") == []


def test_research_asset_without_authorization_proof_stays_audit_only(
    tmp_path: Path,
) -> None:
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    _write_json(
        execution / "sources/commons/meta.json",
        {
            "sourceUseMode": "rights_audit_only",
            "rightsMode": "rights_audit_only",
            "researchLane": "video",
        },
    )
    index_path = execution / "sources/commons/assets/index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["assets"][0]["authorizationProof"] = ""
    _write_json(index_path, index)
    manifest_path = execution / "posts" / POST_REF / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["assets"][0]["authorizationProof"] = ""
    _write_json(manifest_path, manifest)

    build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )

    rights = json.loads((package / "object/rights.json").read_text(encoding="utf-8"))
    asset = rights["assets"][0]
    assert asset["sourceUseMode"] == "rights_audit_only"
    assert asset["rightsAuditStatus"] == "unverified"
    assert asset["authorizationProof"] == ""
    assert asset["rightsAuditIssues"] == [
        "authorizationProof: not independently verified for research distribution"
    ]
    assert validate_result(rights, "release", "asset_rights_closure") == []


def test_canonical_transaction_rejects_source_use_mode_upgrade(
    tmp_path: Path,
) -> None:
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    _write_json(
        execution / "sources/commons/meta.json",
        {
            "sourceUseMode": "factual_reference_only",
            "researchLane": "image",
        },
    )
    manifest_path = execution / "posts" / POST_REF / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sourceUseMode"] = "licensed_adaptation"
    _write_json(manifest_path, manifest)

    with pytest.raises(
        ObjectTransactionError,
        match="sourceUseMode 与 source unit 真值冲突",
    ):
        build_post_object_transaction_package(
            execution_root=execution,
            object_ref=POST_REF,
            transaction_id=transaction_id,
            package_root=package,
        )


def test_canonical_transaction_rejects_rights_policy_as_source_use_mode(
    tmp_path: Path,
) -> None:
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    _write_json(
        execution / "sources/commons/meta.json",
        {
            "sourceUseMode": "attribution_no_watermark",
            "rightsMode": "attribution_no_watermark",
            "researchLane": "video",
        },
    )

    with pytest.raises(
        ObjectTransactionError,
        match="sourceUseMode 非法或缺失",
    ):
        build_post_object_transaction_package(
            execution_root=execution,
            object_ref=POST_REF,
            transaction_id=transaction_id,
            package_root=package,
        )


def test_video_transaction_closes_poster_cas_and_path_bound_source_rights(
    tmp_path: Path,
) -> None:
    execution_id = "20260718--travel-video-cold-start--test-region-a--scale-902"
    post_ref = "video/西湖/光影短片"
    execution = tmp_path / "tasks" / execution_id
    post = execution / "posts" / post_ref
    source_dir = execution / "sources/wiki/assets"
    source_dir.mkdir(parents=True)
    frame = source_dir / "frame-1.jpg"
    Image.new("RGB", (1280, 720), color=(35, 90, 150)).save(frame)
    _write_json(
        source_dir / "index.json",
        {
            "assets": [
                {
                    "sourceAssetId": "001_001",
                    "fileName": frame.name,
                    "url": "https://upload.wikimedia.org/wikipedia/commons/frame-1.jpg",
                    "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:Frame-1.jpg",
                    "authorizationProof": "https://commons.wikimedia.org/wiki/File:Frame-1.jpg",
                    "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
                    "creator": "Fixture Photographer",
                    "license": "CC BY 4.0",
                    "platform": "Wikimedia Commons",
                    "fetchedAt": "2026-07-18T04:00:00Z",
                    "usageScope": "app_publish",
                    "modelReleaseStatus": "not_required",
                }
            ]
        },
    )
    _write_json(
        execution / "sources/wiki/meta.json",
        {
            "sourceUseMode": "licensed_adaptation",
            "researchLane": "video",
        },
    )
    assets = post / "assets"
    assets.mkdir(parents=True)
    video = assets / "video.mp4"
    video.write_bytes(b"fixture-video-payload")
    poster = assets / "poster.webp"
    Image.new("RGB", (1080, 1920), color=(25, 75, 125)).save(poster, format="WEBP")
    frame_ref = frame.relative_to(execution).as_posix()
    video_id = "west-lake-video"
    poster_id = "west-lake-video-cover"
    target_set = {
        "executionId": execution_id,
        "entityCatalogDigest": "sha256:" + "4" * 64,
    }
    target_set_digest = hashlib.sha256(
        json.dumps(
            target_set,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    _write_json(execution / "0.plan/target_set.json", target_set)
    _write_json(
        execution / "execution_manifest.json",
        {
            "executionId": execution_id,
            "createdAt": "2026-07-18T04:00:00Z",
                "sourceDigest": current_source_definition_snapshot().to_document(),
                "executionBundle": current_execution_bundle_identity().to_document(),
            "targetSetRef": "0.plan/target_set.json",
            "targetSetDigest": target_set_digest,
        },
    )
    _write_json(
        post / "manifest.json",
        {
                "schema": "quwoquan_data.post_manifest",
                "vertical": "travel",
                "topicId": "西湖__video_1",
                    "contentIdentity": "work",
                    "contentId": "qwq_data_west_lake_video_fixture",
                    "version": 1,
                    "contentType": "video",
            "carrier": "video",
            "title": "西湖光影短片",
            "caption": "湖岸与长桥的光影",
                "creatorProfileId": CREATOR_REF,
                "sourceAttribution": _source_attribution(),
            "sourceUrls": ["https://commons.wikimedia.org/wiki/File:Frame-1.jpg"],
            "entityRefs": ["/entity/地点/景区/西湖"],
            "tagRefs": ["Topic/旅行/玩法/摄影旅拍"],
            "generator": "agent",
            "createdAt": "2026-07-18T04:00:00Z",
            "updatedAt": "2026-07-18T04:00:00Z",
            "assets": [
                {
                    "assetId": video_id,
                    "fileName": "assets/video.mp4",
                    "kind": "video",
                    "posterAssetId": poster_id,
                    "sourceAssetRefs": [frame_ref],
                    "sha256": "sha256:" + hashlib.sha256(video.read_bytes()).hexdigest(),
                    "mimeType": "video/mp4",
                    "width": 1080,
                        "height": 1920,
                        "usageScope": "app_publish",
                        "modelReleaseStatus": "not_required",
                        "rightsAuditStatus": "verified",
                        "rightsAuditIssues": [],
                },
                {
                    "assetId": poster_id,
                    "fileName": "assets/poster.webp",
                    "kind": "image",
                    "role": "cover",
                    "sourceAssetRefs": [frame_ref],
                    "sha256": "sha256:" + hashlib.sha256(poster.read_bytes()).hexdigest(),
                        "mimeType": "image/webp",
                        "usageScope": "app_publish",
                        "modelReleaseStatus": "not_required",
                        "rightsAuditStatus": "verified",
                        "rightsAuditIssues": [],
                },
            ],
        },
    )
    _write_json(
        post / "1.download/source_refs.json",
        {
            "sources": [
                {
                    "sourceUrl": "https://commons.wikimedia.org/wiki/File:Frame-1.jpg",
                    "sourceAssetRef": frame_ref,
                }
            ]
        },
    )
    _write_json(
        post / "5.review/attestation.json",
        {
            "decision": "approved",
            "deterministicGate": {"status": "passed"},
            "independentReviewer": {"status": "passed"},
            "mediaRefReview": {"status": "passed"},
        },
    )
    _write_json(post / "5.review/evidence_index.json", {"evidence": []})
    transaction_id = (
        f"{execution_id}--post-"
        f"{hashlib.sha256(post_ref.encode('utf-8')).hexdigest()[:12]}"
    )
    package_root = execution / "evidence/object-transactions" / transaction_id

    package = build_post_object_transaction_package(
        execution_root=execution,
        object_ref=post_ref,
        transaction_id=transaction_id,
        package_root=package_root,
    )

    assert len(package["closure"]["casRefs"]) == 2
    rights = json.loads((package_root / "object/rights.json").read_text(encoding="utf-8"))
    assert {row["assetId"] for row in rights["assets"]} == {video_id, poster_id}
    assert all(row["source"] == "https://commons.wikimedia.org/wiki/File:Frame-1.jpg" for row in rights["assets"])
    manifest = json.loads((package_root / "object/manifest.json").read_text(encoding="utf-8"))
    canonical_assets = {row["assetId"]: row for row in manifest["assets"]}
    assert canonical_assets[video_id]["posterAssetId"] == poster_id
    assert canonical_assets[poster_id]["role"] == "cover"

    publish = tmp_path / "publish-video"
    for relative in ("creators", "entities", "posts", "tags", "media/objects"):
        (publish / relative).mkdir(parents=True, exist_ok=True)
    _copy_creator_avatar_cas(publish)
    _admit_packaged_creator(package_root, publish)
    output = tmp_path / "output-video"
    audit = audit_object_transaction(
        publish_root=publish,
        output_root=output,
        package_root=package_root,
        transaction_id=transaction_id,
        expected_canonical_merkle=load_or_bootstrap_inventory(publish)["stats"][
            "merkleRoot"
        ],
    )
    apply_object_transaction(
        publish_root=publish,
        output_root=output,
        package_root=package_root,
        transaction_id=transaction_id,
        dry_run_attestation_sha256=str(audit["dryRunAttestationSha256"]),
    )
    assert validate_publish_invariants(publish)["status"] == "passed"
