"""Workflow runtime context for task/run.py.

This module owns the context object, managed-agent defaults, and workflow state
persistence.  The CLI facade stays in task.run; shared runtime state lives here
so stage orchestration can depend on a narrow, explicit contract.
"""
from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from _common.io import read_json, write_json
from _common.paths import batch_workflow_packet_path
from task import store

WORKFLOW_STATE_VERSION = "quwoquan.task.workflow_state"
PIPELINE_STATE_VERSION = WORKFLOW_STATE_VERSION

# 节点类型
AUTO = "auto"          # CLI 确定性执行
CHECKPOINT = "checkpoint"  # 等待 Agent 物化产物后 resume


@dataclass
class StageResult:
    """单 stage 执行结果。"""
    stage: str
    kind: str
    status: str           # done | waiting | failed | skipped
    message: str = ""
    checkpoint_hint: str = ""
    fallback_stage: str | None = None   # ReAct 回退目标 DAG stage（failed 时消费）
    issues: list[str] = field(default_factory=list)


# ReAct 回退：CLI gate fallbackStage(download/compose) → DAG stage
# 语义：证据不足回到检索 checkpoint；质量不达回到 compose 重组。
FALLBACK_DAG_STAGE = {
    "download": "download_plan",
    "compose": "produce_compose",
    "agent_compose": "produce_compose",
    "manual": "produce_compose",
    "produce_compose": "produce_compose",
    "download_plan": "download_plan",
}
MAX_REACT_REWINDS = 2  # 单 stage 自动回退次数上限，超出转人工，防无限自省
MAX_MANAGED_INFRA_RETRIES = 3
DEFAULT_CURSOR_AGENT_MODEL = os.environ.get("QWQ_CURSOR_AGENT_MODEL", "composer")
DEFAULT_CODEX_AGENT_MODEL = os.environ.get("QWQ_CODEX_AGENT_MODEL", "").strip()
DEFAULT_MANAGED_AGENT_PROVIDER = os.environ.get("QWQ_MANAGED_AGENT_PROVIDER", "cursor_sdk")
MANAGED_AGENT_PROVIDERS = {"cursor_sdk", "codex_cli"}
_DEFAULT_MANAGED_LANE_LIMITS = {"homepage": 3, "article": 3, "image": 4}


def _parse_managed_lane_limits(raw: str | None) -> dict[str, int]:
    limits = dict(_DEFAULT_MANAGED_LANE_LIMITS)
    text = str(raw or "").strip()
    if not text:
        return limits
    for part in re.split(r"[,;]\s*", text):
        if not part:
            continue
        if ":" in part:
            key, value = part.split(":", 1)
        elif "=" in part:
            key, value = part.split("=", 1)
        else:
            continue
        lane = key.strip()
        if lane not in limits:
            continue
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        limits[lane] = max(1, parsed)
    return limits


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


MANAGED_LANE_LIMITS = _parse_managed_lane_limits(os.environ.get("QWQ_MANAGED_LANE_LIMITS"))
MANAGED_AGENT_TIMEOUT_SECONDS = max(
    60, int(os.environ.get("QWQ_MANAGED_AGENT_TIMEOUT_SECONDS", "360"))
)
MANAGED_AGENT_FUTURE_GRACE_SECONDS = max(
    5, int(os.environ.get("QWQ_MANAGED_AGENT_FUTURE_GRACE_SECONDS", "15"))
)
MANAGED_SCHEDULER_STALE_SECONDS = max(
    60, int(os.environ.get("QWQ_MANAGED_SCHEDULER_STALE_SECONDS", "900"))
)
DOWNLOAD_FETCH_ONLY_RETRY_LIMIT = max(
    0, int(os.environ.get("QWQ_DOWNLOAD_FETCH_ONLY_RETRY_LIMIT", "1"))
)
_CURSOR_BRIDGE_LAUNCH_COOLDOWN_SECONDS = max(
    0.0, float(os.environ.get("QWQ_CURSOR_BRIDGE_LAUNCH_COOLDOWN_SECONDS", "2.0"))
)
_CURSOR_BRIDGE_READY_DELAY_SECONDS = max(
    0.0, float(os.environ.get("QWQ_CURSOR_BRIDGE_READY_DELAY_SECONDS", "1.5"))
)
_RAW_MANAGED_LOCAL_CURSOR_MAX_WORKERS = os.environ.get("QWQ_MANAGED_LOCAL_CURSOR_MAX_WORKERS")
MANAGED_LOCAL_CURSOR_MAX_WORKERS = (
    max(1, int(_RAW_MANAGED_LOCAL_CURSOR_MAX_WORKERS))
    if _RAW_MANAGED_LOCAL_CURSOR_MAX_WORKERS
    else None
)
MANAGED_CODEX_CLI_MAX_WORKERS = max(
    1, int(os.environ.get("QWQ_MANAGED_CODEX_CLI_MAX_WORKERS", "1"))
)
REPLACEMENT_MAX_WAVES = max(
    1, int(os.environ.get("QWQ_REPLACEMENT_MAX_WAVES", "3"))
)
REPLACEMENT_MAX_CANDIDATES_PER_WAVE = max(
    1, int(os.environ.get("QWQ_REPLACEMENT_MAX_CANDIDATES_PER_WAVE", "8"))
)
REPLACEMENT_MAX_SCREENED_PER_RUN = max(
    1, int(os.environ.get("QWQ_REPLACEMENT_MAX_SCREENED_PER_RUN", "64"))
)
TARGET_SET_DEPENDENT_STAGES = (
    "download_fetch",
    "build_prepare",
    "build_homepage",
    "build_validate",
    "content_plan",
    "produce_plan",
    "produce_compose",
    "produce_author",
    "produce_annotate",
    "produce_review",
    "publish",
)

_MANAGED_AGENT_SUBPROCESS_LOCK = threading.Lock()
_MANAGED_AGENT_SUBPROCESS_PIDS: set[int] = set()


@dataclass
class PipelineContext:
    task_id: str
    batch_id: str
    entity_ids: list[str]
    spec: dict
    baseline_packet: dict | None = None
    baseline_packet_path: Path | None = None
    until: str | None = None
    completed: list[str] = field(default_factory=list)
    managed: bool = False
    runtime: str = "local"
    max_workers: int = 10
    model: str = DEFAULT_CURSOR_AGENT_MODEL
    agent_provider: str = "cursor_sdk"
    release_only: bool = False
    agent_runner: Callable[[str], dict[str, Any]] | None = None
    force_clean_workspace_agent_state: bool = False


def _managed_local_cursor_worker_cap(
    ctx: PipelineContext,
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
        state = load_workflow_state(ctx.task_id, ctx.batch_id)
    except Exception:  # noqa: BLE001 - cap must never block preflight/tests
        return base
    last = state.get("lastAgentRun") if isinstance(state.get("lastAgentRun"), Mapping) else {}
    if str((last or {}).get("stage") or "") != "produce_author":
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


def _managed_uses_serial_local_cursor(ctx: PipelineContext) -> bool:
    return (
        _normalize_managed_agent_provider(ctx.agent_provider) == "cursor_sdk"
        and str(ctx.runtime) == "local"
        and _managed_local_cursor_worker_cap(ctx) == 1
    )


def _write_workflow_packet(
    ctx: PipelineContext,
    *,
    stage_name: str,
    kind: str,
    result: StageResult,
    completed: list[str],
    next_stage: str | None,
    state: dict,
) -> Path:
    from _common.command_packet import build_packet, write_packet

    packet = build_packet(
        task_id=ctx.task_id,
        command="data workflow run",
        object_kind="workflow",
        object_ref=f"{ctx.task_id}::{ctx.batch_id}",
        stage=stage_name,
        read_policy=[
            "baseline_freeze_packet.json",
            "workflow_state.json",
            "current stage inputs",
        ],
        stop_if=[f"stage {stage_name} failed", f"stage {stage_name} waiting"] if result.status != "done" else [],
        output_policy=[
            "write _shared/workflow_packets/<stage>.json",
            "write _shared/task_workflow_state.json",
            "advance only when gate is green",
        ],
        inputs={
            "baselinePacketPath": str(ctx.baseline_packet_path or ""),
            "completedStages": completed,
            "waitingCheckpoint": state.get("waitingCheckpoint"),
            "until": ctx.until or "",
        },
        outputs={
            "status": result.status,
            "message": result.message,
            "checkpointHint": result.checkpoint_hint,
            "fallbackStage": result.fallback_stage,
            "issues": list(result.issues),
            "nextStage": next_stage or "",
        },
        handoff_to=result.fallback_stage or (next_stage or stage_name),
        evidence={
            "kind": kind,
            "completed": result.status == "done",
            "issueCount": len(result.issues),
        },
        summary={
            "taskId": ctx.task_id,
            "batchId": ctx.batch_id,
            "stage": stage_name,
            "status": result.status,
            "message": result.message,
        },
    )
    return write_packet(batch_workflow_packet_path(ctx.task_id, ctx.batch_id, stage_name), packet)


def _state_path(task_id: str, batch_id: str) -> Path:
    from _common.paths import batch_workflow_state_path
    return batch_workflow_state_path(task_id, batch_id)


def load_workflow_state(task_id: str, batch_id: str) -> dict:
    p = _state_path(task_id, batch_id)
    if p.exists():
        return read_json(p)
    return {
        "schemaVersion": WORKFLOW_STATE_VERSION,
        "taskId": task_id,
        "batchId": batch_id,
        "completed": [],
        "waitingCheckpoint": None,
        "status": "queued",
        "owner": None,
        "heartbeatAt": None,
        "retryCounts": {},
        "infrastructureRetryCounts": {},
        "failedObjects": [],
        "abandonedObjects": [],
        "nextAction": None,
        "updatedAt": store.now_iso(),
    }


def save_workflow_state(state: dict) -> Path:
    state["updatedAt"] = store.now_iso()
    p = _state_path(state["taskId"], state["batchId"])
    p.parent.mkdir(parents=True, exist_ok=True)
    write_json(p, state)
    return p
