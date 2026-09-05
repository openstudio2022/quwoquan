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
    cohort_selection: Any,
    excluded: tuple[Mapping[str, str], ...],
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
    result.update(
        {
            "poolDigest": cohort_selection.pool_digest,
            "poolEligibleCount": cohort_selection.eligible_count,
        }
    )
    if cohort_selection.milestone is not None:
        result["milestone"] = cohort_selection.milestone
        result["milestoneTargets"] = dict(
            cohort_selection.milestone_targets or {}
        )
    result["excluded"] = list(excluded)
    result["excludedCount"] = len(excluded)
    return result


__all__ = ["aggregate_release_result"]
