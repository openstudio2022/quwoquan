from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

import pytest
from content.execution.campaign import failed_execution_reconciliation as reconciliation
from content.execution.campaign import (
    failed_execution_reconciliation_controller as controller_contract,
)
from content.execution.campaign.external_inputs import payload_digest
from content.execution.campaign.submission_reconciliation_contract import (
    CampaignSubmissionReconciliationError,
    canonical_digest,
)
from content.execution.identity import build_execution_id
from core.io import read_json, write_json
from core.source_digest import content_source_revision
from support.semantic_preflight_fixture import ready_semantic_preflight


ROOT_ID = (
    "20260808--travel-homepage-m1--china-beta-bootstrap-not-m100--scale-016"
)
CARRIERS = ("homepage", "article", "image", "video")
SOURCE_DIGEST = "sha256:" + "a" * 64
CATALOG_DIGEST = "sha256:" + "b" * 64
OBSERVED_SOURCE_DIGEST = "sha256:" + "c" * 64
RUN_ID = "controller-before-claim-run"
FENCING_TOKEN = "sha256:" + "f" * 64


def _execution_id(carrier: str) -> str:
    return build_execution_id(
        run_date="20260808",
        vertical="travel",
        content_type=carrier,
        intent="m1",
        scope="china-beta-bootstrap-not-m100",
        phase="scale",
        sequence=16,
    )


def _write_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, Path, dict[str, str]]:
    output_root = tmp_path / "output"
    _receipt_path, preflight_binding = ready_semantic_preflight(
        "default",
        output_root=output_root,
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
    source_document = {
        "algorithm": "sha256",
        "digest": SOURCE_DIGEST,
        "inputs": ["quwoquan_data/scripts"],
    }
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
            "retryOf": execution_ids[carrier].replace("scale-016", "scale-015"),
            "gitBranch": "dev1.0",
            "gitCommitSha": "d" * 40,
            "sourceRevision": source_revision,
            "sourceDigest": source_document,
            "entityCatalogDigest": CATALOG_DIGEST,
            "externalInputRefs": [],
            "externalInputsDigest": empty_external,
            "semanticPreflightReceipt": preflight_binding,
        }
        request_digest = canonical_digest(stable)
        request_digests[carrier] = request_digest
        write_json(
            campaign / "submissions" / f"{execution_ids[carrier]}.json",
            {**stable, "requestDigest": request_digest, "submittedAt": "2026-08-08T04:56:22Z"},
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
        "semanticPreflightReceipt": preflight_binding,
        "laneExternalInputs": lane_external_inputs,
        "externalInputsDigest": payload_digest(
            {
                "schema": "quwoquan_data.campaign_external_input_set",
                "refs": lane_external_inputs,
            }
        ),
        "submissionDigests": request_digests,
        "executionIds": execution_ids,
        "frozenAt": "2026-08-08T04:56:31Z",
        "distributedRun": {
            "campaignRunId": RUN_ID,
            "campaignGeneration": 1,
            "campaignFencingToken": FENCING_TOKEN,
        },
    }
    plan = {**stable_plan, "planDigest": canonical_digest(stable_plan)}
    write_json(campaign / "campaign_plan.json", plan)
    runtime_path = campaign / "runtime/snapshot.json"
    write_json(
        runtime_path,
        {
            "schema": "quwoquan_data.content_campaign_runtime_snapshot",
            "rootExecutionId": ROOT_ID,
            "runId": RUN_ID,
            "generation": 1,
            "fencingToken": FENCING_TOKEN,
            "status": "interrupted",
            "phase": "controller",
            "planDigest": plan["planDigest"],
            "pid": 999_991,
            "pgid": 999_992,
            "hostname": "contract.invalid",
            "controllerProcessIdentity": "sha256:" + "1" * 64,
            "leaseSeconds": 900,
            "startedAt": "2026-08-08T04:56:30Z",
            "heartbeatAt": "2026-08-08T04:56:47Z",
            "updatedAt": "2026-08-08T04:56:47Z",
            "finishedAt": "2026-08-08T04:56:47Z",
            "failure": (
                "CampaignControllerTerminated: "
                "DATA.CAMPAIGN.CONTROLLER_TERMINATED signal=SIGTERM"
            ),
            "lanes": {},
        },
    )
    monkeypatch.setattr(controller_contract, "_pid_alive", lambda _pid: False)
    monkeypatch.setattr(
        reconciliation,
        "current_source_digest",
        lambda **_kwargs: SimpleNamespace(
            to_document=lambda: {
                "algorithm": "sha256",
                "digest": OBSERVED_SOURCE_DIGEST,
                "inputs": ["quwoquan_data/scripts"],
            }
        ),
    )
    monkeypatch.setattr(
        reconciliation,
        "entity_catalog_digest",
        lambda _ref: CATALOG_DIGEST,
    )
    return output_root, campaign, runtime_path, execution_ids


def _reconcile(tmp_path: Path, output_root: Path):
    return reconciliation.reconcile_failed_campaign(
        ROOT_ID,
        reason="controller_interrupted_before_claim",
        repo_root=tmp_path,
        output_root=output_root,
    )


def test_controller_interrupted_before_claim_writes_create_once_typed_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root, _campaign, runtime_path, execution_ids = _write_boundary(
        tmp_path, monkeypatch
    )

    first, receipt_path = _reconcile(tmp_path, output_root)
    repeated, repeated_path = _reconcile(tmp_path, output_root)

    assert repeated_path == receipt_path
    assert repeated == first
    assert first["reason"] == "controller_interrupted_before_claim"
    assert first["errorCode"] == (
        "DATA.CAMPAIGN.CONTROLLER_INTERRUPTED_BEFORE_CLAIM"
    )
    assert first["blockerEvidence"] == first["campaignEvidence"]["runtimeSnapshot"]
    assert first["campaignEvidence"]["campaignReportExists"] is False
    assert first["campaignEvidence"]["claimsPresent"] is False
    assert first["campaignEvidence"]["runtimeLaneCheckpointsPresent"] is False
    assert {
        row["executionId"] for row in first["executionEvidence"]["lanes"]
    } == set(execution_ids.values())
    assert Path(runtime_path).is_file()
    assert reconciliation.validate_failed_campaign_reconciliation_receipt(
        receipt_path,
        output_root=output_root,
    ) == first


@pytest.mark.parametrize(
    ("case", "expected_code"),
    (
        ("runtime_status", "CAMPAIGN_NOT_TERMINAL_FAILED"),
        ("runtime_phase", "CAMPAIGN_NOT_TERMINAL_FAILED"),
        ("runtime_lanes", "CAMPAIGN_NOT_TERMINAL_FAILED"),
        ("runtime_identity", "IDENTITY_DRIFT"),
        ("plan_identity", "IDENTITY_DRIFT"),
        ("claim_present", "CAMPAIGN_EVIDENCE_INVALID"),
        ("report_present", "CAMPAIGN_EVIDENCE_INVALID"),
        ("checkpoint_present", "CAMPAIGN_EVIDENCE_INVALID"),
        ("task_root_present", "EXECUTION_EVIDENCE_PRESENT"),
        ("live_controller", "CAMPAIGN_NOT_TERMINAL_FAILED"),
    ),
)
def test_controller_interrupted_before_claim_rejects_non_exact_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    expected_code: str,
) -> None:
    output_root, campaign, runtime_path, execution_ids = _write_boundary(
        tmp_path, monkeypatch
    )
    runtime = read_json(runtime_path)
    plan_path = campaign / "campaign_plan.json"
    plan = read_json(plan_path)
    assert isinstance(runtime, dict) and isinstance(plan, dict)
    if case == "runtime_status":
        runtime["status"] = "active"
    elif case == "runtime_phase":
        runtime["phase"] = "submission"
    elif case == "runtime_lanes":
        runtime["lanes"] = {"homepage": {"status": "starting"}}
    elif case == "runtime_identity":
        runtime["runId"] = "other-run"
    elif case == "plan_identity":
        plan["executionIds"]["article"] = "other-execution"
        stable = {key: value for key, value in plan.items() if key != "planDigest"}
        plan["planDigest"] = canonical_digest(stable)
        runtime["planDigest"] = plan["planDigest"]
        write_json(plan_path, plan)
    elif case == "claim_present":
        write_json(campaign / "claims/homepage.json", {"status": "starting"})
    elif case == "report_present":
        write_json(campaign / "campaign_report.json", {"status": "interrupted"})
    elif case == "checkpoint_present":
        write_json(campaign / "runtime/lanes/homepage.json", {"status": "starting"})
    elif case == "task_root_present":
        (output_root / "data/tasks" / execution_ids["homepage"]).mkdir(parents=True)
    elif case == "live_controller":
        monkeypatch.setattr(
            controller_contract,
            "_pid_alive",
            lambda pid: pid == runtime["pid"],
        )
    write_json(runtime_path, runtime)

    with pytest.raises(CampaignSubmissionReconciliationError) as captured:
        _reconcile(tmp_path, output_root)
    assert expected_code in captured.value.code


def test_controller_interruption_rejects_identity_drift_and_create_once_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root, campaign, runtime_path, _execution_ids = _write_boundary(
        tmp_path, monkeypatch
    )
    _receipt, receipt_path = _reconcile(tmp_path, output_root)
    runtime = read_json(runtime_path)
    assert isinstance(runtime, dict)
    runtime["fencingToken"] = "sha256:" + "2" * 64
    write_json(runtime_path, runtime)
    with pytest.raises(CampaignSubmissionReconciliationError) as drift:
        reconciliation.validate_failed_campaign_reconciliation_receipt(
            receipt_path,
            output_root=output_root,
        )
    assert "IDENTITY_DRIFT" in drift.value.code

    write_json(runtime_path, {**runtime, "fencingToken": FENCING_TOKEN})
    with pytest.raises(CampaignSubmissionReconciliationError) as collision:
        reconciliation.reconcile_failed_campaign(
            ROOT_ID,
            reason="source_drift",
            blocker_evidence=campaign / "runtime/snapshot.json",
            repo_root=tmp_path,
            output_root=output_root,
        )
    assert "CREATE_ONCE_COLLISION" in collision.value.code


def test_failed_campaign_cli_accepts_explicit_controller_reason_without_blocker() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command")
    reconciliation.register_reconcile_failed_campaign_parser(commands)

    args = parser.parse_args(
        [
            "reconcile-failed-campaign",
            "--campaign-root-execution-id",
            ROOT_ID,
            "--reason",
            "controller_interrupted_before_claim",
        ]
    )

    assert args.reason == "controller_interrupted_before_claim"
    assert args.blocker_evidence is None
