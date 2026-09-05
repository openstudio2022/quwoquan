"""Build the stable operator result for one immutable aggregate release."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def aggregate_release_result(
    *,
    release_id: str,
    release_root: str,
    execution_ids: list[str],
    entity_count: int,
    post_count: int,
    creator_count: int,
    carrier_counts: Mapping[str, int],
    canonical_merkle: str,
    manifest_digest: str,
    environment_selection: Any | None,
    excluded: tuple[Mapping[str, str], ...],
    sample_plan_ref: str | None,
    sample_plan_digest: str | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": "quwoquan_data.aggregate_release_result",
        "releaseId": release_id,
        "releaseRoot": release_root,
        "executionIds": execution_ids,
        "entityCount": entity_count,
        "postCount": post_count,
        "creatorCount": creator_count,
        "counts": dict(carrier_counts),
        "canonicalMerkle": canonical_merkle,
        "manifestDigest": manifest_digest,
        "idempotent": False,
    }
    if environment_selection is not None:
        result.update(
            {
                "selectionScope": environment_selection.selection_scope,
                "releaseMode": environment_selection.release_mode,
                "poolDigest": environment_selection.pool_digest,
                "poolEligibleCount": environment_selection.eligible_count,
                "counts": environment_selection.counts,
            }
        )
        if environment_selection.milestone is not None:
            result["milestone"] = environment_selection.milestone
            result["milestoneTargets"] = dict(
                environment_selection.milestone_targets or {}
            )
        if sample_plan_ref is not None:
            result["samplePlanRef"] = sample_plan_ref
            result["samplePlanDigest"] = sample_plan_digest
    result["excluded"] = list(excluded)
    result["excludedCount"] = len(excluded)
    return result


__all__ = ["aggregate_release_result"]
