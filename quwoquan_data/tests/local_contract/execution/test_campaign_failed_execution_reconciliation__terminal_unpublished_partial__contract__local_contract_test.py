from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from content.execution.campaign import failed_execution_reconciliation as reconciliation
from content.execution.campaign import (
    failed_execution_reconciliation_terminal_unpublished as terminal_contract,
)
from content.execution.campaign import request_envelope_writer
from content.execution.campaign.submission_reconciliation_contract import (
    CampaignSubmissionReconciliationError,
    load_reconciliation_reference,
    reconciliation_reference,
)
from core.io import read_json, write_json
from local_contract.execution.test_campaign_failed_execution_reconciliation__claimed_execution_source_drift__contract__local_contract_test import (
    CARRIERS,
    OBSERVED_SOURCE_DIGEST,
    ROOT_ID,
    _source_document,
    _write_boundary,
)

_QUALIFIED = ("image", "video")


def _write_prepared_transaction(
    output_root: Path,
    execution_id: str,
) -> None:
    transaction_id = f"{execution_id}--post-prepared"
    root = (
        output_root
        / "data/tasks"
        / execution_id
        / "evidence/object-transactions"
        / transaction_id
    )
    write_json(
        root / "object/manifest.json",
        {
            "schema": "quwoquan_data.post_object",
            "executionId": execution_id,
            "contentType": "image",
            "publishAngle": "画报",
            "publishTitle": "都江堰测试图集",
            "publishSeq": 1,
        },
    )
    write_json(
        root / "object_transaction_package.json",
        {
            "schema": "quwoquan_data.object_transaction_package",
            "transactionId": transaction_id,
            "executionId": execution_id,
            "publishMediaMode": "embedded_media",
            "sourcePolicyRevision": "rights-cleared-content",
            "target": {
                "layoutSchema": "quwoquan_data.canonical_publish",
                "objectKind": "posts",
                "objectRef": "image/画报/都江堰测试图集/1",
                "objectSchema": "quwoquan_data.post_object",
                "packageObjectRef": "object",
            },
            "closure": {
                "creatorRefs": [],
                "tagRefs": [],
                "sourceCatalogRef": "source_catalog.json",
                "rightsRef": "rights.json",
                "casRefs": [
                    {
                        "sourceRef": "cas/source.jpg",
                        "objectKey": "media/objects/sha256/aa/aa/" + "a" * 64 + ".jpg",
                        "sha256": "sha256:" + "a" * 64,
                        "bytes": 1,
                    }
                ],
            },
            "review": {
                "attestationRef": "attestation.json",
                "evidenceIndexRef": "evidence_index.json",
            },
            "objectClosureDigest": "sha256:" + "b" * 64,
        },
    )


def _write_terminal_unpublished_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, dict[str, str]]:
    output_root, campaign, execution_ids = _write_boundary(tmp_path, monkeypatch)
    report_path = campaign / "campaign_report.json"
    report = read_json(report_path)
    assert isinstance(report, dict)
    report.update(
        {
            "status": "blocked",
            "phase": "completed",
            "failure": "homepage:RuntimeError: terminal publish process failed",
        }
    )
    for carrier in CARRIERS:
        qualified = carrier in _QUALIFIED
        claim = read_json(campaign / "claims" / f"{carrier}.json")
        lane = report["lanes"][carrier]
        lane.update(
            {
                "status": "blocked",
                "phase": "review" if qualified else "submission",
                "reviewReturnCode": 0 if qualified else 19,
                "publishReturnCode": 17,
                "sourceCapsuleRef": claim["capsuleRef"],
                "executionRootRef": f"data/tasks/{execution_ids[carrier]}",
                "cleanupStatus": "cleaned",
                "approvedQuota": 1 if qualified else None,
                "qualifiedCount": 1 if qualified else None,
                "finalizedCount": 0 if qualified else None,
                "selectedCount": 1 if qualified else None,
                "discardedCount": 0 if qualified else None,
                "shortfallCount": 0 if qualified else None,
                "error": "RuntimeError: terminal lane failed",
            }
        )
        if qualified:
            write_json(
                campaign / "receipts" / f"{carrier}-review.json",
                {
                    "schema": "quwoquan_data.content_campaign_lane_receipt",
                    "rootExecutionId": ROOT_ID,
                    "executionId": execution_ids[carrier],
                    "carrier": carrier,
                    "phase": "review",
                    "status": "qualified",
                    "approvedQuota": 1,
                    "qualifiedCount": 1,
                    "finalizedCount": 0,
                    "selectedCount": 1,
                    "discardedCount": 0,
                    "shortfallCount": 0,
                    "discards": [],
                },
            )
    _write_prepared_transaction(output_root, execution_ids["image"])
    write_json(report_path, report)
    monkeypatch.setattr(terminal_contract, "_process_group_alive", lambda _pgid: False)
    return output_root, campaign, execution_ids


def test_terminal_unpublished_source_drift_binds_reviews_without_release_credit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root, campaign, execution_ids = _write_terminal_unpublished_boundary(
        tmp_path,
        monkeypatch,
    )
    blocker = campaign / "campaign_report.json"
    receipt, path = reconciliation.reconcile_failed_campaign(
        ROOT_ID,
        reason="terminal_unpublished_source_drift",
        blocker_evidence=blocker,
        repo_root=tmp_path,
        output_root=output_root,
    )
    repeated, repeated_path = reconciliation.reconcile_failed_campaign(
        ROOT_ID,
        reason="terminal_unpublished_source_drift",
        blocker_evidence=blocker,
        repo_root=tmp_path,
        output_root=output_root,
    )

    assert repeated_path == path
    assert repeated == receipt
    assert path.parent.name == "terminal-unpublished-source-drift"
    assert (
        path.stem
        == receipt["observedSourceIdentity"]["sourceRevision"].split(":", 1)[1]
    )
    reference = reconciliation_reference(path, output_root=output_root)
    loaded, loaded_path = load_reconciliation_reference(
        reference,
        output_root=output_root,
    )
    assert loaded == receipt
    assert loaded_path == path
    assert reference["receiptRef"].endswith(
        f"terminal-unpublished-source-drift/{path.name}"
    )
    assert receipt["errorCode"] == "DATA.CAMPAIGN.TERMINAL_UNPUBLISHED_SOURCE_DRIFT"
    assert receipt["originalSourceIdentity"] != receipt["observedSourceIdentity"]
    evidence = receipt["executionEvidence"]
    assert evidence["observedFinalizedCount"] == 0
    assert evidence["reviewQualifiedLaneCount"] == 2
    assert evidence["preparedObjectTransactionCount"] == 1
    assert evidence["objectTransactionAppliedEvidencePresent"] is False
    assert evidence["excludedFromRetryRelease"] is True
    assert evidence["eligibleForRelease"] is False
    lanes = {row["carrier"]: row for row in evidence["lanes"]}
    assert {row["executionId"] for row in lanes.values()} == set(execution_ids.values())
    assert all(row["terminalStatus"] == "failed" for row in lanes.values())
    assert all(row["observedFinalizedCount"] == 0 for row in lanes.values())
    assert all(row["publishReceiptPresent"] is False for row in lanes.values())
    assert all(row["publishRefPresent"] is False for row in lanes.values())
    assert len(lanes["image"]["preparedObjectTransactions"]) == 1
    assert lanes["image"]["preparedObjectTransactions"][0]["state"] == (
        "prepared_unapplied"
    )
    assert all(
        row["objectTransactionAppliedEvidencePresent"] is False
        for row in lanes.values()
    )
    assert all(
        lanes[carrier]["reviewReceiptPresent"] is (carrier in _QUALIFIED)
        for carrier in CARRIERS
    )

    next_source_digest = "sha256:" + "d" * 64
    monkeypatch.setattr(
        reconciliation,
        "current_source_digest",
        lambda **_kwargs: SimpleNamespace(
            to_document=lambda: _source_document(next_source_digest)
        ),
    )
    next_receipt, next_path = reconciliation.reconcile_failed_campaign(
        ROOT_ID,
        reason="terminal_unpublished_source_drift",
        blocker_evidence=blocker,
        repo_root=tmp_path,
        output_root=output_root,
    )
    assert next_path != path
    assert next_receipt["observedSourceIdentity"] != receipt["observedSourceIdentity"]
    assert read_json(path) == receipt

    copied_path = path.parent / ("e" * 64 + ".json")
    write_json(copied_path, receipt)
    with pytest.raises(CampaignSubmissionReconciliationError) as caught:
        reconciliation.validate_failed_campaign_reconciliation_receipt(
            copied_path,
            output_root=output_root,
        )
    assert "ROOT_DRIFT" in str(caught.value)


@pytest.mark.parametrize(
    "tamper",
    ("publish_receipt", "publish_ref", "transaction", "release", "blocker"),
)
def test_terminal_unpublished_source_drift_rejects_publish_or_blocker_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
) -> None:
    output_root, campaign, execution_ids = _write_terminal_unpublished_boundary(
        tmp_path,
        monkeypatch,
    )
    blocker = campaign / "campaign_report.json"
    if tamper == "publish_receipt":
        write_json(
            campaign / "receipts/homepage-publish.json",
            {"executionId": execution_ids["homepage"]},
        )
    elif tamper == "publish_ref":
        write_json(
            output_root / "data/tasks" / execution_ids["homepage"] / "publish_ref.json",
            {"executionId": execution_ids["homepage"]},
        )
    elif tamper == "transaction":
        write_json(
            output_root
            / "data/tasks"
            / execution_ids["article"]
            / "evidence/object-transactions/tx/package.json",
            {"transactionId": "tx"},
        )
    elif tamper == "release":
        write_json(
            output_root / "data/releases/release-test/payload/release.json",
            {"executionIds": [execution_ids["video"]]},
        )
    else:
        blocker = campaign / "claims/homepage.json"

    with pytest.raises(CampaignSubmissionReconciliationError):
        reconciliation.reconcile_failed_campaign(
            ROOT_ID,
            reason="terminal_unpublished_source_drift",
            blocker_evidence=blocker,
            repo_root=tmp_path,
            output_root=output_root,
        )


def test_terminal_unpublished_successor_must_equal_receipt_observed_identity() -> None:
    observed = {
        "sourceRevision": "sha256:" + "1" * 64,
        "sourceDigest": _source_document(OBSERVED_SOURCE_DIGEST),
        "entityCatalogDigest": "sha256:" + "2" * 64,
    }
    receipt = {
        "reason": "terminal_unpublished_source_drift",
        "observedSourceIdentity": observed,
        "retryPolicy": "new_four_lane_execution_with_retryOf",
        "executionEvidence": {
            "excludedFromRetryRelease": True,
            "eligibleForRelease": False,
        },
    }
    request_envelope_writer._assert_one_source_identity(
        {carrier: dict(observed) for carrier in CARRIERS},
        predecessor_reconciliation_receipt=receipt,
    )
    drifted = {
        carrier: {**observed, "sourceRevision": "sha256:" + "3" * 64}
        for carrier in CARRIERS
    }
    with pytest.raises(ValueError, match="retry source identity drifted"):
        request_envelope_writer._assert_one_source_identity(
            drifted,
            predecessor_reconciliation_receipt=receipt,
        )
