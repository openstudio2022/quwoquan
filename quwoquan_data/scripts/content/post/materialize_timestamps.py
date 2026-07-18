"""Resolve stable creation/update timestamps for materialized manifests."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from content.execution.contracts import ExecutionRuntimeState


def _time_fact(payload: Mapping[str, Any], key: str) -> str | None:
    text = str(payload.get(key) or "").strip()
    return text or None


def materialized_manifest_times(
    compose_payload: Mapping[str, Any],
    review_payload: Mapping[str, Any],
    runtime_state: ExecutionRuntimeState | None,
) -> tuple[str, str]:
    created_at = (
        _time_fact(compose_payload, "createdAt")
        or _time_fact(review_payload, "createdAt")
        or (runtime_state.created_at if runtime_state is not None else "")
        or datetime.now(timezone.utc).isoformat()
    )
    updated_at = (
        _time_fact(compose_payload, "updatedAt")
        or _time_fact(review_payload, "updatedAt")
        or (runtime_state.updated_at if runtime_state is not None else "")
        or created_at
    )
    return created_at, updated_at
