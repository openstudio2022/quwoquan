"""Immutable execution-target helpers.

The execution manifest freezes the complete target set. Runtime stages may
repair evidence for those targets, but they must never substitute, abandon, or
silently suppress a target.
"""
from __future__ import annotations

from typing import Any

from content.execution.active_spec import active_spec
from content.execution.context import ExecutionContext


def frozen_target_names(ctx: ExecutionContext) -> tuple[str, ...]:
    """Return the ordered target names from the immutable execution spec."""
    names = tuple(
        str(target.get("name") or "").strip()
        for target in ((active_spec(ctx).get("scope") or {}).get("coverageTargets") or [])
        if str(target.get("name") or "").strip()
    )
    if names != tuple(ctx.entity_ids):
        raise ValueError(
            "execution context entity_ids must exactly match immutable coverageTargets"
        )
    if len(names) != len(set(names)):
        raise ValueError("immutable coverageTargets must not contain duplicates")
    return names


def prune_non_target_homepage_artifacts(
    ctx: ExecutionContext,
    *,
    reason: str,
) -> list[dict[str, Any]]:
    """Remove stale homepage artifacts that are outside the frozen target set."""
    from core.entity_artifacts import prune_inactive_entity_artifacts

    pruned = prune_inactive_entity_artifacts(
        ctx.execution_id,
        active_entity_names=list(frozen_target_names(ctx)),
    )
    if pruned:
        print(
            "[task execute] Pruned non-target homepage artifact(s): "
            + ", ".join(str(row.get("entity") or "") for row in pruned[:12])
            + (" ..." if len(pruned) > 12 else "")
            + f"; reason={reason}"
        )
    return pruned
