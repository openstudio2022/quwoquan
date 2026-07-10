"""Article commercial closure policy helpers."""
from __future__ import annotations

from typing import Any, Mapping

ARTICLE_COMMERCIAL_CLOSURE_FLAG = "articleCommercialClosure"


def article_commercial_closure_enabled(
    spec: Mapping[str, Any] | None = None,
    *,
    task_id: str = "",
) -> bool:
    candidate: Mapping[str, Any] | None = spec if isinstance(spec, Mapping) else None
    if candidate is None and str(task_id or "").strip():
        try:
            from task import store

            candidate = store.load_spec(str(task_id))
        except Exception:  # noqa: BLE001
            candidate = None
    workflow = candidate.get("workflowPolicy") if isinstance(candidate, Mapping) else {}
    workflow = workflow if isinstance(workflow, Mapping) else {}
    return bool(workflow.get(ARTICLE_COMMERCIAL_CLOSURE_FLAG) is True)


__all__ = [
    "ARTICLE_COMMERCIAL_CLOSURE_FLAG",
    "article_commercial_closure_enabled",
]
