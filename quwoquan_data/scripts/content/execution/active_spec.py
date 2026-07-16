"""Read-only active-target and completion-policy projections for an execution."""
from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from content.execution.context import ExecutionContext


def active_spec(ctx: ExecutionContext) -> dict[str, Any]:
    """Return the immutable execution specification used by every stage."""
    return copy.deepcopy(ctx.spec)


def active_target(ctx: ExecutionContext, entity_id: str) -> dict[str, Any]:
    for target in ((active_spec(ctx).get("scope") or {}).get("coverageTargets") or []):
        if isinstance(target, Mapping) and str(target.get("name") or "").strip() == entity_id:
            return dict(target)
    return {}


def entity_homepages_per_target(ctx: ExecutionContext) -> int:
    content = ctx.spec.get("content") if isinstance(ctx.spec.get("content"), Mapping) else {}
    quotas = content.get("quotas") if isinstance(content.get("quotas"), Mapping) else {}
    raw = quotas.get("entityHomepagesPerTarget")
    if raw is None:
        return 1
    try:
        return max(0, int(raw or 0))
    except (TypeError, ValueError):
        return 1


def content_quota_int(ctx: ExecutionContext, key: str, *, default: int = 0) -> int:
    content = ctx.spec.get("content") if isinstance(ctx.spec.get("content"), Mapping) else {}
    quotas = content.get("quotas") if isinstance(content.get("quotas"), Mapping) else {}
    raw = quotas.get(key)
    if raw is None:
        return default
    try:
        return max(0, int(raw or 0))
    except (TypeError, ValueError):
        return default


def is_homepage_only_workflow(ctx: ExecutionContext) -> bool:
    from core.execution_branch import is_homepage_only_spec

    return is_homepage_only_spec(ctx.spec)

