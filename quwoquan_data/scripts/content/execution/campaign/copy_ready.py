"""COPY_READY receipt: scale-proof for session copy, never a publish veto."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from content.execution.campaign.lane import CAMPAIGN_CARRIERS
from content.execution.campaign.receipt import lane_receipt_path, load_lane_receipt
from content.execution.campaign.submission import campaign_root
from core.io import read_json, write_json
from core.schema import assert_valid

COPY_READY_MIN_QUALIFIED = 1


def copy_ready_receipt_path(root_execution_id: str, *, root: Path) -> Path:
    return campaign_root(root_execution_id, root=root) / "copy_ready_receipt.json"


def _output_ref(path: Path, *, output_root: Path) -> str:
    return path.relative_to(output_root).as_posix()


def maybe_write_copy_ready_receipt(
    *,
    root_execution_id: str,
    plan: Mapping[str, Any],
    submissions: Mapping[str, Mapping[str, Any]],
    lanes: Mapping[str, Mapping[str, Any]],
    campaigns_root: Path,
    output_root: Path,
    assessed_at: str,
    assessment_ref: str | None = None,
) -> Path | None:
    """Write COPY_READY when every lane published at least one qualified object.

    Requested quota/count and their attainment remain receipt statistics. Zero
    typed discards is allowed. If discards exist, each must already have passed
    lane-receipt evidence completeness checks.
    """
    lane_rows: dict[str, dict[str, Any]] = {}
    total_discards = 0
    for carrier in CAMPAIGN_CARRIERS:
        submission = submissions[carrier]
        lane = lanes[carrier]
        review = load_lane_receipt(
            root_execution_id, carrier, "review", root=campaigns_root
        )
        publish = load_lane_receipt(
            root_execution_id, carrier, "publish", root=campaigns_root
        )
        requested_quota = int(submission["quota"])
        requested_count = int(submission["count"])
        selected = int(publish["selectedCount"])
        qualified = int(publish["qualifiedCount"])
        discarded = int(publish["discardedCount"])
        finalized = int(publish["finalizedCount"])
        shortfall = int(publish["shortfallCount"])
        discards = list(publish["discards"])
        if (
            qualified < COPY_READY_MIN_QUALIFIED
            or finalized != qualified
            or discarded != len(discards)
            or selected != qualified + discarded
            or review["selectedCount"] != publish["selectedCount"]
            or review["qualifiedCount"] != publish["qualifiedCount"]
            or review["discardedCount"] != publish["discardedCount"]
            or review["discards"] != publish["discards"]
            or lane.get("status") not in {"finalized", "partial"}
            or lane.get("cleanupStatus") != "cleaned"
            or str(publish.get("status") or "") not in {"finalized", "partial"}
        ):
            return None
        if any(
            not str(row.get("objectRef") or "").strip()
            or not [
                issue for issue in row.get("issues") or [] if str(issue).strip()
            ]
            for row in discards
        ):
            return None
        total_discards += discarded
        review_path = lane_receipt_path(
            root_execution_id, carrier, "review", root=campaigns_root
        )
        publish_path = lane_receipt_path(
            root_execution_id, carrier, "publish", root=campaigns_root
        )
        lane_rows[carrier] = {
            "executionId": str(submission["executionId"]),
            "requestedQuota": requested_quota,
            "requestedCount": requested_count,
            "selectedCount": selected,
            "qualifiedCount": qualified,
            "discardedCount": discarded,
            "finalizedCount": finalized,
            "shortfallCount": shortfall,
            "quotaAttainmentRate": qualified / requested_quota,
            "reviewReceiptRef": _output_ref(review_path, output_root=output_root),
            "publishReceiptRef": _output_ref(publish_path, output_root=output_root),
        }
    path = copy_ready_receipt_path(root_execution_id, root=campaigns_root)
    existing = read_json(path) if path.is_file() else None
    payload = {
        "schema": "quwoquan_data.content_copy_ready_receipt",
        "status": "copy_ready",
        "rootExecutionId": root_execution_id,
        "campaignPlanDigest": str(plan["planDigest"]),
        "gitBranch": str(plan["gitBranch"]),
        "gitCommitSha": str(plan["gitCommitSha"]),
        "sourceDigest": str(plan["sourceDigest"]),
        "entityCatalogDigest": str(plan["entityCatalogDigest"]),
        **({"assessmentRef": assessment_ref} if assessment_ref else {}),
        "minimums": {
            "qualifiedPerLane": COPY_READY_MIN_QUALIFIED,
        },
        "totalDiscardedCount": total_discards,
        "lanes": lane_rows,
        "assessedAt": str(existing["assessedAt"]) if existing else assessed_at,
    }
    assert_valid(
        payload,
        "execution",
        "content_copy_ready_receipt",
        label=f"content copy ready receipt:{root_execution_id}",
    )
    if existing is not None:
        if existing != payload:
            raise ValueError(f"content copy ready receipt collision: {path}")
        return path
    write_json(path, payload)
    return path


__all__ = [
    "COPY_READY_MIN_QUALIFIED",
    "copy_ready_receipt_path",
    "maybe_write_copy_ready_receipt",
]
