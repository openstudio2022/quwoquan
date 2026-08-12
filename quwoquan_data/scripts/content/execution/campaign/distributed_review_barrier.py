"""Identity-bound review barrier for distributed campaign lanes."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

from content.execution.campaign.lane import CAMPAIGN_CARRIERS
from content.execution.campaign.workspace import CampaignRuntimePaths

ClaimReader = Callable[
    [CampaignRuntimePaths, str, str],
    Mapping[str, Any] | None,
]


def wait_for_parallel_review_claims(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    *,
    plan: Mapping[str, Any],
    timeout_seconds: float,
    read_claim: ClaimReader,
) -> None:
    """Start review only after every frozen lane owns its matching claim."""

    distributed = plan["distributedRun"]
    deadline = time.monotonic() + timeout_seconds
    while True:
        missing: list[str] = []
        for carrier in CAMPAIGN_CARRIERS:
            claim = read_claim(runtime, root_execution_id, carrier)
            if claim is None:
                missing.append(carrier)
                continue
            if (
                claim.get("rootExecutionId") != root_execution_id
                or claim.get("planDigest") != plan["planDigest"]
                or claim.get("campaignRunId") != distributed["campaignRunId"]
                or claim.get("campaignGeneration")
                != distributed["campaignGeneration"]
                or claim.get("campaignFencingToken")
                != distributed["campaignFencingToken"]
                or claim.get("carrier") != carrier
                or claim.get("executionId") != plan["executionIds"].get(carrier)
            ):
                raise ValueError(f"{carrier} review barrier claim identity drift")
            if claim.get("status") not in {"active", "starting", "running"}:
                raise RuntimeError(
                    f"{carrier} review barrier claim is not runnable: "
                    f"{claim.get('status')}"
                )
        if not missing:
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(
                "campaign review barrier timed out waiting for lane claims: "
                + ", ".join(sorted(missing))
            )
        time.sleep(min(0.05, remaining))


__all__ = ["wait_for_parallel_review_claims"]
