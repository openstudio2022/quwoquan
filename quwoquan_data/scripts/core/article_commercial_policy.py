"""Article commercial closure policy helpers."""
from __future__ import annotations

from typing import Any, Mapping

ARTICLE_COMMERCIAL_CLOSURE_FLAG = "articleCommercialClosure"


def article_commercial_closure_enabled(
    spec: Mapping[str, Any] | None = None,
) -> bool:
    candidate: Mapping[str, Any] | None = spec if isinstance(spec, Mapping) else None
    workflow = candidate.get("workflowPolicy") if isinstance(candidate, Mapping) else {}
    workflow = workflow if isinstance(workflow, Mapping) else {}
    return bool(workflow.get(ARTICLE_COMMERCIAL_CLOSURE_FLAG) is True)


__all__ = [
    "ARTICLE_COMMERCIAL_CLOSURE_FLAG",
    "article_commercial_closure_enabled",
]
