"""Typed object-level publish exclusions shared by execution and release gates."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


PUBLISH_APPLY_FAILED = "DATA.PUBLISH.OBJECT_APPLY_FAILED"
PUBLISH_JOB_FAILED = "DATA.PUBLISH.JOB_FAILED"
PUBLISH_PREPARATION_FAILED = "DATA.PUBLISH.OBJECT_PREPARATION_FAILED"
# Over-budget objects are blocked whole. The two causes stay apart because they
# hand the operator two different next steps: reference fewer assets in this
# object, versus replace the one asset that exceeds the object budget by itself.
OBJECT_CLOSURE_OVER_BUDGET = "DATA.PUBLISH.OBJECT_CLOSURE_OVER_BUDGET"
OBJECT_ASSET_OVER_BUDGET = "DATA.PUBLISH.OBJECT_ASSET_OVER_BUDGET"

_HARD_FAILURE_MARKERS = (
    "BATCH_DIGEST",
    "CANONICAL OBJECT DRIFT",
    "CANONICAL_PUBLISH_DRIFT",
    "CAS ",
    "CAS_",
    "CREATE-ONCE",
    "CREATE_ONCE",
    "DUPLICATE TARGET",
    "EXECUTION_SCHEMA",
    "FENC",
    "GLOBAL_SCHEMA",
    "IMMUTABLE_COLLISION",
    "INVENTORY",
    "SOURCE DIGEST",
    "SOURCEDIGEST",
    "SOURCE IDENTITY DRIFT",
    "SOURCE_IDENTITY_DRIFT",
    "SOURCE_REVISION",
    "TARGET_CONFLICT",
    "VERSION_CONFLICT",
    "VERSION_GAP",
)


class TypedPublishExclusion(Exception):
    """A failure that already named its object-level exclusion code.

    Deriving a code by matching an exception message keeps a translation table
    outside the closed set: rewording one error string would silently change
    what an operator reads as the reason. A failure that knows its own code
    carries it instead.
    """

    def __init__(self, issue_code: str, message: str) -> None:
        code = str(issue_code or "").strip()
        if not code:
            raise ValueError("typed publish exclusion requires an issue code")
        super().__init__(message)
        self.issue_code = code


def is_hard_publish_failure(error: BaseException) -> bool:
    """Keep shared identity/fence/CAS corruption outside object isolation."""

    if isinstance(error, TypedPublishExclusion):
        return False
    message = str(error).strip().upper()
    return any(marker in message for marker in _HARD_FAILURE_MARKERS)


def publish_issue_code(error: BaseException) -> str:
    if isinstance(error, TypedPublishExclusion):
        return error.issue_code
    message = str(error).strip().upper()
    if "DUPLICATE" in message or "ALREADY EXISTS" in message:
        return "DATA.PUBLISH.OBJECT_DUPLICATE"
    if "ADMISSION" in message or "NOT_ADMITTED" in message:
        return "DATA.PUBLISH.OBJECT_ADMISSION_FAILED"
    if "ATTESTATION" in message or "REVIEW" in message:
        return "DATA.PUBLISH.OBJECT_ATTESTATION_FAILED"
    return PUBLISH_APPLY_FAILED


def publish_discard(
    object_ref: object,
    *,
    issue: str,
) -> dict[str, Any]:
    ref = str(object_ref or "").strip()
    code = str(issue or "").strip()
    if not ref or not code:
        raise ValueError("publish discard requires objectRef and typed issue")
    return {"objectRef": ref, "issues": [code]}


def normalize_publish_discards(
    rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        object_ref = str(row.get("objectRef") or "").strip()
        issues = sorted(
            {
                str(issue).strip()
                for issue in (row.get("issues") or [])
                if str(issue).strip()
            }
        )
        if not object_ref or not issues or object_ref in seen:
            raise ValueError(
                "publish discards require unique objectRef and typed issues"
            )
        seen.add(object_ref)
        normalized.append({"objectRef": object_ref, "issues": issues})
    return sorted(normalized, key=lambda row: row["objectRef"])


__all__ = [
    "OBJECT_ASSET_OVER_BUDGET",
    "OBJECT_CLOSURE_OVER_BUDGET",
    "PUBLISH_APPLY_FAILED",
    "PUBLISH_JOB_FAILED",
    "PUBLISH_PREPARATION_FAILED",
    "TypedPublishExclusion",
    "is_hard_publish_failure",
    "normalize_publish_discards",
    "publish_discard",
    "publish_issue_code",
]
