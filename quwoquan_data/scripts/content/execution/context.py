"""Execution runtime context for task/run.py.

This module owns the context object, managed-agent defaults, and execution state
persistence. The CLI entry lives in content.execution.controller.entrypoint; shared runtime state lives here
so stage orchestration can depend on a narrow, explicit contract.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Mapping

from core.control_types import (
    AgentProvider,
    ExecutionStage,
    ExecutionStateStatus,
    RuntimeEnvironment,
    StageKind,
    StageStatus,
)
from core.data_issue import (
    DataIssue,
    DataIssueCode,
    DataIssueStage,
    DataRecoveryAction,
    data_issues,
    issue_messages,
)

from core.io import read_json, write_json
from core.runtime_policy import active_runtime_policy
from content.execution import store
from content.execution.contracts import (
    ExecutionState,
    ExecutionStateTransition,
)
from content.execution.spec_contract import ExecutionSpec
from content.execution.workspace import ExecutionWorkspace, execution_command_packet_path, execution_state_path

EXECUTION_STATE_CONTRACT = "quwoquan.content.execution_state"

# 节点类型
AUTO = StageKind.AUTO
CHECKPOINT = StageKind.CHECKPOINT


@dataclass(frozen=True, slots=True)
class StageResult:
    """单 stage 执行结果。

    The execution target set is immutable. Stage results describe evidence
    repair or failure only and can never mutate target identity.
    """
    stage: ExecutionStage
    kind: StageKind
    status: StageStatus
    message: str = ""
    checkpoint_hint: str = ""
    fallback_stage: ExecutionStage | None = None
    issue_records: tuple[DataIssue, ...] = field(default_factory=tuple)
    controller_yield: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "issue_records", tuple(self.issue_records))
        if not isinstance(self.stage, ExecutionStage):
            raise TypeError("StageResult.stage must be an ExecutionStage")
        if not isinstance(self.kind, StageKind):
            raise TypeError("StageResult.kind must be a StageKind")
        if not isinstance(self.status, StageStatus):
            raise TypeError("StageResult.status must be a StageStatus")
        if self.fallback_stage is not None and not isinstance(
            self.fallback_stage,
            ExecutionStage,
        ):
            raise TypeError("StageResult.fallback_stage must be an ExecutionStage")
        if not all(isinstance(issue, DataIssue) for issue in self.issue_records):
            raise TypeError("StageResult.issue_records must contain DataIssue values")

    @property
    def issues(self) -> tuple[str, ...]:
        """Presentation-only rendering of the typed issue records."""
        return tuple(issue_messages(self.issue_records))

    @property
    def issue_stage(self) -> DataIssueStage:
        """Return the closed issue-stage value for this orchestration stage."""
        try:
            return DataIssueStage(self.stage.value)
        except ValueError as exc:
            raise ValueError(f"unknown execution stage: {self.stage}") from exc


def stage_issues(
    stage: ExecutionStage,
    messages: Iterable[object],
    *,
    code: DataIssueCode = DataIssueCode.QUALITY_FAILED,
    recovery: DataRecoveryAction = DataRecoveryAction.STOP,
    ref: str = "",
) -> tuple[DataIssue, ...]:
    """Convert presentation messages at a validation boundary into typed issues."""
    if not isinstance(stage, ExecutionStage):
        raise TypeError("stage_issues.stage must be an ExecutionStage")
    return tuple(data_issues(
        code,
        stage=DataIssueStage(stage.value),
        ref=ref,
        messages=messages,
        recovery=recovery,
    ))


_RUNTIME_POLICY = active_runtime_policy()
MAX_REACT_REWINDS = _RUNTIME_POLICY.react_rewind_limit
MAX_MANAGED_INFRA_RETRIES = _RUNTIME_POLICY.preflight_startup_attempts
DEFAULT_CURSOR_AGENT_MODEL = _RUNTIME_POLICY.cursor_model
DEFAULT_MANAGED_AGENT_PROVIDER = _RUNTIME_POLICY.cursor_provider
MANAGED_AGENT_PROVIDERS = {item.value for item in AgentProvider}
def _normalize_managed_agent_provider(raw: str | None) -> str:
    provider = str(raw or DEFAULT_MANAGED_AGENT_PROVIDER.value).strip()
    if provider not in MANAGED_AGENT_PROVIDERS:
        raise ValueError(f"unsupported managed agent provider: {provider}")
    return provider


def _resolve_managed_model(provider: str, raw_model: str | None) -> str:
    _normalize_managed_agent_provider(provider)
    model = str(raw_model or "").strip()
    return model or DEFAULT_CURSOR_AGENT_MODEL


MANAGED_LANE_LIMITS = {
    "homepage": _RUNTIME_POLICY.author_workers,
    "article": _RUNTIME_POLICY.author_workers,
    "image": _RUNTIME_POLICY.research_workers,
    "video": _RUNTIME_POLICY.author_workers,
}
MANAGED_AGENT_TIMEOUT_SECONDS = _RUNTIME_POLICY.agent_timeout_seconds
MANAGED_AGENT_FUTURE_GRACE_SECONDS = _RUNTIME_POLICY.managed_future_grace_seconds
MANAGED_SCHEDULER_STALE_SECONDS = _RUNTIME_POLICY.scheduler_stale_seconds
DOWNLOAD_FETCH_ONLY_RETRY_LIMIT = _RUNTIME_POLICY.download_fetch_retry_limit
_CURSOR_BRIDGE_LAUNCH_COOLDOWN_SECONDS = _RUNTIME_POLICY.bridge_launch_cooldown_seconds
_CURSOR_BRIDGE_READY_DELAY_SECONDS = _RUNTIME_POLICY.bridge_ready_delay_seconds
MANAGED_LOCAL_CURSOR_MAX_WORKERS = min(
    _RUNTIME_POLICY.author_workers,
    _RUNTIME_POLICY.cursor_bridge_instances,
)
_MANAGED_AGENT_SUBPROCESS_LOCK = threading.Lock()
_MANAGED_AGENT_SUBPROCESS_PIDS: set[int] = set()


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    execution_id: str
    entity_ids: tuple[str, ...]
    spec: ExecutionSpec
    baseline_packet: Mapping[str, object] | None = None
    baseline_packet_path: Path | None = None
    until: ExecutionStage | None = None
    completed: tuple[ExecutionStage, ...] = field(default_factory=tuple)
    managed: bool = False
    runtime: RuntimeEnvironment = RuntimeEnvironment.LOCAL
    max_workers: int = _RUNTIME_POLICY.author_workers
    model: str = DEFAULT_CURSOR_AGENT_MODEL
    agent_provider: AgentProvider = AgentProvider.CURSOR_SDK
    release_only: bool = False
    agent_runner: Callable[[str], Mapping[str, object]] | None = None
    force_clean_workspace_agent_state: bool = False
    controller_run_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "execution_id",
            ExecutionWorkspace(self.execution_id).execution_id,
        )
        object.__setattr__(self, "entity_ids", tuple(self.entity_ids))
        object.__setattr__(self, "completed", tuple(self.completed))
        if not isinstance(self.spec, ExecutionSpec):
            if not isinstance(self.spec, Mapping):
                raise TypeError("ExecutionContext.spec must be a mapping")
            object.__setattr__(self, "spec", ExecutionSpec.from_mapping(self.spec))
        if self.spec.execution_id != self.execution_id:
            raise ValueError(
                "ExecutionContext execution_id must match ExecutionSpec.execution_id"
            )
        if not isinstance(self.runtime, RuntimeEnvironment):
            object.__setattr__(self, "runtime", RuntimeEnvironment(str(self.runtime)))
        if not isinstance(self.agent_provider, AgentProvider):
            object.__setattr__(
                self,
                "agent_provider",
                AgentProvider(str(self.agent_provider)),
            )
        if self.until is not None and not isinstance(self.until, ExecutionStage):
            object.__setattr__(self, "until", ExecutionStage(str(self.until)))

    @property
    def workspace(self) -> ExecutionWorkspace:
        return ExecutionWorkspace(self.execution_id)


def _managed_local_cursor_worker_cap(
    ctx: ExecutionContext,
) -> int:
    if _normalize_managed_agent_provider(ctx.agent_provider) != "cursor_sdk":
        return max(1, int(ctx.max_workers))
    return min(max(1, int(ctx.max_workers)), MANAGED_LOCAL_CURSOR_MAX_WORKERS)


def _managed_uses_serial_local_cursor(ctx: ExecutionContext) -> bool:
    return (
        _normalize_managed_agent_provider(ctx.agent_provider) == "cursor_sdk"
        and str(ctx.runtime) == "local"
        and _managed_local_cursor_worker_cap(ctx) == 1
    )


def _write_execution_packet(
    ctx: ExecutionContext,
    *,
    stage_name: str,
    kind: str,
    result: StageResult,
    completed: list[str],
    next_stage: str | None,
    state: ExecutionStateTransition,
) -> Path:
    from core.command_packet import build_packet, write_packet

    packet = build_packet(
        execution_id=ctx.execution_id,
        command="task execute",
        object_kind="execution",
        object_ref=ctx.execution_id,
        stage=stage_name,
        read_policy=[
            "baseline_freeze_packet.json",
            "execution_state.json",
            "current stage inputs",
        ],
        stop_if=[f"stage {stage_name} failed", f"stage {stage_name} waiting"]
        if result.status is not StageStatus.DONE
        else [],
        output_policy=[
            "write _shared/command_packets/<stage>.json",
            "write _shared/execution_state.json",
            "advance only when gate is green",
        ],
        inputs={
            "baselinePacketPath": str(ctx.baseline_packet_path or ""),
            "completedStages": completed,
            "waitingCheckpoint": state.waiting_checkpoint,
            "until": ctx.until.value if ctx.until else "",
        },
        outputs={
            "status": result.status.value,
            "message": result.message,
            "checkpointHint": result.checkpoint_hint,
            "fallbackStage": result.fallback_stage.value if result.fallback_stage else None,
            "issues": list(result.issues),
            "issueRecords": [issue.as_dict() for issue in result.issue_records],
            "nextStage": next_stage or "",
        },
        handoff_to=(result.fallback_stage.value if result.fallback_stage else (next_stage or stage_name)),
        evidence={
            "kind": kind,
            "completed": result.status is StageStatus.DONE,
            "issueCount": len(result.issues),
            "issueRecordCount": len(result.issue_records),
        },
        summary={
            "executionId": ctx.execution_id,
            "stage": stage_name,
            "status": result.status.value,
            "message": result.message,
        },
    )
    return write_packet(execution_command_packet_path(ctx.execution_id, stage_name), packet)


def _state_path(execution_id: str) -> Path:
    return execution_state_path(execution_id)


def load_execution_state(execution_id: str) -> ExecutionStateTransition:
    p = _state_path(execution_id)
    if p.exists():
        return ExecutionState.from_mapping(read_json(p)).open_transition()
    return ExecutionState.from_mapping({
        "schema": EXECUTION_STATE_CONTRACT,
        "executionId": execution_id,
        "completed": [],
        "waitingCheckpoint": None,
        "status": ExecutionStateStatus.QUEUED.value,
        "owner": None,
        "heartbeatAt": None,
        "retryCounts": {},
        "infrastructureRetryCounts": {},
        "failedObjects": [],
        "nextAction": None,
        "updatedAt": store.now_iso(),
    }).open_transition()


def execution_state_status(state: ExecutionStateTransition) -> ExecutionStateStatus:
    return state.status


def save_execution_state(state: ExecutionStateTransition) -> Path:
    from core.schema import assert_valid

    state.updated_at = store.now_iso()
    payload = state.freeze().to_dict()
    # execution state 的字段唯一定义在 schema/execution/execution_state.schema.json；
    # 新增字段必须先补 Schema，未知字段 fail-closed 拒绝落盘。
    assert_valid(
        payload,
        "execution",
        "execution_state",
        label=f"execution_state:{state.execution_id}",
    )
    p = _state_path(state.execution_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    write_json(p, payload)
    return p
