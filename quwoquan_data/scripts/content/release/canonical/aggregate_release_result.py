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
    canonical_merkle: str,
    manifest_digest: str,
    environment_selection: Any | None,
    excluded: tuple[Mapping[str, str], ...],
    pool_wide: bool,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": "quwoquan_data.aggregate_release_result",
        "releaseId": release_id,
        "releaseRoot": release_root,
        "executionIds": execution_ids,
        "entityCount": entity_count,
        "postCount": post_count,
        "creatorCount": creator_count,
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
        if environment_selection.environment is not None:
            result["targetEnvironment"] = environment_selection.environment
        if environment_selection.milestone is not None:
            result["milestone"] = environment_selection.milestone
            result["milestoneTargets"] = dict(
                environment_selection.milestone_targets or {}
            )
    if pool_wide:
        result["excluded"] = list(excluded)
        result["excludedCount"] = len(excluded)
    return result


__all__ = ["aggregate_release_result"]
