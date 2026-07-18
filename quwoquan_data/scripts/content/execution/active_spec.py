"""Read-only active-target and completion-policy projections for an execution."""
from __future__ import annotations

from typing import Any

from content.execution.context import ExecutionContext


def active_spec(ctx: ExecutionContext) -> dict[str, Any]:
    """Return the immutable execution specification used by every stage."""
    return ctx.spec.to_dict()


def active_target(ctx: ExecutionContext, entity_id: str) -> dict[str, Any]:
    for target in ctx.spec.scope.coverage_targets:
        if target.name == entity_id:
            return target.to_dict()
    return {}


def entity_homepages_per_target(ctx: ExecutionContext) -> int:
    return ctx.spec.content.quotas.entity_homepages_per_target


def is_homepage_only_execution(ctx: ExecutionContext) -> bool:
    from core.execution_branch import is_homepage_only_spec

    return is_homepage_only_spec(ctx.spec.to_dict())
