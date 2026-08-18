"""Operator-facing progress, bottleneck and remaining-time projection.

At ten objects an operator can read the stage log. At a thousand they cannot,
and "is this still working or is it stuck?" becomes the only question that
matters. This module answers it from evidence already on disk — the completed
stage set, the quota pursuit ledger and the isolated per-object outcomes — so
observability does not need a second bookkeeping path that could disagree with
the execution state.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def _parse_iso(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class ExecutionProgress:
    """One projection of how far an execution has got and what is holding it."""

    execution_id: str
    approved_quota: int
    produced_count: int
    failed_count: int
    completed_stages: tuple[str, ...]
    total_stages: int
    current_stage: str | None
    bottleneck: str | None
    elapsed_seconds: int | None
    estimated_remaining_seconds: int | None

    @property
    def remaining_deficit(self) -> int:
        return max(0, self.approved_quota - self.produced_count)

    @property
    def object_completion_rate(self) -> float:
        if self.approved_quota <= 0:
            return 0.0
        return min(1.0, self.produced_count / self.approved_quota)

    @property
    def stage_completion_rate(self) -> float:
        if self.total_stages <= 0:
            return 0.0
        return min(1.0, len(self.completed_stages) / self.total_stages)

    def to_document(self) -> dict[str, Any]:
        return {
            "executionId": self.execution_id,
            "approvedQuota": self.approved_quota,
            "producedCount": self.produced_count,
            "failedCount": self.failed_count,
            "remainingDeficit": self.remaining_deficit,
            "objectCompletionRate": round(self.object_completion_rate, 4),
            "stageCompletionRate": round(self.stage_completion_rate, 4),
            "completedStageCount": len(self.completed_stages),
            "totalStageCount": self.total_stages,
            "currentStage": self.current_stage,
            "bottleneck": self.bottleneck,
            "elapsedSeconds": self.elapsed_seconds,
            "estimatedRemainingSeconds": self.estimated_remaining_seconds,
        }

    def render(self) -> str:
        """One dense operator line: progress, bottleneck and remaining time."""

        parts = [
            f"{self.execution_id}",
            f"objects {self.produced_count}/{self.approved_quota}"
            f" ({self.object_completion_rate:.0%})",
            f"stages {len(self.completed_stages)}/{self.total_stages}",
        ]
        if self.failed_count:
            parts.append(f"failed {self.failed_count}")
        if self.current_stage:
            parts.append(f"at {self.current_stage}")
        if self.bottleneck:
            parts.append(f"bottleneck {self.bottleneck}")
        if self.estimated_remaining_seconds is not None:
            parts.append(f"eta ~{self.estimated_remaining_seconds}s")
        return " | ".join(parts)


def project_execution_progress(
    *,
    execution_id: str,
    approved_quota: int,
    produced_count: int,
    failed_count: int,
    completed_stages: tuple[str, ...],
    total_stages: int,
    current_stage: str | None,
    started_at: object = None,
    observed_at: object = None,
    bottleneck: str | None = None,
) -> ExecutionProgress:
    """Project progress and remaining time from durable execution evidence.

    ``estimated_remaining_seconds`` stays absent rather than guessing: with no
    start timestamp or no delivered object there is no measured rate, and a
    fabricated estimate is worse than an admitted unknown.
    """

    if isinstance(approved_quota, bool) or approved_quota < 1:
        raise ValueError("progress projection requires a positive approvedQuota")
    for label, value in (
        ("producedCount", produced_count),
        ("failedCount", failed_count),
        ("totalStageCount", total_stages),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"progress projection {label} must be non-negative")
    started = _parse_iso(started_at)
    observed = _parse_iso(observed_at) or datetime.now(timezone.utc)
    elapsed_seconds: int | None = None
    remaining_seconds: int | None = None
    if started is not None:
        elapsed_seconds = max(0, int((observed - started).total_seconds()))
        deficit = max(0, approved_quota - produced_count)
        if produced_count > 0 and elapsed_seconds > 0 and deficit:
            seconds_per_object = elapsed_seconds / produced_count
            remaining_seconds = int(seconds_per_object * deficit)
        elif not deficit:
            remaining_seconds = 0
    resolved_bottleneck = bottleneck
    if resolved_bottleneck is None and failed_count and current_stage:
        resolved_bottleneck = (
            f"{current_stage}: {failed_count} objects isolated as failed"
        )
    return ExecutionProgress(
        execution_id=str(execution_id),
        approved_quota=approved_quota,
        produced_count=produced_count,
        failed_count=failed_count,
        completed_stages=tuple(completed_stages),
        total_stages=total_stages,
        current_stage=current_stage,
        bottleneck=resolved_bottleneck,
        elapsed_seconds=elapsed_seconds,
        estimated_remaining_seconds=remaining_seconds,
    )


__all__ = ["ExecutionProgress", "project_execution_progress"]
