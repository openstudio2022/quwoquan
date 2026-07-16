"""Resolve stable creation/update timestamps for materialized manifests."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping


def _time_fact(payload: Mapping[str, Any], key: str) -> str | None:
    text = str(payload.get(key) or "").strip()
    return text or None


def materialized_manifest_times(
    compose_payload: Mapping[str, Any],
    review_payload: Mapping[str, Any],
    batch_manifest: Mapping[str, Any],
) -> tuple[str, str]:
    created_at = (
        _time_fact(compose_payload, "createdAt")
        or _time_fact(review_payload, "createdAt")
        or str(batch_manifest.get("createdAt") or "").strip()
        or datetime.now(timezone.utc).isoformat()
    )
    updated_at = (
        _time_fact(compose_payload, "updatedAt")
        or _time_fact(review_payload, "updatedAt")
        or str(batch_manifest.get("updatedAt") or "").strip()
        or created_at
    )
    return created_at, updated_at
