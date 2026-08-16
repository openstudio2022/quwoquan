"""Typed issue projection for canonical pool inspection."""

from __future__ import annotations

from content.release.canonical.pool_inspection import (
    _REASON_MESSAGES,
    Any,
    Counter,
    Mapping,
    _issue,
)


def _not_admitted_issue(
    issues: list[dict[str, str]],
    *,
    record: Mapping[str, Any] | None,
    admission_missing: bool,
    ref: str,
) -> None:
    if admission_missing:
        _issue(
            issues,
            gate="eligibility",
            code="DATA.POOL.EXPLICIT_ADMISSION_MISSING",
            ref=ref,
        )
        return
    gate = (
        "quality"
        if isinstance(record, Mapping) and record.get("qualityResult") == "failed"
        else "eligibility"
    )
    _issue(
        issues,
        gate=gate,
        code="DATA.POOL.OBJECT_NOT_ADMITTED",
        ref=ref,
    )


def _reason_summary(issues: list[dict[str, str]]) -> list[dict[str, Any]]:
    counts = Counter((row["gate"], row["code"]) for row in issues)
    return [
        {
            "gate": gate,
            "code": code,
            "count": count,
            "message": _REASON_MESSAGES.get(code, code),
        }
        for (gate, code), count in sorted(counts.items())
    ]
