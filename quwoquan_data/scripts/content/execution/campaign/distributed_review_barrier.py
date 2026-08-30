"""Identity-bound review barrier for distributed campaign lanes."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

from content.execution.campaign.lane import normalize_active_carriers
from content.execution.campaign.workspace import CampaignRuntimePaths

ClaimReader = Callable[
    [CampaignRuntimePaths, str, str],
    Mapping[str, Any] | None,
]

_RUNNABLE_CLAIM_STATUSES = frozenset({"active", "starting", "running"})
# lane 级失败隔离：单 lane 的终态（失败或已完成）不得阻断其余 lane 的
# review。终态 lane 已退出并行协调，其 typed 失败证据保留在 claim 里；
# 只有身份漂移或未知状态才是需要 fail-closed 的异常。
_SETTLED_CLAIM_STATUSES = frozenset(
    {"failed", "interrupted", "completed", "delivery_pending", "superseded"}
)


def wait_for_parallel_review_claims(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    *,
    plan: Mapping[str, Any],
    timeout_seconds: float | None,
    read_claim: ClaimReader,
) -> None:
    """Start review only after every frozen lane owns its claim or has settled."""

    distributed = plan["distributedRun"]
    deadline = (
        None if timeout_seconds is None else time.monotonic() + timeout_seconds
    )
    while True:
        missing: list[str] = []
        for carrier in normalize_active_carriers(plan["activeCarriers"]):
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
            status = str(claim.get("status") or "")
            if status in _SETTLED_CLAIM_STATUSES:
                continue
            if status not in _RUNNABLE_CLAIM_STATUSES:
                raise RuntimeError(
                    f"{carrier} review barrier claim is not runnable: {status}"
                )
        if not missing:
            return
        remaining = None if deadline is None else deadline - time.monotonic()
        if remaining is not None and remaining <= 0:
            raise TimeoutError(
                "campaign review barrier timed out waiting for lane claims: "
                + ", ".join(sorted(missing))
            )
        time.sleep(0.05 if remaining is None else min(0.05, remaining))


__all__ = ["wait_for_parallel_review_claims"]
