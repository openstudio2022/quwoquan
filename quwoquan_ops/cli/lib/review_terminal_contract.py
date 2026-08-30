"""Closed terminal-code contract used by Review plan assembly."""
from __future__ import annotations

from typing import Any, Callable

EMITTED_REVIEW_CODES = frozenset(
    {
        "REVIEW.UNKNOWN_WORKFLOW",
        "REVIEW.SEGMENT_NOT_ALLOWED",
        "REVIEW.INVALID_ROUND",
        "REVIEW.PREVIOUS_PLAN_INVALID",
        "REVIEW.PREVIOUS_PLAN_REQUIRED",
        "REVIEW.CONTROL_WORKFLOW_DELIVERABLE_FORBIDDEN",
        "REVIEW.FINGERPRINT_CHANGED",
        "REVIEW.REGISTRY_VERSION_UNSUPPORTED",
        "REVIEW.INVALID_LIMIT",
        "REVIEW.INVALID_EVIDENCE",
        "REVIEW.DUPLICATE_EVIDENCE_COMMAND",
        "REVIEW.PARALLEL_LIMIT_EXCEEDED",
        "REVIEW.REREVIEW_CHAIN_FORBIDDEN",
        "REVIEW.NEW_REVIEW_REQUIRED",
        "REVIEW.INVALID_FINDING_OWNER",
        "REVIEW.INVOCATION_LIMIT_EXCEEDED",
        "REVIEW.UNKNOWN_EVIDENCE",
        "REVIEW.CHECKLIST_MISSING",
        "REVIEW.OWNER_MANIFEST_REQUIRED",
        "REVIEW.OWNER_MANIFEST_SCHEMA_UNSUPPORTED",
        "REVIEW.OWNER_MANIFEST_INVALID",
        "REVIEW.CONTEXT_MANIFEST_BUDGET_EXCEEDED",
        "REVIEW.OWNER_MANIFEST_SCOPE_MISMATCH",
        "REVIEW.OWNER_MANIFEST_TARGET_MISMATCH",
        "REVIEW.OWNER_MANIFEST_STALE",
        "REVIEW.ROLE_MISSING",
        "REVIEW.CONTEXT_BUDGET_EXCEEDED",
        "REVIEW.PATH_OUTSIDE_REPOSITORY",
        "REVIEW.INVALID_INCOMPLETE_ROLE",
        "REVIEW.REQUIRED_REVIEWER_INCOMPLETE",
        "REVIEW.OPTIONAL_REVIEWER_INCOMPLETE",
        "REVIEW.INVALID_EVIDENCE_RESULT",
        "REVIEW.EVIDENCE_FAILED",
        "REVIEW.CANCELLED",
        "REVIEW.TERMINAL_CONTRACT_INVALID",
        "REVIEW.RUNTIME_OUTPUT_CONTRACT_INVALID",
        "REVIEW.OUTPUT_PATH_OUTSIDE_RUNTIME_ROOT",
        "REVIEW.JSON_INVALID",
    }
)


def validate_emitted_terminal_closure(contract_section: Callable[[str], dict[str, Any]]) -> None:
    declared = set(contract_section("terminal_codes"))
    missing = sorted(EMITTED_REVIEW_CODES - declared)
    extra = sorted(declared - EMITTED_REVIEW_CODES)
    if missing or extra:
        raise ValueError(
            f"REVIEW terminal 闭集漂移：missing={missing}, extra={extra}"
        )



__all__ = ["EMITTED_REVIEW_CODES", "validate_emitted_terminal_closure"]
