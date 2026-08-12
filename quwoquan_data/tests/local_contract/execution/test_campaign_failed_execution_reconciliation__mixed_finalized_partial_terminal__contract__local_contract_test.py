from __future__ import annotations

from pathlib import Path

import pytest
from content.execution.campaign import failed_execution_reconciliation as reconciliation
from content.execution.campaign import (
    failed_execution_reconciliation_mixed as mixed_contract,
)
from content.execution.campaign import request_envelope_writer
from content.execution.campaign.submission_reconciliation_contract import (
    CampaignSubmissionReconciliationError,
)
from core.io import read_json, write_json
from local_contract.execution.test_campaign_failed_execution_reconciliation__claimed_execution_source_drift__contract__local_contract_test import (
    CARRIERS,
    CATALOG_DIGEST,
    FENCING_TOKEN,
    OBSERVED_SOURCE_DIGEST,
    ROOT_ID,
    RUN_ID,
    _source_document,
    _write_boundary,
)

_FINALIZED = ("homepage", "image", "video")


def _write_mixed_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    failed_carrier: str = "article",
) -> tuple[Path, Path, Path, dict[str, str]]:
    output_root, campaign, execution_ids = _write_boundary(tmp_path, monkeypatch)
    report_path = campaign / "campaign_report.json"
    report = read_json(report_path)
    assert isinstance(report, dict)
    report.update(
        {
            "status": "succeeded_partial",
            "phase": "completed",
            "failure": f"{failed_carrier}:DATA.SOURCE.RETAINED_SHORTFALL",
        }
    )
    for carrier in CARRIERS:
        claim_path = campaign / "claims" / f"{carrier}.json"
        claim = read_json(claim_path)
        assert isinstance(claim, dict)
        if carrier != failed_carrier:
            claim.update({"status": "completed", "returnCode": 0, "error": None})
            report["lanes"][carrier].update(
                {
                    "status": "finalized",
                    "phase": "publish",
                    "reviewReturnCode": 0,
                    "publishReturnCode": 0,
                    "sourceCapsuleRef": claim["capsuleRef"],
                    "executionRootRef": f"data/tasks/{execution_ids[carrier]}",
                    "cleanupStatus": "cleaned",
                    "approvedQuota": 1,
                    "qualifiedCount": 1,
                    "finalizedCount": 1,
                    "selectedCount": 1,
                    "discardedCount": 0,
                    "shortfallCount": 0,
                    "error": None,
                }
            )
        else:
            report["lanes"][carrier].update(
                {
                    "status": "blocked",
                    "phase": "submission",
                    "reviewReturnCode": None,
                    "publishReturnCode": 1,
                    "sourceCapsuleRef": claim["capsuleRef"],
                    "executionRootRef": f"data/tasks/{execution_ids[carrier]}",
                    "cleanupStatus": "cleaned",
                    "approvedQuota": None,
                    "qualifiedCount": None,
                    "finalizedCount": None,
                    "selectedCount": None,
                    "discardedCount": None,
                    "shortfallCount": None,
                    "error": "DATA.SOURCE.RETAINED_SHORTFALL",
                }
            )
        write_json(claim_path, claim)
    write_json(report_path, report)

    publish_root = tmp_path / "publish"
    monkeypatch.setattr(mixed_contract.paths, "PUBLISH_ROOT", publish_root)
    monkeypatch.setattr(mixed_contract, "_process_group_alive", lambda _pgid: False)
    submissions = {
        carrier: read_json(campaign / "submissions" / f"{execution_ids[carrier]}.json")
        for carrier in CARRIERS
    }
    for carrier in CARRIERS:
        if carrier == failed_carrier:
            continue
        execution_id = execution_ids[carrier]
        execution_root = output_root / "data/tasks" / execution_id
        object_kind = "entities" if carrier == "homepage" else "posts"
        object_ref = (
            "entity/china/hangzhou-xihu"
            if carrier == "homepage"
            else f"{carrier}/travel/hangzhou-xihu/1"
        )
        publish_path = execution_root / "publish_ref.json"
        refs = {
            "entities": [object_ref] if object_kind == "entities" else [],
            "posts": [object_ref] if object_kind == "posts" else [],
        }
        write_json(
            publish_path,
            {
                "schema": "quwoquan_data.execution_publish_ref",
                "executionId": execution_id,
                "canonicalPublishRoot": "quwoquan_data/publish",
                "publishedRefs": refs,
            },
        )
        manifest = {
            "schema": "quwoquan_data.entity_homepage"
            if carrier == "homepage"
            else "quwoquan_data.post_object",
            "executionId": execution_id,
            "sourceDigest": submissions[carrier]["sourceDigest"],
        }
        if carrier != "homepage":
            manifest["contentType"] = carrier
        write_json(
            publish_root / object_kind / object_ref / "manifest.json",
            manifest,
        )
        write_json(
            campaign / "receipts" / f"{carrier}-publish.json",
            {
                "schema": "quwoquan_data.content_campaign_lane_receipt",
                "rootExecutionId": ROOT_ID,
                "executionId": execution_id,
                "carrier": carrier,
                "phase": "publish",
                "status": "finalized",
                "approvedQuota": 1,
                "qualifiedCount": 1,
                "finalizedCount": 1,
                "selectedCount": 1,
                "discardedCount": 0,
                "shortfallCount": 0,
                "discards": [],
                "executionPublishRef": publish_path.relative_to(output_root).as_posix(),
                "executionPublishSha256": reconciliation.file_digest(publish_path),
                "campaignRunId": RUN_ID,
                "campaignGeneration": 1,
                "campaignFencingToken": FENCING_TOKEN,
            },
        )
    return output_root, campaign, publish_root, execution_ids


def test_mixed_terminal_accepts_video_as_the_single_failed_lane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root, campaign, _publish_root, _execution_ids = _write_mixed_boundary(
        tmp_path,
        monkeypatch,
        failed_carrier="video",
    )
    receipt, _path = reconciliation.reconcile_failed_campaign(
        ROOT_ID,
        reason="mixed_finalized_partial_terminal",
        blocker_evidence=campaign / "claims/video.json",
        repo_root=tmp_path,
        output_root=output_root,
    )
    lanes = {row["carrier"]: row for row in receipt["executionEvidence"]["lanes"]}
    assert lanes["video"]["evidenceDisposition"] == "failed_unpublished"
    assert lanes["video"]["observedFinalizedCount"] == 0
    assert lanes["article"]["evidenceDisposition"] == "preserved_unadopted"
    assert lanes["article"]["observedFinalizedCount"] == 1


def test_mixed_terminal_preserves_three_finalized_without_release_or_adoption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root, campaign, _publish_root, execution_ids = _write_mixed_boundary(
        tmp_path, monkeypatch
    )
    blocker = campaign / "claims/article.json"

    receipt, path = reconciliation.reconcile_failed_campaign(
        ROOT_ID,
        reason="mixed_finalized_partial_terminal",
        blocker_evidence=blocker,
        repo_root=tmp_path,
        output_root=output_root,
    )
    repeated, repeated_path = reconciliation.reconcile_failed_campaign(
        ROOT_ID,
        reason="mixed_finalized_partial_terminal",
        blocker_evidence=blocker,
        repo_root=tmp_path,
        output_root=output_root,
    )

    assert repeated_path == path
    assert repeated == receipt
    assert receipt["errorCode"] == "DATA.CAMPAIGN.MIXED_FINALIZED_PARTIAL_TERMINAL"
    evidence = receipt["executionEvidence"]
    assert evidence["observedFinalizedCount"] == 3
    assert evidence["excludedFromRetryRelease"] is True
    assert evidence["eligibleForRelease"] is False
    lanes = {row["carrier"]: row for row in evidence["lanes"]}
    assert lanes["article"]["observedFinalizedCount"] == 0
    assert lanes["article"]["publishReceiptPresent"] is False
    assert all(
        lanes[carrier]["observedFinalizedCount"] == 1
        and lanes[carrier]["evidenceDisposition"] == "preserved_unadopted"
        and lanes[carrier]["excludedFromRetryRelease"] is True
        for carrier in _FINALIZED
    )
    assert {row["executionId"] for row in evidence["lanes"]} == set(
        execution_ids.values()
    )
    assert not (campaign / "release_selections").exists()


def test_mixed_terminal_rejects_a_blocker_other_than_the_failed_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root, campaign, _publish_root, _execution_ids = _write_mixed_boundary(
        tmp_path, monkeypatch
    )

    with pytest.raises(CampaignSubmissionReconciliationError) as caught:
        reconciliation.reconcile_failed_campaign(
            ROOT_ID,
            reason="mixed_finalized_partial_terminal",
            blocker_evidence=campaign / "campaign_report.json",
            repo_root=tmp_path,
            output_root=output_root,
        )

    assert (
        caught.value.code
        == "DATA.CAMPAIGN.SUBMISSION_RECONCILIATION_BLOCKER_INVALID"
    )


@pytest.mark.parametrize(
    "tamper", ("count", "manifest", "release_selection", "failure")
)
def test_mixed_terminal_rejects_tampered_finalized_or_release_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
) -> None:
    output_root, campaign, publish_root, execution_ids = _write_mixed_boundary(
        tmp_path, monkeypatch
    )
    if tamper == "count":
        path = campaign / "receipts/video-publish.json"
        payload = read_json(path)
        payload["finalizedCount"] = 2
        write_json(path, payload)
    elif tamper == "manifest":
        path = publish_root / "posts/image/travel/hangzhou-xihu/1/manifest.json"
        payload = read_json(path)
        payload["executionId"] = execution_ids["article"]
        write_json(path, payload)
    elif tamper == "release_selection":
        write_json(campaign / "release_selections/forged.json", {"releaseId": "forged"})
    else:
        path = campaign / "campaign_report.json"
        payload = read_json(path)
        payload["failure"] = "article:DATA.INTERNAL.UNEXPECTED"
        write_json(path, payload)

    with pytest.raises(CampaignSubmissionReconciliationError):
        reconciliation.reconcile_failed_campaign(
            ROOT_ID,
            reason="mixed_finalized_partial_terminal",
            blocker_evidence=campaign / "claims/article.json",
            repo_root=tmp_path,
            output_root=output_root,
        )


def test_mixed_terminal_retry_envelope_allows_superseding_source_identity() -> None:
    observed = {
        "sourceRevision": "sha256:" + "1" * 64,
        "sourceDigest": _source_document(OBSERVED_SOURCE_DIGEST),
        "entityCatalogDigest": CATALOG_DIGEST,
    }
    payloads = {carrier: dict(observed) for carrier in CARRIERS}
    receipt = {
        "reason": "mixed_finalized_partial_terminal",
        "observedSourceIdentity": observed,
        "retryPolicy": "new_four_lane_execution_with_retryOf",
        "executionEvidence": {
            "excludedFromRetryRelease": True,
            "eligibleForRelease": False,
        },
    }
    request_envelope_writer._assert_one_source_identity(
        payloads,
        predecessor_reconciliation_receipt=receipt,
    )
    payloads["video"]["sourceDigest"] = _source_document("sha256:" + "9" * 64)
    with pytest.raises(ValueError, match="source identity changed while freezing"):
        request_envelope_writer._assert_one_source_identity(
            payloads,
            predecessor_reconciliation_receipt=receipt,
        )
    drifted = {
        carrier: {**observed, "sourceRevision": "sha256:" + "2" * 64}
        for carrier in CARRIERS
    }
    request_envelope_writer._assert_one_source_identity(
        drifted,
        predecessor_reconciliation_receipt=receipt,
    )

    without_exclusion = {
        **receipt,
        "executionEvidence": {
            "excludedFromRetryRelease": False,
            "eligibleForRelease": False,
        },
    }
    with pytest.raises(ValueError, match="does not exclude predecessor objects"):
        request_envelope_writer._assert_one_source_identity(
            drifted,
            predecessor_reconciliation_receipt=without_exclusion,
        )
