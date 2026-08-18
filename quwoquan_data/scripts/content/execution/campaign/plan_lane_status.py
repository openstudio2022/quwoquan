"""Campaign lane receipt loading and aggregate status projection."""

from __future__ import annotations

from typing import Any

from content.execution.campaign.receipt import load_lane_receipt
from content.execution.campaign.workspace import CampaignRuntimePaths


def apply_receipt_fields(
    lanes: dict[str, dict[str, Any]],
    carrier: str,
    receipt: dict[str, Any],
    *,
    phase: str,
) -> None:
    status = str(receipt.get("status") or "")
    if phase == "review":
        lane_status = (
            "review_qualified"
            if status == "qualified"
            else status
            if status in {"partial", "blocked"}
            else "reviewed"
        )
    elif status == "finalized":
        lane_status = "finalized"
    elif status == "partial":
        lane_status = "partial"
    else:
        lane_status = "blocked"
    lanes[carrier].update(
        {
            "approvedQuota": int(receipt["approvedQuota"]),
            "qualifiedCount": int(receipt["qualifiedCount"]),
            "finalizedCount": int(receipt["finalizedCount"]),
            "selectedCount": int(receipt["selectedCount"]),
            "discardedCount": int(receipt["discardedCount"]),
            "shortfallCount": int(receipt["shortfallCount"]),
            "deliveryPendingCount": 0,
            "deliveryIntentRefs": [],
            "status": lane_status,
            "phase": phase,
        }
    )


def load_review_for_lane(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    carrier: str,
    *,
    expected_execution_id: str,
    expected_quota: int,
) -> dict[str, Any] | None:
    try:
        receipt = load_lane_receipt(
            root_execution_id,
            carrier,
            "review",
            root=runtime.campaigns_root,
        )
    except (OSError, ValueError):
        return None
    if str(receipt.get("executionId") or "") != expected_execution_id:
        raise ValueError(f"{carrier} campaign receipt executionId drift")
    if int(receipt["approvedQuota"]) != expected_quota:
        raise ValueError(f"{carrier} campaign receipt approvedQuota drift")
    return receipt


def load_publish_for_lane(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    carrier: str,
    *,
    expected_execution_id: str,
    expected_quota: int,
) -> dict[str, Any] | None:
    try:
        receipt = load_lane_receipt(
            root_execution_id,
            carrier,
            "publish",
            root=runtime.campaigns_root,
        )
    except (OSError, ValueError):
        return None
    if str(receipt.get("executionId") or "") != expected_execution_id:
        raise ValueError(f"{carrier} campaign publish receipt executionId drift")
    if int(receipt["approvedQuota"]) != expected_quota:
        raise ValueError(f"{carrier} campaign publish receipt approvedQuota drift")
    return receipt


def aggregate_status(lanes: dict[str, dict[str, Any]]) -> str:
    finalized_or_partial = 0
    delivery_pending = 0
    milestone_met = 0
    for lane in lanes.values():
        qualified = int(lane.get("qualifiedCount") or 0)
        finalized = int(lane.get("finalizedCount") or 0)
        approved = int(lane.get("approvedQuota") or 0)
        status = str(lane.get("status") or "")
        pending = int(lane.get("deliveryPendingCount") or 0)
        if (
            status == "delivery_pending"
            and qualified > 0
            and pending == qualified
            and finalized == 0
        ):
            delivery_pending += 1
        if finalized > 0 and status in {"finalized", "partial", "published"}:
            finalized_or_partial += 1
            if approved > 0 and finalized >= approved and qualified >= approved:
                milestone_met += 1
    if finalized_or_partial == 0 and delivery_pending == 0:
        return "blocked"
    if milestone_met == len(lanes):
        return "succeeded"
    return "succeeded_partial"


__all__ = [
    "aggregate_status",
    "apply_receipt_fields",
    "load_publish_for_lane",
    "load_review_for_lane",
]
