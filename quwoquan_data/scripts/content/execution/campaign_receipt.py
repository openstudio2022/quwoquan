"""Campaign-owned review and publish receipts for one carrier lane."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from core.io import read_json, write_json
from core.schema import assert_valid
from content.execution import store
from content.execution.campaign_submission import campaign_root
from content.execution.identity import parse_execution_id, validate_execution_id
from content.execution.workspace import execution_root


def lane_receipt_path(
    root_execution_id: str,
    carrier: str,
    phase: str,
    *,
    root: Path | None = None,
) -> Path:
    if carrier not in {"homepage", "article", "image", "video"}:
        raise ValueError(f"campaign carrier is invalid: {carrier}")
    if phase not in {"review", "publish"}:
        raise ValueError(f"campaign receipt phase is invalid: {phase}")
    return (
        campaign_root(root_execution_id, root=root)
        / "receipts"
        / f"{carrier}-{phase}.json"
    )


def _write_immutable_receipt(path: Path, payload: dict[str, Any]) -> Path:
    assert_valid(
        payload,
        "execution",
        "content_campaign_lane_receipt",
        label=f"campaign lane receipt:{path.name}",
    )
    if path.is_file():
        if read_json(path) != payload:
            raise ValueError(f"campaign lane receipt collision: {path}")
        return path
    write_json(path, payload)
    return path


def _lane_status(*, qualified: int, approved: int) -> str:
    if qualified <= 0:
        return "blocked"
    if qualified < approved:
        return "partial"
    return "qualified"


def _normalize_discards(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        object_ref = str(row.get("objectRef") or "").strip()
        issues = [
            str(issue).strip()
            for issue in (row.get("issues") or [])
            if str(issue).strip()
        ]
        if not object_ref or not issues:
            raise ValueError(
                "campaign discard requires non-empty objectRef and typed issues"
            )
        normalized.append({"objectRef": object_ref, "issues": issues})
    return normalized


@dataclass(frozen=True, slots=True)
class LaneReviewEvidence:
    approved_quota: int
    qualified_count: int
    selected_count: int
    discarded_count: int
    discards: tuple[dict[str, Any], ...]

    @property
    def shortfall_count(self) -> int:
        return max(0, self.approved_quota - self.qualified_count)

    @property
    def status(self) -> str:
        return _lane_status(
            qualified=self.qualified_count,
            approved=self.approved_quota,
        )


def _review_evidence(execution_id: str, carrier: str) -> LaneReviewEvidence:
    if carrier == "homepage":
        from content.execution.controller.homepage_authoring import (
            homepage_quota_verdict,
        )

        verdict = homepage_quota_verdict(
            SimpleNamespace(
                execution_id=execution_id,
                spec=store.load_spec_model(execution_id),
            )
        )
        discards = _normalize_discards(
            [
                {"objectRef": ref, "issues": list(issues)}
                for ref, issues in sorted(verdict.discarded.items())
            ]
        )
        return LaneReviewEvidence(
            approved_quota=verdict.approved_quota,
            qualified_count=verdict.qualified_count,
            selected_count=verdict.qualified_count + len(discards),
            discarded_count=len(discards),
            discards=tuple(discards),
        )

    from content.execution.post_review_closure import (
        indexed_post_targets,
        load_post_review_closure,
    )

    closure = load_post_review_closure(
        execution_id,
        expected_object_targets=indexed_post_targets(execution_id),
        require_quota_milestone=False,
    )
    if closure.carrier != carrier:
        raise ValueError("campaign post review closure carrier drift")
    discards = _normalize_discards(
        [
            {"objectRef": row.object_ref, "issues": list(row.issues)}
            for row in closure.discarded
        ]
    )
    return LaneReviewEvidence(
        approved_quota=closure.approved_quota,
        qualified_count=closure.qualified_count,
        selected_count=len(closure.objects),
        discarded_count=len(discards),
        discards=tuple(discards),
    )


def write_review_receipt(
    *,
    root_execution_id: str,
    execution_id: str,
) -> Path:
    normalized = validate_execution_id(execution_id)
    carrier = parse_execution_id(normalized).content_type.value
    evidence = _review_evidence(normalized, carrier)
    if (
        evidence.selected_count
        != evidence.qualified_count + evidence.discarded_count
        or evidence.discarded_count != len(evidence.discards)
    ):
        raise ValueError("campaign review receipt selected/discard count drift")
    payload = {
        "schema": "quwoquan_data.content_campaign_lane_receipt",
        "rootExecutionId": validate_execution_id(root_execution_id),
        "executionId": normalized,
        "carrier": carrier,
        "phase": "review",
        "status": evidence.status,
        "approvedQuota": evidence.approved_quota,
        "qualifiedCount": evidence.qualified_count,
        "finalizedCount": 0,
        "selectedCount": evidence.selected_count,
        "discardedCount": evidence.discarded_count,
        "shortfallCount": evidence.shortfall_count,
        "discards": list(evidence.discards),
    }
    return _write_immutable_receipt(
        lane_receipt_path(root_execution_id, carrier, "review"),
        payload,
    )


def write_publish_receipt(
    *,
    root_execution_id: str,
    execution_id: str,
) -> Path:
    normalized = validate_execution_id(execution_id)
    carrier = parse_execution_id(normalized).content_type.value
    review = load_lane_receipt(root_execution_id, carrier, "review")
    if str(review.get("status") or "") == "blocked":
        raise ValueError(
            f"campaign publish refused for blocked review lane: {carrier}"
        )
    publish_ref_path = execution_root(normalized) / "publish_ref.json"
    if not publish_ref_path.is_file():
        raise FileNotFoundError(
            f"campaign publish receipt is missing: {publish_ref_path}"
        )
    publish_ref = read_json(publish_ref_path)
    assert_valid(
        publish_ref,
        "execution",
        "publish_ref",
        label=f"publish_ref:{normalized}",
    )
    if str(publish_ref.get("executionId") or "") != normalized:
        raise ValueError("campaign publish_ref executionId drift")
    refs = publish_ref.get("publishedRefs") or {}
    ref_key = "entities" if carrier == "homepage" else "posts"
    finalized_count = len(refs.get(ref_key) or [])
    qualified_count = int(review["qualifiedCount"])
    approved_quota = int(review["approvedQuota"])
    if finalized_count != qualified_count:
        raise ValueError(
            "campaign publish closure differs from review qualified set: "
            f"finalized={finalized_count} qualified={qualified_count}"
        )
    if finalized_count <= 0:
        raise ValueError("campaign publish has no qualified objects to finalize")
    status = (
        "finalized"
        if finalized_count >= approved_quota
        else "partial"
    )
    payload = {
        "schema": "quwoquan_data.content_campaign_lane_receipt",
        "rootExecutionId": validate_execution_id(root_execution_id),
        "executionId": normalized,
        "carrier": carrier,
        "phase": "publish",
        "status": status,
        "approvedQuota": approved_quota,
        "qualifiedCount": qualified_count,
        "finalizedCount": finalized_count,
        "selectedCount": int(review["selectedCount"]),
        "discardedCount": int(review["discardedCount"]),
        "shortfallCount": max(0, approved_quota - finalized_count),
        "discards": list(review["discards"]),
    }
    return _write_immutable_receipt(
        lane_receipt_path(root_execution_id, carrier, "publish"),
        payload,
    )


def load_lane_receipt(
    root_execution_id: str,
    carrier: str,
    phase: str,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    path = lane_receipt_path(root_execution_id, carrier, phase, root=root)
    payload = read_json(path)
    assert_valid(
        payload,
        "execution",
        "content_campaign_lane_receipt",
        label=f"campaign lane receipt:{path.name}",
    )
    if (
        str(payload.get("rootExecutionId") or "")
        != validate_execution_id(root_execution_id)
        or str(payload.get("carrier") or "") != carrier
        or str(payload.get("phase") or "") != phase
    ):
        raise ValueError(f"campaign lane receipt identity drift: {path}")
    discards = payload.get("discards") or []
    if int(payload.get("discardedCount") or 0) != len(discards):
        raise ValueError(f"campaign lane receipt discard count drift: {path}")
    if any(
        not str(row.get("objectRef") or "").strip()
        or not [
            issue for issue in (row.get("issues") or []) if str(issue).strip()
        ]
        for row in discards
    ):
        raise ValueError(
            f"campaign lane receipt discard evidence incomplete: {path}"
        )
    return payload


def require_lane_review_receipt(
    root_execution_id: str,
    *,
    execution_id: str,
) -> dict[str, Any]:
    """Own-lane publish gate: review receipt must exist and be publishable."""
    carrier = parse_execution_id(validate_execution_id(execution_id)).content_type.value
    receipt = load_lane_receipt(root_execution_id, carrier, "review")
    if str(receipt.get("executionId") or "") != validate_execution_id(execution_id):
        raise ValueError(f"{carrier} campaign review receipt executionId drift")
    status = str(receipt.get("status") or "")
    qualified = int(receipt["qualifiedCount"])
    if status == "blocked" or qualified <= 0:
        raise ValueError(
            f"{carrier} campaign review has no publishable qualified objects: "
            f"status={status} qualified={qualified}"
        )
    if status not in {"qualified", "partial"}:
        raise ValueError(
            f"{carrier} campaign review status is not publishable: {status}"
        )
    return receipt


# Backward-compatible alias used by older call sites / docs.
def require_campaign_quota_barrier(root_execution_id: str) -> None:
    """Deprecated cross-lane barrier; kept only to fail closed if still called."""
    raise RuntimeError(
        "cross-lane campaign quota barrier is retired; "
        f"use per-lane review receipts for {root_execution_id}"
    )


__all__ = [
    "LaneReviewEvidence",
    "lane_receipt_path",
    "load_lane_receipt",
    "require_campaign_quota_barrier",
    "require_lane_review_receipt",
    "write_publish_receipt",
    "write_review_receipt",
]
