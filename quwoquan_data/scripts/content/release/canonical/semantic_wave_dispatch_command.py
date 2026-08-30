"""Exact CLI argv projection for one standalone semantic-wave slot."""

from __future__ import annotations

from content.execution.request import RuntimeExecutionRequest


def task_execute_argv(
    *,
    execution_id: str,
    carrier: str,
    request: RuntimeExecutionRequest,
    semantic_receipt_ref: str | None,
    retry_of: str | None = None,
    retry_unfinished_refs: tuple[str, ...] = (),
) -> list[str]:
    binding = dict(request.scale_source_pool or {})
    selection = dict(request.source_pool_selection or {})
    authority = dict(request.execution_authority)
    if authority.get("mode") != "governed_calibration":
        raise ValueError(
            "GATE_BLOCK DATA.EXECUTION.AUTHORITY_INVALID: semantic wave "
            "dispatch requires governed_calibration authority"
        )
    # Canonical order is positional for the command prefix only. Every optional
    # option below is appended once in the order declared here; validators parse
    # option/value tokens and must not assume lineage is the argv suffix.
    argv = [
        "python3",
        "quwoquan_data/scripts/cli.py",
        "task",
        "execute",
        "--stage",
        "plan-only",
        "--execution-id",
        execution_id,
        "--family",
        request.family_ref,
        "--region-ref",
        request.region_ref,
        "--selector",
        request.selector.value,
        "--quota",
        str(request.quota),
        "--count",
        str(request.count),
        "--capacity-calibration-receipt",
        str(
            authority["calibration"]["calibrationReceiptRef"]
        ),
        "--semantic-selection-id",
        "cursor_grok",
        "--scale-source-pool-id",
        str(binding["poolId"]),
        "--scale-source-pool-target-scale",
        str(binding["targetScale"]),
        "--scale-source-pool-plan-ref",
        str(binding["planRef"]),
        "--scale-source-pool-plan-digest",
        str(binding["planDigest"]),
        "--scale-source-pool-plan-file-sha256",
        str(binding["planFileSha256"]),
        "--source-pool-source-revision",
        str(binding["sourceRevision"]),
        "--source-pool-source-digest",
        str(binding["sourceDigest"]),
        "--source-pool-entity-catalog-digest",
        str(binding["entityCatalogDigest"]),
        "--source-pool-evidence-root-ref",
        str(request.source_pool_evidence_root_ref),
        "--source-pool-carrier",
        carrier,
        "--source-pool-selection-digest",
        str(selection["selectionDigest"]),
        "--topic",
        str(request.topic),
    ]
    if semantic_receipt_ref:
        argv.extend(("--semantic-preflight-receipt", semantic_receipt_ref))
    for candidate_id in selection["candidateIds"]:
        argv.extend(("--source-pool-candidate-id", str(candidate_id)))
    for name in request.target_names:
        argv.extend(("--target", name))
    if retry_of:
        argv.extend(("--retry-of", retry_of))
        for ref in retry_unfinished_refs:
            argv.extend(("--retry-unfinished-ref", ref))
    return argv


__all__ = ["task_execute_argv"]
