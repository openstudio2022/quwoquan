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
from core.schema import assert_valid, validate_result
from core.source_digest import (
    current_execution_bundle_identity,
    current_source_definition_snapshot,
)
from PIL import Image

from support.post_object_transaction_fixture import (
    CREATOR_REF,
    POST_REF,
    _admit_packaged_creator,
    _seed_creator_avatar_holding,
    _fixture,
    _isolate_creator_avatar_cas,
    _source_attribution,
    _write_json,
    build_post_object_transaction_package,
)


def test_travel_unverified_asset_is_rejected_without_downgrade(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    manifest_path = execution / "posts" / POST_REF / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    asset = manifest["assets"][0]
    asset["distributionDecision"] = "commercial_allowed"
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
    source_asset["distributionDecision"] = "commercial_allowed"
    source_asset["authorizationProof"] = ""
    source_asset["termsUrl"] = ""
    source_asset["creator"] = ""
    source_asset["license"] = ""
    source_asset["rightsAuditStatus"] = "unverified"
    source_asset["rightsAuditIssues"] = list(asset["rightsAuditIssues"])
    _write_json(source_index_path, source_index)

    with pytest.raises(ObjectTransactionError, match="rights facts drift|commercial rights proof"):
        build_post_object_transaction_package(
            execution_root=execution,
            object_ref=POST_REF,
            transaction_id=transaction_id,
            package_root=package,
        )


def test_unverified_collection_page_is_rejected_without_downgrade(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution, package, _publish, transaction_id = _fixture(tmp_path)
    manifest_path = execution / "posts" / POST_REF / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sourceUrls"] = ["https://content.example.test/article/landscape"]
    asset = manifest["assets"][0]
    asset.pop("sourceAssetId", None)
    asset["distributionDecision"] = "commercial_allowed"
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
            "distributionDecision": "commercial_allowed",
            "license": "",
            "rightsAuditStatus": "unverified",
            "rightsAuditIssues": ["imageRights: source terms not yet verified"],
        }
    )
    _write_json(source_index_path, source_index)

    with pytest.raises(ObjectTransactionError, match="rights facts drift|commercial rights proof"):
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
    assert rights["assets"][0]["distributionDecision"] == "research_allowed"
    assert_valid(rights, "release", "asset_rights_closure")
    assert validate_result(rights, "release", "asset_rights_closure") == []


def test_internal_reference_asset_is_rejected_without_scope_upgrade(
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

    with pytest.raises(ObjectTransactionError, match="sourceUseMode|internal_reference"):
        build_post_object_transaction_package(
            execution_root=execution,
            object_ref=POST_REF,
            transaction_id=transaction_id,
            package_root=package,
        )


def test_research_asset_without_authorization_proof_is_rejected(
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

    with pytest.raises(ObjectTransactionError, match="rights facts drift|authorizationProof"):
        build_post_object_transaction_package(
            execution_root=execution,
            object_ref=POST_REF,
            transaction_id=transaction_id,
            package_root=package,
        )


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
