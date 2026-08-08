"""Evidence contract for a controller interrupted before any lane claim."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.execution.campaign.lane import CAMPAIGN_CARRIERS
from content.execution.campaign.runtime_process import _pid_alive
from content.execution.campaign.submission_reconciliation_contract import (
    campaigns_root,
    canonical_digest,
    file_digest,
    safe_regular_ref,
    typed,
)
from core.io import read_json
from core.schema import assert_valid


_TERMINATION_PREFIX = (
    "CampaignControllerTerminated: "
    "DATA.CAMPAIGN.CONTROLLER_TERMINATED signal="
)


def _file_binding(
    path: Path,
    *,
    output_root: Path,
    label: str,
) -> dict[str, str]:
    return {
        "ref": safe_regular_ref(path, output_root=output_root, label=label),
        "sha256": file_digest(path),
    }


def _empty_directory(path: Path, *, label: str) -> None:
    if path.is_symlink():
        raise typed("CAMPAIGN_EVIDENCE_INVALID", f"{label} must not be a symlink")
    if not path.exists():
        return
    if not path.is_dir() or any(path.iterdir()):
        raise typed("CAMPAIGN_EVIDENCE_INVALID", f"{label} must be absent or empty")


def _dead_process(value: object, *, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 2:
        raise typed("CAMPAIGN_EVIDENCE_INVALID", f"controller {label} is invalid")
    if _pid_alive(value):
        raise typed("CAMPAIGN_NOT_TERMINAL_FAILED", f"controller {label} is still live")


def controller_interrupted_before_claim_evidence(
    root_execution_id: str,
    submissions: Mapping[str, Mapping[str, Any]],
    original_source_identity: Mapping[str, Any],
    *,
    output_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return immutable evidence only for the exact pre-claim interruption state."""

    campaign = campaigns_root(output_root) / root_execution_id
    plan_path = campaign / "campaign_plan.json"
    runtime_path = campaign / "runtime/snapshot.json"
    report_path = campaign / "campaign_report.json"
    plan = read_json(plan_path)
    runtime = read_json(runtime_path)
    if not isinstance(plan, dict) or not isinstance(runtime, Mapping):
        raise typed(
            "CAMPAIGN_EVIDENCE_INVALID",
            "controller interruption requires one plan and runtime snapshot",
        )
    try:
        assert_valid(
            plan,
            "execution",
            "content_campaign_plan",
            label=f"interrupted campaign plan:{root_execution_id}",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise typed("CAMPAIGN_EVIDENCE_INVALID", str(exc)) from exc
    stable_plan = {key: value for key, value in plan.items() if key != "planDigest"}
    if plan.get("planDigest") != canonical_digest(stable_plan):
        raise typed("CAMPAIGN_EVIDENCE_INVALID", "campaign planDigest drifted")

    distributed = plan.get("distributedRun")
    expected_execution_ids = {
        carrier: str(submissions[carrier]["executionId"])
        for carrier in CAMPAIGN_CARRIERS
    }
    expected_submission_digests = {
        carrier: str(submissions[carrier]["requestDigest"])
        for carrier in CAMPAIGN_CARRIERS
    }
    if (
        plan.get("rootExecutionId") != root_execution_id
        or plan.get("executionIds") != expected_execution_ids
        or plan.get("submissionDigests") != expected_submission_digests
        or plan.get("sourceRevision")
        != original_source_identity.get("sourceRevision")
        or plan.get("sourceDigest")
        != (original_source_identity.get("sourceDigest") or {}).get("digest")
        or plan.get("entityCatalogDigest")
        != original_source_identity.get("entityCatalogDigest")
        or not isinstance(distributed, Mapping)
    ):
        raise typed(
            "IDENTITY_DRIFT",
            "campaign plan is not bound to the four immutable submissions",
        )

    if (
        runtime.get("schema") != "quwoquan_data.content_campaign_runtime_snapshot"
        or runtime.get("rootExecutionId") != root_execution_id
        or runtime.get("runId") != distributed.get("campaignRunId")
        or runtime.get("generation") != distributed.get("campaignGeneration")
        or runtime.get("fencingToken")
        != distributed.get("campaignFencingToken")
        or runtime.get("planDigest") != plan.get("planDigest")
    ):
        raise typed("IDENTITY_DRIFT", "controller runtime identity drifted")
    if (
        runtime.get("status") != "interrupted"
        or runtime.get("phase") != "controller"
        or runtime.get("lanes") != {}
        or not str(runtime.get("finishedAt") or "").strip()
        or not str(runtime.get("failure") or "").startswith(_TERMINATION_PREFIX)
    ):
        raise typed(
            "CAMPAIGN_NOT_TERMINAL_FAILED",
            "campaign is not one terminal controller-before-claim interruption",
        )
    _dead_process(runtime.get("pid"), label="pid")
    _dead_process(runtime.get("pgid"), label="pgid")

    if report_path.exists():
        raise typed(
            "CAMPAIGN_EVIDENCE_INVALID",
            "controller-before-claim campaign must not have a report",
        )
    _empty_directory(campaign / "claims", label="campaign claims")
    _empty_directory(
        campaign / "runtime/lanes",
        label="campaign runtime lane checkpoints",
    )
    return (
        {
            "plan": _file_binding(
                plan_path,
                output_root=output_root,
                label="interrupted campaign plan",
            ),
            "runtimeSnapshot": _file_binding(
                runtime_path,
                output_root=output_root,
                label="interrupted campaign runtime snapshot",
            ),
            "campaignReportExists": False,
            "claimsPresent": False,
            "runtimeLaneCheckpointsPresent": False,
        },
        plan,
    )


def failed_campaign_execution_absence(
    submissions: Mapping[str, Mapping[str, Any]],
    *,
    output_root: Path,
) -> dict[str, Any]:
    """Prove that none of the four submitted lanes owns a task root."""

    lanes: list[dict[str, Any]] = []
    for carrier in CAMPAIGN_CARRIERS:
        execution_id = str(submissions[carrier]["executionId"])
        execution_root = output_root / "data/tasks" / execution_id
        if execution_root.exists():
            raise typed(
                "EXECUTION_EVIDENCE_PRESENT",
                f"{carrier} execution root must be discarded first",
            )
        lanes.append(
            {
                "carrier": carrier,
                "executionId": execution_id,
                "executionRootRef": f"data/tasks/{execution_id}",
                "executionRootExists": False,
                "executionManifestExists": False,
                "targetSetExists": False,
                "publishRefExists": False,
            }
        )
    return {"lanes": lanes}


__all__ = [
    "controller_interrupted_before_claim_evidence",
    "failed_campaign_execution_absence",
]
