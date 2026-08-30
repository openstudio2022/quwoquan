"""Read and validate an already-frozen distributed campaign."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.io import read_json
from core.schema import assert_valid

from content.execution.campaign.lane import normalize_active_carriers
from content.execution.campaign.plan import report_path, sha256_payload
from content.execution.campaign.runtime import read_runtime_snapshot
from content.execution.campaign.submission import campaign_root, load_submissions
from content.execution.campaign.workspace import CampaignRuntimePaths


def load_distributed_plan(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
) -> dict[str, Any]:
    path = (
        campaign_root(root_execution_id, root=runtime.campaigns_root)
        / "campaign_plan.json"
    )
    plan = read_json(path)
    assert_valid(
        plan,
        "execution",
        "content_campaign_plan",
        label=f"distributed campaign plan:{root_execution_id}",
    )
    stable = {key: value for key, value in plan.items() if key != "planDigest"}
    if (
        plan.get("rootExecutionId") != root_execution_id
        or plan.get("executionMode") != "distributed"
        or plan.get("planDigest") != sha256_payload(stable)
    ):
        raise ValueError("distributed campaign plan identity or digest drift")
    return plan


def reuse_existing_frozen_campaign(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
) -> Path | None:
    campaign = campaign_root(root_execution_id, root=runtime.campaigns_root)
    if not (campaign / "campaign_plan.json").is_file():
        return None
    plan = load_distributed_plan(runtime, root_execution_id)
    submissions = load_submissions(
        root_execution_id,
        root=runtime.campaigns_root,
    )
    active = normalize_active_carriers(plan["activeCarriers"])
    if set(submissions) != set(active):
        raise ValueError("existing frozen campaign submissions are incomplete")
    for carrier in active:
        if (
            plan["executionIds"].get(carrier)
            != submissions[carrier].get("executionId")
            or plan["submissionDigests"].get(carrier)
            != submissions[carrier].get("requestDigest")
        ):
            raise ValueError(
                f"existing frozen campaign {carrier} submission drift"
            )
    distributed_run = plan.get("distributedRun")
    snapshot = read_runtime_snapshot(runtime, root_execution_id)
    if (
        not isinstance(distributed_run, dict)
        or not isinstance(snapshot, dict)
        or snapshot.get("runId") != distributed_run.get("campaignRunId")
        or snapshot.get("generation")
        != distributed_run.get("campaignGeneration")
        or snapshot.get("fencingToken")
        != distributed_run.get("campaignFencingToken")
        or snapshot.get("planDigest") != plan.get("planDigest")
        or snapshot.get("status") != "frozen"
        or not snapshot.get("finishedAt")
    ):
        raise ValueError("existing frozen campaign runtime fence drift")
    path = report_path(runtime, root_execution_id)
    if not path.is_file():
        raise ValueError("existing frozen campaign report is missing")
    report = read_json(path)
    assert_valid(
        report,
        "execution",
        "content_campaign_report",
        label=f"distributed campaign report:{root_execution_id}",
    )
    if (
        report.get("rootExecutionId") != root_execution_id
        or report.get("planDigest") != plan.get("planDigest")
    ):
        raise ValueError("existing frozen campaign report identity drift")
    return path


__all__ = ["load_distributed_plan", "reuse_existing_frozen_campaign"]
