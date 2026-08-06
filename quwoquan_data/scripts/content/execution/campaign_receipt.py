"""Campaign-owned review and publish receipts for one carrier lane."""

from __future__ import annotations

import fcntl
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from core.io import read_json, write_json
from core.schema import assert_valid

from content.execution import store
from content.execution.campaign_publish_binding import (
    PUBLISH_BINDING_FIELDS,
    CampaignPublishProjection,
    CampaignReceiptError,
    project_publish_receipt_binding,
)
from content.execution.campaign_publish_binding import (
    project_publish_receipt as _project_publish_receipt_binding,
)
from content.execution.campaign_publish_binding import (
    receipt_error as _receipt_error,
)
from content.execution.campaign_submission import campaign_root
from content.execution.campaign_workspace import CampaignRuntimePaths
from content.execution.identity import parse_execution_id, validate_execution_id
from content.execution.reviewed_closure_adoption_campaign_contract import (
    CAMPAIGN_ADOPTION_FIELD,
    validate_campaign_adoption_binding,
)

_ADOPTION_PUBLISH_FIELDS = (CAMPAIGN_ADOPTION_FIELD, "adoptedObjectRefs")


@contextmanager
def _receipt_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.parent / f".{path.name}.lock"
    with lock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _assert_phase_binding(payload: Mapping[str, Any], *, path: Path) -> None:
    phase = str(payload.get("phase") or "")
    standard_present = [field for field in PUBLISH_BINDING_FIELDS if field in payload]
    adoption_present = [field for field in _ADOPTION_PUBLISH_FIELDS if field in payload]
    if phase == "publish":
        standard_complete = all(field in payload for field in PUBLISH_BINDING_FIELDS)
        adoption_complete = all(
            field in payload for field in _ADOPTION_PUBLISH_FIELDS
        ) and all(
            field in payload
            for field in (
                "campaignRunId",
                "campaignGeneration",
                "campaignFencingToken",
            )
        )
        if standard_complete == adoption_complete:
            if standard_present and not adoption_present:
                detail = "publish receipt lacks " + ", ".join(
                    field
                    for field in PUBLISH_BINDING_FIELDS
                    if field not in payload
                )
            elif adoption_present and not standard_present:
                detail = "adoption publish receipt lacks " + ", ".join(
                    field
                    for field in (
                        *_ADOPTION_PUBLISH_FIELDS,
                        "campaignRunId",
                        "campaignGeneration",
                        "campaignFencingToken",
                    )
                    if field not in payload
                )
            else:
                detail = (
                    "publish receipt must carry exactly one canonical publish or "
                    "reviewed-closure adoption binding"
                )
            raise _receipt_error(
                "PUBLISH_BINDING_MISSING",
                detail,
                evidence=path,
            )
        if standard_complete and adoption_present:
            raise _receipt_error(
                "PUBLISH_BINDING_CONFLICT",
                "publish receipt cannot mix canonical and adoption bindings",
                evidence=path,
            )
        if adoption_complete and any(
            field in payload
            for field in ("executionPublishRef", "executionPublishSha256")
        ):
            raise _receipt_error(
                "PUBLISH_BINDING_CONFLICT",
                "adoption receipt cannot carry canonical publish_ref fields",
                evidence=path,
            )
    elif phase == "review" and (standard_present or adoption_present):
        raise _receipt_error(
            "REVIEW_BINDING_FORBIDDEN",
            "review receipt cannot freeze publish fields: "
            + ", ".join([*standard_present, *adoption_present]),
            evidence=path,
        )


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
    _assert_phase_binding(payload, path=path)
    assert_valid(
        payload,
        "execution",
        "content_campaign_lane_receipt",
        label=f"campaign lane receipt:{path.name}",
    )
    with _receipt_lock(path):
        if path.is_symlink():
            raise _receipt_error(
                "PATH_INVALID",
                "campaign lane receipt cannot be a symlink",
                evidence=path,
            )
        if path.is_file():
            if read_json(path) != payload:
                raise _receipt_error(
                    "IMMUTABLE_COLLISION",
                    "campaign lane receipt already differs",
                    evidence=path,
                )
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
        evidence.selected_count != evidence.qualified_count + evidence.discarded_count
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
    runtime_paths: CampaignRuntimePaths | None = None,
) -> Path:
    runtime = runtime_paths or CampaignRuntimePaths.defaults()
    normalized = validate_execution_id(execution_id)
    carrier = parse_execution_id(normalized).content_type.value
    review = load_lane_receipt(
        root_execution_id,
        carrier,
        "review",
        root=runtime.campaigns_root,
    )
    if str(review.get("status") or "") == "blocked":
        raise ValueError(f"campaign publish refused for blocked review lane: {carrier}")
    projection = _project_publish_receipt_binding(
        root_execution_id=root_execution_id,
        execution_id=normalized,
        runtime_paths=runtime,
    )
    refs = projection.publish_ref.get("publishedRefs") or {}
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
    status = "finalized" if finalized_count >= approved_quota else "partial"
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
        **projection.binding,
    }
    return _write_immutable_receipt(
        lane_receipt_path(
            root_execution_id,
            carrier,
            "publish",
            root=runtime.campaigns_root,
        ),
        payload,
    )


def write_adoption_publish_receipt(
    *,
    root_execution_id: str,
    execution_id: str,
    reviewed_closure_adoption: Mapping[str, Any],
    adopted_object_refs: list[str],
    run_session: Any,
) -> Path:
    """Derive one finalized lane receipt from the current fenced adoption run."""

    runtime = run_session.runtime
    normalized = validate_execution_id(execution_id)
    carrier = parse_execution_id(normalized).content_type.value
    snapshot = run_session.assert_fence()
    plan_path = (
        campaign_root(root_execution_id, root=runtime.campaigns_root)
        / "campaign_plan.json"
    )
    plan = read_json(plan_path)
    if (
        plan.get("planDigest") != snapshot.get("planDigest")
        or plan.get(CAMPAIGN_ADOPTION_FIELD) != dict(reviewed_closure_adoption)
        or (plan.get("executionIds") or {}).get(carrier) != normalized
    ):
        raise ValueError("reviewed closure publish plan/fence binding drift")
    validate_campaign_adoption_binding(
        reviewed_closure_adoption,
        output_root=runtime.output_root,
    )
    if not adopted_object_refs or adopted_object_refs != sorted(
        set(adopted_object_refs)
    ):
        raise ValueError("reviewed closure adoptedObjectRefs must be sorted and unique")
    count = len(adopted_object_refs)
    payload = {
        "schema": "quwoquan_data.content_campaign_lane_receipt",
        "rootExecutionId": validate_execution_id(root_execution_id),
        "executionId": normalized,
        "carrier": carrier,
        "phase": "publish",
        "status": "finalized",
        "approvedQuota": count,
        "qualifiedCount": count,
        "finalizedCount": count,
        "selectedCount": count,
        "discardedCount": 0,
        "shortfallCount": 0,
        "discards": [],
        "campaignRunId": run_session.run_id,
        "campaignGeneration": run_session.generation,
        "campaignFencingToken": run_session.fencing_token,
        CAMPAIGN_ADOPTION_FIELD: dict(reviewed_closure_adoption),
        "adoptedObjectRefs": list(adopted_object_refs),
    }
    return _write_immutable_receipt(
        lane_receipt_path(
            root_execution_id,
            carrier,
            "publish",
            root=runtime.campaigns_root,
        ),
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
    if isinstance(payload, Mapping):
        # Give the campaign boundary's stable typed error priority over the
        # lower-level oneOf diagnostic.  The strict schema remains the next
        # gate and still rejects every other malformed shape.
        _assert_phase_binding(payload, path=path)
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
        or not [issue for issue in (row.get("issues") or []) if str(issue).strip()]
        for row in discards
    ):
        raise ValueError(f"campaign lane receipt discard evidence incomplete: {path}")
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


__all__ = [
    "CampaignPublishProjection",
    "CampaignReceiptError",
    "LaneReviewEvidence",
    "lane_receipt_path",
    "load_lane_receipt",
    "project_publish_receipt_binding",
    "require_lane_review_receipt",
    "write_adoption_publish_receipt",
    "write_publish_receipt",
    "write_review_receipt",
]
