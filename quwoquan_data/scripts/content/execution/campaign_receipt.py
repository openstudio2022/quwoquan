"""Campaign-owned review and publish receipts for one carrier lane."""
from __future__ import annotations

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


def _review_counts(execution_id: str, carrier: str) -> tuple[int, int, int]:
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
        if not verdict.passed:
            raise ValueError(
                "campaign homepage review quota shortfall: "
                f"qualified={verdict.qualified_count} "
                f"approvedQuota={verdict.approved_quota}"
            )
        return (
            verdict.approved_quota,
            verdict.qualified_count,
            verdict.qualified_count + len(verdict.discarded),
        )

    from content.execution.post_review_closure import (
        indexed_post_targets,
        load_post_review_closure,
    )

    closure = load_post_review_closure(
        execution_id,
        expected_object_targets=indexed_post_targets(execution_id),
    )
    if closure.carrier != carrier:
        raise ValueError("campaign post review closure carrier drift")
    return closure.approved_quota, closure.qualified_count, len(closure.objects)


def write_review_receipt(
    *,
    root_execution_id: str,
    execution_id: str,
) -> Path:
    normalized = validate_execution_id(execution_id)
    carrier = parse_execution_id(normalized).content_type.value
    approved_quota, qualified_count, finalized_count = _review_counts(
        normalized,
        carrier,
    )
    payload = {
        "schema": "quwoquan_data.content_campaign_lane_receipt",
        "rootExecutionId": validate_execution_id(root_execution_id),
        "executionId": normalized,
        "carrier": carrier,
        "phase": "review",
        "status": "qualified",
        "approvedQuota": approved_quota,
        "qualifiedCount": qualified_count,
        "finalizedCount": finalized_count,
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
    if finalized_count != qualified_count or finalized_count < approved_quota:
        raise ValueError(
            "campaign publish closure differs from review barrier: "
            f"finalized={finalized_count} qualified={qualified_count} "
            f"approvedQuota={approved_quota}"
        )
    payload = {
        "schema": "quwoquan_data.content_campaign_lane_receipt",
        "rootExecutionId": validate_execution_id(root_execution_id),
        "executionId": normalized,
        "carrier": carrier,
        "phase": "publish",
        "status": "finalized",
        "approvedQuota": approved_quota,
        "qualifiedCount": qualified_count,
        "finalizedCount": finalized_count,
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
    return payload


def require_campaign_quota_barrier(root_execution_id: str) -> None:
    """Prevent a campaign-bound lane from publishing before all reviews qualify."""
    for carrier in ("homepage", "article", "image", "video"):
        receipt = load_lane_receipt(root_execution_id, carrier, "review")
        approved = int(receipt["approvedQuota"])
        qualified = int(receipt["qualifiedCount"])
        if (
            str(receipt.get("status") or "") != "qualified"
            or qualified < approved
        ):
            raise ValueError(
                f"{carrier} campaign review quota is not qualified: "
                f"qualified={qualified} approvedQuota={approved}"
            )


__all__ = [
    "lane_receipt_path",
    "load_lane_receipt",
    "require_campaign_quota_barrier",
    "write_publish_receipt",
    "write_review_receipt",
]
