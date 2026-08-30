"""Pure report helpers for canonical pool-append planning and apply."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


_HARD_BATCH_MARKERS = (
    "BACKUP_CONFLICT",
    "BATCH_",
    "CAS ",
    "CREATE-ONCE",
    "CREATE_ONCE",
    "INVENTORY",
    "RECORD_OBJECT_TYPE_INVALID",
    "SOURCE_ATTRIBUTION_DRIFT",
    "SOURCE_IDENTITY_DRIFT",
    "SOURCE_REF_MISMATCH",
    "TARGET_CONFLICT",
    "VERSION_CONFLICT",
    "VERSION_GAP",
)


def is_hard_batch_failure(exc: BaseException) -> bool:
    """Return true for shared batch/source/CAS corruption, never business rejects."""

    message = str(exc).strip().upper()
    return any(marker in message for marker in _HARD_BATCH_MARKERS)


def excluded_outcome(item: Mapping[str, Any]) -> dict[str, Any]:
    record = item.get("record")
    if not isinstance(record, Mapping):
        record = {}
    return {
        "itemId": str(item.get("itemId") or ""),
        "objectType": str(record.get("objectType") or ""),
        "objectId": str(record.get("objectId") or ""),
        "contentVersion": int(record.get("contentVersion") or 0),
        "recordSequence": int(record.get("recordSequence") or 0),
        "status": "excluded",
        "eligibilityResult": str(record.get("eligibilityResult") or ""),
        "usageScope": record.get("usageScope"),
    }


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


__all__ = [
    "batch_reason",
    "batch_report",
    "excluded_outcome",
    "is_hard_batch_failure",
]
