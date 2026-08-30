"""Terminalize abandoned claims after a frozen campaign source drift."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from core.io import read_json, write_json
from core.schema import assert_valid

from content.execution.campaign.failed_execution_reconciliation_common import _now
from content.execution.campaign.lane import CAMPAIGN_CARRIERS
from content.execution.campaign.runtime_process import _pid_alive
from content.execution.campaign.submission_reconciliation_contract import (
    campaigns_root,
    typed,
)
from content.execution.campaign.failed_execution_reconciliation_source_drift import (
    source_drift_successor,
)


def _terminalize_dead_source_drift_claims(
    root_id: str,
    *,
    output_root: Path,
) -> None:
    campaign = campaigns_root(output_root) / root_id
    plan = read_json(campaign / "campaign_plan.json")
    report = read_json(campaign / "campaign_report.json")
    runtime = read_json(campaign / "runtime/snapshot.json")
    if not all(isinstance(item, Mapping) for item in (plan, report, runtime)):
        return
    if not source_drift_successor(plan, report, runtime):
        return
    distributed = plan["distributedRun"]
    for carrier in CAMPAIGN_CARRIERS:
        path = campaign / "claims" / f"{carrier}.json"
        claim = read_json(path)
        if not isinstance(claim, dict) or claim.get("status") not in {
            "active",
            "starting",
            "running",
        }:
            continue
        execution_root = Path(str(claim.get("executionRoot") or ""))
        if (
            claim.get("rootExecutionId") != root_id
            or claim.get("carrier") != carrier
            or claim.get("planDigest") != plan.get("planDigest")
            or claim.get("campaignRunId") != distributed.get("campaignRunId")
            or claim.get("campaignGeneration")
            != distributed.get("campaignGeneration")
            or claim.get("campaignFencingToken")
            != distributed.get("campaignFencingToken")
            or _pid_alive(claim.get("pid"))
            or _pid_alive(claim.get("pgid"))
            or execution_root.exists()
        ):
            raise typed(
                "CAMPAIGN_NOT_TERMINAL_FAILED",
                f"{carrier} source-drift claim is still live or identity-drifted",
            )
        now = _now()
        claim.update(
            {
                "status": "failed",
                "phase": "completed",
                "returnCode": (
                    claim["returnCode"]
                    if isinstance(claim.get("returnCode"), int)
                    and claim["returnCode"] != 0
                    else 130
                ),
                "error": str(claim.get("error") or "").strip()
                or "DATA.CAMPAIGN.LANE_PROCESS_GONE_AFTER_SOURCE_DRIFT",
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
            label=f"source-drift terminal campaign lane claim:{carrier}",
        )
        write_json(path, claim)
