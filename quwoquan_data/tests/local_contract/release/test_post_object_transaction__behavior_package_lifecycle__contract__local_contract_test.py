"""场景组：post 交易包生命周期、幂等与 publishMediaMode 契约。

从 test_post_object_transaction__behavior__contract__local_contract_test.py
按场景拆出（本文件经 git mv 承接原文件历史）；测试逐字搬移。
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest
from content.release.canonical import post_promotion, post_transaction
from content.release.canonical.application import apply_object_transaction
from content.release.canonical.canonical_inventory import load_or_bootstrap_inventory
from content.release.canonical.object_transaction_audit import (
    audit_object_transaction,
    validate_publish_invariants,
)
from content.release.canonical.post_transaction import (
    ObjectTransactionError,
)
from support.post_object_transaction_fixture import (
    CREATOR_REF,
    EXECUTION_ID,
    POST_REF,
    _admit_packaged_creator,
    _fixture,
    _isolate_creator_avatar_cas,
    _write_json,
    build_post_object_transaction_package,
    make_text_only_article,
)


def test_post_transaction_resolves_independently_admitted_creator(
    tmp_path: Path,
) -> None:
    execution, package, publish, transaction_id = _fixture(tmp_path)
    transaction = build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )
    _admit_packaged_creator(package, publish)
    output = tmp_path / "output"
    audit = audit_object_transaction(
        publish_root=publish,
        output_root=output,
        package_root=package,
        transaction_id=transaction_id,
        expected_canonical_merkle=load_or_bootstrap_inventory(publish)["stats"][
            "merkleRoot"
        ],
    )
    apply_object_transaction(
        publish_root=publish,
        output_root=output,
        package_root=package,
        transaction_id=transaction_id,
        dry_run_attestation_sha256=str(audit["dryRunAttestationSha256"]),
    )

    assert (publish / "posts" / POST_REF / "manifest.json").is_file()
    assert (publish / "creators" / CREATOR_REF / "_creator.json").is_file()
    published_manifest = json.loads(
        (publish / "posts" / POST_REF / "manifest.json").read_text(encoding="utf-8")
    )
    assert datetime.fromisoformat(published_manifest["publishedAt"]).tzinfo is not None
    assert published_manifest["sourceTaskId"] == EXECUTION_ID
    assert published_manifest["payloadDigest"].startswith("sha256:")
    assert published_manifest["sourceIdentity"]["executionId"] == EXECUTION_ID
    assert "sourceDigest" not in published_manifest
    assert "executionBundle" not in published_manifest
    assert validate_publish_invariants(publish)["status"] == "passed"


def test_post_transaction_caps_commercial_facts_at_ai_research_scope(
    tmp_path: Path,
) -> None:
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    manifest_path = execution / "posts" / POST_REF / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sourceAttribution"].update(
        publicationAdmission="commercial_release",
        commercialAuthorizationStatus="verified",
        authorizationProofUrl="https://example.test/proof",
        termsUrl="https://example.test/terms",
    )
    manifest["assets"][0]["distributionDecision"] = "commercial_allowed"
    _write_json(manifest_path, manifest)
    source_index_path = execution / "sources/commons/assets/index.json"
    source_index = json.loads(source_index_path.read_text(encoding="utf-8"))
    source_index["assets"][0]["distributionDecision"] = "commercial_allowed"
    _write_json(source_index_path, source_index)
    review_path = execution / "posts" / POST_REF / "5.review/media_ref_review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["rightsReviews"][0]["usageScope"] = "research"
    _write_json(review_path, review)
    attestation_path = execution / "posts" / POST_REF / "5.review/attestation.json"
    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    attestation["mediaRefReview"]["digest"] = (
        "sha256:" + hashlib.sha256(review_path.read_bytes()).hexdigest()
    )
    _write_json(attestation_path, attestation)

    build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )
    canonical = json.loads(
        (package / "object/manifest.json").read_text(encoding="utf-8")
    )
    assert canonical["admission"]["usageScope"] == "research"


def test_post_transaction_rejects_ai_research_commercial_variant(
    tmp_path: Path,
) -> None:
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    manifest_path = execution / "posts" / POST_REF / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["variantPurpose"] = "commercial_variant"
    manifest["sourceAttribution"].update(
        publicationAdmission="commercial_release",
        commercialAuthorizationStatus="verified",
        authorizationProofUrl="https://example.test/proof",
        termsUrl="https://example.test/terms",
    )
    manifest["assets"][0]["distributionDecision"] = "commercial_allowed"
    _write_json(manifest_path, manifest)
    source_index_path = execution / "sources/commons/assets/index.json"
    source_index = json.loads(source_index_path.read_text(encoding="utf-8"))
    source_index["assets"][0]["distributionDecision"] = "commercial_allowed"
    _write_json(source_index_path, source_index)
    review_path = execution / "posts" / POST_REF / "5.review/media_ref_review.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["rightsReviews"][0]["usageScope"] = "research"
    _write_json(review_path, review)
    attestation_path = execution / "posts" / POST_REF / "5.review/attestation.json"
    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    attestation["mediaRefReview"]["digest"] = (
        "sha256:" + hashlib.sha256(review_path.read_bytes()).hexdigest()
    )
    _write_json(attestation_path, attestation)

    with pytest.raises(ObjectTransactionError, match="COMMERCIAL_VARIANT_NOT_ADMITTED"):
        build_post_object_transaction_package(
            execution_root=execution,
            object_ref=POST_REF,
            transaction_id=transaction_id,
            package_root=package,
        )


def test_post_transaction_copies_source_asset_hard_facts(tmp_path: Path) -> None:
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    source_index_path = execution / "sources/commons/assets/index.json"
    source_index = json.loads(source_index_path.read_text(encoding="utf-8"))
    source_index["assets"][0]["acquisitionReceiptRef"] = "receipts/acquired.json"
    published_asset = execution / "posts" / POST_REF / "assets/cover.jpg"
    derivative = {
        "originalSha256": "sha256:" + "1" * 64,
        "originalBytes": 12,
        "originalMimeType": "image/jpeg",
        "policy": "source_unit_asset_budget",
        "profile": "image",
        "derivedSha256": "sha256:" + hashlib.sha256(published_asset.read_bytes()).hexdigest(),
        "derivedBytes": published_asset.stat().st_size,
        "derivedMimeType": "image/jpeg",
        "derivedExtension": ".jpg",
    }
    source_index["assets"][0]["derivativeBinding"] = derivative
    _write_json(source_index_path, source_index)

    build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )
    binding = json.loads(
        (package / "object/asset.refs.json").read_text(encoding="utf-8")
    )["assets"][0]
    assert binding["sourceAssetRefs"] == ["sources/commons/assets/cover.jpg"]
    assert binding["acquisitionReceiptRefs"] == ["receipts/acquired.json"]
    assert binding["derivativeBinding"] == derivative


def test_post_transaction_rejects_missing_acquisition_receipt(tmp_path: Path) -> None:
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    source_index_path = execution / "sources/commons/assets/index.json"
    source_index = json.loads(source_index_path.read_text(encoding="utf-8"))
    source_index["assets"][0].pop("acquisitionReceiptRef")
    _write_json(source_index_path, source_index)

    with pytest.raises(ObjectTransactionError, match="acquisitionReceiptRef"):
        build_post_object_transaction_package(
            execution_root=execution,
            object_ref=POST_REF,
            transaction_id=transaction_id,
            package_root=package,
        )


def test_post_transaction_same_key_requires_same_payload_digest(
    tmp_path: Path,
) -> None:
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    first = build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )
    replay = build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )
    assert replay == first

    content_path = execution / "posts" / POST_REF / "content.md"
    content_path.write_text("# changed payload\n", encoding="utf-8")
    with pytest.raises(ObjectTransactionError, match="IDEMPOTENCY_CONFLICT"):
        build_post_object_transaction_package(
            execution_root=execution,
            object_ref=POST_REF,
            transaction_id=transaction_id,
            package_root=package,
        )


def test_applied_post_pool_digest_repair_appends_record_sequence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(post_transaction, "PUBLISH_ROOT", tmp_path / "identity-publish")
    execution, package, publish, transaction_id = _fixture(tmp_path)
    build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )
    canonical = publish / "posts" / POST_REF
    shutil.copytree(package / "object", canonical)
    for root in (package / "object", canonical):
        record_path = root / "_pool/versions/1.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["payloadDigest"] = record["canonicalObjectDigest"] = (
            "sha256:" + "0" * 64
        )
        _write_json(record_path, record)

    assert post_promotion.repair_applied_post_pool_record_drift(
        package_root=package,
        canonical_post=canonical,
        canonical_ref=POST_REF,
    )
    from content.release.canonical.content_pool_record import latest_pool_record

    repaired = latest_pool_record(canonical, "content")
    assert repaired is not None
    assert repaired["recordSequence"] == 2
    assert repaired["contentVersion"] == 1


def test_text_only_post_transaction_does_not_require_media_asset(tmp_path: Path) -> None:
    execution, package, publish, transaction_id = _fixture(tmp_path)
    make_text_only_article(execution)

    transaction = build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )

    asset_refs = json.loads(
        (package / "object/asset.refs.json").read_text(encoding="utf-8")
    )
    assert asset_refs == {"assets": []}
    assert transaction["publishMediaMode"] == "text_only"
    assert transaction["closure"]["casRefs"] == []
    rights = json.loads((package / "object/rights.json").read_text(encoding="utf-8"))
    assert rights == {
        "schema": "quwoquan_data.asset_rights_closure",
        "publishMediaMode": "text_only",
        "assets": [],
    }
    _admit_packaged_creator(package, publish)
    from content.release.canonical.object_transaction_contract import _verify_package

    verified = _verify_package(
        package,
        canonical_root=publish,
        require_target_absent=False,
    )
    assert verified["rights"]["assets"] == []


def test_pre_audit_text_only_package_adds_missing_media_mode_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    make_text_only_article(execution)
    first = build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )
    package_path = package / "object_transaction_package.json"
    legacy = json.loads(package_path.read_text(encoding="utf-8"))
    legacy.pop("publishMediaMode")
    _write_json(package_path, legacy)
    rights_path = package / "object/rights.json"
    legacy_rights = json.loads(rights_path.read_text(encoding="utf-8"))
    legacy_rights.pop("publishMediaMode")
    _write_json(rights_path, legacy_rights)
    monkeypatch.setattr(post_transaction, "OUTPUT_ROOT", tmp_path / "output")

    resumed = build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )

    assert {
        key: value
        for key, value in resumed.items()
        if key != "objectClosureDigest"
    } == {
        key: value
        for key, value in first.items()
        if key != "objectClosureDigest"
    }
    assert json.loads(package_path.read_text(encoding="utf-8")) == resumed
    assert json.loads(rights_path.read_text(encoding="utf-8"))["publishMediaMode"] == "text_only"
    from content.release.canonical.content_pool_record import latest_pool_record

    record = latest_pool_record(package / "object", "content")
    assert record is not None
    assert record["payloadDigest"] == record["canonicalObjectDigest"]


def test_media_post_transaction_rejects_empty_cas_closure(tmp_path: Path) -> None:
    execution, package, publish, transaction_id = _fixture(tmp_path)
    transaction = build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )
    assert transaction["publishMediaMode"] == "embedded_media"
    document_path = package / "object_transaction_package.json"
    document = json.loads(document_path.read_text(encoding="utf-8"))
    document["closure"]["casRefs"] = []
    _write_json(document_path, document)

    from content.release.canonical.object_transaction_contract import _verify_package

    with pytest.raises(ObjectTransactionError, match="casRefs"):
        _verify_package(
            package,
            canonical_root=publish,
            require_target_absent=False,
        )


def test_media_post_transaction_rejects_empty_rights_closure(tmp_path: Path) -> None:
    execution, package, publish, transaction_id = _fixture(tmp_path)
    build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )
    _admit_packaged_creator(package, publish)
    rights_path = package / "object/rights.json"
    rights = json.loads(rights_path.read_text(encoding="utf-8"))
    rights["assets"] = []
    _write_json(rights_path, rights)

    from content.release.canonical.object_transaction_contract import _verify_package

    with pytest.raises(ObjectTransactionError, match="minItems 1"):
        _verify_package(
            package,
            canonical_root=publish,
            require_target_absent=False,
        )


def test_text_only_package_rejects_media_mode_drift(tmp_path: Path) -> None:
    execution, package, publish, transaction_id = _fixture(tmp_path)
    make_text_only_article(execution)
    build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )
    document_path = package / "object_transaction_package.json"
    document = json.loads(document_path.read_text(encoding="utf-8"))
    packaged_manifest_path = package / "object/manifest.json"
    packaged_manifest = json.loads(
        packaged_manifest_path.read_text(encoding="utf-8")
    )
    packaged_manifest.pop("publishMediaMode")
    _write_json(packaged_manifest_path, packaged_manifest)

    from content.release.canonical.object_transaction_contract import _verify_package

    with pytest.raises(ObjectTransactionError, match="publishMediaMode"):
        _verify_package(
            package,
            canonical_root=publish,
            require_target_absent=False,
        )


def test_text_only_package_rejects_missing_rights_media_mode(tmp_path: Path) -> None:
    execution, package, publish, transaction_id = _fixture(tmp_path)
    make_text_only_article(execution)
    build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )
    _admit_packaged_creator(package, publish)
    rights_path = package / "object/rights.json"
    rights = json.loads(rights_path.read_text(encoding="utf-8"))
    rights.pop("publishMediaMode")
    _write_json(rights_path, rights)

    from content.release.canonical.object_transaction_contract import _verify_package

    with pytest.raises(ObjectTransactionError, match="publishMediaMode"):
        _verify_package(
            package,
            canonical_root=publish,
            require_target_absent=False,
        )
