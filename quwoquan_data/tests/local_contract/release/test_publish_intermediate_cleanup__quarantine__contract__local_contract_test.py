from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import pytest
from content.release.canonical.asset_review_adoption import (
    build_independent_asset_review_binding,
)
from content.release.canonical.canonical_inventory import (
    apply_inventory_delta,
    load_or_bootstrap_inventory,
    write_inventory,
)
from content.release.canonical.handler import register_parser
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _json_bytes,
)
from content.release.canonical.publish_intermediate_cleanup import (
    apply_publish_intermediate_cleanup,
    plan_publish_intermediate_cleanup,
)
from content.source.independent_asset_review_contract import (
    canonical_digest,
    file_digest,
)
from core.io import read_json, write_json
from verify.verify_publish_purity import publish_structure_issues

EXECUTION_ID = (
    "20260808--travel-image-m1--china-beta-bootstrap-not-m100--scale-015"
)
REVIEW_ID = "asset-review-" + "a" * 64
CONTENT_SHA = "sha256:" + "c" * 64


def _digest(seed: str) -> str:
    return "sha256:" + hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _receipt() -> dict:
    execution = {
        "executionId": EXECUTION_ID,
        "objectRef": "杭州西湖_image",
        "provider": "cursor_sdk",
        "model": "auto",
        "runId": "run-author-001",
        "evidenceRef": f"data/tasks/{EXECUTION_ID}/evidence/author.json",
        "evidenceSha256": _digest("author"),
    }
    document = {
        "schema": "quwoquan_data.independent_asset_review_receipt",
        "reviewId": REVIEW_ID,
        "assetKind": "image",
        "objectRef": "杭州西湖_image",
        "sourceRevision": _digest("revision"),
        "sourceDigest": _digest("source"),
        "entityCatalogDigest": _digest("catalog"),
        "acquisitionReceiptRef": (
            "data/local/workspace/source-acquisition/receipts/" + "1" * 64 + ".json"
        ),
        "acquisitionReceiptDigest": _digest("acquisition-receipt"),
        "acquisitionReceiptSha256": _digest("acquisition-file"),
        "executionManifestRef": f"data/tasks/{EXECUTION_ID}/execution_manifest.json",
        "executionManifestSha256": _digest("manifest"),
        "assetSnapshot": {
            "assetId": "professional-image-1",
            "entityId": "杭州西湖",
            "observedEntityId": "杭州西湖",
            "contentSha256": CONTENT_SHA,
            "casRef": "cas/sha256/cc/image.jpg",
            "sourceUrl": "https://www.pinterest.com/pin/example/",
            "platform": "pinterest",
            "creator": "摄影师甲",
            "capturedAt": "2026-08-08T00:00:00Z",
            "license": "unknown",
            "termsUrl": "https://policy.pinterest.com/terms-of-service",
            "authorizationProof": "",
            "rightsIssues": ["distribution authorization remains unverified"],
            "acquisitionStatus": "acquired",
            "rightsStatus": "unverified",
            "authorizationRequired": True,
            "distributionDecision": "research_allowed",
        },
        "acquisitionExecution": {
            **execution,
            "runId": "run-acquisition-001",
            "evidenceRef": "data/local/workspace/source-acquisition/receipt.json",
            "evidenceSha256": _digest("acquisition"),
        },
        "authorExecution": execution,
        "reviewerExecution": {
            **execution,
            "runId": "run-reviewer-001",
            "modelFamily": "cursor-auto",
            "resultHash": _digest("review-result"),
            "evidenceRef": f"data/tasks/{EXECUTION_ID}/evidence/reviewer.json",
            "evidenceSha256": _digest("reviewer"),
        },
        "judgment": {
            "rightsStatus": "unverified",
            "authorizationRequired": True,
            "distributionDecision": "research_allowed",
            "safetyStatus": "passed",
            "entityMatch": "matched",
            "qualityStatus": "passed",
            "privacyRisk": "none",
            "minorRisk": "none",
            "maliciousMediaRisk": "none",
            "watermarkStatus": "absent",
            "findings": [],
        },
        "reviewDecision": "accepted",
        "recordedAt": "2026-08-08T00:10:00Z",
    }
    document["receiptDigest"] = canonical_digest(document, excluded="receiptDigest")
    return document


def _rights(binding: dict) -> dict:
    return {
        "schema": "quwoquan_data.asset_rights_closure",
        "assets": [
            {
                "assetId": "image-1",
                "acquisitionReceiptRef": binding["acquisitionReceiptRef"],
                "independentAssetReview": binding,
                "sourceKind": "pinterest",
                "sourceUseMode": "rights_audit_only",
                "canonicalFilePage": "https://www.pinterest.com/pin/example/",
                "snapshotUrl": "https://www.pinterest.com/pin/example/",
                "pageRevision": _digest("page"),
                "originalAssetUrl": "https://images.example/image.jpg",
                "author": "摄影师甲",
                "source": "Pinterest",
                "licenseName": "unknown",
                "licenseShortName": "unknown",
                "licenseUrl": "",
                "usageScope": "app_publish",
                "attribution": "摄影师甲 · Pinterest",
                "caption": "杭州西湖",
                "captionSource": "captured source metadata",
                "modifications": "none",
                "fetchedAt": "2026-08-08T00:00:00Z",
                "snapshot": {
                    "ref": "object/rights_snapshots/image-1.json",
                    "sha256": _digest("snapshot"),
                    "bytes": 128,
                },
                "asset": {
                    "ref": "cas/image-1.jpg",
                    "sha256": CONTENT_SHA,
                    "bytes": 1024,
                    "mimeType": "image/jpeg",
                    "width": 800,
                    "height": 640,
                },
                "authorizationProof": "",
                "modelReleaseStatus": "not_required",
                "rightsAuditStatus": "unverified",
                "rightsAuditIssues": ["distribution authorization remains unverified"],
            }
        ],
    }


def _legacy_fixture(
    tmp_path: Path,
    *,
    output_root: Path | None = None,
) -> dict[str, Path]:
    publish_root = tmp_path / "publish"
    output_root = output_root or (tmp_path / "output")
    object_root = publish_root / "posts/image/gallery/west-lake/1"
    external = (
        output_root
        / "data/tasks"
        / EXECUTION_ID
        / "evidence/asset_reviews/receipts"
        / f"{REVIEW_ID}.json"
    )
    write_json(external, _receipt())
    local = object_root / "asset_reviews/receipts" / external.name
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(external.read_bytes())
    binding = build_independent_asset_review_binding(
        read_json(external),
        receipt_ref=f"asset_reviews/receipts/{external.name}",
        receipt_file_sha256=file_digest(external),
    )
    write_json(
        object_root / "manifest.json",
        {
            "schema": "quwoquan_data.post_object",
            "executionId": EXECUTION_ID,
            "sourceTaskId": EXECUTION_ID,
            "sourceDigest": {
                "algorithm": "sha256",
                "digest": _digest("source"),
                "inputs": ["quwoquan_data/scripts"],
            },
            "rightsRef": "rights.json",
        },
    )
    write_json(object_root / "rights.json", _rights(binding))
    return {
        "publish": publish_root,
        "output": output_root,
        "object": object_root,
        "local": local,
        "external": external,
    }


def test_cleanup_migrates_rights_then_quarantines_receipt_with_one_delta(
    tmp_path: Path,
) -> None:
    fixture = _legacy_fixture(tmp_path)
    publish_root = fixture["publish"]
    output_root = fixture["output"]
    receipt_bytes = fixture["local"].read_bytes()
    before = load_or_bootstrap_inventory(publish_root)

    plan, plan_path = plan_publish_intermediate_cleanup(
        cleanup_id="cleanup-legacy-asset-reviews",
        publish_root=publish_root,
        output_root=output_root,
    )

    assert plan_path.is_file()
    assert [row["operation"] for row in plan["inventoryDelta"]] == [
        "delete",
        "replace",
    ]
    assert plan["beforeInventoryDigest"] == before["inventoryDigest"]
    migration = plan["candidates"][0]["receiptMigrations"][0]

    applied, receipt_path = apply_publish_intermediate_cleanup(
        cleanup_id="cleanup-legacy-asset-reviews",
        plan_digest=plan["planDigest"],
        publish_root=publish_root,
        output_root=output_root,
    )

    assert applied["status"] == "applied"
    assert applied["permanentDeletion"] is False
    assert not fixture["local"].exists()
    assert fixture["external"].read_bytes() == receipt_bytes
    rights = read_json(fixture["object"] / "rights.json")
    assert rights["assets"][0]["independentAssetReview"]["receiptRef"] == migration[
        "externalRef"
    ]
    quarantine = output_root / applied["quarantined"][0]["quarantineRef"]
    assert (quarantine / "receipts" / fixture["local"].name).read_bytes() == receipt_bytes
    assert receipt_path.is_file()
    assert publish_structure_issues(publish_root) == []
    after = load_or_bootstrap_inventory(publish_root)
    assert after["inventoryDigest"] == plan["afterInventoryDigest"]
    assert after["stats"]["fileCount"] == before["stats"]["fileCount"] - 1

    repeated, repeated_path = apply_publish_intermediate_cleanup(
        cleanup_id="cleanup-legacy-asset-reviews",
        plan_digest=plan["planDigest"],
        publish_root=publish_root,
        output_root=output_root,
    )
    assert repeated_path == receipt_path
    assert repeated["idempotent"] is True
    assert repeated["receiptDigest"] == applied["receiptDigest"]


def test_cleanup_blocks_when_external_receipt_is_missing(tmp_path: Path) -> None:
    fixture = _legacy_fixture(tmp_path)
    fixture["external"].unlink()

    with pytest.raises(ObjectTransactionError, match="external review receipt is missing"):
        plan_publish_intermediate_cleanup(
            cleanup_id="cleanup-missing-external",
            publish_root=fixture["publish"],
            output_root=fixture["output"],
        )


def test_cleanup_blocks_external_receipt_bytes_collision(tmp_path: Path) -> None:
    fixture = _legacy_fixture(tmp_path)
    fixture["external"].write_bytes(fixture["external"].read_bytes() + b" ")

    with pytest.raises(ObjectTransactionError, match="bytes collision"):
        plan_publish_intermediate_cleanup(
            cleanup_id="cleanup-external-collision",
            publish_root=fixture["publish"],
            output_root=fixture["output"],
        )


def test_cleanup_recovers_rights_and_move_before_inventory_commit(tmp_path: Path) -> None:
    fixture = _legacy_fixture(tmp_path)
    plan, _ = plan_publish_intermediate_cleanup(
        cleanup_id="cleanup-interrupted",
        publish_root=fixture["publish"],
        output_root=fixture["output"],
    )
    candidate = plan["candidates"][0]
    (fixture["object"] / "rights.json").write_bytes(
        _json_bytes(candidate["afterRights"])
    )
    source = fixture["local"].parents[1]
    quarantine = (
        fixture["output"]
        / "data/local/workspace/quarantine/canonical-publish-intermediates"
        / "cleanup-interrupted/publish"
        / source.relative_to(fixture["publish"])
    )
    quarantine.parent.mkdir(parents=True, exist_ok=True)
    source.replace(quarantine)

    applied, _ = apply_publish_intermediate_cleanup(
        cleanup_id="cleanup-interrupted",
        plan_digest=plan["planDigest"],
        publish_root=fixture["publish"],
        output_root=fixture["output"],
    )

    assert applied["quarantinedCount"] == 1
    assert load_or_bootstrap_inventory(fixture["publish"])["inventoryDigest"] == plan[
        "afterInventoryDigest"
    ]


def test_cleanup_plan_is_create_once_for_one_publish_identity(tmp_path: Path) -> None:
    shared_output = tmp_path / "shared-output"
    fixture = _legacy_fixture(tmp_path / "first", output_root=shared_output)
    plan_publish_intermediate_cleanup(
        cleanup_id="cleanup-create-once",
        publish_root=fixture["publish"],
        output_root=shared_output,
    )
    second = _legacy_fixture(tmp_path / "second", output_root=shared_output)

    with pytest.raises(ObjectTransactionError, match="request drift"):
        plan_publish_intermediate_cleanup(
            cleanup_id="cleanup-create-once",
            publish_root=second["publish"],
            output_root=shared_output,
        )


def test_cleanup_refuses_non_receipt_content_under_asset_reviews(tmp_path: Path) -> None:
    fixture = _legacy_fixture(tmp_path)
    unsupported = fixture["object"] / "asset_reviews/report.json"
    unsupported.write_text("{}", encoding="utf-8")

    with pytest.raises(ObjectTransactionError, match="unsupported evidence"):
        plan_publish_intermediate_cleanup(
            cleanup_id="cleanup-unsupported",
            publish_root=fixture["publish"],
            output_root=fixture["output"],
        )


def test_inventory_delete_binds_before_bytes_and_reverses_exactly(tmp_path: Path) -> None:
    publish_root = tmp_path / "publish"
    receipt = publish_root / "posts/image/example/receipt.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_bytes(b"frozen receipt\n")
    before = load_or_bootstrap_inventory(publish_root)
    delta = [
        {
            "operation": "delete",
            "destination": receipt.relative_to(publish_root).as_posix(),
            "beforeSha256": file_digest(receipt),
            "beforeBytes": receipt.stat().st_size,
        }
    ]
    deleted = apply_inventory_delta(before, delta, publish_root=publish_root)
    receipt.unlink()
    write_inventory(publish_root, deleted)
    assert load_or_bootstrap_inventory(publish_root)["stats"]["fileCount"] == 0

    restored = apply_inventory_delta(
        load_or_bootstrap_inventory(publish_root),
        delta,
        publish_root=publish_root,
        reverse=True,
    )
    receipt.write_bytes(b"frozen receipt\n")
    write_inventory(publish_root, restored)
    assert restored["stats"]["merkleRoot"] == before["stats"]["merkleRoot"]

    with pytest.raises(ObjectTransactionError, match="bind only before bytes"):
        apply_inventory_delta(
            load_or_bootstrap_inventory(publish_root),
            [{**delta[0], "sha256": file_digest(receipt), "bytes": receipt.stat().st_size}],
            publish_root=publish_root,
        )


def test_release_cli_exposes_digest_bound_publish_intermediate_cleanup() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    register_parser(commands)

    planned = parser.parse_args(
        [
            "release",
            "publish-intermediate-cleanup",
            "plan",
            "--cleanup-id",
            "cleanup-cli",
        ]
    )
    applied = parser.parse_args(
        [
            "release",
            "publish-intermediate-cleanup",
            "apply",
            "--cleanup-id",
            "cleanup-cli",
            "--plan-digest",
            "sha256:" + "1" * 64,
        ]
    )

    assert planned.release_cleanup_action == "plan"
    assert applied.release_cleanup_action == "apply"
    assert applied.plan_digest == "sha256:" + "1" * 64
