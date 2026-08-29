from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import pytest
from content.execution.closure.pool_delivery import write_pool_delivery_intent
from content.release.canonical import creator_projection
from content.release.canonical import handler as release_handler
from content.release.canonical import object_transaction_audit as transaction
from content.release.canonical.application import (
    apply_object_transaction,
    replay_object_transaction,
    rollback_object_transaction,
)
from content.release.canonical.canonical_inventory import load_or_bootstrap_inventory
from content.release.canonical.object_transaction import (
    _source_asset_for_manifest_asset,
    _source_assets_by_ref,
    build_entity_object_transaction_package,
)
from content.templates.registry import TemplateRegistry
from core import paths as core_paths
from core.tree_integrity import tree_integrity_stats
from governance.creators.assignment import creator_assignment_from_profile
from PIL import Image
from support import execution_manifest_fixture
from support.execution_manifest_fixture import ExecutionFixtureBuilder
from support.media_fixture import (
    admit_media_body,
    seed_system_creator_avatar_holding,
)
from support.object_transaction_fixtures import (
    OBJECT_REF,
    TRANSACTION_ID,
    build_canonical,
    build_package,
)


def test_object_transaction_rollback_cli_binds_exact_roots_and_transaction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    parser = argparse.ArgumentParser()
    release_handler.register_parser(
        parser.add_subparsers(dest="command", required=True)
    )
    output_root = tmp_path / "output"
    publish_root = tmp_path / "publish"
    observed: dict[str, object] = {}

    def _rollback(**kwargs: object) -> dict[str, object]:
        observed.update(kwargs)
        return {
            "schema": "quwoquan_data.object_transaction_rollback",
            "transactionId": "transaction-cli-001",
            "status": "rolled_back",
        }

    monkeypatch.setattr(release_handler, "rollback_object_transaction", _rollback)
    args = parser.parse_args(
        [
            "release",
            "object-transaction",
            "rollback",
            "--transaction-id",
            "transaction-cli-001",
            "--output-root",
            str(output_root),
            "--publish-root",
            str(publish_root),
        ]
    )
    args.handler(args)

    assert observed == {
        "publish_root": publish_root.resolve(),
        "output_root": output_root.resolve(),
        "transaction_id": "transaction-cli-001",
    }
    assert json.loads(capsys.readouterr().out)["status"] == "rolled_back"

BUILT_EXECUTION_ID = (
    "20260808--travel-homepage-canonical-assets--contract-region-a--pilot-015"
)
BUILT_OBJECT_REF = "地点/景区/真实构建地点"
BUILT_ASSET_ID = "homepage-cover"
DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)


def _source_attribution() -> dict[str, object]:
    return {
        "isOriginal": False,
        "originalCreatorId": None,
        "originalCreatorName": "Fixture Photographer",
        "originalCreatorProfileUrl": None,
        "platform": "Wikimedia Commons",
        "sourcePostUrl": "https://commons.wikimedia.org/wiki/File:Cover.png",
        "originalAssetUrl": "https://upload.wikimedia.org/example/cover.png",
        "attributionText": "Fixture Photographer / CC BY 4.0",
        "rightsBasis": "CC BY 4.0",
        "commercialAuthorizationStatus": "unverified",
        "publicationAdmission": "research_release",
        "authorizationProofUrl": None,
        "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
        "riskAcceptanceId": None,
        "watermarkStatus": "absent",
        "audioRightsStatus": "no_audio",
        "modelReleaseStatus": "not_required",
        "propertyReleaseStatus": "not_required",
        "collectedAt": "2026-08-08T00:00:00Z",
        "takedownPolicy": "quwoquan_standard_notice_and_takedown",
        "derivedModifications": [],
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def _build_approved_entity_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, str]:
    output_root = tmp_path / "output"
    data_root = output_root / "data"
    monkeypatch.setattr(core_paths, "OUTPUT_ROOT", output_root)
    monkeypatch.setattr(core_paths, "DATA_OUTPUT_ROOT", data_root)
    monkeypatch.setattr(core_paths, "DATA_EXECUTIONS_ROOT", data_root / "tasks")
    monkeypatch.setattr(core_paths, "DATA_LOCAL_ROOT", data_root / "local")
    monkeypatch.setattr(core_paths, "RUNTIME_ROOT", data_root / "tasks")

    # 对象事务不消费队列观察二进制；跳过其构建使输入与输出完全留在 tmp_path。
    monkeypatch.setattr(
        execution_manifest_fixture,
        "freeze_execution_queue_backend",
        lambda *_args, **_kwargs: None,
    )
    ExecutionFixtureBuilder(BUILT_EXECUTION_ID).build()
    execution_root = core_paths.execution_root(BUILT_EXECUTION_ID)
    entity_root = execution_root / "entities" / BUILT_OBJECT_REF
    source_asset = execution_root / "sources/commons/assets/cover.png"
    source_asset.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (2, 2), color=(30, 80, 140)).save(source_asset)

    entity_asset = entity_root / "assets/cover.png"
    entity_asset.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_asset, entity_asset)
    admit_media_body(source_asset.read_bytes())
    source_asset_ref = source_asset.relative_to(execution_root).as_posix()
    creator = creator_assignment_from_profile(
        TemplateRegistry.load().creators["qwq_creator_travel_blogger_001"]
    )
    seed_system_creator_avatar_holding("qwq_creator_travel_blogger_001")
    attribution = _source_attribution()
    _write_json(
        source_asset.parent / "index.json",
        {
            "assets": [
                {
                    "sourceAssetId": BUILT_ASSET_ID,
                    "fileName": source_asset.name,
                    "url": "https://upload.wikimedia.org/example/cover.png",
                    "collectionPageUrl": (
                        "https://commons.wikimedia.org/wiki/File:Cover.png"
                    ),
                    "authorizationProof": (
                        "https://commons.wikimedia.org/wiki/File:Cover.png"
                    ),
                    "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
                    "creator": "Fixture Photographer",
                    "license": "CC BY 4.0",
                    "fetchedAt": "2026-08-08T00:00:00Z",
                    "usageScope": "app_publish",
                    "modelReleaseStatus": "not_required",
                }
            ]
        },
    )
    _write_json(
        entity_root / "_entity.json",
        {
            "entityRef": f"/entity/{BUILT_OBJECT_REF}",
            **creator,
            "tagRefs": ["Topic/旅行/玩法/文化体验"],
            "primarySource": {"sourceKind": "wikipedia"},
            "sourceAttribution": attribution,
        },
    )
    _write_json(
        entity_root / "manifest.json",
        {
            "vertical": "travel",
            "sourceAttribution": attribution,
            "assets": [
                {
                    "assetId": BUILT_ASSET_ID,
                    "fileName": "cover.png",
                    "sourceAssetId": BUILT_ASSET_ID,
                    "sourceAssetRef": source_asset_ref,
                    "caption": "真实构建测试封面",
                    "credit": "Fixture Photographer",
                    "license": "CC BY 4.0",
                    "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
                    "authorizationProof": (
                        "https://commons.wikimedia.org/wiki/File:Cover.png"
                    ),
                    "usageScope": "app_publish",
                    "distributionDecision": "commercial_allowed",
                    "modelReleaseStatus": "not_required",
                    "rightsAuditStatus": "verified",
                    "rightsAuditIssues": [],
                }
            ],
        },
    )
    (entity_root / "page.md").write_text("# 真实构建地点\n", encoding="utf-8")
    _write_json(
        entity_root / "evidence/source_catalog.json",
        {
            "sources": [
                {
                    "sourceKind": "wikipedia",
                    "sourceUrl": "https://zh.wikipedia.org/wiki/真实构建地点",
                }
            ]
        },
    )
    _write_json(
        entity_root / "5.review/attestation.json",
        {
            "decision": "approved",
            "deterministicGate": {"status": "passed"},
            "independentReviewer": {"status": "passed"},
            "mediaRefReview": {"status": "passed"},
        },
    )
    _write_json(entity_root / "5.review/evidence_index.json", {"evidence": []})
    transaction_id = (
        f"{BUILT_EXECUTION_ID}--entity-"
        f"{hashlib.sha256(BUILT_OBJECT_REF.encode('utf-8')).hexdigest()[:12]}"
    )
    return execution_root, transaction_id


def _audit(tmp_path: Path) -> tuple[Path, Path, Path, dict]:
    canonical = build_canonical(tmp_path)
    output = tmp_path / ".qwq_output"
    package = build_package(tmp_path, canonical)
    report = transaction.audit_object_transaction(
        publish_root=canonical,
        output_root=output,
        package_root=package,
        transaction_id=TRANSACTION_ID,
        expected_canonical_merkle=load_or_bootstrap_inventory(canonical)["stats"][
            "merkleRoot"
        ],
    )
    return canonical, output, package, report


def test_audit_binds_current_merkle_freeze_policy_closure_and_review(
    tmp_path: Path,
) -> None:
    canonical = build_canonical(tmp_path)
    package = build_package(tmp_path, canonical)
    before = tree_integrity_stats(canonical)["merkleRoot"]

    with pytest.raises(
        transaction.ObjectTransactionError,
        match="current canonical Merkle",
    ):
        transaction.audit_object_transaction(
            publish_root=canonical,
            output_root=tmp_path / ".qwq_output",
            package_root=package,
            transaction_id=TRANSACTION_ID,
            expected_canonical_merkle="sha256:" + "0" * 64,
        )

    assert tree_integrity_stats(canonical)["merkleRoot"] == before


def test_entity_transaction_builder_projects_one_asset_identity_consistently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution_root, transaction_id = _build_approved_entity_execution(
        tmp_path,
        monkeypatch,
    )
    package_root = execution_root / "evidence/object-transactions" / transaction_id

    intent, _intent_path = write_pool_delivery_intent(
        BUILT_EXECUTION_ID,
        carrier="homepage",
        object_ref=f"/entity/{BUILT_OBJECT_REF}",
        content_object_dir=f"entities/{BUILT_OBJECT_REF}",
        root=execution_root,
        publish_root=tmp_path / "canonical-publish",
        reservation_root=tmp_path / "delivery-reservations",
    )

    package = build_entity_object_transaction_package(
        execution_root=execution_root,
        object_ref=BUILT_OBJECT_REF,
        transaction_id=transaction_id,
        package_root=package_root,
        pool_delivery_intent=intent,
    )

    manifest = json.loads(
        (package_root / "object/manifest.json").read_text(encoding="utf-8")
    )
    rights = json.loads(
        (package_root / "object/rights.json").read_text(encoding="utf-8")
    )
    asset_refs = json.loads(
        (package_root / "object/asset.refs.json").read_text(encoding="utf-8")
    )
    manifest_asset = next(
        asset for asset in manifest["assets"] if asset["assetId"] == BUILT_ASSET_ID
    )
    rights_asset = next(
        asset for asset in rights["assets"] if asset["assetId"] == BUILT_ASSET_ID
    )
    refs_asset = next(
        asset for asset in asset_refs["assets"] if asset["assetId"] == BUILT_ASSET_ID
    )
    cas_ref = next(
        item
        for item in package["closure"]["casRefs"]
        if item["objectKey"] == manifest_asset["objectKey"]
    )

    assert (
        manifest_asset["sha256"],
        manifest_asset["bytes"],
    ) == (
        rights_asset["asset"]["sha256"],
        rights_asset["asset"]["bytes"],
    ) == (
        refs_asset["sha256"],
        refs_asset["bytes"],
    ) == (
        cas_ref["sha256"],
        cas_ref["bytes"],
    )


def test_entity_transaction_projects_legacy_research_asset_to_editorial_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution_root, transaction_id = _build_approved_entity_execution(
        tmp_path,
        monkeypatch,
    )
    entity_root = execution_root / "entities" / BUILT_OBJECT_REF
    manifest_path = entity_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_asset = manifest["assets"][0]
    manifest_asset.pop("usageScope")
    manifest_asset["rightsAuditStatus"] = "unverified"
    manifest_asset["rightsAuditIssues"] = [
        "imageRights: missing required field usageScope"
    ]
    _write_json(manifest_path, manifest)

    source_index_path = execution_root / "sources/commons/assets/index.json"
    source_index = json.loads(source_index_path.read_text(encoding="utf-8"))
    source_asset = source_index["assets"][0]
    source_asset.pop("usageScope")
    source_asset.update(
        acquisitionStatus="acquired",
        distributionDecision="research_allowed",
        rightsAuditStatus="unverified",
        rightsAuditIssues=["imageRights: missing required field usageScope"],
    )
    _write_json(source_index_path, source_index)

    intent, _intent_path = write_pool_delivery_intent(
        BUILT_EXECUTION_ID,
        carrier="homepage",
        object_ref=f"/entity/{BUILT_OBJECT_REF}",
        content_object_dir=f"entities/{BUILT_OBJECT_REF}",
        root=execution_root,
        publish_root=tmp_path / "canonical-publish",
        reservation_root=tmp_path / "delivery-reservations",
    )
    package_root = execution_root / "evidence/object-transactions" / transaction_id
    build_entity_object_transaction_package(
        execution_root=execution_root,
        object_ref=BUILT_OBJECT_REF,
        transaction_id=transaction_id,
        package_root=package_root,
        pool_delivery_intent=intent,
    )

    rights = json.loads(
        (package_root / "object/rights.json").read_text(encoding="utf-8")
    )
    assert rights["assets"][0]["usageScope"] == "editorial"
    assert rights["assets"][0]["rightsAuditStatus"] == "unverified"
    assert rights["assets"][0]["rightsAuditIssues"] == [
        "imageRights: missing required field usageScope",
        "commercial distribution proof incomplete; retained for research",
    ]


def test_entity_transaction_rejects_manifest_asset_digest_drift(
    tmp_path: Path,
) -> None:
    canonical = build_canonical(tmp_path)
    package = build_package(tmp_path, canonical)
    manifest_path = package / "object/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["assets"][0].pop("sha256")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )

    with pytest.raises(
        transaction.ObjectTransactionError,
        match="entity manifest 与 rights digest/bytes 漂移",
    ):
        transaction.audit_object_transaction(
            publish_root=canonical,
            output_root=tmp_path / ".qwq_output",
            package_root=package,
            transaction_id=TRANSACTION_ID,
            expected_canonical_merkle=load_or_bootstrap_inventory(canonical)["stats"][
                "merkleRoot"
            ],
        )


def test_apply_is_atomic_create_once_idempotent_and_has_no_layout_parent(
    tmp_path: Path,
) -> None:
    canonical, output, package, audit = _audit(tmp_path)

    applied = apply_object_transaction(
        publish_root=canonical,
        output_root=output,
        package_root=package,
        transaction_id=TRANSACTION_ID,
        dry_run_attestation_sha256=audit["dryRunAttestationSha256"],
    )

    assert applied["status"] == "applied"
    assert (canonical / "entities" / OBJECT_REF / "_entity.json").is_file()
    assert (canonical / "tags/Topic/旅行/_definition.json").is_file()
    assert Path(applied["rollbackRef"]).is_dir()
    assert "releaseRef" not in applied
    serialized = json.dumps(applied, ensure_ascii=False)
    assert "publish-layout" not in serialized

    rerun = apply_object_transaction(
        publish_root=canonical,
        output_root=output,
        package_root=package,
        transaction_id=TRANSACTION_ID,
        dry_run_attestation_sha256=audit["dryRunAttestationSha256"],
    )
    assert rerun["idempotent"] is True


def test_content_transaction_requires_independently_admitted_author(
    tmp_path: Path,
) -> None:
    canonical = build_canonical(tmp_path)
    package = build_package(tmp_path, canonical)
    shutil.rmtree(canonical)
    output = tmp_path / ".qwq_output"

    with pytest.raises(
        transaction.ObjectTransactionError,
        match="DATA.POOL.AUTHOR_NOT_ADMITTED",
    ):
        transaction.audit_object_transaction(
            publish_root=canonical,
            output_root=output,
            package_root=package,
            transaction_id=TRANSACTION_ID,
            expected_canonical_merkle=load_or_bootstrap_inventory(canonical)["stats"][
                "merkleRoot"
            ],
        )


def test_rollback_restores_before_merkle_and_preserves_transaction_evidence(
    tmp_path: Path,
) -> None:
    canonical, output, package, audit = _audit(tmp_path)
    applied = apply_object_transaction(
        publish_root=canonical,
        output_root=output,
        package_root=package,
        transaction_id=TRANSACTION_ID,
        dry_run_attestation_sha256=audit["dryRunAttestationSha256"],
    )

    rolled_back = rollback_object_transaction(
        publish_root=canonical,
        output_root=output,
        transaction_id=TRANSACTION_ID,
    )

    assert rolled_back["restoredMerkle"] == applied["beforeMerkle"]
    assert not (canonical / "entities" / OBJECT_REF).exists()
    assert Path(rolled_back["rollbackRefPreserved"]).is_dir()
    assert not (
        output
        / "data/local/workspace/object-transactions"
        / TRANSACTION_ID
        / "rollback/canonical_before"
    ).exists()

    replayed = replay_object_transaction(
        publish_root=canonical,
        output_root=output,
        transaction_id=TRANSACTION_ID,
    )

    assert replayed["restoredMerkle"] == applied["afterMerkle"]
    assert (canonical / "entities" / OBJECT_REF).is_dir()


def test_entity_transaction_resolves_duplicate_source_asset_ids_by_full_reference(
    tmp_path: Path,
) -> None:
    execution = tmp_path / "execution"
    first = execution / "sources" / "first" / "assets"
    second = execution / "sources" / "second" / "assets"
    for directory, url in (
        (first, "https://upload.wikimedia.org/first.jpg"),
        (second, "https://upload.wikimedia.org/second.jpg"),
    ):
        directory.mkdir(parents=True)
        (directory / "image.jpg").write_bytes(b"image")
        (directory / "index.json").write_text(
            json.dumps(
                {
                    "assets": [
                        {
                            "sourceAssetId": "001_001",
                            "fileName": "image.jpg",
                            "url": url,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

    source_ref, source_asset = _source_asset_for_manifest_asset(
        {
            "sourceAssetId": "001_001",
            "sourceAssetRef": "sources/second/assets/image.jpg",
        },
        _source_assets_by_ref(execution),
    )

    assert source_ref == "sources/second/assets/image.jpg"
    assert source_asset["url"] == "https://upload.wikimedia.org/second.jpg"
