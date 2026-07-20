"""Typed persistence boundary for managed-agent checkpoint history."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Iterable

from core.codec import JsonObject, JsonObjectDecodeError
from core.control_types import (
    AgentProvider,
    ExecutionStage,
    ManagedAgentCheckpointStatus,
)
from content.execution.agent.outcome import ManagedAgentJobOutcome

if TYPE_CHECKING:
    from content.execution.contracts import ExecutionStateTransition


def _non_negative_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _non_negative_float(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative number")
    return float(value)


def _optional_text(value: object, *, field_name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string or null")
    return value.strip()


def _required_boolean(value: object, *, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return value


@dataclass(frozen=True, slots=True)
class ManagedAgentScheduler:
    requested_max_workers: int
    effective_worker_count: int
    local_cursor_max_workers: int
    runtime: str
    prompt_count: int
    estimated_min_waves: int
    lane_limits: tuple[tuple[str, int], ...]
    provider: AgentProvider
    started_at: str
    finished_at: str
    elapsed_seconds: float

    def __post_init__(self) -> None:
        for field_name in (
            "requested_max_workers",
            "effective_worker_count",
            "local_cursor_max_workers",
            "prompt_count",
            "estimated_min_waves",
        ):
            _non_negative_int(getattr(self, field_name), field_name=field_name)
        _non_negative_float(self.elapsed_seconds, field_name="elapsed_seconds")
        if not self.runtime or not self.started_at or not self.finished_at:
            raise ValueError("scheduler runtime and timestamps are required")
        if not isinstance(self.provider, AgentProvider):
            raise TypeError("scheduler provider must be AgentProvider")
        for lane, limit in self.lane_limits:
            if not lane or _non_negative_int(limit, field_name=f"lane_limits.{lane}") < 1:
                raise ValueError("scheduler lane limits must be positive")

    @classmethod
    def from_document(cls, value: object, *, label: str) -> "ManagedAgentScheduler":
        try:
            doc = JsonObject.from_value(value, label=label)
            lane_values = doc.value("laneLimits")
            lane_doc = JsonObject.from_value(lane_values, label=f"{label}.laneLimits")
            lane_limits = tuple(
                sorted(
                    (
                        lane,
                        _non_negative_int(limit, field_name=f"laneLimits.{lane}"),
                    )
                    for lane, limit in lane_doc.to_document().items()
                )
            )
            return cls(
                requested_max_workers=_non_negative_int(
                    doc.value("requestedMaxWorkers"),
                    field_name="requestedMaxWorkers",
                ),
                effective_worker_count=_non_negative_int(
                    doc.value("effectiveWorkerCount"),
                    field_name="effectiveWorkerCount",
                ),
                local_cursor_max_workers=_non_negative_int(
                    doc.value("localCursorMaxWorkers"),
                    field_name="localCursorMaxWorkers",
                ),
                runtime=doc.string("runtime").strip(),
                prompt_count=_non_negative_int(doc.value("promptCount"), field_name="promptCount"),
                estimated_min_waves=_non_negative_int(
                    doc.value("estimatedMinWaves"),
                    field_name="estimatedMinWaves",
                ),
                lane_limits=lane_limits,
                provider=AgentProvider(doc.string("agentProvider")),
                started_at=doc.string("startedAt").strip(),
                finished_at=doc.string("finishedAt").strip(),
                elapsed_seconds=_non_negative_float(
                    doc.value("elapsedSeconds"),
                    field_name="elapsedSeconds",
                ),
            )
        except (JsonObjectDecodeError, ValueError) as exc:
            raise ValueError(f"{label} is invalid: {exc}") from exc

    def to_document(self) -> dict[str, object]:
        return {
            "requestedMaxWorkers": self.requested_max_workers,
            "effectiveWorkerCount": self.effective_worker_count,
            "localCursorMaxWorkers": self.local_cursor_max_workers,
            "runtime": self.runtime,
            "promptCount": self.prompt_count,
            "estimatedMinWaves": self.estimated_min_waves,
            "laneLimits": dict(self.lane_limits),
            "agentProvider": self.provider.value,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "elapsedSeconds": self.elapsed_seconds,
        }


@dataclass(frozen=True, slots=True)
class ManagedAgentRunRecord:
    stage: ExecutionStage
    job_count: int
    planned_job_count: int
    scheduler: ManagedAgentScheduler
    refs: tuple[str, ...]
    started_count: int
    finished_count: int
    infrastructure_failures: int
    outcomes: tuple[ManagedAgentJobOutcome, ...]
    finished_at: str
    recovered: bool = False
    recovered_at: str = ""
    recovery_reason: str = ""
    status: ManagedAgentCheckpointStatus = ManagedAgentCheckpointStatus.COMPLETED
    interrupt_reason: str = ""
    cancelled_queued_job_count: int = 0
    cancelled_active_job_count: int = 0
    terminated_subprocess_pids: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "job_count",
            "planned_job_count",
            "started_count",
            "finished_count",
            "infrastructure_failures",
            "cancelled_queued_job_count",
            "cancelled_active_job_count",
        ):
            _non_negative_int(getattr(self, field_name), field_name=field_name)
        if self.finished_count > self.job_count or self.started_count > self.job_count:
            raise ValueError("managed agent run counts cannot exceed job_count")
        if len(self.outcomes) != self.job_count:
            raise ValueError("managed agent run outcomes must match job_count")
        if not self.finished_at:
            raise ValueError("managed agent run finished_at is required")
        if self.recovered and not (self.recovered_at and self.recovery_reason):
            raise ValueError("recovered managed agent run requires recovery evidence")
        if not isinstance(self.status, ManagedAgentCheckpointStatus):
            raise TypeError("managed agent run status must be ManagedAgentCheckpointStatus")
        if (self.status is ManagedAgentCheckpointStatus.INTERRUPTED) != bool(
            self.interrupt_reason
        ):
            raise ValueError("interrupted managed agent run requires an interrupt reason")
        if any(pid < 1 for pid in self.terminated_subprocess_pids):
            raise ValueError("terminated subprocess pids must be positive")

    @classmethod
    def from_document(cls, value: object, *, label: str = "managed agent run") -> "ManagedAgentRunRecord":
        try:
            doc = JsonObject.from_value(value, label=label)
            raw_outcomes = doc.value("outcomes")
            if not isinstance(raw_outcomes, list):
                raise ValueError("outcomes must be an array")
            raw_pids = doc.value("terminatedSubprocessPids")
            if not isinstance(raw_pids, list):
                raise ValueError("terminatedSubprocessPids must be an array")
            return cls(
                stage=ExecutionStage(doc.string("stage")),
                job_count=_non_negative_int(doc.value("jobCount"), field_name="jobCount"),
                planned_job_count=_non_negative_int(
                    doc.value("plannedJobCount"),
                    field_name="plannedJobCount",
                ),
                scheduler=ManagedAgentScheduler.from_document(
                    doc.value("scheduler"),
                    label=f"{label}.scheduler",
                ),
                refs=doc.string_sequence("refs"),
                started_count=_non_negative_int(doc.value("startedCount"), field_name="startedCount"),
                finished_count=_non_negative_int(doc.value("finishedCount"), field_name="finishedCount"),
                infrastructure_failures=_non_negative_int(
                    doc.value("infrastructureFailures"),
                    field_name="infrastructureFailures",
                ),
                outcomes=tuple(
                    ManagedAgentJobOutcome.from_document(
                        item,
                        label=f"{label}.outcomes[{index}]",
                    )
                    for index, item in enumerate(raw_outcomes)
                ),
                finished_at=doc.string("finishedAt").strip(),
                recovered=_required_boolean(doc.value("recovered"), field_name="recovered"),
                recovered_at=_optional_text(doc.value("recoveredAt"), field_name="recoveredAt"),
                recovery_reason=_optional_text(doc.value("recoveryReason"), field_name="recoveryReason"),
                status=ManagedAgentCheckpointStatus(doc.string("status")),
                interrupt_reason=_optional_text(doc.value("interruptReason"), field_name="interruptReason"),
                cancelled_queued_job_count=_non_negative_int(
                    doc.value("cancelledQueuedJobCount"),
                    field_name="cancelledQueuedJobCount",
                ),
                cancelled_active_job_count=_non_negative_int(
                    doc.value("cancelledActiveJobCount"),
                    field_name="cancelledActiveJobCount",
                ),
                terminated_subprocess_pids=tuple(
                    _non_negative_int(item, field_name="terminatedSubprocessPids item")
                    for item in raw_pids
                ),
            )
        except (JsonObjectDecodeError, ValueError) as exc:
            raise ValueError(f"{label} is invalid: {exc}") from exc

    def to_document(self) -> dict[str, object]:
        return {
            "stage": self.stage.value,
            "jobCount": self.job_count,
            "plannedJobCount": self.planned_job_count,
            "scheduler": self.scheduler.to_document(),
            "refs": list(self.refs),
            "startedCount": self.started_count,
            "finishedCount": self.finished_count,
            "infrastructureFailures": self.infrastructure_failures,
            "outcomes": [outcome.to_document() for outcome in self.outcomes],
            "finishedAt": self.finished_at,
            "recovered": self.recovered,
            "recoveredAt": self.recovered_at or None,
            "recoveryReason": self.recovery_reason or None,
            "status": self.status.value,
            "interruptReason": self.interrupt_reason or None,
            "cancelledQueuedJobCount": self.cancelled_queued_job_count,
            "cancelledActiveJobCount": self.cancelled_active_job_count,
            "terminatedSubprocessPids": list(self.terminated_subprocess_pids),
        }

    def with_recovery(self, *, recovered_at: str, recovery_reason: str) -> "ManagedAgentRunRecord":
        return replace(
            self,
            recovered=True,
            recovered_at=recovered_at.strip(),
            recovery_reason=recovery_reason.strip(),
        )


def dedupe_managed_agent_runs(
    records: Iterable[ManagedAgentRunRecord],
) -> tuple[ManagedAgentRunRecord, ...]:
    index_by_key: dict[tuple[ExecutionStage, str, str, int, tuple[str, ...]], int] = {}
    unique: list[ManagedAgentRunRecord] = []
    for record in records:
        key = (
            record.stage,
            record.scheduler.started_at,
            record.finished_at,
            record.planned_job_count,
            record.refs,
        )
        existing_index = index_by_key.get(key)
        if existing_index is None:
            index_by_key[key] = len(unique)
            unique.append(record)
        else:
            unique[existing_index] = record
    return tuple(unique)


def state_managed_agent_runs(
    state: "ExecutionStateTransition",
) -> tuple[ManagedAgentRunRecord, ...]:
    documents = [*state.agent_run_history]
    if state.last_agent_run is not None:
        documents.append(state.last_agent_run)
    return dedupe_managed_agent_runs(
        ManagedAgentRunRecord.from_document(document, label="execution agent history")
        for document in documents
    )


def last_managed_agent_run(
    state: "ExecutionStateTransition",
) -> ManagedAgentRunRecord | None:
    if state.last_agent_run is None:
        return None
    return ManagedAgentRunRecord.from_document(
        state.last_agent_run,
        label="execution lastAgentRun",
    )


def save_managed_agent_run(
    state: "ExecutionStateTransition",
    record: ManagedAgentRunRecord,
    *,
    include_history: bool = True,
) -> None:
    if include_history:
        prior = state_managed_agent_runs(state)
        state.agent_run_history = [
            item.to_document()
            for item in dedupe_managed_agent_runs((*prior, record))[-20:]
        ]
    state.last_agent_run = record.to_document()


__all__ = [
    "ManagedAgentRunRecord",
    "ManagedAgentScheduler",
    "dedupe_managed_agent_runs",
    "last_managed_agent_run",
    "save_managed_agent_run",
    "state_managed_agent_runs",
]
