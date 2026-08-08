from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from content.execution.campaign import failed_execution_reconciliation as reconciliation
from content.execution.campaign import (
    failed_execution_reconciliation_claimed as claimed_contract,
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
    execution_ids = {carrier: _execution_id(carrier) for carrier in CARRIERS}
    request_digests: dict[str, str] = {}
    for carrier in CARRIERS:
        stable = {
            "schema": "quwoquan_data.content_execution_submission",
            "scale": "M1",
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
            "targetNames": ["杭州西湖"],
            "sourceProviders": [],
            "semanticSelectionId": "default",
            "retryOf": execution_ids[carrier].replace("scale-021", "scale-020"),
            "gitBranch": "dev1.0",
            "gitCommitSha": "d" * 40,
            "sourceRevision": source_revision,
            "sourceDigest": _source_document(SOURCE_DIGEST),
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
        for carrier in CARRIERS
    }
    stable_plan = {
        "schema": "quwoquan_data.content_campaign_plan",
        "rootExecutionId": ROOT_ID,
        "executionMode": "distributed",
        "scale": "M1",
        "gitBranch": "dev1.0",
        "gitCommitSha": "d" * 40,
        "sourceRevision": source_revision,
        "sourceDigest": SOURCE_DIGEST,
        "entityCatalogDigest": CATALOG_DIGEST,
        "semanticSelectionId": "default",
        "semanticPreflightReceipt": preflight,
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
        for carrier in CARRIERS
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
    for carrier in CARRIERS:
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
                "rootExecutionId": ROOT_ID,
                "planDigest": plan["planDigest"],
                "campaignRunId": RUN_ID,
                "campaignGeneration": 1,
                "campaignFencingToken": FENCING_TOKEN,
                "carrier": carrier,
                "executionId": execution_ids[carrier],
                "status": "failed",
                "phase": "completed",
                "capsuleRef": "data/local/cache/capsules/shared",
                "executionRoot": str(execution_root),
                "pid": 999_991,
                "pgid": 999_992,
                "returnCode": 1,
                "error": "DATA.CONTRACT.INVALID",
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
        "current_source_digest",
        lambda **_kwargs: SimpleNamespace(
            to_document=lambda: _source_document(OBSERVED_SOURCE_DIGEST)
        ),
    )
    monkeypatch.setattr(
        reconciliation, "entity_catalog_digest", lambda _ref: CATALOG_DIGEST
    )
    return output_root, campaign, execution_ids


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
