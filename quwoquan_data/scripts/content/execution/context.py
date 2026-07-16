"""Workflow runtime context for task/run.py.

This module owns the context object, managed-agent defaults, and workflow state
persistence. The CLI entry lives in content.execution.pipeline.cli; shared runtime state lives here
so stage orchestration can depend on a narrow, explicit contract.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from core.control_types import AgentProvider, ExecutionStage, RuntimeEnvironment, StageKind, StageStatus
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
from content.execution.workspace import ExecutionWorkspace, execution_workflow_packet_path, execution_workflow_state_path

WORKFLOW_STATE_VERSION = "quwoquan.content.workflow_state"
PIPELINE_STATE_VERSION = WORKFLOW_STATE_VERSION

# 节点类型
AUTO = StageKind.AUTO
CHECKPOINT = StageKind.CHECKPOINT


@dataclass
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
    issue_records: list[DataIssue] = field(default_factory=list)
    controller_yield: bool = False

    def __post_init__(self) -> None:
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
    def issues(self) -> list[str]:
        """Presentation-only rendering of the typed issue records."""
        return issue_messages(self.issue_records)

    @property
    def issue_stage(self) -> DataIssueStage:
        """Return the closed issue-stage value for this orchestration stage."""
        try:
            return DataIssueStage(self.stage.value)
        except ValueError as exc:
            raise ValueError(f"unknown workflow stage: {self.stage}") from exc


def stage_issues(
    stage: ExecutionStage,
    messages: Iterable[object],
    *,
    code: DataIssueCode = DataIssueCode.QUALITY_FAILED,
    recovery: DataRecoveryAction = DataRecoveryAction.STOP,
    ref: str = "",
) -> list[DataIssue]:
    """Convert a legacy boundary message list into typed stage outcomes."""
    if not isinstance(stage, ExecutionStage):
        raise TypeError("stage_issues.stage must be an ExecutionStage")
    return data_issues(
        code,
        stage=DataIssueStage(stage.value),
        ref=ref,
        messages=messages,
        recovery=recovery,
    )


_RUNTIME_POLICY = active_runtime_policy()
MAX_REACT_REWINDS = _RUNTIME_POLICY.react_rewind_limit
MAX_MANAGED_INFRA_RETRIES = _RUNTIME_POLICY.preflight_startup_attempts
DEFAULT_CURSOR_AGENT_MODEL = _RUNTIME_POLICY.cursor_model
DEFAULT_CODEX_AGENT_MODEL = os.environ.get("QWQ_CODEX_AGENT_MODEL", "").strip()
DEFAULT_MANAGED_AGENT_PROVIDER = AgentProvider.CURSOR_SDK
MANAGED_AGENT_PROVIDERS = {item.value for item in AgentProvider}
def _normalize_managed_agent_provider(raw: str | None) -> str:
    provider = str(raw or DEFAULT_MANAGED_AGENT_PROVIDER or "cursor_sdk").strip()
    if provider not in MANAGED_AGENT_PROVIDERS:
        return "cursor_sdk"
    return provider


def _resolve_managed_model(provider: str, raw_model: str | None) -> str:
    model = str(raw_model or "").strip()
    if model:
        return model
    if _normalize_managed_agent_provider(provider) == "codex_cli":
        return DEFAULT_CODEX_AGENT_MODEL
    return DEFAULT_CURSOR_AGENT_MODEL


MANAGED_LANE_LIMITS = {
    "homepage": _RUNTIME_POLICY.author_workers,
    "article": _RUNTIME_POLICY.author_workers,
    "image": _RUNTIME_POLICY.research_workers,
}
MANAGED_AGENT_TIMEOUT_SECONDS = _RUNTIME_POLICY.agent_timeout_seconds
MANAGED_AGENT_FUTURE_GRACE_SECONDS = _RUNTIME_POLICY.managed_future_grace_seconds
MANAGED_SCHEDULER_STALE_SECONDS = _RUNTIME_POLICY.scheduler_stale_seconds
DOWNLOAD_FETCH_ONLY_RETRY_LIMIT = _RUNTIME_POLICY.download_fetch_retry_limit
_CURSOR_BRIDGE_LAUNCH_COOLDOWN_SECONDS = _RUNTIME_POLICY.bridge_launch_cooldown_seconds
_CURSOR_BRIDGE_READY_DELAY_SECONDS = _RUNTIME_POLICY.bridge_ready_delay_seconds
MANAGED_LOCAL_CURSOR_MAX_WORKERS = _RUNTIME_POLICY.author_workers
MANAGED_CODEX_CLI_MAX_WORKERS = _RUNTIME_POLICY.codex_cli_workers
_MANAGED_AGENT_SUBPROCESS_LOCK = threading.Lock()
_MANAGED_AGENT_SUBPROCESS_PIDS: set[int] = set()


@dataclass
class ExecutionContext:
    execution_id: str
    entity_ids: list[str]
    spec: dict
    baseline_packet: dict | None = None
    baseline_packet_path: Path | None = None
    until: str | None = None
    completed: list[str] = field(default_factory=list)
    managed: bool = False
    runtime: str = RuntimeEnvironment.LOCAL
    max_workers: int = _RUNTIME_POLICY.author_workers
    model: str = DEFAULT_CURSOR_AGENT_MODEL
    agent_provider: str = AgentProvider.CURSOR_SDK
    release_only: bool = False
    agent_runner: Callable[[str], dict[str, Any]] | None = None
    force_clean_workspace_agent_state: bool = False

    def __post_init__(self) -> None:
        self.execution_id = ExecutionWorkspace(self.execution_id).execution_id

    @property
    def workspace(self) -> ExecutionWorkspace:
        return ExecutionWorkspace(self.execution_id)


def _managed_local_cursor_worker_cap(
    ctx: ExecutionContext,
    *,
    local_cursor_max_workers: int | None = MANAGED_LOCAL_CURSOR_MAX_WORKERS,
) -> int:
    if _normalize_managed_agent_provider(ctx.agent_provider) != "cursor_sdk":
        return max(1, int(ctx.max_workers or 1))
    if local_cursor_max_workers is not None:
        return max(1, int(local_cursor_max_workers))
    base = max(1, int(ctx.max_workers or 1))
    if str(ctx.runtime) != "local":
        return base
    try:
        state = load_workflow_state(ctx.execution_id)
    except Exception:  # noqa: BLE001 - cap must never block preflight/tests
        return base
    last = state.get("lastAgentRun") if isinstance(state.get("lastAgentRun"), Mapping) else {}
    if str((last or {}).get("stage") or "") != "post_author":
        return base
    infra = int((last or {}).get("infrastructureFailures") or 0)
    if infra <= 0:
        return base
    scheduler = last.get("scheduler") if isinstance(last.get("scheduler"), Mapping) else {}
    previous = int((scheduler or {}).get("effectiveWorkerCount") or base)
    # Cursor local bridge failures tend to be concurrency-sensitive.  Back off
    # aggressively so unattended reruns converge instead of replaying the same
    # connection-refused wave.
    return max(1, min(base, max(1, previous // 2)))


def _managed_uses_serial_local_cursor(ctx: ExecutionContext) -> bool:
    return (
        _normalize_managed_agent_provider(ctx.agent_provider) == "cursor_sdk"
        and str(ctx.runtime) == "local"
        and _managed_local_cursor_worker_cap(ctx) == 1
    )


def _write_workflow_packet(
    ctx: ExecutionContext,
    *,
    stage_name: str,
    kind: str,
    result: StageResult,
    completed: list[str],
    next_stage: str | None,
    state: dict,
) -> Path:
    from core.command_packet import build_packet, write_packet

    packet = build_packet(
        execution_id=ctx.execution_id,
        command="task geo-homepages",
        object_kind="workflow",
        object_ref=ctx.execution_id,
        stage=stage_name,
        read_policy=[
            "baseline_freeze_packet.json",
            "workflow_state.json",
            "current stage inputs",
        ],
        stop_if=[f"stage {stage_name} failed", f"stage {stage_name} waiting"] if result.status != "done" else [],
        output_policy=[
            "write _shared/workflow_packets/<stage>.json",
            "write _shared/workflow_state.json",
            "advance only when gate is green",
        ],
        inputs={
            "baselinePacketPath": str(ctx.baseline_packet_path or ""),
            "completedStages": completed,
            "waitingCheckpoint": state.get("waitingCheckpoint"),
            "until": ctx.until or "",
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
    return write_packet(execution_workflow_packet_path(ctx.execution_id, stage_name), packet)


def _state_path(execution_id: str) -> Path:
    return execution_workflow_state_path(execution_id)


def load_workflow_state(execution_id: str) -> dict:
    p = _state_path(execution_id)
    if p.exists():
        return read_json(p)
    return {
        "schemaVersion": WORKFLOW_STATE_VERSION,
        "executionId": execution_id,
        "completed": [],
        "waitingCheckpoint": None,
        "status": "queued",
        "owner": None,
        "heartbeatAt": None,
        "retryCounts": {},
        "infrastructureRetryCounts": {},
        "failedObjects": [],
        "nextAction": None,
        "updatedAt": store.now_iso(),
    }


def save_workflow_state(state: dict) -> Path:
    from core.schema import assert_valid

    state["updatedAt"] = store.now_iso()
    # workflow state 的字段唯一定义在 schema/execution/workflow_state.schema.json；
    # 新增字段必须先补 Schema，未知字段 fail-closed 拒绝落盘。
    assert_valid(state, "execution", "workflow_state", label=f"workflow_state:{state.get('executionId', '')}")
    p = _state_path(state["executionId"])
    p.parent.mkdir(parents=True, exist_ok=True)
    write_json(p, state)
    return p
