"""Consume one preserved mixed-finalized predecessor boundary."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from content.execution.campaign.lane import CAMPAIGN_CARRIERS
from content.execution.campaign.submission_reconciliation import (
    load_reconciliation_reference,
    predecessor_campaign_root_execution_id,
)
from content.release.canonical.campaign_release_contract import (
    CampaignReleaseRoots,
    typed_error,
)

_SCOPE_FIELDS = (
    "familyRef",
    "regionRef",
    "selector",
    "quota",
    "count",
    "topic",
    "targetNames",
    "sourceProviders",
)


def validate_reconciliation_retry_set(
    submissions: Mapping[str, Mapping[str, Any]],
    plan: Mapping[str, Any],
    *,
    roots: CampaignReleaseRoots,
) -> None:
    """Require one exact four-lane retry set for terminal-unpublished lineage."""

    references = [row.get("predecessorReconciliation") for row in submissions.values()]
    present = [row for row in references if row is not None]
    if not present:
        return
    unique = {
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for row in present
    }
    if len(present) != len(CAMPAIGN_CARRIERS) or len(unique) != 1:
        for reference in present:
            if not isinstance(reference, Mapping):
                continue
            try:
                receipt, receipt_path = load_reconciliation_reference(
                    reference,
                    output_root=roots.output_root,
                )
            except (OSError, TypeError, ValueError):
                continue
            if receipt.get("reason") == "terminal_unpublished_source_drift":
                raise typed_error(
                    "RETRY_IDENTITY_DRIFT",
                    "terminal unpublished reconciliation must bind all four lanes",
                    evidence=receipt_path,
                )
        return
    reference = present[0]
    if not isinstance(reference, Mapping):
        return
    try:
        receipt, receipt_path = load_reconciliation_reference(
            reference,
            output_root=roots.output_root,
        )
    except (OSError, TypeError, ValueError) as exc:
        raise typed_error("RETRY_EVIDENCE_INVALID", str(exc)) from exc
    if receipt.get("reason") != "terminal_unpublished_source_drift":
        return
    predecessor_rows = receipt.get("submissions")
    if (
        not isinstance(predecessor_rows, Mapping)
        or set(predecessor_rows) != set(CAMPAIGN_CARRIERS)
        or any(
            submissions[carrier].get("retryOf")
            != (predecessor_rows.get(carrier) or {}).get("executionId")
            for carrier in CAMPAIGN_CARRIERS
        )
        or reference.get("predecessorRootExecutionId")
        != receipt.get("rootExecutionId")
        or plan.get("reviewedClosureAdoption") is not None
    ):
        raise typed_error(
            "RETRY_IDENTITY_DRIFT",
            "terminal unpublished reconciliation requires exact four-lane retryOf",
            evidence=receipt_path,
        )


def _consume_terminal_unpublished_boundary(
    carrier: str,
    execution_id: str,
    submission: Mapping[str, Any],
    plan: Mapping[str, Any],
    receipt: Mapping[str, Any],
    receipt_path: Any,
) -> bool:
    if receipt.get("reason") != "terminal_unpublished_source_drift":
        return False
    row = (receipt.get("submissions") or {}).get(carrier)
    evidence = receipt.get("executionEvidence")
    lanes = evidence.get("lanes") if isinstance(evidence, Mapping) else None
    lane = next(
        (
            item
            for item in lanes or []
            if isinstance(item, Mapping) and item.get("carrier") == carrier
        ),
        None,
    )
    expected_identity = {
        "sourceRevision": plan["sourceRevision"],
        "sourceDigest": submission["sourceDigest"],
        "entityCatalogDigest": plan["entityCatalogDigest"],
    }
    qualified_lanes = sum(
        isinstance(item, Mapping) and int(item.get("reviewQualifiedCount") or 0) > 0
        for item in lanes or []
    )
    invalid = (
        not isinstance(row, Mapping)
        or not isinstance(evidence, Mapping)
        or not isinstance(lanes, list)
        or len(lanes) != len(CAMPAIGN_CARRIERS)
        or {
            item.get("carrier")
            for item in lanes
            if isinstance(item, Mapping)
        }
        != set(CAMPAIGN_CARRIERS)
        or not isinstance(lane, Mapping)
        or row.get("executionId") != execution_id
        or lane.get("executionId") != execution_id
        or receipt.get("rootExecutionId")
        != predecessor_campaign_root_execution_id(execution_id)
        or receipt.get("originalSourceIdentity") == expected_identity
        or receipt.get("observedSourceIdentity") != expected_identity
        or any(row.get(key) != submission.get(key) for key in _SCOPE_FIELDS)
        or evidence.get("observedFinalizedCount") != 0
        or evidence.get("reviewQualifiedLaneCount") != qualified_lanes
        or not 1 <= qualified_lanes < len(CAMPAIGN_CARRIERS)
        or evidence.get("campaignPublishReceiptsPresent") is not False
        or evidence.get("campaignPublishRefsPresent") is not False
        or evidence.get("objectTransactionEvidencePresent") is not False
        or evidence.get("immutableReleaseEvidencePresent") is not False
        or evidence.get("reviewedClosureAdoptionPresent") is not False
        or evidence.get("evidenceDisposition") != "failed_unpublished"
        or evidence.get("excludedFromRetryRelease") is not True
        or evidence.get("eligibleForRelease") is not False
        or lane.get("terminalStatus") != "failed"
        or lane.get("reportStatus") != "blocked"
        or lane.get("observedFinalizedCount") != 0
        or lane.get("publishReceiptPresent") is not False
        or lane.get("publishRefPresent") is not False
        or lane.get("objectTransactionEvidencePresent") is not False
        or lane.get("evidenceDisposition") != "failed_unpublished"
        or lane.get("excludedFromRetryRelease") is not True
        or lane.get("eligibleForRelease") is not False
        or not isinstance(lane.get("claim"), Mapping)
        or (
            lane.get("reviewReceiptPresent") is True
            and not isinstance(lane.get("reviewReceipt"), Mapping)
        )
        or (
            lane.get("reviewReceiptPresent") is False
            and lane.get("reviewReceipt") is not None
        )
    )
    if invalid:
        raise typed_error(
            "RETRY_IDENTITY_DRIFT",
            f"{carrier} terminal unpublished predecessor binding drift",
            evidence=receipt_path,
        )
    return True


def consume_mixed_finalized_boundary(
    carrier: str,
    execution_id: str,
    submission: Mapping[str, Any],
    plan: Mapping[str, Any],
    reference: Mapping[str, Any],
    *,
    roots: CampaignReleaseRoots,
) -> bool:
    """Validate and terminate lineage at an excluded mixed-finalized boundary."""

    try:
        receipt, receipt_path = load_reconciliation_reference(
            reference,
            output_root=roots.output_root,
        )
    except (OSError, TypeError, ValueError) as exc:
        raise typed_error(
            "RETRY_EVIDENCE_INVALID",
            str(exc),
            evidence=roots.tasks_root / execution_id,
        ) from exc
    if _consume_terminal_unpublished_boundary(
        carrier,
        execution_id,
        submission,
        plan,
        receipt,
        receipt_path,
    ):
        return True
    if receipt.get("reason") != "mixed_finalized_partial_terminal":
        return False
    row = (receipt.get("submissions") or {}).get(carrier)
    execution_evidence = receipt.get("executionEvidence")
    lanes = (
        execution_evidence.get("lanes")
        if isinstance(execution_evidence, Mapping)
        else None
    )
    lane = next(
        (
            item
            for item in lanes or []
            if isinstance(item, Mapping) and item.get("carrier") == carrier
        ),
        None,
    )
    expected_observed = {
        "sourceRevision": plan["sourceRevision"],
        "sourceDigest": submission["sourceDigest"],
        "entityCatalogDigest": plan["entityCatalogDigest"],
    }
    common_invalid = (
        not isinstance(row, Mapping)
        or not isinstance(execution_evidence, Mapping)
        or not isinstance(lanes, list)
        or len(lanes) != len(CAMPAIGN_CARRIERS)
        or not isinstance(lane, Mapping)
        or row.get("executionId") != execution_id
        or lane.get("executionId") != execution_id
        or receipt.get("rootExecutionId")
        != predecessor_campaign_root_execution_id(execution_id)
        or receipt.get("observedSourceIdentity") != expected_observed
        or any(row.get(key) != submission.get(key) for key in _SCOPE_FIELDS)
        or execution_evidence.get("observedFinalizedCount") != 3
        or execution_evidence.get("immutableReleaseEvidencePresent") is not False
        or execution_evidence.get("reviewedClosureAdoptionPresent") is not False
        or execution_evidence.get("evidenceDisposition") != "preserved_unadopted"
        or execution_evidence.get("excludedFromRetryRelease") is not True
        or execution_evidence.get("eligibleForRelease") is not False
        or lane.get("excludedFromRetryRelease") is not True
        or lane.get("eligibleForRelease") is not False
        or sum(
            1
            for item in lanes or []
            if isinstance(item, Mapping)
            and item.get("terminalStatus") == "failed"
        )
        != 1
    )
    if lane.get("terminalStatus") == "failed":
        lane_invalid = (
            lane.get("terminalStatus") != "failed"
            or lane.get("reportStatus") != "blocked"
            or lane.get("observedFinalizedCount") != 0
            or lane.get("publishReceiptPresent") is not False
            or lane.get("publishRefPresent") is not False
            or lane.get("objectTransactionEvidencePresent") is not False
            or lane.get("evidenceDisposition") != "failed_unpublished"
        )
    else:
        lane_invalid = (
            lane.get("terminalStatus") != "finalized"
            or lane.get("reportStatus") != "finalized"
            or lane.get("observedFinalizedCount") != 1
            or lane.get("publishSelectionFinalizedCount") != 1
            or lane.get("evidenceDisposition") != "preserved_unadopted"
            or not isinstance(lane.get("publishReceipt"), Mapping)
            or not isinstance(lane.get("publishRef"), Mapping)
            or not isinstance(lane.get("canonicalManifests"), list)
            or len(lane["canonicalManifests"]) != 1
        )
    if common_invalid or lane_invalid:
        raise typed_error(
            "RETRY_IDENTITY_DRIFT",
            f"{carrier} mixed finalized predecessor binding drift",
            evidence=receipt_path,
        )
    return True


__all__ = ["consume_mixed_finalized_boundary", "validate_reconciliation_retry_set"]
