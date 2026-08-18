"""Dispatch typed failed-campaign evidence contracts without growing the CLI owner."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from content.execution.campaign.failed_execution_reconciliation_claimed import (
    claimed_execution_source_drift_evidence,
)
from content.execution.campaign.failed_execution_reconciliation_controller import (
    controller_interrupted_before_claim_evidence,
    failed_campaign_execution_absence,
)
from content.execution.campaign.failed_execution_reconciliation_mixed import (
    mixed_finalized_partial_terminal_evidence,
)
from content.execution.campaign.failed_execution_reconciliation_post_publish import (
    post_publish_partial_terminal_evidence,
)
from content.execution.campaign.failed_execution_reconciliation_terminal_unpublished import (
    terminal_unpublished_source_drift_evidence,
)

Evidence = tuple[dict[str, Any], dict[str, Any], dict[str, Any]]
Fallback = Callable[[str], tuple[dict[str, Any], dict[str, Any]]]


def failed_campaign_evidence(
    reason: str,
    root_execution_id: str,
    submissions: Mapping[str, Mapping[str, Any]],
    original_source_identity: Mapping[str, Any],
    *,
    output_root: Path,
    fallback: Fallback,
) -> Evidence:
    if reason == "controller_interrupted_before_claim":
        campaign, report = controller_interrupted_before_claim_evidence(
            root_execution_id,
            submissions,
            original_source_identity,
            output_root=output_root,
        )
        execution = failed_campaign_execution_absence(
            submissions,
            output_root=output_root,
        )
        return campaign, execution, report
    if reason == "claimed_execution_source_drift":
        return claimed_execution_source_drift_evidence(
            root_execution_id,
            submissions,
            original_source_identity,
            output_root=output_root,
        )
    if reason == "post_publish_partial_terminal":
        return post_publish_partial_terminal_evidence(
            root_execution_id,
            submissions,
            original_source_identity,
            output_root=output_root,
        )
    if reason == "mixed_finalized_partial_terminal":
        return mixed_finalized_partial_terminal_evidence(
            root_execution_id,
            submissions,
            original_source_identity,
            output_root=output_root,
        )
    if reason in {
        "terminal_unpublished_source_drift",
        "terminal_unpublished_retryable_shortfall",
    }:
        return terminal_unpublished_source_drift_evidence(
            root_execution_id,
            submissions,
            original_source_identity,
            output_root=output_root,
        )
    campaign, report = fallback(root_execution_id)
    execution = failed_campaign_execution_absence(
        submissions,
        output_root=output_root,
    )
    return campaign, execution, report


__all__ = ["failed_campaign_evidence"]
