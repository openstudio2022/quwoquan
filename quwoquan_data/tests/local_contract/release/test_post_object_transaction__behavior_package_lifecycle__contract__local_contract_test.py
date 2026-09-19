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
from core.schema import assert_valid
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


def _admit_referenced_homepage(publish: Path, package: Path) -> None:
    """复用现役 dependency producer，避免复制旧 _entity/sidecar 布局。"""
    from local_contract.release.test_publish_package__self_contained__local_contract_test import _admit_dependencies
    _admit_dependencies(package, publish)


def test_post_transaction_resolves_independently_admitted_creator(
    tmp_path: Path,
) -> None:
    execution, package, publish, transaction_id = _fixture(tmp_path)
    assert transaction_id.endswith("--self-contained-v2")
    transaction = build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )
    _admit_packaged_creator(package, publish)
    _admit_referenced_homepage(publish, package)
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

    canonical = publish / transaction["target"]["objectPath"]
    assert (canonical / "manifest.json").is_file()
    assert (publish / "creators" / CREATOR_REF / "_creator.json").is_file()
    published_manifest = json.loads((canonical / "manifest.json").read_text(encoding="utf-8"))
    assert datetime.fromisoformat(published_manifest["publishedAt"]).tzinfo is not None
    assert published_manifest["sourceTaskId"] == EXECUTION_ID
    assert published_manifest["payloadDigest"].startswith("sha256:")
    assert published_manifest["sourceIdentity"]["executionId"] == EXECUTION_ID
    assert "sourceDigest" not in published_manifest
    assert "executionBundle" not in published_manifest
    canonical_review = canonical / "content_review.json"
    source_review = execution / "posts" / POST_REF / "5.review/content_review.json"
    assert canonical_review.read_bytes() == source_review.read_bytes()
    assert not (canonical / "5.review").exists()
    assert not (canonical / "attestation.json").exists()
    assert not (canonical / "rights_authority.json").exists()
    assert published_manifest["admission"]["evidenceRef"] == "content_review.json"
    assert published_manifest["admission"]["rightsAuthorityRef"] == (
        f"posts/{POST_REF}/content_review.json"
    )
    expected_review_digest = "sha256:" + hashlib.sha256(canonical_review.read_bytes()).hexdigest()
    assert published_manifest["admission"]["evidenceDigest"] == expected_review_digest
    assert published_manifest["admission"]["rightsAuthorityDigest"] == expected_review_digest
    assert validate_publish_invariants(publish)["status"] == "passed"


def test_fresh_reviewed_work_without_variant_publishes_as_original(
    tmp_path: Path,
) -> None:
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    make_text_only_article(execution)
    manifest_path = execution / "posts" / POST_REF / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "variantPurpose" not in manifest
    manifest.update(
        generator="agent",
        createdAt="2026-09-05T12:00:00Z",
        updatedAt="2026-09-05T12:00:00Z",
    )
    assert manifest["contentType"] == "article"
    assert "publicationAdmission" not in manifest["sourceAttribution"]
    _write_json(manifest_path, manifest)

    build_post_object_transaction_package(
        execution_root=execution,
        object_ref=POST_REF,
        transaction_id=transaction_id,
        package_root=package,
    )

    canonical = json.loads(
        (package / "object/manifest.json").read_text(encoding="utf-8")
    )
    assert canonical["sourceType"] == "data"
    assert "variantPurpose" not in canonical
    assert canonical["admission"]["processResult"] == "completed"
    assert canonical["admission"]["qualityResult"] == "passed"
    assert canonical["admission"]["rightsResult"] == "passed"
    assert "usageScope" not in canonical["admission"]
    assert canonical["status"] == "active"
    assert_valid(canonical, "content", "post_manifest")
    for field in ("assetRefsRef", "creatorRefsRef", "tagRefsRef"):
        with pytest.raises(ValueError, match="schema violation"):
            assert_valid({**canonical, field: "old.json"}, "content", "post_manifest")


@pytest.mark.parametrize("field_path", ["variantPurpose", "publicationAdmission", "distributionDecision", "reviewUsageScope"])
def test_post_transaction_rejects_retired_classification(field_path: str, tmp_path: Path) -> None:
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    manifest_path = execution / "posts" / POST_REF / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if field_path == "variantPurpose":
        manifest["variantPurpose"] = "commercial_variant"
    elif field_path == "publicationAdmission":
        manifest["sourceAttribution"]["publicationAdmission"] = "commercial_release"
    elif field_path == "distributionDecision":
        manifest["assets"][0]["distributionDecision"] = "commercial_allowed"
    else:
        review_path = execution / "posts" / POST_REF / "5.review/content_review.json"
        review = json.loads(review_path.read_text(encoding="utf-8"))
        review["assetRights"][0]["usageScope"] = "research"
        _write_json(review_path, review)
    _write_json(manifest_path, manifest)
    with pytest.raises((ObjectTransactionError, ValueError), match="RETIRED_CLASSIFICATION_FIELD|schema violation|distributionDecision|usageScope|variantPurpose|publicationAdmission"):
        build_post_object_transaction_package(
            execution_root=execution, object_ref=POST_REF,
            transaction_id=transaction_id, package_root=package,
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
        (package / "object/manifest.json").read_text(encoding="utf-8")
    )["assets"][0]
    assert binding["sourceAssetRefs"] == ["sources/commons/assets/cover.jpg"]
    assert binding["acquisitionReceiptRefs"] == ["receipts/acquired.json"]
    assert binding["derivativeBinding"] == derivative
    assert binding["bytes"] == published_asset.stat().st_size
    assert binding["sha256"] == derivative["derivedSha256"]
    canonical = json.loads((package / "object/manifest.json").read_bytes())
    assert canonical["finalContentRef"] == "manifest.json"
    assert canonical["creatorProfileId"] == CREATOR_REF
    for name in ("asset.refs.json", "creator.refs.json", "tag.refs.json"):
        assert not (package / "object" / name).exists()
    assert not {"assetRefsRef", "creatorRefsRef", "tagRefsRef"} & canonical.keys()


def test_post_manifest_preserves_declared_source_and_receipt_order(tmp_path: Path) -> None:
    """spec_ref: multi-carrier-release/GWT-032 — 取得绑定在同一资产行且不按字典序重排。"""
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    index = json.loads((execution / "sources/commons/assets/index.json").read_bytes())
    second = dict(index["assets"][0], acquisitionReceiptRef="receipts/z.json")
    _write_json(execution / "sources/z/assets/index.json", {"assets": [second]})
    z_source = execution / "sources/z/source.md"
    z_source.parent.mkdir(parents=True, exist_ok=True)
    z_source.write_text("Fixture source evidence.\n", encoding="utf-8")
    z_meta = json.loads((execution / "sources/commons/meta.json").read_bytes())
    z_meta.update(canonicalUrl="https://example.test/source-z", sourceMarkdownSha256="sha256:" + hashlib.sha256(z_source.read_bytes()).hexdigest())
    _write_json(execution / "sources/z/meta.json", z_meta)
    source_refs = ["sources/z/assets/cover.jpg", "sources/commons/assets/cover.jpg"]
    path = execution / "posts" / POST_REF / "manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest["assets"][0].pop("sourceAssetRef", None)
    manifest["assets"][0]["sourceAssetRefs"] = source_refs
    _write_json(path, manifest)
    review_path = execution / "posts" / POST_REF / "5.review/content_review.json"
    review = json.loads(review_path.read_bytes())
    review["assetRights"].append(dict(review["assetRights"][0], assetRef=source_refs[0]))
    _write_json(review_path, review)

    build_post_object_transaction_package(
        execution_root=execution, object_ref=POST_REF,
        transaction_id=transaction_id, package_root=package,
    )
    asset = json.loads((package / "object/manifest.json").read_bytes())["assets"][0]
    assert asset["sourceAssetRefs"] == source_refs
    assert asset["acquisitionReceiptRefs"] == ["receipts/z.json", index["assets"][0]["acquisitionReceiptRef"]]
    from content.release.canonical.producer_release_handoff import _sealed_review_source_assets

    sources = _sealed_review_source_assets(package / "object", required_asset_refs=tuple(source_refs))
    assert set(sources) == set(source_refs)
    assert not (package / "object/rights_snapshots").exists()


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
        record_path = root / "records/1.json"
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
        (package / "object/manifest.json").read_text(encoding="utf-8")
    )
    assert asset_refs["assets"] == []
    assert not (package / "object/asset.refs.json").exists()
    assert transaction["publishMediaMode"] == "text_only"
    assert transaction["closure"]["casRefs"] == []
    assert not (package / "object/rights.json").exists()
    _admit_packaged_creator(package, publish)
    from content.release.canonical.object_transaction_contract import _verify_package

    verified = _verify_package(
        package,
        canonical_root=publish,
        require_target_absent=False,
    )
    assert verified["rights"]["assets"] == []


def test_pre_audit_text_only_package_rejects_retired_rights_sidecar(
    tmp_path: Path,
) -> None:
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    make_text_only_article(execution)
    build_post_object_transaction_package(
        execution_root=execution, object_ref=POST_REF,
        transaction_id=transaction_id, package_root=package,
    )
    _write_json(package / "object/rights.json", {"publishMediaMode": "text_only", "assets": []})
    from content.release.canonical.object_transaction_contract import _verify_package
    with pytest.raises(ObjectTransactionError, match="RETIRED_SIDECAR"):
        _verify_package(package, canonical_root=_publish, require_target_absent=False)


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


def test_media_post_transaction_rejects_empty_cas_rights_binding(tmp_path: Path) -> None:
    execution, package, publish, transaction_id = _fixture(tmp_path)
    build_post_object_transaction_package(
        execution_root=execution, object_ref=POST_REF, transaction_id=transaction_id, package_root=package,
    )
    document_path = package / "object_transaction_package.json"
    document = json.loads(document_path.read_text(encoding="utf-8"))
    document["closure"]["casRefs"] = []
    _write_json(document_path, document)
    from content.release.canonical.object_transaction_contract import _verify_package
    with pytest.raises(ObjectTransactionError, match="CAS|casRefs|closure"):
        _verify_package(package, canonical_root=publish, require_target_absent=False)


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


def test_text_only_package_has_no_retired_rights_sidecar(tmp_path: Path) -> None:
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    make_text_only_article(execution)
    build_post_object_transaction_package(
        execution_root=execution, object_ref=POST_REF, transaction_id=transaction_id, package_root=package,
    )
    assert not (package / "object/rights.json").exists()
