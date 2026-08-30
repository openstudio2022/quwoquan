"""Evidence contract for a frozen campaign whose claimed executions are superseded."""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.io import read_json, write_json
from core.schema import assert_valid

from content.execution.campaign.runtime_process import _pid_alive
from content.execution.campaign.submission_reconciliation_contract import (
    campaigns_root,
    canonical_digest,
    file_digest,
    frozen_plan_workload,
    frozen_submission_workload,
    safe_regular_ref,
    typed,
)
from content.execution.execution_supersession import (
    load_execution_supersession_receipt,
)


def _file_binding(path: Path, *, output_root: Path, label: str) -> dict[str, str]:
    return {
        "ref": safe_regular_ref(path, output_root=output_root, label=label),
        "sha256": file_digest(path),
    }


def _dead_process(value: object, *, carrier: str, label: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 2:
        raise typed(
            "CAMPAIGN_EVIDENCE_INVALID",
            f"{carrier} claim {label} is invalid",
        )
    if _pid_alive(value):
        raise typed(
            "CAMPAIGN_NOT_TERMINAL_FAILED",
            f"{carrier} claim {label} is still live",
        )


def _process_group_alive(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, int) or value < 2:
        return False
    try:
        os.killpg(value, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminalize_superseded_dead_claims(
    campaign: Path,
    *,
    root_execution_id: str,
    expected_ids: Mapping[str, str],
    plan: Mapping[str, Any],
    distributed: Mapping[str, Any],
    original_digest: object,
    output_root: Path,
) -> None:
    """Close stale active claims only after every active execution is superseded.

    A lane wrapper can disappear before its context-manager writes the terminal
    claim. Reconciliation may close that bookkeeping gap, but only after every
    process is dead and every execution has a current-code source-drift
    supersession receipt. Validation is completed for all lanes before the
    first claim byte is changed.
    """

    pending: list[tuple[Path, dict[str, Any]]] = []
    for carrier in expected_ids:
        execution_id = expected_ids[carrier]
        path = campaign / "claims" / f"{carrier}.json"
        claim = read_json(path)
        if not isinstance(claim, dict):
            raise typed(
                "CAMPAIGN_EVIDENCE_INVALID",
                f"{carrier} claimed execution has no claim object",
            )
        terminal = claim.get("status") == "failed" and claim.get("phase") == "completed"
        stale = (
            claim.get("status") in {"active", "starting", "running"}
            and claim.get("phase") in {"claim", "review-only", "run"}
        )
        execution_root = output_root / "data/tasks" / execution_id
        if (
            claim.get("rootExecutionId") != root_execution_id
            or claim.get("carrier") != carrier
            or claim.get("executionId") != execution_id
            or claim.get("planDigest") != plan.get("planDigest")
            or claim.get("campaignRunId") != distributed.get("campaignRunId")
            or claim.get("campaignGeneration")
            != distributed.get("campaignGeneration")
            or claim.get("campaignFencingToken")
            != distributed.get("campaignFencingToken")
            or not (terminal or stale)
        ):
            raise typed(
                "CAMPAIGN_NOT_TERMINAL_FAILED",
                f"{carrier} is not a superseded stale claim",
            )
        _dead_process(claim.get("pid"), carrier=carrier, label="pid")
        pgid = claim.get("pgid")
        if (
            isinstance(pgid, bool)
            or not isinstance(pgid, int)
            or pgid < 2
            or _process_group_alive(pgid)
        ):
            raise typed(
                "CAMPAIGN_NOT_TERMINAL_FAILED",
                f"{carrier} claim pgid is invalid or still live",
            )
        try:
            observed_root = Path(str(claim.get("executionRoot") or "")).resolve()
            root_matches = observed_root == execution_root.resolve()
        except (OSError, RuntimeError):
            root_matches = False
        loaded = None
        if (
            root_matches
            and execution_root.is_dir()
            and not execution_root.is_symlink()
        ):
            loaded = load_execution_supersession_receipt(execution_root)
        if loaded is None:
            raise typed(
                "EXECUTION_EVIDENCE_INVALID",
                f"{carrier} execution lacks a supersession receipt",
            )
        supersession, _supersession_path = loaded
        if (
            supersession.get("executionId") != execution_id
            or supersession.get("reason") != "source_drift"
            or supersession.get("decision") != "superseded"
            or (supersession.get("manifestSourceDigest") or {}).get("digest")
            != original_digest
        ):
            raise typed(
                "EXECUTION_EVIDENCE_INVALID",
                f"{carrier} stale claim supersession identity drifted",
            )
        assert_valid(
            claim,
            "execution",
            "content_campaign_lane_claim",
            label=f"claimed source-drift claim:{carrier}",
        )
        if stale:
            pending.append((path, claim))

    now = datetime.now(timezone.utc).isoformat()
    for path, claim in pending:
        claim.update(
            {
                "status": "failed",
                "phase": "completed",
                "returnCode": (
                    claim["returnCode"]
                    if isinstance(claim.get("returnCode"), int)
                    and int(claim["returnCode"]) != 0
                    else 130
                ),
                "error": str(claim.get("error") or "").strip()
                or "DATA.CAMPAIGN.LANE_PROCESS_GONE_AFTER_CLAIMED_SOURCE_DRIFT",
                "terminationOwner": claim.get("terminationOwner")
                or "external_or_kernel",
                "updatedAt": now,
                "finishedAt": now,
            }
        )
        assert_valid(
            claim,
            "execution",
            "content_campaign_lane_claim",
            label=f"claimed source-drift terminal claim:{claim['carrier']}",
        )
        write_json(path, claim)


def claimed_execution_source_drift_evidence(
    root_execution_id: str,
    submissions: Mapping[str, Mapping[str, Any]],
    original_source_identity: Mapping[str, Any],
    *,
    output_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Bind active failed claims to current-code supersession receipts.

    The only permitted mutation is an atomic-after-validation terminal update
    for stale claims whose processes are dead and whose executions are already
    superseded. Campaign reports and execution roots remain immutable.
    """

    campaign = campaigns_root(output_root) / root_execution_id
    plan_path = campaign / "campaign_plan.json"
    report_path = campaign / "campaign_report.json"
    runtime_path = campaign / "runtime/snapshot.json"
    plan = read_json(plan_path)
    report = read_json(report_path)
    runtime = read_json(runtime_path)
    if not all(isinstance(row, dict) for row in (plan, report, runtime)):
        raise typed(
            "CAMPAIGN_EVIDENCE_INVALID",
            "claimed execution reconciliation requires plan/report/runtime objects",
        )
    try:
        assert_valid(
            plan,
            "execution",
            "content_campaign_plan",
            label=f"claimed campaign plan:{root_execution_id}",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise typed("CAMPAIGN_EVIDENCE_INVALID", str(exc)) from exc
    stable_plan = {key: value for key, value in plan.items() if key != "planDigest"}
    if plan.get("planDigest") != canonical_digest(stable_plan):
        raise typed("CAMPAIGN_EVIDENCE_INVALID", "campaign planDigest drifted")

    original_digest = (original_source_identity.get("sourceDigest") or {}).get(
        "digest"
    )
    distributed = plan.get("distributedRun")
    report_lanes = report.get("lanes")
    active_carriers, _workloads, plan_execution_ids, _root = frozen_plan_workload(
        plan,
        root_execution_id=root_execution_id,
    )
    submission_carriers, _submission_workloads, _submission_root = (
        frozen_submission_workload(
            submissions,
            root_execution_id=root_execution_id,
        )
    )
    if (
        plan.get("rootExecutionId") != root_execution_id
        or plan.get("sourceRevision")
        != original_source_identity.get("sourceRevision")
        or plan.get("sourceDigest") != original_digest
        or plan.get("entityCatalogDigest")
        != original_source_identity.get("entityCatalogDigest")
        or not isinstance(distributed, Mapping)
        or not isinstance(report_lanes, Mapping)
    ):
        raise typed("IDENTITY_DRIFT", "claimed campaign plan identity drifted")
    expected_ids = {
        carrier: str(submissions[carrier]["executionId"])
        for carrier in active_carriers
    }
    expected_digests = {
        carrier: str(submissions[carrier]["requestDigest"])
        for carrier in active_carriers
    }
    if (
        active_carriers != submission_carriers
        or plan_execution_ids != expected_ids
        or plan.get("executionIds") != expected_ids
        or plan.get("submissionDigests") != expected_digests
        or set(report_lanes) != set(active_carriers)
    ):
        raise typed(
            "IDENTITY_DRIFT",
            "claimed campaign plan is not bound to the active submissions",
        )
    _terminalize_superseded_dead_claims(
        campaign,
        root_execution_id=root_execution_id,
        expected_ids=expected_ids,
        plan=plan,
        distributed=distributed,
        original_digest=original_digest,
        output_root=output_root,
    )
    if (
        report.get("rootExecutionId") != root_execution_id
        or report.get("status") != "running"
        or report.get("phase") != "capsule"
        or report.get("planDigest") != plan.get("planDigest")
        or report.get("campaignRunId") != distributed.get("campaignRunId")
        or report.get("campaignGeneration")
        != distributed.get("campaignGeneration")
        or report.get("campaignFencingToken")
        != distributed.get("campaignFencingToken")
        or report.get("sourceDigest") != original_digest
        or report.get("entityCatalogDigest")
        != original_source_identity.get("entityCatalogDigest")
    ):
        raise typed(
            "CAMPAIGN_EVIDENCE_INVALID",
            "campaign report is not the frozen pre-finalize boundary",
        )
    if (
        runtime.get("rootExecutionId") != root_execution_id
        or runtime.get("status") != "frozen"
        or runtime.get("phase") != "capsule"
        or runtime.get("planDigest") != plan.get("planDigest")
        or runtime.get("runId") != distributed.get("campaignRunId")
        or runtime.get("generation") != distributed.get("campaignGeneration")
        or runtime.get("fencingToken")
        != distributed.get("campaignFencingToken")
        or runtime.get("lanes") != {}
        or not str(runtime.get("finishedAt") or "").strip()
    ):
        raise typed(
            "CAMPAIGN_EVIDENCE_INVALID",
            "campaign runtime is not one frozen capsule boundary",
        )

    claim_bindings: dict[str, dict[str, str]] = {}
    execution_rows: list[dict[str, Any]] = []
    capsule_ref: str | None = None
    for carrier in active_carriers:
        execution_id = expected_ids[carrier]
        claim_path = campaign / "claims" / f"{carrier}.json"
        claim = read_json(claim_path)
        lane = report_lanes.get(carrier)
        execution_root = output_root / "data/tasks" / execution_id
        if (
            not isinstance(claim, Mapping)
            or not isinstance(lane, Mapping)
            or claim.get("rootExecutionId") != root_execution_id
            or claim.get("carrier") != carrier
            or claim.get("executionId") != execution_id
            or claim.get("planDigest") != plan.get("planDigest")
            or claim.get("campaignRunId") != distributed.get("campaignRunId")
            or claim.get("campaignGeneration")
            != distributed.get("campaignGeneration")
            or claim.get("campaignFencingToken")
            != distributed.get("campaignFencingToken")
            or claim.get("status") != "failed"
            or claim.get("phase") != "completed"
            or not isinstance(claim.get("returnCode"), int)
            or int(claim.get("returnCode")) == 0
            or not str(claim.get("error") or "").strip()
            or not str(claim.get("finishedAt") or "").strip()
            or lane.get("executionId") != execution_id
            or lane.get("status") != "capsule_ready"
            or lane.get("phase") != "capsule"
        ):
            raise typed(
                "CAMPAIGN_NOT_TERMINAL_FAILED",
                f"{carrier} is not one terminal claimed execution failure",
            )
        _dead_process(claim.get("pid"), carrier=carrier, label="pid")
        pgid = claim.get("pgid")
        if (
            isinstance(pgid, bool)
            or not isinstance(pgid, int)
            or pgid < 2
            or _process_group_alive(pgid)
        ):
            raise typed(
                "CAMPAIGN_NOT_TERMINAL_FAILED",
                f"{carrier} claim pgid is invalid or still live",
            )
        try:
            observed_execution_root = Path(str(claim.get("executionRoot") or ""))
            same_root = observed_execution_root.resolve() == execution_root.resolve()
        except (OSError, RuntimeError):
            same_root = False
        if (
            not same_root
            or execution_root.is_symlink()
            or not execution_root.is_dir()
        ):
            raise typed(
                "EXECUTION_EVIDENCE_INVALID",
                f"{carrier} execution root is missing or identity-drifted",
            )
        loaded = load_execution_supersession_receipt(execution_root)
        if loaded is None:
            raise typed(
                "EXECUTION_EVIDENCE_INVALID",
                f"{carrier} execution lacks a supersession receipt",
            )
        supersession, supersession_path = loaded
        if (
            supersession.get("executionId") != execution_id
            or supersession.get("reason") != "source_drift"
            or supersession.get("decision") != "superseded"
            or (supersession.get("manifestSourceDigest") or {}).get("digest")
            != original_digest
            or supersession.get("observedSourceDigest")
            == original_source_identity.get("sourceDigest")
        ):
            raise typed(
                "EXECUTION_EVIDENCE_INVALID",
                f"{carrier} supersession is not bound to the campaign source drift",
            )
        observed_capsule = str(claim.get("capsuleRef") or "")
        if not observed_capsule or (
            capsule_ref is not None and observed_capsule != capsule_ref
        ):
            raise typed(
                "CAMPAIGN_EVIDENCE_INVALID",
                "claimed executions do not share one frozen capsule",
            )
        capsule_ref = observed_capsule
        claim_bindings[carrier] = _file_binding(
            claim_path,
            output_root=output_root,
            label=f"{carrier} terminal claim",
        )
        execution_rows.append(
            {
                "carrier": carrier,
                "executionId": execution_id,
                "executionRootRef": execution_root.relative_to(output_root).as_posix(),
                "executionRootExists": True,
                "supersessionReceipt": _file_binding(
                    supersession_path,
                    output_root=output_root,
                    label=f"{carrier} supersession receipt",
                ),
                "supersessionReceiptDigest": supersession["receiptDigest"],
                "previousStatus": supersession["previousStatus"],
            }
        )

    campaign_evidence = {
        "plan": _file_binding(
            plan_path, output_root=output_root, label="claimed campaign plan"
        ),
        "report": _file_binding(
            report_path, output_root=output_root, label="claimed campaign report"
        ),
        "runtimeSnapshot": _file_binding(
            runtime_path, output_root=output_root, label="claimed campaign runtime"
        ),
        "claims": claim_bindings,
    }
    return campaign_evidence, {"lanes": execution_rows}, report


__all__ = ["claimed_execution_source_drift_evidence"]
