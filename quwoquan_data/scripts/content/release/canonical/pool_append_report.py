"""Pure report helpers for canonical pool-append planning and apply."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def batch_reason(item: Mapping[str, Any], exc: BaseException) -> dict[str, str]:
    message = str(exc)
    return {
        "category": "quality" if "QUALITY" in message else "eligibility",
        "itemId": str(item.get("itemId") or ""),
        "code": message.split(":", 1)[0],
    }


def batch_report(
    *,
    apply: bool,
    total: int,
    ready: int,
    pending: int,
    failed: int,
    reasons: list[dict[str, str]],
    outcomes: list[dict[str, Any]],
) -> dict[str, Any]:
    if ready and not pending and not failed:
        result = "ready"
    elif ready:
        result = "partial"
    else:
        result = "blocked"
    return {
        "schema": "quwoquan_data.pool_append_result",
        "mode": "apply" if apply else "plan",
        "result": result,
        "checks": {
            "quality": "failed" if failed else "passed",
            "eligibility": "failed" if pending or failed else "passed",
            "delivery": "passed" if ready else "failed",
        },
        "counts": {
            "total": total,
            "ready": ready,
            "eligibilityPending": pending,
            "failed": failed,
        },
        "reasons": reasons,
        "detailsRef": None,
        "items": outcomes,
    }


__all__ = ["batch_reason", "batch_report"]
