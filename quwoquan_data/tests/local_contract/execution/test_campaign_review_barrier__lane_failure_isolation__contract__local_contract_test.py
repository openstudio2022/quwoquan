# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-001
"""review barrier 的 lane 级失败隔离契约。

单 lane 的终态（failed/interrupted/completed 等）表示该 lane 已退出并行
协调并留下 typed 证据；它不得把其余活 lane 的 review 一起炸掉，否则
「任何单点失败只阻断该 lane」的 campaign 语义不成立（历史缺陷：video
供给硬顶导致 QUALIFICATION_EXHAUSTED 后，homepage/article/image 全部
在 barrier 处 RuntimeError）。
"""
from __future__ import annotations

from typing import Any

import pytest
from content.execution.campaign.distributed_review_barrier import (
    wait_for_parallel_review_claims,
)
from content.execution.planning.carrier_demand import CAMPAIGN_CARRIERS

_PLAN = {
    "planDigest": "sha256:" + "a" * 64,
    # 冻结 plan 必带 activeCarriers；barrier 用下标读它是 fail-closed 契约，
    # fixture 省略它就等于测了一份真实流水线不会产生的 plan。
    "activeCarriers": list(CAMPAIGN_CARRIERS),
    "executionIds": {
        carrier: f"20260813--travel-{carrier}-m100--china--scale-004"
        for carrier in CAMPAIGN_CARRIERS
    },
    "distributedRun": {
        "campaignRunId": "run-1",
        "campaignGeneration": 1,
        "campaignFencingToken": "sha256:" + "b" * 64,
    },
}


def _claim(carrier: str, status: str) -> dict[str, Any]:
    return {
        "rootExecutionId": "root-1",
        "planDigest": _PLAN["planDigest"],
        "campaignRunId": "run-1",
        "campaignGeneration": 1,
        "campaignFencingToken": _PLAN["distributedRun"]["campaignFencingToken"],
        "carrier": carrier,
        "executionId": _PLAN["executionIds"][carrier],
        "status": status,
    }


def _barrier(claims: dict[str, dict[str, Any] | None]) -> None:
    wait_for_parallel_review_claims(
        None,  # type: ignore[arg-type]  # reader 不使用 runtime
        "root-1",
        plan=_PLAN,
        timeout_seconds=0.2,
        read_claim=lambda _runtime, _root, carrier: claims.get(carrier),
    )


def test_settled_failed_lane_does_not_block_runnable_lanes() -> None:
    claims = {carrier: _claim(carrier, "active") for carrier in CAMPAIGN_CARRIERS}
    claims["video"] = _claim("video", "failed")

    _barrier(claims)


def test_completed_lane_does_not_block_late_lanes() -> None:
    claims = {carrier: _claim(carrier, "running") for carrier in CAMPAIGN_CARRIERS}
    claims["image"] = _claim("image", "completed")

    _barrier(claims)


def test_unknown_claim_status_still_fails_closed() -> None:
    claims = {carrier: _claim(carrier, "active") for carrier in CAMPAIGN_CARRIERS}
    claims["article"] = _claim("article", "zombie")

    with pytest.raises(RuntimeError, match="article review barrier claim is not runnable"):
        _barrier(claims)


def test_missing_claim_still_times_out() -> None:
    claims: dict[str, dict[str, Any] | None] = {
        carrier: _claim(carrier, "active") for carrier in CAMPAIGN_CARRIERS
    }
    claims["homepage"] = None

    with pytest.raises(TimeoutError, match="homepage"):
        _barrier(claims)


def test_missing_claim_has_no_implicit_batch_deadline() -> None:
    claims = {carrier: _claim(carrier, "active") for carrier in CAMPAIGN_CARRIERS}
    homepage_reads = 0

    def read_claim(_runtime, _root, carrier):
        nonlocal homepage_reads
        if carrier == "homepage":
            homepage_reads += 1
            if homepage_reads == 1:
                return None
        return claims[carrier]

    wait_for_parallel_review_claims(
        None,  # type: ignore[arg-type]  # reader 不使用 runtime
        "root-1",
        plan=_PLAN,
        timeout_seconds=None,
        read_claim=read_claim,
    )

    assert homepage_reads == 2


def test_identity_drift_still_fails_closed() -> None:
    claims = {carrier: _claim(carrier, "active") for carrier in CAMPAIGN_CARRIERS}
    claims["image"]["campaignGeneration"] = 2

    with pytest.raises(ValueError, match="image review barrier claim identity drift"):
        _barrier(claims)
