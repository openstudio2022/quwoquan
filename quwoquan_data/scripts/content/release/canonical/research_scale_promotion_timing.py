"""Revalidate and project campaign wall-clock evidence into promotion receipts."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any


class ResearchScalePromotionTimingError(RuntimeError):
    pass


_BUDGET_SECONDS = {"M100": None, "M1000": None, "M10000": 604800}


def _timestamp(value: object, *, label: str) -> datetime:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ResearchScalePromotionTimingError(
            f"DATA.SCALE.ATTAINMENT_TIMING_BLOCKED: {label} is invalid"
        ) from exc
    if parsed.tzinfo is None:
        raise ResearchScalePromotionTimingError(
            f"DATA.SCALE.ATTAINMENT_TIMING_BLOCKED: {label} lacks timezone"
        )
    return parsed.astimezone(timezone.utc)


def validate_promotion_timing(
    *,
    target_scale: str,
    evidence: Mapping[str, Any],
    resource_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    if target_scale not in _BUDGET_SECONDS:
        raise ResearchScalePromotionTimingError(
            f"unsupported research milestone: {target_scale}"
        )
    started = _timestamp(evidence.get("scaleStartedAt"), label="scaleStartedAt")
    completed = _timestamp(evidence.get("scaleCompletedAt"), label="scaleCompletedAt")
    resource_completed = _timestamp(
        resource_evidence.get("terminalResidualSampleAt"),
        label="terminalResidualSampleAt",
    )
    raw_seconds = evidence.get("wallClockSeconds")
    budget = _BUDGET_SECONDS[target_scale]
    elapsed = int((completed - started).total_seconds())
    if (
        evidence.get("targetScale") != target_scale
        or completed != resource_completed
        or elapsed < 0
        or isinstance(raw_seconds, bool)
        or not isinstance(raw_seconds, int)
        or raw_seconds != elapsed
        or evidence.get("wallClockBudgetSeconds") != budget
    ):
        raise ResearchScalePromotionTimingError(
            "DATA.SCALE.ATTAINMENT_TIMING_BLOCKED: campaign timing evidence drift"
        )
    return {
        "scaleStartedAt": started.isoformat(),
        "scaleCompletedAt": completed.isoformat(),
        "wallClockBudgetSeconds": budget,
        "wallClockSeconds": elapsed,
    }


__all__ = ["ResearchScalePromotionTimingError", "validate_promotion_timing"]
