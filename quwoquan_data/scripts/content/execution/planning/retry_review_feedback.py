"""Typed final-review feedback for a failed-object-only ``retryOf`` execution."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from content.execution.campaign.review_interruption_reconciliation import (
    _content_object_paths,
    review_interruption_receipt_path,
    validate_review_interruption_reconciliation_receipt,
)
from content.execution.campaign.submission_reconciliation_contract import (
    canonical_digest,
    file_digest,
    safe_regular_ref,
)
from content.execution.identity import parse_execution_id
from core.entity_object import parse_entity_ref
from core.io import read_json
from core.schema import assert_valid


@dataclass(frozen=True, slots=True)
class RetryReviewFeedbackSource:
    predecessor_execution_id: str
    object_refs: tuple[str, ...]
    entity_refs: tuple[str, ...]
    target_names: tuple[str, ...]
    items: tuple[dict[str, Any], ...]

    def to_document(self, successor_execution_id: str) -> dict[str, Any]:
        successor = parse_execution_id(successor_execution_id)
        predecessor = parse_execution_id(self.predecessor_execution_id)
        comparable = ("vertical", "content_type", "intent", "scope", "phase")
        if any(
            getattr(successor, field) != getattr(predecessor, field)
            for field in comparable
        ) or successor.sequence <= predecessor.sequence:
            raise ValueError(
                "retry review feedback successor must be a later sequence in the same scope"
            )
        stable: dict[str, Any] = {
            "schema": "quwoquan_data.retry_review_feedback",
            "executionId": successor.execution_id,
            "retryOf": predecessor.execution_id,
            "failedObjectRefs": list(self.object_refs),
            "items": [dict(item) for item in self.items],
        }
        document = {**stable, "feedbackDigest": canonical_digest(stable)}
        assert_valid(document, "execution", "retry_review_feedback")
        return document


def validate_retry_review_feedback(document: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(document)
    assert_valid(payload, "execution", "retry_review_feedback")
    stable = {key: value for key, value in payload.items() if key != "feedbackDigest"}
    if payload.get("feedbackDigest") != canonical_digest(stable):
        raise ValueError("retry review feedback digest drift")
    failed_refs = tuple(str(value) for value in payload.get("failedObjectRefs") or [])
    item_refs = tuple(
        str(item.get("predecessorObjectRef") or "")
        for item in payload.get("items") or []
        if isinstance(item, Mapping)
    )
    if item_refs != failed_refs:
        raise ValueError("retry review feedback item order/scope drift")
    parse_execution_id(str(payload["executionId"]))
    parse_execution_id(str(payload["retryOf"]))
    return payload


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be one object")
    return payload


def _final_review_row(
    *,
    output_root: Path,
    execution_id: str,
    object_ref: str,
    object_dir: Path,
) -> tuple[str, dict[str, Any]] | None:
    review_dir = object_dir / "5.review"
    result_path = review_dir / "reviewer_result.json"
    attestation_path = review_dir / "attestation.json"
    evidence_path = review_dir / "evidence_index.json"
    if not all(path.is_file() for path in (result_path, attestation_path, evidence_path)):
        return None
    result = _read_object(result_path, label="predecessor reviewer result")
    attestation = _read_object(
        attestation_path,
        label="predecessor review attestation",
    )
    evidence = _read_object(evidence_path, label="predecessor review evidence index")
    assert_valid(result, "content", "reviewer_result")
    assert_valid(attestation, "content", "review_attestation")
    assert_valid(evidence, "content", "evidence_index")
    if (
        result.get("executionId") != execution_id
        or result.get("objectRef") != object_ref
        or attestation.get("executionId") != execution_id
        or attestation.get("objectRef") != object_ref
        or evidence.get("executionId") != execution_id
        or evidence.get("objectRef") != object_ref
    ):
        raise ValueError(f"predecessor final review identity drift: {object_ref}")
    result_sha = file_digest(result_path)
    if not any(
        isinstance(row, Mapping)
        and row.get("kind") == "independent_reviewer_result"
        and row.get("ref") == "5.review/reviewer_result.json"
        and row.get("sha256") == result_sha
        for row in evidence.get("evidence") or []
    ):
        return None
    reviewer = attestation.get("independentReviewer")
    repair = attestation.get("repair")
    if not isinstance(reviewer, Mapping) or not isinstance(repair, Mapping):
        raise ValueError(f"predecessor independent reviewer binding missing: {object_ref}")
    for field in ("provider", "model", "modelFamily", "runId", "resultHash"):
        if reviewer.get(field) != result.get(field):
            raise ValueError(
                f"predecessor independent reviewer {field} drift: {object_ref}"
            )
    verdict = str(result.get("verdict") or "")
    issues = [str(value) for value in result.get("issues") or []]
    decision = str(attestation.get("decision") or "")
    if verdict == "passed":
        if (
            issues
            or decision != "approved"
            or reviewer.get("status") != "passed"
            or repair.get("status") != "not_required"
        ):
            raise ValueError(f"predecessor passed review closure drift: {object_ref}")
        return "passed", {}
    if (
        verdict != "failed"
        or not issues
        or decision not in {"revision_needed", "rejected"}
        or reviewer.get("status") != "failed"
        or repair.get("status") != "pending"
    ):
        raise ValueError(f"predecessor failed review closure drift: {object_ref}")
    return (
        "failed",
        {
            "decision": decision,
            "issues": issues,
            "findings": [str(value) for value in result.get("findings") or []],
            "evidenceKind": "final_reviewer_result",
            "evidenceRef": safe_regular_ref(
                result_path,
                output_root=output_root,
                label="predecessor final reviewer result",
            ),
            "evidenceSha256": result_sha,
            "responseDigest": str(result["resultHash"]),
            "reviewer": {
                "provider": str(result["provider"]),
                "model": str(result["model"]),
                "modelFamily": str(result["modelFamily"]),
                "runId": str(result["runId"]),
            },
        },
    )


def load_retry_review_feedback_source(
    predecessor_root: Path,
    *,
    predecessor_execution_id: str,
    required_object_refs: Sequence[str] | None = None,
    root_execution_id: str | None = None,
) -> RetryReviewFeedbackSource:
    """Resolve every predecessor object, then expose failed objects only.

    Coverage is complete only when each planned object has either a bound final
    independent review or a validated interruption reconciliation receipt.
    A deterministic reviewer projection and a bare pending file are not final
    review evidence.
    """

    predecessor = parse_execution_id(predecessor_execution_id)
    root = predecessor_root.expanduser().resolve()
    if root.name != predecessor.execution_id or not root.is_dir():
        raise ValueError("retry predecessor execution root is unavailable")
    output_root = root.parents[2].resolve()
    plan_path = root / "_shared/content_plan_packet.json"
    plan = _read_object(plan_path, label="predecessor content plan packet")
    if plan.get("executionId") != predecessor.execution_id:
        raise ValueError("predecessor content plan executionId drift")
    raw_items = plan.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("predecessor content plan items are invalid")
    plan_items: list[tuple[str, str, str]] = []
    for raw in raw_items:
        if not isinstance(raw, Mapping):
            raise ValueError("predecessor content plan item is invalid")
        object_ref = str(raw.get("ref") or "").strip()
        entity_refs = raw.get("entityRefs")
        if not object_ref or not isinstance(entity_refs, list) or len(entity_refs) != 1:
            raise ValueError(
                f"predecessor review item requires one entityRef: {object_ref}"
            )
        entity_ref = str(entity_refs[0])
        parsed = parse_entity_ref(entity_ref)
        if parsed is None:
            raise ValueError(f"predecessor review entityRef is invalid: {object_ref}")
        plan_items.append((object_ref, entity_ref, parsed[2]))
    if len({row[0] for row in plan_items}) != len(plan_items):
        raise ValueError("predecessor content plan repeats object refs")

    _index_path, object_paths = _content_object_paths(
        root,
        execution_id=predecessor.execution_id,
    )
    if set(object_paths) != {row[0] for row in plan_items}:
        raise ValueError("predecessor content plan/object index coverage drift")
    campaign_root_id = root_execution_id or predecessor.execution_id
    failed: list[tuple[str, str, str, dict[str, Any]]] = []
    for object_ref, entity_ref, target_name in plan_items:
        final = _final_review_row(
            output_root=output_root,
            execution_id=predecessor.execution_id,
            object_ref=object_ref,
            object_dir=object_paths[object_ref],
        )
        receipt_path = review_interruption_receipt_path(
            campaign_root_id,
            object_ref,
            output_root=output_root,
        )
        receipt = (
            validate_review_interruption_reconciliation_receipt(
                receipt_path,
                output_root=output_root,
            )
            if receipt_path.is_file()
            else None
        )
        if final is not None and receipt is not None:
            raise ValueError(
                f"predecessor review has final/reconciliation collision: {object_ref}"
            )
        if receipt is not None:
            if (
                receipt.get("executionId") != predecessor.execution_id
                or receipt.get("objectRef") != object_ref
            ):
                raise ValueError(
                    f"predecessor review reconciliation identity drift: {object_ref}"
                )
            feedback = {
                "decision": str(receipt["decision"]),
                "issues": [str(value) for value in receipt["issues"]],
                "findings": [str(value) for value in receipt["findings"]],
                "evidenceKind": "interrupted_review_reconciliation",
                "evidenceRef": safe_regular_ref(
                    receipt_path,
                    output_root=output_root,
                    label="review interruption reconciliation receipt",
                ),
                "evidenceSha256": file_digest(receipt_path),
                "responseDigest": str(
                    receipt["executionEvidence"]["pendingResponse"]["responseDigest"]
                ),
                "reviewer": {
                    "provider": str(receipt["semanticEvidence"]["provider"]),
                    "model": str(receipt["semanticEvidence"]["model"]),
                    "modelFamily": str(receipt["semanticEvidence"]["modelFamily"]),
                    "runId": str(receipt["semanticEvidence"]["runId"]),
                },
            }
            failed.append((object_ref, entity_ref, target_name, feedback))
            continue
        if final is None:
            raise ValueError(
                f"predecessor final review coverage is incomplete: {object_ref}"
            )
        status, feedback = final
        if status == "failed":
            failed.append((object_ref, entity_ref, target_name, feedback))

    derived_refs = tuple(row[0] for row in failed)
    if not derived_refs:
        raise ValueError("predecessor has no failed final-review objects")
    if required_object_refs is not None:
        required_refs = tuple(str(value).strip() for value in required_object_refs)
        if (
            not required_refs
            or any(not value for value in required_refs)
            or len(set(required_refs)) != len(required_refs)
            or required_refs != derived_refs
        ):
            raise ValueError(
                "retry review refs must exactly match predecessor failed final-review objects"
            )
    items = tuple(
        {
            "predecessorObjectRef": object_ref,
            "entityRef": entity_ref,
            "targetName": target_name,
            **feedback,
        }
        for object_ref, entity_ref, target_name, feedback in failed
    )
    return RetryReviewFeedbackSource(
        predecessor_execution_id=predecessor.execution_id,
        object_refs=derived_refs,
        entity_refs=tuple(row[1] for row in failed),
        target_names=tuple(row[2] for row in failed),
        items=items,
    )


def retry_review_feedback_evidence_present(
    predecessor_root: Path,
    *,
    root_execution_id: str | None = None,
) -> bool:
    """Return whether a retry must be governed by final-review feedback.

    This is only a routing signal.  Once any independent final-review or
    interruption-reconciliation evidence exists, the strict loader above must
    validate complete predecessor object coverage and fails closed on drift.
    """

    root = predecessor_root.expanduser().resolve()
    execution_id = root.name
    if (root / "_shared/post_review_closure.json").is_file():
        return True
    for evidence_path in root.glob("posts/**/5.review/evidence_index.json"):
        try:
            evidence = read_json(evidence_path)
        except (OSError, TypeError, ValueError):
            return True
        if not isinstance(evidence, Mapping):
            return True
        if any(
            isinstance(row, Mapping)
            and row.get("kind") == "independent_reviewer_result"
            for row in evidence.get("evidence") or []
        ):
            return True
    output_root = root.parents[2]
    campaign_root_id = str(root_execution_id or execution_id).strip()
    receipt_dir = (
        output_root
        / "data/local/workspace/content-campaign-submissions"
        / campaign_root_id
        / "reconciliation/review-interruption"
    )
    return receipt_dir.is_dir() and any(receipt_dir.glob("*.json"))


__all__ = [
    "RetryReviewFeedbackSource",
    "load_retry_review_feedback_source",
    "retry_review_feedback_evidence_present",
    "validate_retry_review_feedback",
]
