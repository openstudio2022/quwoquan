"""Failed-only Article retry scope for immutable campaign submissions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from content.execution.request import RuntimeExecutionRequest


def campaign_review_retry_feedback_source(
    *,
    campaigns_dir: Path,
    output_root: Path,
    execution_id: str,
    carrier: str,
    retry_of: str | None,
) -> Any | None:
    """Load the one failed-review scope shared by envelope and submission."""

    if not retry_of or carrier != "article":
        return None
    predecessor_root = output_root / "data/tasks" / retry_of
    if not predecessor_root.is_dir():
        return None
    owners = sorted(campaigns_dir.glob(f"*/submissions/{retry_of}.json"))
    if len(owners) > 1:
        raise ValueError("retry predecessor belongs to multiple campaigns")
    predecessor_campaign_root_id = (
        owners[0].parent.parent.name if owners else retry_of
    )
    from content.execution.planning.retry_review_feedback import (
        load_retry_review_feedback_source,
        retry_review_feedback_evidence_present,
    )

    if not retry_review_feedback_evidence_present(
        predecessor_root,
        root_execution_id=predecessor_campaign_root_id,
    ):
        return None
    feedback = load_retry_review_feedback_source(
        predecessor_root,
        predecessor_execution_id=retry_of,
        root_execution_id=predecessor_campaign_root_id,
    )
    feedback.to_document(execution_id)
    return feedback


def campaign_review_retry_refs(
    *,
    campaigns_dir: Path,
    output_root: Path,
    execution_id: str,
    carrier: str,
    retry_of: str | None,
    request: RuntimeExecutionRequest,
) -> tuple[str, ...]:
    """Derive failed-only article refs from immutable predecessor review evidence."""

    feedback = campaign_review_retry_feedback_source(
        campaigns_dir=campaigns_dir,
        output_root=output_root,
        execution_id=execution_id,
        carrier=carrier,
        retry_of=retry_of,
    )
    if feedback is None:
        return ()
    expected_count = len(feedback.object_refs)
    if (
        request.count != expected_count
        or request.quota != expected_count
        or request.target_names != feedback.target_names
    ):
        raise ValueError(
            "GATE_BLOCK DATA.CAMPAIGN.REVIEW_RETRY_SCOPE_DRIFT: article retry "
            "count/quota/targetNames must equal predecessor failed final-review objects"
        )
    return feedback.object_refs
