"""Campaign-envelope identity and retry-lineage checks for submission freeze."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from core import paths

from content.execution.request import RuntimeExecutionRequest


def validate_envelope_identity(
    envelope: Mapping[str, Any],
    *,
    scale: str,
    workload_mode: str,
    active_carriers: Sequence[str],
    workloads: Mapping[str, int],
    root_execution_id: str,
    execution_id: str,
    operation: str,
    carrier: str,
    request: RuntimeExecutionRequest,
    retry_of: str | None,
    git_branch: str,
    git_commit_sha: str,
    source_revision: str,
    source: Mapping[str, Any],
    execution_bundle: Mapping[str, Any],
    entity_catalog_digest: str,
) -> None:
    expected = {
        "scale": scale,
        "workloadMode": workload_mode,
        "activeCarriers": list(active_carriers),
        "workloads": dict(workloads),
        "rootExecutionId": root_execution_id,
        "executionId": execution_id,
        "operation": operation,
        "carrier": carrier,
        "familyRef": request.family_ref,
        "regionRef": request.region_ref,
        "selector": request.selector.value,
        "quota": request.quota,
        "count": request.count,
        "executionAuthority": dict(request.execution_authority),
        "workerHostSetBinding": (
            dict(request.worker_host_set_binding)
            if request.worker_host_set_binding is not None
            else None
        ),
        "scaleSourcePool": (
            dict(request.scale_source_pool)
            if request.scale_source_pool is not None
            else None
        ),
        "sourcePoolEvidenceRootRef": request.source_pool_evidence_root_ref,
        "sourcePoolSelection": (
            dict(request.source_pool_selection)
            if request.source_pool_selection is not None
            else None
        ),
        "topic": request.topic,
        "targetNames": list(request.target_names),
        "sourceProviders": list(request.source_providers),
        "semanticSelectionId": envelope.get("semanticSelectionId"),
        "semanticPreflightReceipt": envelope.get("semanticPreflightReceipt"),
        "retryOf": retry_of,
        "gitBranch": git_branch,
        "gitCommitSha": git_commit_sha,
        "sourceRevision": source_revision,
        "sourceDigest": dict(source),
        "executionBundle": dict(execution_bundle),
        "entityCatalogDigest": entity_catalog_digest,
        "predecessorReconciliation": envelope.get("predecessorReconciliation"),
    }
    drift = [key for key, value in expected.items() if envelope.get(key) != value]
    if drift:
        raise ValueError(
            "GATE_BLOCK DATA.CAMPAIGN.EXTERNAL_INPUT_IDENTITY_DRIFT: "
            "campaign envelope drift: " + ", ".join(drift)
        )


def validate_predecessor_reconciliation(
    binding: Mapping[str, Any],
    *,
    carrier: str,
    retry_of: str | None,
    request: RuntimeExecutionRequest,
    source_revision: str,
    source: Mapping[str, Any],
    execution_bundle: Mapping[str, Any],
    entity_catalog_digest: str,
) -> None:
    from content.execution.campaign.submission_reconciliation import (
        load_reconciliation_reference,
    )

    receipt, _receipt_path = load_reconciliation_reference(
        binding,
        output_root=paths.OUTPUT_ROOT,
    )
    predecessor_row = (receipt.get("submissions") or {}).get(carrier)
    current_source_identity = {
        "sourceRevision": source_revision,
        "sourceDigest": dict(source),
        "executionBundle": dict(execution_bundle),
        "entityCatalogDigest": entity_catalog_digest,
    }
    expected_scope = {
        "executionId": retry_of,
        "familyRef": request.family_ref,
        "regionRef": request.region_ref,
        "selector": request.selector.value,
        "quota": request.quota,
        "count": request.count,
        "topic": request.topic,
        "targetNames": list(request.target_names),
        "sourceProviders": list(request.source_providers),
    }
    shortfall_retry = receipt.get("reason") == (
        "terminal_unpublished_retryable_shortfall"
    )
    execution_evidence = receipt.get("executionEvidence")
    lanes = (
        execution_evidence.get("lanes")
        if isinstance(execution_evidence, Mapping)
        else None
    )
    predecessor_lane = next(
        (
            row
            for row in lanes or ()
            if isinstance(row, Mapping)
            and row.get("carrier") == carrier
            and row.get("executionId") == retry_of
        ),
        None,
    )
    shortfall_scope_valid = (
        shortfall_retry
        and receipt.get("retryPolicy")
        == "active_workload_execution_with_retryOf"
        and isinstance(execution_evidence, Mapping)
        and execution_evidence.get("excludedFromRetryRelease") is True
        and execution_evidence.get("eligibleForRelease") is False
        and isinstance(predecessor_row, Mapping)
        and isinstance(predecessor_lane, Mapping)
        and predecessor_lane.get("terminalStatus") == "failed"
        and predecessor_lane.get("evidenceDisposition") == "failed_unpublished"
        and predecessor_lane.get("excludedFromRetryRelease") is True
        and predecessor_lane.get("eligibleForRelease") is False
        and all(
            predecessor_row.get(key) == expected_scope[key]
            for key in (
                "executionId",
                "familyRef",
                "regionRef",
                "selector",
                "topic",
            )
        )
        and 1 <= request.quota <= int(predecessor_row.get("quota") or 0)
        and request.quota <= request.count <= int(predecessor_row.get("count") or 0)
    )
    if (
        not isinstance(predecessor_row, Mapping)
        or (
            receipt.get("reason") == "source_drift"
            and receipt.get("originalSourceIdentity") == current_source_identity
        )
        or (
            not shortfall_scope_valid
            and any(
                predecessor_row.get(key) != value
                for key, value in expected_scope.items()
            )
        )
    ):
        raise ValueError(
            "GATE_BLOCK DATA.CAMPAIGN.SUBMISSION_RECONCILIATION_DRIFT: "
            "predecessor receipt lineage/target/scope binding drift"
        )


__all__ = ["validate_envelope_identity", "validate_predecessor_reconciliation"]
