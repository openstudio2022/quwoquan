from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from content.execution.campaign import failed_execution_reconciliation as reconciliation
from content.execution.campaign import (
    failed_execution_reconciliation_claimed as claimed_contract,
)
from content.execution.campaign import (
    failed_execution_reconciliation_post_publish as post_publish_contract,
)
from content.execution.campaign import request_envelope_writer
from content.execution.campaign.external_inputs import payload_digest
from content.execution.campaign.submission_reconciliation_contract import (
    CampaignSubmissionReconciliationError,
    canonical_digest,
)
from content.execution.identity import build_execution_id
from core.io import read_json, write_json
from core.source_digest import content_source_revision
from support.capacity_calibration_fixture import (
    synthetic_capacity_source_binding,
    synthetic_governed_execution_authority,
)
from support.semantic_preflight_fixture import ready_semantic_preflight

ROOT_ID = "20260808--travel-homepage-m1--china-beta-bootstrap-not-m100--scale-021"
CARRIERS = ("homepage", "article", "image", "video")
SOURCE_DIGEST = "sha256:" + "a" * 64
OBSERVED_SOURCE_DIGEST = "sha256:" + "c" * 64
CATALOG_DIGEST = "sha256:" + "b" * 64
RUN_ID = "claimed-execution-run"
FENCING_TOKEN = "sha256:" + "f" * 64


def _execution_id(carrier: str) -> str:
    return build_execution_id(
        run_date="20260808",
        vertical="travel",
        content_type=carrier,
        intent="m1",
        scope="china-beta-bootstrap-not-m100",
        phase="scale",
        sequence=21,
    )


def _source_document(digest: str) -> dict[str, object]:
    return {
        "algorithm": "sha256",
        "digest": digest,
        "inputs": ["quwoquan_data/scripts"],
    }


def _write_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    active_carriers: tuple[str, ...] = CARRIERS,
    target_names: tuple[str, ...] = ("杭州西湖",),
) -> tuple[Path, Path, dict[str, str]]:
    output_root = tmp_path / "output"
    _preflight_path, preflight = ready_semantic_preflight(
        "default", output_root=output_root
    )
    campaign = (
        output_root
        / "data/local/workspace/content-campaign-submissions"
        / ROOT_ID
    )
    source_revision = content_source_revision(
        source_digest=SOURCE_DIGEST,
        entity_catalog_digest=CATALOG_DIGEST,
    )
    empty_external = payload_digest(
        {"schema": "quwoquan_data.campaign_external_input_set", "refs": []}
    )
    execution_ids = {carrier: _execution_id(carrier) for carrier in active_carriers}
    request_digests: dict[str, str] = {}
    for carrier in active_carriers:
        stable = {
            "schema": "quwoquan_data.content_execution_submission",
            "scale": "M1",
            "workloadMode": "explicit",
            "activeCarriers": list(active_carriers),
            "workloads": {item: 1 for item in active_carriers},
            "rootExecutionId": ROOT_ID,
            "executionId": execution_ids[carrier],
            "operation": f"{carrier}.generate",
            "carrier": carrier,
            "familyRef": f"content/travel/{carrier}/{carrier}",
            "regionRef": "china",
            "selector": "source-ready-priority",
            "quota": 1,
            "count": 2,
            "topic": "beta-bootstrap-not-m100",
            "targetNames": list(target_names),
            "sourceProviders": [],
            "semanticSelectionId": "default",
            "executionAuthority": synthetic_governed_execution_authority(),
            "retryOf": execution_ids[carrier].replace("scale-021", "scale-020"),
            "gitBranch": "dev1.0",
            "gitCommitSha": "d" * 40,
            "sourceRevision": source_revision,
            "sourceDigest": _source_document(SOURCE_DIGEST),
            "executionBundle": {
                "algorithm": "sha256",
                "digest": "sha256:" + "e" * 64,
                "inputs": ["quwoquan_data/scripts"],
            },
            "entityCatalogDigest": CATALOG_DIGEST,
            "externalInputRefs": [],
            "externalInputsDigest": empty_external,
            "semanticPreflightReceipt": preflight,
        }
        request_digests[carrier] = canonical_digest(stable)
        write_json(
            campaign / "submissions" / f"{execution_ids[carrier]}.json",
            {
                **stable,
                "requestDigest": request_digests[carrier],
                "submittedAt": "2026-08-08T10:04:31Z",
            },
        )
    lane_external_inputs = {
        carrier: {
            "executionId": execution_ids[carrier],
            "externalInputRefs": [],
            "externalInputsDigest": empty_external,
        }
        for carrier in active_carriers
    }
    stable_plan = {
        "schema": "quwoquan_data.content_campaign_plan",
        "rootExecutionId": ROOT_ID,
        "executionMode": "distributed",
        "scale": "M1",
        "workloadMode": "explicit",
        "activeCarriers": list(active_carriers),
        "workloads": {carrier: 1 for carrier in active_carriers},
        "gitBranch": "dev1.0",
        "gitCommitSha": "d" * 40,
        "sourceRevision": source_revision,
        "sourceDigest": SOURCE_DIGEST,
        "executionBundle": {
            "algorithm": "sha256",
            "digest": "sha256:" + "e" * 64,
            "inputs": ["quwoquan_data/scripts"],
        },
        "entityCatalogDigest": CATALOG_DIGEST,
        "semanticSelectionId": "default",
        "semanticPreflightReceipt": preflight,
        "executionAuthority": synthetic_governed_execution_authority(),
        "laneExternalInputs": lane_external_inputs,
        "externalInputsDigest": payload_digest(
            {
                "schema": "quwoquan_data.campaign_external_input_set",
                "refs": lane_external_inputs,
            }
        ),
        "submissionDigests": request_digests,
        "executionIds": execution_ids,
        "frozenAt": "2026-08-08T10:04:40Z",
        "distributedRun": {
            "campaignRunId": RUN_ID,
            "campaignGeneration": 1,
            "campaignFencingToken": FENCING_TOKEN,
        },
    }
    plan = {**stable_plan, "planDigest": canonical_digest(stable_plan)}
    write_json(campaign / "campaign_plan.json", plan)
    lane_rows = {
        carrier: {
            "executionId": execution_ids[carrier],
            "status": "capsule_ready",
            "phase": "capsule",
        }
        for carrier in active_carriers
    }
    write_json(
        campaign / "campaign_report.json",
        {
            "rootExecutionId": ROOT_ID,
            "campaignRunId": RUN_ID,
            "campaignGeneration": 1,
            "campaignFencingToken": FENCING_TOKEN,
            "status": "running",
            "phase": "capsule",
            "planDigest": plan["planDigest"],
            "sourceDigest": SOURCE_DIGEST,
            "entityCatalogDigest": CATALOG_DIGEST,
            "lanes": lane_rows,
        },
    )
    write_json(
        campaign / "runtime/snapshot.json",
        {
            "rootExecutionId": ROOT_ID,
            "runId": RUN_ID,
            "generation": 1,
            "fencingToken": FENCING_TOKEN,
            "status": "frozen",
            "phase": "capsule",
            "planDigest": plan["planDigest"],
            "lanes": {},
            "finishedAt": "2026-08-08T10:04:59Z",
        },
    )
    for carrier in active_carriers:
        execution_root = output_root / "data/tasks" / execution_ids[carrier]
        execution_root.mkdir(parents=True)
        supersession_path = (
            execution_root
            / "_shared/reconciliation"
            / f"supersession-{'1' * 64}.json"
        )
        write_json(supersession_path, {"carrier": carrier})
        write_json(
            campaign / "claims" / f"{carrier}.json",
            {
                "schema": "quwoquan_data.content_campaign_lane_claim",
                "rootExecutionId": ROOT_ID,
                "planDigest": plan["planDigest"],
                "campaignRunId": RUN_ID,
                "campaignGeneration": 1,
                "campaignFencingToken": FENCING_TOKEN,
                "carrier": carrier,
                "executionId": execution_ids[carrier],
                "claimId": "sha256:" + str(CARRIERS.index(carrier) + 1) * 64,
                "claimAttempt": 1,
                "status": "failed",
                "phase": "completed",
                "capsuleRef": "data/local/cache/capsules/shared",
                "executionRoot": str(execution_root),
                "pid": 999_991,
                "pgid": 999_992,
                "returnCode": 1,
                "error": "DATA.CONTRACT.INVALID",
                "acquiredAt": "2026-08-08T10:05:00Z",
                "heartbeatAt": "2026-08-08T10:19:31Z",
                "updatedAt": "2026-08-08T10:19:32Z",
                "finishedAt": "2026-08-08T10:19:32Z",
            },
        )

    def _load(root: Path):
        carrier = root.name.split("--travel-", 1)[1].split("-m1--", 1)[0]
        path = next((root / "_shared/reconciliation").glob("supersession-*.json"))
        return (
            {
                "executionId": root.name,
                "decision": "superseded",
                "reason": "source_drift",
                "manifestSourceDigest": _source_document(SOURCE_DIGEST),
                "observedSourceDigest": _source_document(OBSERVED_SOURCE_DIGEST),
                "receiptDigest": "sha256:" + CARRIERS.index(carrier).__format__("064x"),
                "previousStatus": "manual_required",
            },
            path,
        )

    monkeypatch.setattr(claimed_contract, "_pid_alive", lambda _pid: False)
    monkeypatch.setattr(
        claimed_contract, "_process_group_alive", lambda _pgid: False
    )
    monkeypatch.setattr(
        claimed_contract, "load_execution_supersession_receipt", _load
    )
    monkeypatch.setattr(
        reconciliation,
        "current_source_definition_snapshot",
        lambda **_kwargs: SimpleNamespace(
            to_document=lambda: _source_document(OBSERVED_SOURCE_DIGEST)
        ),
    )
    monkeypatch.setattr(
        reconciliation, "entity_catalog_digest", lambda _ref: CATALOG_DIGEST
    )
    return output_root, campaign, execution_ids


def _write_post_publish_boundary(
    tmp_path: Path,
    output_root: Path,
    campaign: Path,
    execution_ids: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    report_path = campaign / "campaign_report.json"
    report = read_json(report_path)
    assert isinstance(report, dict)
    report.update({"status": "blocked", "phase": "completed"})
    for carrier in CARRIERS:
        lane = report["lanes"][carrier]
        lane.update(
            {
                "status": "blocked",
                "phase": "review" if carrier in {"homepage", "article"} else "submission",
                "reviewReturnCode": 0 if carrier in {"homepage", "article"} else None,
                "publishReturnCode": 1,
                "executionRootRef": f"data/tasks/{execution_ids[carrier]}",
                "cleanupStatus": "cleaned",
                "approvedQuota": 1 if carrier in {"homepage", "article"} else None,
                "qualifiedCount": 1 if carrier in {"homepage", "article"} else None,
                "finalizedCount": 0 if carrier in {"homepage", "article"} else None,
                "selectedCount": 1 if carrier in {"homepage", "article"} else None,
                "discardedCount": 0 if carrier in {"homepage", "article"} else None,
                "shortfallCount": 0 if carrier in {"homepage", "article"} else None,
                "error": "RuntimeError: terminal lane failed",
            }
        )
    write_json(report_path, report)

    article_id = execution_ids["article"]
    article_root = output_root / "data/tasks" / article_id
    transaction_id = f"{article_id}--post-test"
    object_ref = "article/攻略/都江堰市/1"
    merkle = "sha256:" + "9" * 64
    fence = "sha256:" + "8" * 64
    closure = "sha256:" + "7" * 64
    package_path = (
        article_root
        / "evidence/object-transactions"
        / transaction_id
        / "object_transaction_package.json"
    )
    write_json(
        package_path,
        {
            "schema": "quwoquan_data.object_transaction_package",
            "executionId": article_id,
            "transactionId": transaction_id,
            "objectClosureDigest": closure,
            "target": {"objectKind": "posts", "objectRef": object_ref},
        },
    )
    transaction_root = (
        output_root / "data/local/workspace/object-transactions" / transaction_id
    )
    write_json(
        transaction_root / "audit_report.json",
        {
            "schema": "quwoquan_data.object_transaction_dry_run",
            "executionId": article_id,
            "transactionId": transaction_id,
            "objectRef": object_ref,
            "objectClosureDigest": closure,
            "packageSha256": reconciliation.file_digest(package_path),
            "afterCanonical": {"merkleRoot": merkle},
        },
    )
    write_json(
        transaction_root / "apply_report.json",
        {
            "schema": "quwoquan_data.object_transaction_apply",
            "status": "applied",
            "executionId": article_id,
            "transactionId": transaction_id,
            "objectRef": object_ref,
            "objectClosureDigest": closure,
            "afterMerkle": merkle,
            "fenceToken": fence,
        },
    )
    write_json(
        transaction_root / "apply_completion.json",
        {
            "transactionId": transaction_id,
            "afterMerkle": merkle,
            "fenceToken": fence,
        },
    )
    write_json(
        transaction_root / "pointer.json",
        {
            "transactionId": transaction_id,
            "executionId": article_id,
            "state": "applied",
            "afterMerkle": merkle,
            "activeMerkle": merkle,
            "fenceToken": fence,
        },
    )
    write_json(
        article_root / "evidence/reliabletask/publish/job-set/report.json",
        {
            "executionId": article_id,
            "stage": "publish",
            "passed": True,
            "objectTransactionResultCount": 1,
            "researchAcceptedCount": 1,
            "finalizedObjectCount": 0,
            "duplicatePublishCount": 0,
            "missingObjectCount": 0,
        },
    )
    write_json(
        article_root / "publish_ref.json",
        {
            "executionId": article_id,
            "publishedRefs": {"entities": [], "posts": [object_ref]},
        },
    )
    state_path = article_root / "_shared/execution_state.json"
    write_json(
        state_path,
        {
            "executionId": article_id,
            "status": "manual_required",
            "completed": ["publish"],
            "completionGateIssues": ["frozen capsule completion import failed"],
            "throughput": {
                "objectTransactionResultCount": 1,
                "researchAcceptedCount": 1,
                "finalizedObjectCount": 0,
            },
        },
    )
    publish_root = tmp_path / "publish"
    write_json(
        publish_root / "posts" / object_ref / "manifest.json",
        {
            "schema": "quwoquan_data.post_object",
            "executionId": article_id,
            "carrier": "article",
        },
    )
    monkeypatch.setattr(post_publish_contract.paths, "PUBLISH_ROOT", publish_root)
    return state_path


def test_claimed_execution_source_drift_writes_create_once_lineage_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root, campaign, execution_ids = _write_boundary(tmp_path, monkeypatch)
    blocker = campaign / "claims/homepage.json"

    first, path = reconciliation.reconcile_failed_campaign(
        ROOT_ID,
        reason="claimed_execution_source_drift",
        blocker_evidence=blocker,
        repo_root=tmp_path,
        output_root=output_root,
    )
    repeated, repeated_path = reconciliation.reconcile_failed_campaign(
        ROOT_ID,
        reason="claimed_execution_source_drift",
        blocker_evidence=blocker,
        repo_root=tmp_path,
        output_root=output_root,
    )

    assert repeated_path == path
    assert repeated == first
    assert first["errorCode"] == "DATA.CAMPAIGN.CLAIMED_EXECUTION_SOURCE_DRIFT"
    assert [row["executionId"] for row in first["executionEvidence"]["lanes"]] == [
        execution_ids[carrier] for carrier in CARRIERS
    ]
    assert all(
        row["executionRootExists"] is True
        for row in first["executionEvidence"]["lanes"]
    )
    assert read_json(campaign / "campaign_report.json")["status"] == "running"


def test_claimed_recovery_ignores_inactive_article_and_image_lanes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active = ("homepage", "video")
    output_root, campaign, execution_ids = _write_boundary(
        tmp_path,
        monkeypatch,
        active_carriers=active,
    )

    receipt, _path = reconciliation.reconcile_failed_campaign(
        ROOT_ID,
        reason="claimed_execution_source_drift",
        blocker_evidence=campaign / "claims/homepage.json",
        repo_root=tmp_path,
        output_root=output_root,
    )

    assert receipt["activeCarriers"] == list(active)
    assert set(receipt["submissions"]) == set(active)
    assert [row["carrier"] for row in receipt["executionEvidence"]["lanes"]] == list(
        active
    )
    assert set(receipt["campaignEvidence"]["claims"]) == set(active)
    assert execution_ids == {
        carrier: receipt["submissions"][carrier]["executionId"] for carrier in active
    }


def test_claimed_execution_source_drift_requires_four_supersession_receipts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root, campaign, execution_ids = _write_boundary(tmp_path, monkeypatch)
    missing = output_root / "data/tasks" / execution_ids["video"]
    original = claimed_contract.load_execution_supersession_receipt
    monkeypatch.setattr(
        claimed_contract,
        "load_execution_supersession_receipt",
        lambda root: None if root == missing else original(root),
    )

    with pytest.raises(
        CampaignSubmissionReconciliationError,
        match="video execution lacks a supersession receipt",
    ):
        reconciliation.reconcile_failed_campaign(
            ROOT_ID,
            reason="claimed_execution_source_drift",
            blocker_evidence=campaign / "claims/homepage.json",
            repo_root=tmp_path,
            output_root=output_root,
        )


def test_claimed_execution_source_drift_terminalizes_all_dead_stale_claims(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root, campaign, _execution_ids = _write_boundary(tmp_path, monkeypatch)
    for carrier in CARRIERS:
        path = campaign / "claims" / f"{carrier}.json"
        claim = read_json(path)
        claim.update(
            {
                "status": "running",
                "phase": "review-only",
                "returnCode": None,
                "error": None,
                "finishedAt": None,
            }
        )
        write_json(path, claim)

    receipt, _path = reconciliation.reconcile_failed_campaign(
        ROOT_ID,
        reason="claimed_execution_source_drift",
        blocker_evidence=campaign / "claims/homepage.json",
        repo_root=tmp_path,
        output_root=output_root,
    )

    assert receipt["decision"] == "superseded"
    for carrier in CARRIERS:
        claim = read_json(campaign / "claims" / f"{carrier}.json")
        assert claim["status"] == "failed"
        assert claim["phase"] == "completed"
        assert claim["returnCode"] == 130
        assert claim["terminationOwner"] == "external_or_kernel"
        assert claim["finishedAt"]


def test_claimed_execution_source_drift_refuses_live_claim_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root, campaign, _execution_ids = _write_boundary(tmp_path, monkeypatch)
    monkeypatch.setattr(claimed_contract, "_pid_alive", lambda _pid: True)

    with pytest.raises(
        CampaignSubmissionReconciliationError,
        match="homepage claim pid is still live",
    ):
        reconciliation.reconcile_failed_campaign(
            ROOT_ID,
            reason="claimed_execution_source_drift",
            blocker_evidence=campaign / "claims/homepage.json",
            repo_root=tmp_path,
            output_root=output_root,
        )


def test_post_publish_partial_terminal_preserves_applied_article_without_finalizing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root, campaign, execution_ids = _write_boundary(tmp_path, monkeypatch)
    blocker = _write_post_publish_boundary(
        tmp_path, output_root, campaign, execution_ids, monkeypatch
    )

    first, path = reconciliation.reconcile_failed_campaign(
        ROOT_ID,
        reason="post_publish_partial_terminal",
        blocker_evidence=blocker,
        repo_root=tmp_path,
        output_root=output_root,
    )
    repeated, repeated_path = reconciliation.reconcile_failed_campaign(
        ROOT_ID,
        reason="post_publish_partial_terminal",
        blocker_evidence=blocker,
        repo_root=tmp_path,
        output_root=output_root,
    )

    assert repeated_path == path
    assert repeated == first
    assert first["errorCode"] == "DATA.CAMPAIGN.POST_PUBLISH_PARTIAL_TERMINAL"
    evidence = first["executionEvidence"]
    assert evidence["evidenceDisposition"] == "preserved_unadopted"
    assert evidence["excludedFromFinalized"] is True
    assert evidence["eligibleForRelease"] is False
    assert evidence["partialPublish"]["objectRef"] == "article/攻略/都江堰市/1"
    assert evidence["partialPublish"]["researchAcceptedCount"] == 1
    assert evidence["partialPublish"]["finalizedObjectCount"] == 0
    assert not (campaign / "release_selections").exists()


def test_post_publish_partial_terminal_rejects_finalized_or_release_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root, campaign, execution_ids = _write_boundary(tmp_path, monkeypatch)
    blocker = _write_post_publish_boundary(
        tmp_path, output_root, campaign, execution_ids, monkeypatch
    )
    report_path = campaign / "campaign_report.json"
    report = read_json(report_path)
    report["lanes"]["article"]["finalizedCount"] = 1
    write_json(report_path, report)

    with pytest.raises(
        CampaignSubmissionReconciliationError,
        match="article is not one terminal non-finalized lane",
    ):
        reconciliation.reconcile_failed_campaign(
            ROOT_ID,
            reason="post_publish_partial_terminal",
            blocker_evidence=blocker,
            repo_root=tmp_path,
            output_root=output_root,
        )

    report["lanes"]["article"]["finalizedCount"] = 0
    write_json(report_path, report)
    write_json(campaign / "release_selections/release.json", {"releaseId": "forged"})
    with pytest.raises(
        CampaignSubmissionReconciliationError,
        match="already has release selection evidence",
    ):
        reconciliation.reconcile_failed_campaign(
            ROOT_ID,
            reason="post_publish_partial_terminal",
            blocker_evidence=blocker,
            repo_root=tmp_path,
            output_root=output_root,
        )


def test_claimed_execution_reconciliation_requires_retry_to_leave_old_source() -> None:
    payloads = {
        carrier: {
            "sourceRevision": "sha256:" + "1" * 64,
            "sourceDigest": _source_document(OBSERVED_SOURCE_DIGEST),
            "entityCatalogDigest": CATALOG_DIGEST,
        }
        for carrier in CARRIERS
    }
    receipt = {
        "reason": "claimed_execution_source_drift",
        "originalSourceIdentity": {
            "sourceRevision": content_source_revision(
                source_digest=SOURCE_DIGEST,
                entity_catalog_digest=CATALOG_DIGEST,
            ),
            "sourceDigest": _source_document(SOURCE_DIGEST),
            "entityCatalogDigest": CATALOG_DIGEST,
        },
    }
    request_envelope_writer._assert_one_source_identity(
        payloads,
        predecessor_reconciliation_receipt=receipt,
    )
    for payload in payloads.values():
        payload.update(receipt["originalSourceIdentity"])
    with pytest.raises(ValueError, match="did not leave the reconciled source"):
        request_envelope_writer._assert_one_source_identity(
            payloads,
            predecessor_reconciliation_receipt=receipt,
        )
