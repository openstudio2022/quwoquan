"""workflow run — 无人值守任务编排器（DAG 薄编排壳，目标① 全流程自动化）。

把零散的 download/build/plan/produce/review/publish 串成固定 DAG，运营只在入口
(task.yaml) 与出口(抽检)介入，中间不再逐步手敲 10+ 条 CLI。

设计原则（与 13-coding-discipline R24 抽象克制一致）：
- 薄编排：不重写任何 stage 逻辑，只按 DAG 顺序调用既有 handler / 既有薄函数。
- 双类节点：
  * 确定性节点(deterministic)：CLI 直接跑（download fetch / build validate /
    produce review --materialize / publish）。
  * Agent checkpoint：写 assistant_tasks 清单 + 暂停，输出明确指引；Agent 物化产物
    后用 `workflow run --resume` 继续。这是「Agent 会话创作 = 自动化执行者」的接缝，
    不是人手工断点。
- 可 resume：workflow 状态落 runtime/tasks/<taskId>/batches/<batch>/task_workflow_state.json，
  记录已完成 stage、当前等待的 checkpoint、ReAct 回退指针与 baseline 冻结件。

DAG（stage 序）：
  download_plan(checkpoint:Agent 写 source_plan)
  -> download_fetch(auto)
  -> build_prepare(auto 下发主页契约) -> build_homepage(checkpoint:Agent 写 page 三件套)
  -> build_validate(auto 采纳门)
  -> content_plan(checkpoint:Agent 证据驱动篇目+注册+brief)
  -> produce_plan(auto 校验 brief 或 legacy 每实体 brief)
  -> produce_compose(auto compose-brief) -> produce_author(checkpoint:Agent 写 article)
  -> produce_annotate(auto) -> produce_review(auto review+media gate --materialize)
  -> publish(auto)
"""
from __future__ import annotations

import argparse
import copy
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import tempfile
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from _common.entity_extract import require_domain_etype
from _common.io import read_json, write_json
from _common.source_plan_contract import source_plan_rule_signature
from _common.paths import (
    batch_root,
    batch_workflow_packet_path,
    task_baseline_freeze_packet_path,
    ensure_batch_layout,
    release_root,
)
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


MANAGED_LANE_LIMITS = _parse_managed_lane_limits(os.environ.get("QWQ_MANAGED_LANE_LIMITS"))
MANAGED_AGENT_TIMEOUT_SECONDS = max(
    60, int(os.environ.get("QWQ_MANAGED_AGENT_TIMEOUT_SECONDS", "240"))
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
MANAGED_LOCAL_CURSOR_MAX_WORKERS = max(
    1, int(os.environ.get("QWQ_MANAGED_LOCAL_CURSOR_MAX_WORKERS", "1"))
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
    model: str = "composer-2.5"
    release_only: bool = False
    agent_runner: Callable[[str], dict[str, Any]] | None = None


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


def _abandoned_entity_ids(state: Mapping[str, Any]) -> set[str]:
    out: set[str] = set()
    for item in state.get("abandonedObjects") or []:
        if not isinstance(item, Mapping):
            continue
        entity = str(item.get("entityId") or item.get("entity") or "").strip()
        if entity:
            out.add(entity)
    return out


def _abandoned_content_refs(state: Mapping[str, Any]) -> set[str]:
    out: set[str] = set()
    for item in state.get("abandonedContentObjects") or []:
        if not isinstance(item, Mapping):
            continue
        status = str(item.get("status") or "").strip()
        if status and status != "abandoned":
            continue
        ref = str(item.get("ref") or "").strip()
        if ref:
            out.add(ref)
    return out


def _active_replacement_rows(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in state.get("replacementObjects") or []:
        if not isinstance(item, Mapping):
            continue
        if str(item.get("status") or "active") != "active":
            continue
        entity_id = str(item.get("entityId") or "").strip()
        if not entity_id or entity_id in seen:
            continue
        rows.append(dict(item))
        seen.add(entity_id)
    return rows


def _replacement_entity_ids(state: Mapping[str, Any]) -> set[str]:
    ids: set[str] = set()
    for item in state.get("replacementObjects") or []:
        if not isinstance(item, Mapping):
            continue
        entity_id = str(item.get("entityId") or "").strip()
        if entity_id:
            ids.add(entity_id)
    return ids


def _next_replacement_candidates(ctx: PipelineContext, *, needed: int) -> list[dict[str, str]]:
    state = load_workflow_state(ctx.task_id, ctx.batch_id)
    abandoned = _abandoned_entity_ids(state)
    scope = ctx.spec.get("scope") or {}
    reserve_targets = [
        target for target in (scope.get("reserveCoverageTargets") or [])
        if isinstance(target, Mapping) and str(target.get("name") or "").strip()
    ]
    used = set(ctx.entity_ids) | abandoned | _replacement_entity_ids(state)
    candidates: list[dict[str, str]] = []
    for target in reserve_targets:
        if len(candidates) >= max(1, int(needed or 1)):
            break
        entity_id = str(target.get("name") or "").strip()
        if not entity_id or entity_id in used:
            continue
        candidates.append(
            {
                "entityId": entity_id,
                "entityType": str(target.get("entityType") or _coverage_entity_type(ctx.spec)).strip(),
            }
        )
        used.add(entity_id)
    return candidates


def _append_replacement_row(
    ctx: PipelineContext,
    *,
    entity_id: str,
    entity_type: str,
    status: str,
    reason: str,
    source_gate_status: str = "",
    issues: list[str] | None = None,
) -> None:
    state = load_workflow_state(ctx.task_id, ctx.batch_id)
    rows = list(state.get("replacementObjects") or [])
    existing_index = None
    for index, row in enumerate(rows):
        if isinstance(row, Mapping) and str(row.get("entityId") or "").strip() == entity_id:
            existing_index = index
            break
    row = {
        "entityId": entity_id,
        "entityType": entity_type,
        "status": status,
        "reason": reason,
        "activatedAt": store.now_iso() if status == "active" else "",
        "screenedAt": store.now_iso(),
    }
    if source_gate_status:
        row["sourceGateStatus"] = source_gate_status
    if issues:
        row["issues"] = list(issues)
    if existing_index is None:
        rows.append(row)
    else:
        rows[existing_index] = {**dict(rows[existing_index]), **row}
    state["replacementObjects"] = rows
    save_workflow_state(state)


def _activate_replacement_targets(ctx: PipelineContext, *, reason: str) -> list[str]:
    """Promote reserve coverage targets so partial trials keep target count stable."""
    state = load_workflow_state(ctx.task_id, ctx.batch_id)
    abandoned = _abandoned_entity_ids(state)
    scope = ctx.spec.get("scope") or {}
    primary_targets = [
        target for target in (scope.get("coverageTargets") or [])
        if isinstance(target, Mapping) and str(target.get("name") or "").strip()
    ]
    reserve_targets = [
        target for target in (scope.get("reserveCoverageTargets") or [])
        if isinstance(target, Mapping) and str(target.get("name") or "").strip()
    ]
    min_entities = int((ctx.spec.get("acceptance") or {}).get("minEntities") or len(primary_targets))
    active_names = [
        str(target.get("name") or "").strip()
        for target in primary_targets
        if str(target.get("name") or "").strip() not in abandoned
    ]
    replacement_rows = list(state.get("replacementObjects") or [])
    for row in _active_replacement_rows(state):
        entity_id = str(row.get("entityId") or "").strip()
        if entity_id and entity_id not in abandoned and entity_id not in active_names:
            active_names.append(entity_id)
    used = set(active_names) | abandoned | _replacement_entity_ids(state)
    added: list[str] = []
    for target in reserve_targets:
        if len(active_names) >= min_entities:
            break
        entity_id = str(target.get("name") or "").strip()
        if not entity_id or entity_id in used:
            continue
        etype = str(target.get("entityType") or _coverage_entity_type(ctx.spec)).strip()
        replacement_rows.append(
            {
                "entityId": entity_id,
                "entityType": etype,
                "status": "active",
                "reason": reason,
                "sourceGateStatus": "legacy_activation",
                "activatedAt": store.now_iso(),
            }
        )
        active_names.append(entity_id)
        used.add(entity_id)
        added.append(entity_id)
    if added:
        state["replacementObjects"] = replacement_rows
        state["replacementPolicy"] = {
            "mode": "partial_with_replacement_report",
            "minEntities": min_entities,
            "activeTargetCount": len(active_names),
            "reserveTargetCount": len(reserve_targets),
        }
        state["nextAction"] = f"activated replacement targets: {', '.join(added[:8])}"
        save_workflow_state(state)
    ctx.entity_ids = active_names
    return added


def mark_abandoned_entities(
    task_id: str,
    batch_id: str,
    entities: list[str],
    *,
    stage: str,
    reason: str,
) -> dict[str, Any]:
    """Mark deterministic fast-fail entities without blocking the batch."""
    state = load_workflow_state(task_id, batch_id)
    existing = {
        str(item.get("entityId") or "")
        for item in state.get("abandonedObjects") or []
        if isinstance(item, Mapping)
    }
    added: list[str] = []
    rows = list(state.get("abandonedObjects") or [])
    for entity in entities:
        name = str(entity or "").strip()
        if not name or name in existing:
            continue
        rows.append(
            {
                "entityId": name,
                "stage": str(stage or ""),
                "reason": str(reason or "abandoned"),
                "status": "abandoned",
                "abandonedAt": store.now_iso(),
            }
        )
        existing.add(name)
        added.append(name)
    state["abandonedObjects"] = rows
    if added:
        state["nextAction"] = f"continue without abandoned entities: {', '.join(added[:8])}"
        state["status"] = "repairing"
        state["failedObjects"] = [
            item for item in (state.get("failedObjects") or [])
            if not any(entity in str(item) for entity in added)
            and "interrupted" not in str(item).lower()
        ]
        infra = dict(state.get("infrastructureRetryCounts") or {})
        if stage:
            infra.pop(str(stage), None)
        state["infrastructureRetryCounts"] = infra
    save_workflow_state(state)
    return {"added": added, "abandonedObjects": rows}


def _workflow_allows_partial_content(ctx: PipelineContext) -> bool:
    from _common.content_plan import allow_partial_content

    return allow_partial_content(_active_spec(ctx))


def _replacement_capacity_for_abandon(ctx: PipelineContext) -> tuple[int, int, int, bool]:
    state = load_workflow_state(ctx.task_id, ctx.batch_id)
    abandoned = _abandoned_entity_ids(state)
    active_entities = [entity for entity in ctx.entity_ids if entity not in abandoned]
    scope = ctx.spec.get("scope") if isinstance(ctx.spec.get("scope"), Mapping) else {}
    reserve_names = {
        str(target.get("name") or "").strip()
        for target in (scope.get("reserveCoverageTargets") or [])
        if isinstance(target, Mapping) and str(target.get("name") or "").strip()
    }
    used_names = set(active_entities) | abandoned
    used_names.update(_replacement_entity_ids(state))
    acceptance = ctx.spec.get("acceptance") if isinstance(ctx.spec.get("acceptance"), Mapping) else {}
    try:
        min_entities = int((acceptance or {}).get("minEntities") or 0)
    except (TypeError, ValueError):
        min_entities = 0
    policy = ctx.spec.get("workflowPolicy") if isinstance(ctx.spec.get("workflowPolicy"), Mapping) else {}
    requires_replacement = (
        str((policy or {}).get("deliveryMode") or "") == "partial_with_replacement_report"
        or min_entities >= len(active_entities)
    )
    return len(reserve_names - used_names), len(active_entities), min_entities, requires_replacement


def _selection_entity_name(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("地点/") and "/" in text:
        return text.rsplit("/", 1)[-1].strip()
    return text


def _reserve_top_up_count(needed: int) -> int:
    try:
        configured = int(os.environ.get("QWQ_WORKFLOW_RESERVE_TOP_UP_MIN") or 40)
    except ValueError:
        configured = 40
    return max(max(0, needed), max(1, configured))


def _top_up_reserve_targets_from_discovery(ctx: PipelineContext, *, needed: int) -> list[str]:
    """Extend reserveCoverageTargets from the original discovery pool.

    Large partial trials should not stall merely because the first deterministic
    reserve slice was too shallow. The source of truth remains the committed task
    selection report: if it records a discoveryPath, we can deterministically add
    the next unused candidates to the reserve pool and let the normal replacement
    gate continue to decide which targets are usable.
    """

    if needed <= 0:
        return []
    report_path = store.committed_task_root(ctx.task_id) / "_shared" / "target_selection.json"
    if not report_path.is_file():
        return []
    try:
        report = read_json(report_path)
    except Exception:  # noqa: BLE001
        return []
    discovery_ref = str(report.get("discoveryPath") or "").strip()
    if not discovery_ref:
        return []
    discovery_path = Path(discovery_ref)
    if not discovery_path.is_absolute():
        discovery_path = Path.cwd() / discovery_path
    if not discovery_path.is_file():
        return []
    try:
        from task.target_selection import (
            _leaf_selection_name,
            _load_partitions,
            _ordered_partition_leaves,
        )
    except Exception:  # noqa: BLE001
        return []
    try:
        partitions = _load_partitions(discovery_path)
    except Exception:  # noqa: BLE001
        return []

    raw_spec = store.load_raw_spec(ctx.task_id)
    scope = raw_spec.setdefault("scope", {})
    reserve_targets = scope.setdefault("reserveCoverageTargets", [])
    if not isinstance(reserve_targets, list):
        reserve_targets = []
        scope["reserveCoverageTargets"] = reserve_targets
    state = load_workflow_state(ctx.task_id, ctx.batch_id)
    used: set[str] = set()
    for target in (scope.get("coverageTargets") or []):
        if isinstance(target, Mapping):
            used.add(_selection_entity_name(target.get("name")))
    for target in reserve_targets:
        if isinstance(target, Mapping):
            used.add(_selection_entity_name(target.get("name")))
    used.update(_selection_entity_name(item) for item in _abandoned_entity_ids(state))
    for row in _active_replacement_rows(state):
        used.add(_selection_entity_name(row.get("entityId")))

    added_rows: list[dict[str, str]] = []
    target_count = _reserve_top_up_count(needed)
    for part in partitions:
        region = str(part.get("key") or "").strip()
        for leaf in _ordered_partition_leaves(part):
            name = _selection_entity_name(_leaf_selection_name(leaf))
            if not name or name in used:
                continue
            row = {
                "entityType": str(leaf.get("entityType") or _coverage_entity_type(ctx.spec) or "地点/景区"),
                "name": name,
            }
            if region:
                row["region"] = region
            reserve_targets.append(row)
            added_rows.append(row)
            used.add(name)
            if len(added_rows) >= target_count:
                break
        if len(added_rows) >= target_count:
            break
    if not added_rows:
        return []

    store.save_spec(raw_spec)
    ctx.spec = store.load_spec(ctx.task_id)
    added_names = [row["name"] for row in added_rows]
    top_ups = report.get("reserveTopUps") if isinstance(report.get("reserveTopUps"), list) else []
    top_ups.append(
        {
            "batchId": ctx.batch_id,
            "addedAt": store.now_iso(),
            "needed": needed,
            "addedCount": len(added_names),
            "targets": added_rows,
        }
    )
    report["reserveTopUps"] = top_ups
    write_json(report_path, report)
    state = load_workflow_state(ctx.task_id, ctx.batch_id)
    state["nextAction"] = f"reserve top-up added {len(added_names)} target(s)"
    save_workflow_state(state)
    return added_names


def _workflow_allows_content_quota_shortfall(ctx: PipelineContext) -> bool:
    from _common.content_plan import allow_content_quota_shortfall

    return allow_content_quota_shortfall(_active_spec(ctx))


def mark_abandoned_content_refs(
    task_id: str,
    batch_id: str,
    refs: list[str],
    *,
    stage: str,
    reason: str,
) -> dict[str, Any]:
    """Mark deterministic fast-fail content refs without blocking the batch."""
    state = load_workflow_state(task_id, batch_id)
    existing = {
        str(item.get("ref") or "")
        for item in state.get("abandonedContentObjects") or []
        if isinstance(item, Mapping)
    }
    rows = list(state.get("abandonedContentObjects") or [])
    added: list[str] = []
    for ref in refs:
        value = str(ref or "").strip()
        if not value or value in existing:
            continue
        rows.append(
            {
                "ref": value,
                "stage": str(stage or ""),
                "reason": str(reason or "abandoned"),
                "status": "abandoned",
                "abandonedAt": store.now_iso(),
            }
        )
        existing.add(value)
        added.append(value)
    state["abandonedContentObjects"] = rows
    if added:
        state["nextAction"] = f"continue without abandoned content refs: {', '.join(added[:8])}"
        state["status"] = "repairing"
        state["failedObjects"] = [
            item for item in (state.get("failedObjects") or [])
            if not any(ref in str(item) for ref in added)
        ]
        infra = dict(state.get("infrastructureRetryCounts") or {})
        if stage:
            infra.pop(str(stage), None)
        state["infrastructureRetryCounts"] = infra
    save_workflow_state(state)
    return {"added": added, "abandonedContentObjects": rows}


def reset_stage_retries(
    task_id: str,
    batch_id: str,
    *,
    stage: str,
    reason: str,
) -> dict[str, Any]:
    """Clear retry ledgers for an operator-confirmed infrastructure recovery."""
    stage_name = str(stage or "").strip()
    if stage_name not in STAGE_NAMES:
        raise ValueError(f"unknown workflow stage: {stage_name}")
    state = load_workflow_state(task_id, batch_id)
    retry_counts = dict(state.get("retryCounts") or {})
    infra_counts = dict(state.get("infrastructureRetryCounts") or {})
    react_rewinds = dict(state.get("reactRewinds") or {})
    completed_before = set(state.get("completed") or [])
    tail_stages = set(STAGE_NAMES[STAGE_NAMES.index(stage_name):])
    was_waiting_for_stage = str(state.get("waitingCheckpoint") or "") == stage_name
    previous = {
        "retryCount": retry_counts.pop(stage_name, None),
        "infrastructureRetryCount": infra_counts.pop(stage_name, None),
        "reactRewindCount": react_rewinds.get(stage_name),
        "completed": sorted(completed_before),
        "status": state.get("status"),
        "failedObjects": list(state.get("failedObjects") or []),
    }
    for name in list(retry_counts):
        if name in tail_stages:
            retry_counts.pop(name, None)
    for name in list(infra_counts):
        if name in tail_stages:
            infra_counts.pop(name, None)
    for name in list(react_rewinds):
        if name in tail_stages:
            react_rewinds.pop(name, None)
    state["retryCounts"] = retry_counts
    state["infrastructureRetryCounts"] = infra_counts
    state["reactRewinds"] = react_rewinds
    rewound_completed = _rewind_to(completed_before, stage_name)
    state["completed"] = [name for name in STAGE_NAMES if name in rewound_completed]
    state["waitingCheckpoint"] = None
    state["failedObjects"] = []
    if was_waiting_for_stage:
        state["status"] = "waiting_agent"
        state["waitingCheckpoint"] = stage_name
        state["nextAction"] = f"retry {stage_name}: {reason or 'operator requested retry'}"
    else:
        state["status"] = "repairing"
        state["nextAction"] = f"rewind to {stage_name}: {reason or 'operator requested retry'}"
    recoveries = list(state.get("recoveryActions") or [])
    recoveries.append(
        {
            "stage": stage_name,
            "reason": str(reason or "operator requested retry"),
            "previous": previous,
            "recoveredAt": store.now_iso(),
        }
    )
    state["recoveryActions"] = recoveries
    save_workflow_state(state)
    return {
        "stage": stage_name,
        "previous": previous,
        "retryCounts": state.get("retryCounts") or {},
        "infrastructureRetryCounts": state.get("infrastructureRetryCounts") or {},
        "reactRewinds": state.get("reactRewinds") or {},
        "completed": state.get("completed") or [],
        "status": state.get("status"),
        "nextAction": state.get("nextAction"),
    }


def _apply_abandoned_entities(
    ctx: PipelineContext,
    state: Mapping[str, Any],
    *,
    activate_replacements: bool = True,
) -> list[str]:
    abandoned = _abandoned_entity_ids(state)
    original = list(ctx.entity_ids)
    active = [entity for entity in original if entity not in abandoned]
    replacement_rows = _active_replacement_rows(state)
    for row in replacement_rows:
        entity_id = str(row.get("entityId") or "").strip()
        if entity_id and entity_id not in abandoned and entity_id not in active:
            active.append(entity_id)
    ctx.entity_ids = active
    if activate_replacements:
        _activate_replacement_targets(ctx, reason="keep target count after abandoned source-unavailable entity")
    return [entity for entity in original if entity in abandoned]


def _clear_manual_repair_rewind_if_resuming(task_id: str, batch_id: str) -> None:
    """Allow a manually repaired failed stage to be re-evaluated once."""
    state = load_workflow_state(task_id, batch_id)
    if str(state.get("status") or "") != "manual_required":
        return
    stage = str(state.get("lastFailedStage") or "").strip()
    if not stage:
        return
    rewinds = dict(state.get("reactRewinds") or {})
    if stage not in rewinds:
        return
    previous = int(rewinds.pop(stage) or 0)
    state["reactRewinds"] = rewinds
    resumes = list(state.get("manualRepairResumes") or [])
    resumes.append(
        {
            "stage": stage,
            "clearedReactRewinds": previous,
            "resumedAt": store.now_iso(),
        }
    )
    state["manualRepairResumes"] = resumes[-20:]
    state["nextAction"] = f"manual repair resume: revalidate {stage}"
    state["heartbeatAt"] = store.now_iso()
    save_workflow_state(state)
    print(
        f"[task run] manual repair resume: cleared react rewind budget for {stage} "
        f"(previous={previous})",
        flush=True,
    )


def _active_spec(ctx: PipelineContext) -> dict[str, Any]:
    spec = copy.deepcopy(ctx.spec)
    scope = spec.setdefault("scope", {})
    state = load_workflow_state(ctx.task_id, ctx.batch_id)
    active = set(ctx.entity_ids) - _abandoned_entity_ids(state)
    rows = [
        target for target in (scope.get("coverageTargets") or [])
        if str(target.get("name") or "").strip() in active
    ]
    existing = {str(target.get("name") or "").strip() for target in rows}
    for target in (scope.get("reserveCoverageTargets") or []):
        if not isinstance(target, Mapping):
            continue
        name = str(target.get("name") or "").strip()
        if name and name in active and name not in existing:
            rows.append(dict(target))
            existing.add(name)
    scope["coverageTargets"] = rows
    acceptance = spec.setdefault("acceptance", {})
    if "minEntities" in acceptance:
        acceptance["minEntities"] = min(int(acceptance.get("minEntities") or 0), len(active))
    return spec


def _load_baseline_packet(task_id: str, packet_path: Path | None = None) -> tuple[Path, dict]:
    path = packet_path or task_baseline_freeze_packet_path(task_id)
    if not path.is_file():
        raise RuntimeError(
            f"missing baseline freeze packet: {path}. "
            f"Run `qwq-data data baseline --task {task_id}` first."
        )
    packet = read_json(path)
    if not isinstance(packet, dict):
        raise RuntimeError(f"baseline freeze packet unreadable: {path}")
    if str(packet.get("taskId") or "").strip() != task_id:
        raise RuntimeError(
            f"baseline freeze packet taskId mismatch: {packet.get('taskId')} != {task_id}"
        )
    if str(packet.get("command") or "").strip() != "data baseline":
        raise RuntimeError(f"baseline freeze packet command mismatch: {packet.get('command')}")
    return path, packet


# ─── coverage 实体解析（download/build 的输入）────────────────────────
def _coverage_entity_ids(spec: dict) -> list[str]:
    out: list[str] = []
    for target in (spec.get("scope") or {}).get("coverageTargets") or []:
        name = str(target.get("name") or "").strip()
        if name:
            out.append(name)
    return out


# ─── checkpoint 完成度探测（resume 判定 Agent 是否已物化产物）──────────
def _coverage_entity_type(spec: dict) -> str:
    """coverageTargets/entityTypes 的唯一类型真相源；显式任务必须给出明确类型。"""
    scope = spec.get("scope") or {}
    targets = scope.get("coverageTargets") or []
    target_types = {
        str(target.get("entityType") or "").strip()
        for target in targets
        if str(target.get("entityType") or "").strip()
    }
    if len(target_types) > 1:
        raise ValueError(
            "workflow currently requires a single entityType across coverageTargets; "
            f"got {sorted(target_types)}"
        )
    if target_types:
        only = next(iter(target_types))
        require_domain_etype(only, context="scope.coverageTargets[].entityType")
        return only
    types = [str(item).strip() for item in (scope.get("entityTypes") or []) if str(item).strip()]
    if not types:
        return ""
    require_domain_etype(types[0], context="scope.entityTypes[0]")
    return types[0]


def _declared_pixel_issue(image: dict, *, asset_id: str) -> str | None:
    """Validate declared dimensions exactly as provided by the research plan."""
    from _common.image_rules import pixel_size_issue

    raw_width = str(image.get("width") or "").strip()
    raw_height = str(image.get("height") or "").strip()
    if not raw_width and not raw_height:
        return None
    try:
        width = int(float(raw_width or "0"))
        height = int(float(raw_height or "0"))
    except ValueError:
        return f"imagePixels: {asset_id} 像素尺寸字段不可解析 width={raw_width!r} height={raw_height!r}"
    return pixel_size_issue(width, height, asset_id=asset_id)


def _planned_pixel_issue(image: dict, *, asset_id: str) -> str | None:
    """Validate declared dimensions when the research plan provides them."""
    issue = _declared_pixel_issue(image, asset_id=asset_id)
    if issue:
        try:
            from download.fetch import candidate_image_urls

            if len(candidate_image_urls(str(image.get("url") or ""))) > 1:
                return None
        except Exception:  # noqa: BLE001
            pass
    return issue


def _image_repair_hint(
    image: dict,
    *,
    lane: str,
    entity_id: str,
    asset_id: str,
    source_id: str = "",
    image_index: int = 0,
) -> dict[str, Any] | None:
    issue = _declared_pixel_issue(image, asset_id=asset_id)
    if not issue:
        return None
    try:
        from download.fetch import candidate_image_urls

        candidates = candidate_image_urls(str(image.get("url") or ""))
    except Exception:  # noqa: BLE001
        candidates = [str(image.get("url") or "")]
    high_res_candidate = candidates[1] if len(candidates) > 1 else ""
    return {
        "lane": lane,
        "entityId": entity_id,
        "sourceId": source_id,
        "imageIndex": image_index,
        "assetId": asset_id,
        "url": str(image.get("url") or ""),
        "width": image.get("width") or "",
        "height": image.get("height") or "",
        "issue": issue,
        "sameSourceHighResCandidate": high_res_candidate,
        "candidateUrls": candidates[:3],
        "action": (
            "retry_with_same_source_high_resolution_url"
            if high_res_candidate
            else "replace_image_or_source_unit"
        ),
    }


def _image_rights_repair_hint(
    image: dict[str, Any],
    issues: list[str],
    *,
    lane: str,
    entity_id: str,
    asset_id: str,
    source_id: str = "",
    image_index: int = 0,
) -> dict[str, Any] | None:
    if not issues:
        return None
    issue_text = "; ".join(str(issue) for issue in issues)
    license_value = str(image.get("license") or "").strip()
    action = "replace_image_or_source_unit_with_explicit_publishable_image_rights"
    if license_value in {"factual_reference_only", "licensed_adaptation", "blocked"}:
        action = "replace_image_or_source_unit_do_not_use_sourceUseMode_as_image_license"
    return {
        "lane": lane,
        "entityId": entity_id,
        "sourceId": source_id,
        "imageIndex": image_index,
        "assetId": asset_id,
        "url": str(image.get("url") or ""),
        "width": image.get("width") or "",
        "height": image.get("height") or "",
        "issue": issue_text,
        "sameSourceHighResCandidate": "",
        "candidateUrls": [str(image.get("url") or "")] if str(image.get("url") or "") else [],
        "action": action,
    }


def _research_image_repair_hints(
    ctx: PipelineContext,
    entity_id: str,
    etype: str,
) -> list[dict[str, Any]]:
    """Return actionable image-resolution repair hints for the research lanes."""
    from download.source_inputs import curated_images_for_entity, curated_sources_for_entity
    from vertical.license import validate_image_rights

    hints: list[dict[str, Any]] = []
    for lane in ("homepage", "article"):
        for source in curated_sources_for_entity(
            ctx.task_id,
            ctx.batch_id,
            entity_id,
            etype,
            research_lane=lane,
        ):
            source_id = str(source.get("source_id") or "")
            for index, image in enumerate(source.get("imageUrls") or [], start=1):
                rights_hint = _image_rights_repair_hint(
                    image,
                    validate_image_rights(
                        image,
                        vertical=str(ctx.spec.get("vertical") or "travel"),
                    ),
                    lane=lane,
                    entity_id=entity_id,
                    source_id=source_id,
                    image_index=index,
                    asset_id=f"{entity_id}/{source_id}#{index}",
                )
                if rights_hint:
                    hints.append(rights_hint)
                hint = _image_repair_hint(
                    image,
                    lane=lane,
                    entity_id=entity_id,
                    source_id=source_id,
                    image_index=index,
                    asset_id=f"{entity_id}/{source_id}#{index}",
                )
                if hint:
                    hints.append(hint)
    for index, image in enumerate(
        [
            item
            for item in curated_images_for_entity(ctx.task_id, ctx.batch_id, entity_id, etype)
            if str(item.get("researchLane") or "image") == "image"
        ],
        start=1,
    ):
        rights_hint = _image_rights_repair_hint(
            image,
            validate_image_rights(
                image,
                vertical=str(ctx.spec.get("vertical") or "travel"),
            ),
            lane="image",
            entity_id=entity_id,
            source_id=str(image.get("sourceCollectionId") or ""),
            image_index=index,
            asset_id=f"{entity_id}/image#{index}",
        )
        if rights_hint:
            hints.append(rights_hint)
        hint = _image_repair_hint(
            image,
            lane="image",
            entity_id=entity_id,
            source_id=str(image.get("sourceCollectionId") or ""),
            image_index=index,
            asset_id=f"{entity_id}/image#{index}",
        )
        if hint:
            hints.append(hint)
    return hints


def _download_diagnostic_image_repair_hints(
    diagnostics: dict[str, Any],
    *,
    entity_id: str,
) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    for index, raw in enumerate(diagnostics.get("sampleRejected") or [], start=1):
        text = str(raw or "")
        if not text:
            continue
        source_id = ""
        url = ""
        source_match = re.search(r"sourceImage:([^:\s]+):", text)
        if source_match:
            source_id = source_match.group(1)
        url_match = re.search(r"\((https?://[^)]+)\)", text)
        if url_match:
            url = url_match.group(1)
        if source_id.startswith("article") or "article" in text:
            lane = "article"
        elif source_id.startswith("home") or "homepage" in text or "主页" in text:
            lane = "homepage"
        else:
            lane = "image"
        action = "replace_image_or_source_unit"
        if "imageSafety" in text or "watermark" in text:
            action = "replace_unsafe_or_watermarked_image"
        elif "imageFetch" in text or "non-image" in text or "too small" in text:
            action = "replace_unfetchable_or_low_quality_image"
        hints.append(
            {
                "lane": lane,
                "entityId": entity_id,
                "sourceId": source_id,
                "imageIndex": index,
                "assetId": f"{entity_id}/{source_id or 'rejected'}#{index}",
                "url": url,
                "width": "",
                "height": "",
                "issue": text,
                "sameSourceHighResCandidate": "",
                "candidateUrls": [url] if url else [],
                "action": action,
            }
        )
    return hints


def _download_issue_repair_hints(
    issues: list[str],
    *,
    entity_id: str,
) -> list[dict[str, Any]]:
    hints: list[dict[str, Any]] = []
    for index, raw in enumerate(issues, start=1):
        text = str(raw or "")
        if not text:
            continue
        lane = ""
        action = ""
        category_lane = _download_source_category_issue_lane(text)
        if category_lane == "homepage":
            lane = "homepage"
            action = "add_or_replace_homepage_encyclopedia_or_official_seed_source"
        elif category_lane == "article":
            lane = "article"
            action = "add_or_replace_article_text_sources_with_fetchable_quality_evidence"
        elif (
            "text-qualified base sources" in text
            or "article base sources" in text
            or "article sources" in text
            or "文章" in text
        ):
            lane = "article"
            action = "add_or_replace_article_text_sources_with_fetchable_quality_evidence"
        elif (
            "unique publishable image" in text
            or "imageCount" in text
            or "imageFetch" in text
            or "未下到真实图片" in text
            or "合格去重图" in text
            or "source collection" in text
            or "image gates failed" in text
            or "image_fetch_gate" in text
            or "image_rights_gate" in text
            or "图片作品" in text
        ):
            lane = "image"
            action = "add_or_replace_image_source_collections_with_complete_rights"
        elif "homepage" in text or "主页" in text:
            lane = "homepage"
            action = "add_or_replace_homepage_source_images_with_complete_rights"
        if not lane:
            continue
        hints.append(
            {
                "lane": lane,
                "entityId": entity_id,
                "sourceId": "",
                "imageIndex": index,
                "assetId": f"{entity_id}/download_repair#{index}",
                "url": "",
                "width": "",
                "height": "",
                "issue": text,
                "sameSourceHighResCandidate": "",
                "candidateUrls": [],
                "action": action,
            }
        )
    return hints


def _download_repair_lanes(repair: dict[str, Any]) -> set[str]:
    issue_text = " ".join(str(item) for item in (repair.get("issues") or []))
    lanes: set[str] = set()
    category_lane = _download_source_category_issue_lane(issue_text)
    if category_lane:
        lanes.add(category_lane)
    if "article" in issue_text or "文章" in issue_text or "source unit(s) with images" in issue_text:
        lanes.add("article")
    if "homepage" in issue_text or "主页" in issue_text:
        lanes.add("homepage")
    if (
        "image research" in issue_text
        or "imageCount" in issue_text
        or "imageFetch" in issue_text
        or "未下到真实图片" in issue_text
        or "合格去重图" in issue_text
        or "publishable image" in issue_text
        or "sourceCollection" in issue_text
        or "image gates failed" in issue_text
        or "image_fetch_gate" in issue_text
        or "image_rights_gate" in issue_text
        or "图片作品" in issue_text
    ):
        lanes.add("image")
    research_issues = repair.get("researchLaneIssues") or {}
    if isinstance(research_issues, dict):
        lanes.update(
            lane for lane, lane_issues in research_issues.items()
            if lane in {"homepage", "article", "image"} and lane_issues
        )
    if lanes:
        return lanes
    for hint in repair.get("imageRepairHints") or []:
        if isinstance(hint, dict) and str(hint.get("lane") or "") in {"homepage", "article", "image"}:
            lanes.add(str(hint.get("lane")))
    return lanes


def _source_plan_filled(
    ctx: PipelineContext,
    *,
    include_download_repair: bool = True,
) -> tuple[bool, list[str]]:
    """Research checkpoint: validate three isolated modality plans."""
    from download.gate import download_requirements
    from download.source_inputs import (
        curated_images_for_entity,
        curated_sources_for_entity,
        source_plan_rights_issues,
    )
    from _common.image_rules import relevance_issue
    from vertical.license import validate_image_rights

    etype = _coverage_entity_type(ctx.spec)
    from _common.source_catalog import platform_category
    from _common.source_unit import resolve_entity_object_dir

    requirements = download_requirements(ctx.task_id)
    separated_research = str((ctx.spec.get("content") or {}).get("modalityContract") or "") == "separated_research"
    missing: list[str] = []
    abandoned = _abandoned_entity_ids(load_workflow_state(ctx.task_id, ctx.batch_id))
    for eid in ctx.entity_ids:
        if eid in abandoned:
            continue
        obj = resolve_entity_object_dir(ctx.task_id, ctx.batch_id, eid, etype_hint=etype)
        lane_files = {
            lane: obj / "1.download" / f"{lane}_source_plan.json"
            for lane in ("homepage", "article", "image")
        }
        legacy_plan = obj / "1.download" / "source_plan.json"
        has_lane_contract = separated_research or (
            any(path.is_file() for path in lane_files.values())
            and not legacy_plan.is_file()
        )
        if has_lane_contract:
            lane_issues: list[str] = []
            homepage_sources = curated_sources_for_entity(
                ctx.task_id, ctx.batch_id, eid, etype, research_lane="homepage"
            )
            article_sources = curated_sources_for_entity(
                ctx.task_id, ctx.batch_id, eid, etype, research_lane="article"
            )
            images = curated_images_for_entity(ctx.task_id, ctx.batch_id, eid, etype)
            work_images = [
                image for image in images
                if str(image.get("researchLane") or "image") == "image"
            ]
            min_homepage_sources = max(1, int(requirements.get("minHomepageSources") or 0))
            if len(homepage_sources) < min_homepage_sources:
                lane_issues.append(
                    f"homepage sources={len(homepage_sources)} need>={min_homepage_sources}"
                )
            homepage_categories = {
                str(source.get("category") or "") or platform_category(str(source.get("platform") or ""))
                for source in homepage_sources
            }
            if not ({"encyclopedia", "official"} & homepage_categories):
                lane_issues.append("homepage research needs encyclopedia or official evidence")
            for source in homepage_sources:
                category = str(source.get("category") or "") or platform_category(str(source.get("platform") or ""))
                if category in {"travelogue", "guidebook", "review"}:
                    lane_issues.append(
                        f"homepage source {source.get('source_id')}: "
                        f"entity homepage cannot use author/guide/review source category {category}"
                    )
            min_article_sources = int(requirements.get("minArticleBaseSources") or requirements["minSources"])
            if len(article_sources) < min_article_sources:
                lane_issues.append(
                    f"article sources={len(article_sources)} need>={min_article_sources}"
                )
            for source in article_sources:
                for img_index, image in enumerate(source.get("imageUrls") or [], start=1):
                    lane_issues.extend(
                        f"article source {source.get('source_id')} image[{img_index}]: {issue}"
                        for issue in validate_image_rights(
                            image, vertical=str(ctx.spec.get("vertical") or "travel")
                        )
                    )
                    relevance = str(image.get("relevance") or image.get("caption") or "")
                    rel_issue = relevance_issue(
                        relevance,
                        entity_id=eid,
                        asset_id=f"{eid}#{source.get('source_id')}#{img_index}",
                    )
                    if rel_issue:
                        lane_issues.append(
                            f"article source {source.get('source_id')} image[{img_index}]: {rel_issue}"
                        )
                    px_issue = _planned_pixel_issue(
                        image,
                        asset_id=f"{eid}/{source.get('source_id')}#{img_index}",
                    )
                    if px_issue:
                        lane_issues.append(
                            f"article source {source.get('source_id')} image[{img_index}]: {px_issue}"
                        )
            for source in article_sources:
                lane_issues.extend(
                    _article_source_identity_issues(
                        source,
                        platform_category(str(source.get("platform") or "")),
                    )
                )
            duplicate_urls = {
                str(source.get("url") or "")
                for source in homepage_sources
            } & {
                str(source.get("url") or "")
                for source in article_sources
            }
            duplicate_urls.discard("")
            collections: dict[str, list[dict[str, Any]]] = {}
            quotas = ((ctx.spec.get("content") or {}).get("quotas") or {})
            for image in work_images:
                collection_id = str(image.get("sourceCollectionId") or "").strip()
                if collection_id:
                    collections.setdefault(collection_id, []).append(image)
                missing_fields = [
                    field
                    for field in (
                        "sourceCollectionId",
                        "creator",
                        "collectionPageUrl",
                        "license",
                        "termsUrl",
                        "authorizationProof",
                    )
                    if not str(image.get(field) or "").strip()
                ]
                if missing_fields:
                    lane_issues.append(
                        f"image {image.get('url') or '?'} missing collection rights {missing_fields}"
                    )
                if str(image.get("generationModel") or "").strip():
                    lane_issues.append(f"image {image.get('url') or '?'} is AI-generated")
                platform = str(image.get("platform") or "").lower()
                if "pinterest" in platform or "小红书" in platform:
                    lane_issues.append(
                        f"image {image.get('url') or '?'} uses discovery-only platform {platform}"
                    )
            required_image_works = max(1, int(quotas.get("imageWorksPerTarget") or 0))
            # One source collection can form one image work. A multi-image
            # post may use 1..20 images from that collection, but the same
            # collection must not be counted as multiple works by default.
            work_capacity = sum(1 for rows in collections.values() if rows)
            if work_capacity < required_image_works:
                lane_issues.append(
                    "image research needs enough rights-cleared source collections "
                    f"for {required_image_works} image work(s)"
                )
            for lane in ("homepage", "article"):
                lane_issues.extend(
                    f"{lane}: {issue}"
                    for issue in source_plan_rights_issues(
                        ctx.task_id,
                        ctx.batch_id,
                        eid,
                        etype,
                        require_explicit=True,
                        research_lane=lane,
                    )
                )
            for index, image in enumerate(images, start=1):
                lane_issues.extend(
                    f"image[{index}]: {issue}"
                    for issue in validate_image_rights(
                        image, vertical=str(ctx.spec.get("vertical") or "travel")
                    )
                )
                relevance = str(image.get("relevance") or image.get("caption") or "")
                rel_issue = relevance_issue(
                    relevance,
                    entity_id=eid,
                    asset_id=f"{eid}#{index}",
                )
                if rel_issue:
                    lane_issues.append(f"image[{index}]: {rel_issue}")
                px_issue = _planned_pixel_issue(image, asset_id=f"{eid}#image#{index}")
                if px_issue:
                    lane_issues.append(f"image[{index}]: {px_issue}")
            if lane_issues:
                missing.append(f"{eid}: " + "; ".join(lane_issues[:12]))
            continue
        sources = curated_sources_for_entity(ctx.task_id, ctx.batch_id, eid, etype)
        images = curated_images_for_entity(ctx.task_id, ctx.batch_id, eid, etype)
        issues = source_plan_rights_issues(
            ctx.task_id,
            ctx.batch_id,
            eid,
            etype,
            require_explicit=requirements["minSources"] >= 4,
        )
        for index, image in enumerate(images, start=1):
            issues.extend(
                f"image[{index}]: {issue}"
                for issue in validate_image_rights(image, vertical=str(ctx.spec.get("vertical") or "travel"))
            )
            relevance = str(image.get("relevance") or image.get("caption") or "")
            rel_issue = relevance_issue(
                relevance,
                entity_id=eid,
                asset_id=f"{eid}#{index}",
            )
            if rel_issue:
                issues.append(f"image[{index}]: {rel_issue}")
        if len(sources) < requirements["minSources"]:
            issues.append(f"sources={len(sources)} need>={requirements['minSources']}")
        if len(images) < requirements["minImages"]:
            issues.append(f"imageUrls={len(images)} need>={requirements['minImages']}")
        if issues:
            missing.append(f"{eid}: " + "; ".join(issues[:8]))
    repair_path = batch_root(ctx.task_id, ctx.batch_id) / "_shared" / "download_repair.json"
    if include_download_repair and repair_path.is_file():
        pending_unresolved = _pending_download_repair_unresolved(ctx)
        if pending_unresolved:
            pending_repairs: list[str] = []
            for eid, lanes in pending_unresolved.items():
                if eid in abandoned:
                    continue
                details = "; ".join(
                    issue
                    for lane_issues in lanes.values()
                    for issue in lane_issues[:4]
                )
                if details:
                    pending_repairs.append(f"{eid}: {details}")
            if pending_repairs:
                missing.extend(pending_repairs)
    return (not missing), missing


def _download_research_lane_issues(
    ctx: PipelineContext,
    eid: str,
    etype: str,
    lane: str,
) -> list[str]:
    """Validate one separated-current research lane for targeted managed repair."""
    from download.gate import download_requirements
    from download.source_inputs import (
        curated_images_for_entity,
        curated_sources_for_entity,
        source_plan_rights_issues,
    )
    from _common.image_rules import relevance_issue
    from _common.source_catalog import platform_category
    from vertical.license import validate_image_rights

    requirements = download_requirements(ctx.task_id)
    issues: list[str] = []
    if lane == "homepage":
        sources = curated_sources_for_entity(
            ctx.task_id, ctx.batch_id, eid, etype, research_lane="homepage"
        )
        images = [
            image for image in curated_images_for_entity(ctx.task_id, ctx.batch_id, eid, etype)
            if str(image.get("researchLane") or "") == "homepage"
        ]
        min_homepage_sources = max(1, int(requirements.get("minHomepageSources") or 0))
        if len(sources) < min_homepage_sources:
            issues.append(f"homepage sources={len(sources)} need>={min_homepage_sources}")
        categories = {
            str(source.get("category") or "") or platform_category(str(source.get("platform") or ""))
            for source in sources
        }
        if not ({"encyclopedia", "official"} & categories):
            issues.append("homepage research needs encyclopedia or official evidence")
        for source in sources:
            category = str(source.get("category") or "") or platform_category(str(source.get("platform") or ""))
            if category in {"travelogue", "guidebook", "review"}:
                issues.append(
                    f"homepage source {source.get('source_id')}: "
                    f"entity homepage cannot use author/guide/review source category {category}"
                )
        issues.extend(
            f"homepage: {issue}"
            for issue in source_plan_rights_issues(
                ctx.task_id,
                ctx.batch_id,
                eid,
                etype,
                require_explicit=True,
                research_lane="homepage",
            )
        )
        for index, image in enumerate(images, start=1):
            issues.extend(
                f"homepage image[{index}]: {issue}"
                for issue in validate_image_rights(
                    image, vertical=str(ctx.spec.get("vertical") or "travel")
                )
            )
            relevance = str(image.get("relevance") or image.get("caption") or "")
            rel_issue = relevance_issue(
                relevance,
                entity_id=eid,
                asset_id=f"{eid}#homepage#{index}",
            )
            if rel_issue:
                issues.append(f"homepage image[{index}]: {rel_issue}")
            px_issue = _planned_pixel_issue(image, asset_id=f"{eid}#homepage#{index}")
            if px_issue:
                issues.append(f"homepage image[{index}]: {px_issue}")
        return issues

    if lane == "article":
        sources = curated_sources_for_entity(
            ctx.task_id, ctx.batch_id, eid, etype, research_lane="article"
        )
        min_article_sources = int(requirements.get("minArticleBaseSources") or requirements["minSources"])
        if len(sources) < min_article_sources:
            issues.append(f"article sources={len(sources)} need>={min_article_sources}")
        quotas = ((ctx.spec.get("content") or {}).get("quotas") or {})
        required_article_base_sources = min_article_sources if int(quotas.get("entityArticlesPerTarget") or 0) else 0
        article_base_sources = [
            source for source in sources
            if str(source.get("sourceRole") or "") == "base"
        ]
        if required_article_base_sources and len(article_base_sources) < required_article_base_sources:
            issues.append(
                f"article research needs >= {required_article_base_sources} "
                "text-qualified base sources"
            )
        for source in sources:
            gate = source.get("candidateGate") if isinstance(source.get("candidateGate"), dict) else {}
            if gate and not gate.get("passed"):
                issues.append(
                    f"article source {source.get('source_id')}: candidate gate failed "
                    f"{gate.get('issues') or []}"
                )
            if str(source.get("entityMatch") or "") == "weak":
                issues.append(f"article source {source.get('source_id')}: weak entity match")
            source_category = str(source.get("category") or "") or platform_category(str(source.get("platform") or ""))
            if str(source.get("sourceRole") or "") == "base":
                if source_category not in {
                    "travelogue",
                    "guidebook",
                    "travel_guide",
                    "wikivoyage",
                    "official_article",
                    "vertical_professional",
                    "ugc_longform",
                    "community_post",
                    "media_article",
                    "platform_article",
                    "forum_thread",
                    "review_note",
                }:
                    issues.append(
                        f"article source {source.get('source_id')}: base source category "
                        f"must be article-quality, got {source_category or 'unknown'}"
                    )
            for img_index, image in enumerate(source.get("imageUrls") or [], start=1):
                issues.extend(
                    f"article source {source.get('source_id')} image[{img_index}]: {issue}"
                    for issue in validate_image_rights(
                        image, vertical=str(ctx.spec.get("vertical") or "travel")
                    )
                )
                relevance = str(image.get("relevance") or image.get("caption") or "")
                rel_issue = relevance_issue(
                    relevance,
                    entity_id=eid,
                    asset_id=f"{eid}#{source.get('source_id')}#{img_index}",
                )
                if rel_issue:
                    issues.append(
                        f"article source {source.get('source_id')} image[{img_index}]: {rel_issue}"
                    )
                px_issue = _planned_pixel_issue(
                    image,
                    asset_id=f"{eid}/{source.get('source_id')}#{img_index}",
                )
                if px_issue:
                    issues.append(
                        f"article source {source.get('source_id')} image[{img_index}]: {px_issue}"
                    )
        for source in sources:
            issues.extend(
                _article_source_identity_issues(
                    source,
                    str(source.get("category") or "") or platform_category(str(source.get("platform") or "")),
                )
            )
        homepage_urls = {
            str(source.get("url") or "")
            for source in curated_sources_for_entity(
                ctx.task_id, ctx.batch_id, eid, etype, research_lane="homepage"
            )
        }
        article_urls = {str(source.get("url") or "") for source in sources}
        duplicate_urls = homepage_urls & article_urls
        duplicate_urls.discard("")
        if duplicate_urls:
            issues.append(
                "article sources must be independent from homepage lane; duplicate urls="
                + ", ".join(sorted(duplicate_urls)[:3])
            )
        issues.extend(
            f"article: {issue}"
            for issue in source_plan_rights_issues(
                ctx.task_id,
                ctx.batch_id,
                eid,
                etype,
                require_explicit=True,
                research_lane="article",
            )
        )
        return issues

    if lane == "image":
        images = [
            image for image in curated_images_for_entity(ctx.task_id, ctx.batch_id, eid, etype)
            if str(image.get("researchLane") or "image") == "image"
        ]
        collections: dict[str, list[dict[str, Any]]] = {}
        for image in images:
            collection_id = str(image.get("sourceCollectionId") or "").strip()
            if collection_id:
                collections.setdefault(collection_id, []).append(image)
            missing_fields = [
                field
                for field in (
                    "sourceCollectionId",
                    "creator",
                    "collectionPageUrl",
                    "license",
                    "termsUrl",
                    "authorizationProof",
                )
                if not str(image.get(field) or "").strip()
            ]
            if missing_fields:
                issues.append(
                    f"image {image.get('url') or '?'} missing collection rights {missing_fields}"
                )
            if str(image.get("generationModel") or "").strip():
                issues.append(f"image {image.get('url') or '?'} is AI-generated")
            platform = str(image.get("platform") or "").lower()
            if "pinterest" in platform or "小红书" in platform:
                issues.append(f"image {image.get('url') or '?'} uses discovery-only platform {platform}")
        quotas = ((ctx.spec.get("content") or {}).get("quotas") or {})
        required_image_works = max(1, int(quotas.get("imageWorksPerTarget") or 0))
        work_capacity = sum(1 for rows in collections.values() if rows)
        if work_capacity < required_image_works:
            issues.append(
                "image research needs enough rights-cleared source collections "
                f"for {required_image_works} image work(s)"
            )
        for collection_id, rows in sorted(collections.items()):
            creators = {
                str(row.get("creator") or row.get("credit") or "").strip()
                for row in rows
                if str(row.get("creator") or row.get("credit") or "").strip()
            }
            platforms = {
                str(row.get("platform") or "").strip()
                for row in rows
                if str(row.get("platform") or "").strip()
            }
            if len(rows) > 20:
                issues.append(f"image collection {collection_id}: images={len(rows)} exceeds 20")
            if len(creators) > 1:
                issues.append(f"image collection {collection_id}: mixed creators are not allowed")
            if len(platforms) > 1:
                issues.append(f"image collection {collection_id}: mixed platforms are not allowed")
        for index, image in enumerate(images, start=1):
            issues.extend(
                f"image[{index}]: {issue}"
                for issue in validate_image_rights(
                    image, vertical=str(ctx.spec.get("vertical") or "travel")
                )
            )
            relevance = str(image.get("relevance") or image.get("caption") or "")
            rel_issue = relevance_issue(relevance, entity_id=eid, asset_id=f"{eid}#{index}")
            if rel_issue:
                issues.append(f"image[{index}]: {rel_issue}")
            px_issue = _planned_pixel_issue(image, asset_id=f"{eid}#image#{index}")
            if px_issue:
                issues.append(f"image[{index}]: {px_issue}")
        return issues

    return [f"unknown research lane: {lane}"]


def _article_source_identity_issues(source: dict[str, Any], category: str | None) -> list[str]:
    source_id = str(source.get("source_id") or "").strip().lower()
    platform = str(source.get("platform") or "").strip()
    issues: list[str] = []
    if "official" in source_id and category != "official":
        issues.append(
            f"article source {source.get('source_id')}: source_id implies official, "
            f"but platform {platform!r} maps to {category or 'unknown'}"
        )
    if (
        ("wiki" in source_id or "baike" in source_id or "百科" in source_id)
        and "wikivoyage" not in source_id
        and category != "encyclopedia"
    ):
        issues.append(
            f"article source {source.get('source_id')}: source_id implies encyclopedia, "
            f"but platform {platform!r} maps to {category or 'unknown'}"
        )
    return issues


def _download_repair_path(ctx: PipelineContext) -> Path:
    return batch_root(ctx.task_id, ctx.batch_id) / "_shared" / "download_repair.json"


def _download_repair_entry_pending(repair: dict[str, Any]) -> bool:
    if not _download_repair_entry_actionable(repair):
        return False
    if _download_repair_fetch_only_retryable(repair):
        return False
    plan_paths = [
        Path(str(path))
        for path in (repair.get("sourcePlanPaths") or [])
        if str(path).strip()
    ]
    if not plan_paths and str(repair.get("sourcePlanPath") or "").strip():
        plan_paths = [Path(str(repair.get("sourcePlanPath")))]
    failed_mtime = int(repair.get("sourcePlanMtimeNs") or 0)
    current_mtime = max((_source_plan_mtime_ns(path) for path in plan_paths), default=0)
    return current_mtime <= failed_mtime


_SOURCE_CATEGORY_REPAIR_MARKERS = (
    "missing core source categories",
    "source categories",
)


def _download_source_category_issue_lane(issue_text: str) -> str:
    lowered = str(issue_text or "").casefold()
    if not any(marker in lowered for marker in _SOURCE_CATEGORY_REPAIR_MARKERS):
        return ""
    homepage_markers = ("encyclopedia", "official evidence", "homepage", "主页", "百科")
    if any(marker in lowered for marker in homepage_markers):
        return "homepage"
    article_markers = (
        "travelogue",
        "guidebook",
        "official_article",
        "vertical_professional",
        "ugc_longform",
        "community_post",
        "media_article",
        "platform_article",
        "forum_thread",
        "review_note",
    )
    if any(marker in lowered for marker in article_markers):
        return "article"
    return ""


def _download_repair_issue_stale_under_current_rules(
    ctx: PipelineContext,
    *,
    entity_id: str,
    issue: str,
) -> bool:
    """Return True when an old rule-derived repair issue no longer fails today.

    Repair packets are durable runtime state. When the source catalog changes,
    a prior source-category failure can become obsolete without any source_plan
    file mtime change. Re-check only these rule-derived coverage issues against
    the current catalog; concrete fetch/image/source-count failures must remain
    actionable until their own gate passes.
    """
    lowered = str(issue or "").casefold()
    if not any(marker in lowered for marker in _SOURCE_CATEGORY_REPAIR_MARKERS):
        return False
    from _common.source_catalog import coverage_issues
    from download.source_inputs import curated_sources_for_entity

    etype = _coverage_entity_type(ctx.spec)
    sources = curated_sources_for_entity(ctx.task_id, ctx.batch_id, entity_id, etype)
    vertical = str(ctx.spec.get("vertical") or "travel")
    return not coverage_issues(sources, vertical=vertical, entity_id=entity_id)


def _download_repair_active_issues(
    ctx: PipelineContext,
    repair: dict[str, Any],
) -> list[str]:
    entity_id = str(repair.get("entityId") or "").strip()
    if not entity_id:
        return []
    issues: list[str] = []
    for raw_issue in repair.get("issues") or []:
        issue = str(raw_issue or "").strip()
        if not issue or entity_id not in issue:
            continue
        if _download_repair_issue_stale_under_current_rules(ctx, entity_id=entity_id, issue=issue):
            continue
        issues.append(issue)
    return issues


def _download_repair_entry_actionable(repair: dict[str, Any]) -> bool:
    research_issues = repair.get("researchLaneIssues") or {}
    if isinstance(research_issues, dict) and any(research_issues.values()):
        return True
    return any(isinstance(hint, dict) for hint in (repair.get("imageRepairHints") or []))


def _download_repair_fetch_only_retryable(repair: dict[str, Any]) -> bool:
    """Fetch-only image repair gets one deterministic retry before Agent work.

    A source plan with enough rights-cleared image candidates should not be
    sent back to Cursor agents just because the previous network budget was too
    tight or a CDN was transiently unavailable. Repeated failures of the same
    plan still escalate to source-plan repair.
    """

    if DOWNLOAD_FETCH_ONLY_RETRY_LIMIT <= 0:
        return False
    try:
        retry_count = int(repair.get("fetchRetryCount") or 0)
    except (TypeError, ValueError):
        retry_count = 0
    if retry_count > DOWNLOAD_FETCH_ONLY_RETRY_LIMIT:
        return False
    research_issues = repair.get("researchLaneIssues") or {}
    if isinstance(research_issues, dict) and any(research_issues.values()):
        return False
    issue_text = " ".join(str(item) for item in (repair.get("issues") or []))
    if not any(
        token in issue_text
        for token in (
            "imageFetch",
            "imageCount",
            "unique publishable image",
            "未下到真实图片",
            "合格去重图",
        )
    ):
        return False
    diagnostics = repair.get("downloadDiagnostics") or {}
    if not isinstance(diagnostics, dict):
        return False
    rejected_by = diagnostics.get("rejectedByCategory") if isinstance(diagnostics, dict) else {}
    rejected_by = rejected_by if isinstance(rejected_by, dict) else {}
    if int(rejected_by.get("rights") or 0) or int(rejected_by.get("safety_or_watermark") or 0):
        return False
    fetch_rejects = int(rejected_by.get("fetch_or_non_image") or 0)
    planned = int(diagnostics.get("plannedImages") or 0)
    return fetch_rejects > 0 and planned > 0


def _source_plan_mtime_ns(path: Path) -> int:
    if path.is_file():
        return path.stat().st_mtime_ns
    if path.is_dir():
        return max(
            (child.stat().st_mtime_ns for child in path.glob("*_source_plan.json") if child.is_file()),
            default=0,
        )
    return 0


def _source_plan_rule_paths(ctx: PipelineContext) -> list[Path]:
    """Global files whose changes must invalidate legacy generated source plans.

    Entity-scoped rows in vertical source registries are tracked by
    sourceRuleSignature on new plans. Keeping the registry file out of this
    legacy mtime set prevents adding one missing known source from forcing a
    whole-batch refresh.
    """
    data_root = Path(__file__).resolve().parents[2]
    vertical = str(ctx.spec.get("vertical") or "travel").strip() or "travel"
    candidates = [
        data_root / "scripts" / "download" / "research_plan.py",
        data_root / "scripts" / "_common" / "source_catalog.py",
        data_root / "templates" / "_registry" / "catalogs" / "source_catalog.yaml",
        data_root / "templates" / "_registry" / "catalogs" / "content_source_registry.yaml",
        data_root / "verticals" / vertical / "rights" / "license_policy.yaml",
    ]
    return [path for path in candidates if path.is_file()]


def _source_plan_rule_mtime_ns(ctx: PipelineContext) -> int:
    return max((path.stat().st_mtime_ns for path in _source_plan_rule_paths(ctx)), default=0)


def _source_plan_signature_state(
    ctx: PipelineContext,
    *,
    entity_id: str,
    paths: list[Path],
) -> str:
    """Return current/stale/legacy for source plan rule signatures."""
    expected = source_plan_rule_signature(str(ctx.spec.get("vertical") or "travel"), entity_id)
    saw_signature = False
    for path in paths:
        if not path.is_file():
            continue
        try:
            plan = read_json(path)
        except Exception:  # noqa: BLE001
            return "legacy"
        signature = plan.get("sourceRuleSignature")
        if not isinstance(signature, Mapping):
            return "legacy"
        saw_signature = True
        if str(signature.get("hash") or "") != str(expected.get("hash") or ""):
            return "stale"
    return "current" if saw_signature else "legacy"


def _source_plan_lane_paths(
    ctx: PipelineContext,
    entity_id: str,
    etype: str,
) -> list[Path]:
    from _common.source_unit import resolve_entity_object_dir

    plan_dir = resolve_entity_object_dir(
        ctx.task_id,
        ctx.batch_id,
        entity_id,
        etype_hint=etype,
    ) / "1.download"
    lane_paths = [
        plan_dir / "homepage_source_plan.json",
        plan_dir / "article_source_plan.json",
        plan_dir / "image_source_plan.json",
    ]
    existing_lane_paths = [path for path in lane_paths if path.is_file()]
    if existing_lane_paths:
        return existing_lane_paths
    legacy_path = plan_dir / "source_plan.json"
    return [legacy_path] if legacy_path.is_file() else []


def _stale_source_plan_entities(
    ctx: PipelineContext,
    *,
    entity_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return entities whose generated source plans predate source/rights rules."""
    rule_mtime = _source_plan_rule_mtime_ns(ctx)
    if rule_mtime <= 0:
        return []
    etype = _coverage_entity_type(ctx.spec)
    abandoned = _abandoned_entity_ids(load_workflow_state(ctx.task_id, ctx.batch_id))
    scoped_ids = entity_ids if entity_ids is not None else ctx.entity_ids
    stale: list[dict[str, Any]] = []
    for entity_id in scoped_ids:
        if entity_id in abandoned:
            continue
        paths = _source_plan_lane_paths(ctx, entity_id, etype)
        if not paths:
            continue
        signature_state = _source_plan_signature_state(ctx, entity_id=entity_id, paths=paths)
        if signature_state == "current":
            continue
        if signature_state == "stale":
            stale.append(
                {
                    "entityId": entity_id,
                    "sourcePlanRuleState": "signature_stale",
                }
            )
            continue
        plan_mtime = min((_source_plan_mtime_ns(path) for path in paths), default=0)
        if plan_mtime and plan_mtime < rule_mtime:
            stale.append(
                {
                    "entityId": entity_id,
                    "sourcePlanMtimeNs": plan_mtime,
                    "sourceRuleMtimeNs": rule_mtime,
                    "sourcePlanRuleState": "legacy_mtime_stale",
                }
            )
    return stale


def _download_retry_entity_ids(ctx: PipelineContext) -> list[str]:
    """Return failed entities for an object-scoped download repair.

    The repair packet is retained until the next successful fetch. For an
    interrupted older run, derive scope from the current persisted final gate;
    stale per-stage red reports must never widen the repair.
    """
    selected: set[str] = set()
    from download.gate import gate_download

    current_issues = gate_download(ctx.task_id, ctx.batch_id, target_entities=set(ctx.entity_ids))
    if not current_issues:
        repair_path = _download_repair_path(ctx)
        if repair_path.is_file():
            repair_path.unlink()
        return []
    current_scope = {
        entity_id
        for entity_id in ctx.entity_ids
        if any(entity_id in str(issue) for issue in current_issues)
    }
    if current_scope:
        return [entity_id for entity_id in ctx.entity_ids if entity_id in current_scope]

    repair_path = _download_repair_path(ctx)
    if repair_path.is_file():
        try:
            repair = read_json(repair_path)
        except (OSError, ValueError, TypeError):
            repair = {}
        selected.update(
            str(entity.get("entityId") or "")
            for entity in repair.get("entities") or []
            if isinstance(entity, dict) and _download_repair_entry_actionable(entity)
        )
    return [entity_id for entity_id in ctx.entity_ids if entity_id in selected]


def _download_retry_lane(
    ctx: PipelineContext,
    entity_ids: list[str],
) -> str:
    """Return a safe lane scope for deterministic download retry.

    Narrow the expensive fetch/prune cycle only when every pending repair in
    this retry batch points at the same concrete lane. Mixed or unknown repair
    remains full-lane so the workflow cannot accidentally skip required
    evidence.
    """

    unresolved = _pending_download_repair_unresolved(ctx)
    lanes: set[str] = set()
    for entity_id in entity_ids:
        lanes.update(
            lane
            for lane in (unresolved.get(entity_id) or {})
            if lane in {"homepage", "article", "image"}
        )
    return next(iter(lanes)) if len(lanes) == 1 else "all"


def _download_stage_gate_issues(
    ctx: PipelineContext,
    *,
    entity_ids: Iterable[str] | None = None,
) -> list[str]:
    result_root = batch_root(ctx.task_id, ctx.batch_id) / "task_download" / "results"
    scoped_entities = {str(entity_id) for entity_id in (entity_ids or []) if str(entity_id).strip()}
    issues: list[str] = []
    for step in (
        "source_plan_gate",
        "image_rights_gate",
        "image_fetch_gate",
        "source_screen_gate",
        "entity_source_bundle_gate",
    ):
        step_dir = result_root / step
        if not step_dir.is_dir():
            continue
        for path in sorted(step_dir.glob("*.json")):
            try:
                data = read_json(path)
            except (OSError, ValueError, TypeError):
                continue
            payload = data.get("payload") if isinstance(data.get("payload"), dict) else data
            if not isinstance(payload, dict) or payload.get("passed") is not False:
                continue
            evidence = payload.get("evidenceSummary") if isinstance(payload.get("evidenceSummary"), dict) else {}
            entity_ref = (
                str(evidence.get("entityId") or "")
                if step == "source_screen_gate"
                else str(payload.get("ref") or path.stem)
            )
            if scoped_entities and entity_ref not in scoped_entities:
                continue
            ref = str(payload.get("ref") or path.stem)
            raw_issues = payload.get("issues") if isinstance(payload.get("issues"), list) else []
            if raw_issues:
                issues.extend(f"{ref}: {issue}" for issue in raw_issues)
            else:
                issues.append(f"{ref}: {step} failed")
    return issues


def _download_source_units_mtime_ns(ctx: PipelineContext, entity_id: str, etype: str) -> int:
    from _common.source_unit import resolve_entity_object_dir

    sources_dir = (
        resolve_entity_object_dir(
            ctx.task_id,
            ctx.batch_id,
            entity_id,
            etype_hint=etype,
        )
        / "1.download"
        / "sources"
    )
    if not sources_dir.is_dir():
        return 0
    mtimes: list[int] = []
    for path in sources_dir.rglob("*"):
        if path.is_file():
            try:
                mtimes.append(path.stat().st_mtime_ns)
            except OSError:
                continue
    return max(mtimes, default=0)


def _download_report_mtime_ns(ctx: PipelineContext, entity_id: str) -> int:
    result_root = batch_root(ctx.task_id, ctx.batch_id) / "task_download" / "results"
    candidates = [
        result_root / "source_plan_gate" / f"{entity_id}.json",
        result_root / "image_rights_gate" / f"{entity_id}.json",
        result_root / "image_fetch_gate" / f"{entity_id}.json",
        result_root / "entity_source_bundle_gate" / f"{entity_id}.json",
    ]
    mtimes: list[int] = []
    for path in candidates:
        if path.is_file():
            try:
                mtimes.append(path.stat().st_mtime_ns)
            except OSError:
                continue
    return min(mtimes) if mtimes else 0


def _download_fetch_rule_mtime_ns() -> int:
    data_root = Path(__file__).resolve().parents[2]
    candidates = [
        data_root / "scripts" / "download" / "fetch.py",
        data_root / "scripts" / "download" / "handler.py",
        data_root / "scripts" / "_common" / "source_unit.py",
        data_root / "scripts" / "vertical" / "license.py",
    ]
    return max((path.stat().st_mtime_ns for path in candidates if path.is_file()), default=0)


def _download_fetch_stale_entity_ids(ctx: PipelineContext) -> list[str]:
    """Entities whose source plans are newer than fetched source units/reports."""
    etype = _coverage_entity_type(ctx.spec)
    abandoned = _abandoned_entity_ids(load_workflow_state(ctx.task_id, ctx.batch_id))
    enforce_rule_mtime = os.environ.get("QWQ_DOWNLOAD_FETCH_REVALIDATE_RULE_MTIME", "0") == "1"
    fetch_rule_mtime = _download_fetch_rule_mtime_ns() if enforce_rule_mtime else 0
    stale: list[str] = []
    for entity_id in ctx.entity_ids:
        if entity_id in abandoned:
            continue
        plan_mtime = max(
            (_source_plan_mtime_ns(path) for path in _source_plan_lane_paths(ctx, entity_id, etype)),
            default=0,
        )
        if not plan_mtime:
            continue
        units_mtime = _download_source_units_mtime_ns(ctx, entity_id, etype)
        report_mtime = _download_report_mtime_ns(ctx, entity_id)
        if (
            not units_mtime
            or not report_mtime
            or plan_mtime > units_mtime
            or plan_mtime > report_mtime
            or (fetch_rule_mtime and units_mtime < fetch_rule_mtime)
            or (fetch_rule_mtime and report_mtime < fetch_rule_mtime)
        ):
            stale.append(entity_id)
    return stale


def _content_plan_source_shortfall_entity_ids(ctx: PipelineContext) -> list[str]:
    diagnostics_path = batch_root(ctx.task_id, ctx.batch_id) / "_shared" / "content_plan_source_diagnostics.json"
    if not diagnostics_path.is_file():
        return []
    try:
        diagnostics = read_json(diagnostics_path)
    except (OSError, ValueError, TypeError):
        return []
    targets = diagnostics.get("targets") if isinstance(diagnostics.get("targets"), dict) else {}
    quotas = ((ctx.spec.get("content") or {}).get("quotas") or {})
    required_articles = int(quotas.get("entityArticlesPerTarget") or 0)
    required_images = int(quotas.get("imageWorksPerTarget") or 0)
    shortfall: set[str] = set()
    for entity_id, row in targets.items():
        if not isinstance(row, dict):
            continue
        if required_articles and int(row.get("pickedArticleBaseSources") or 0) < required_articles:
            shortfall.add(str(entity_id))
        if required_images and int(row.get("pickedImageSources") or 0) < required_images:
            shortfall.add(str(entity_id))
    return [entity_id for entity_id in ctx.entity_ids if entity_id in shortfall]


def _content_plan_source_shortfall_reasons(ctx: PipelineContext) -> dict[str, str]:
    diagnostics_path = batch_root(ctx.task_id, ctx.batch_id) / "_shared" / "content_plan_source_diagnostics.json"
    if not diagnostics_path.is_file():
        return {}
    try:
        diagnostics = read_json(diagnostics_path)
    except (OSError, ValueError, TypeError):
        return {}
    targets = diagnostics.get("targets") if isinstance(diagnostics.get("targets"), dict) else {}
    quotas = ((ctx.spec.get("content") or {}).get("quotas") or {})
    required_articles = int(quotas.get("entityArticlesPerTarget") or 0)
    required_images = int(quotas.get("imageWorksPerTarget") or 0)
    reasons: dict[str, str] = {}
    for entity_id in ctx.entity_ids:
        row = targets.get(entity_id)
        if not isinstance(row, Mapping):
            continue
        parts: list[str] = []
        picked_articles = int(row.get("pickedArticleBaseSources") or 0)
        picked_images = int(row.get("pickedImageSources") or 0)
        if required_articles and picked_articles < required_articles:
            raw = int(row.get("rawArticleBaseSources") or 0)
            qualified = int(row.get("qualifiedArticleBaseSources") or 0)
            rejects = row.get("articleRejects") if isinstance(row.get("articleRejects"), Mapping) else {}
            reject_summary = ", ".join(
                f"{key}={value}" for key, value in sorted(rejects.items())
            ) or "none"
            parts.append(
                "article base source shortfall "
                f"{picked_articles}<{required_articles}; raw={raw}; "
                f"qualified={qualified}; rejects={{ {reject_summary} }}"
            )
        if required_images and picked_images < required_images:
            parts.append(f"image source shortfall {picked_images}<{required_images}")
        if parts:
            reasons[str(entity_id)] = "; ".join(parts)
    return reasons


def _replace_content_plan_source_shortfall_entities(
    ctx: PipelineContext,
    issues: list[str],
    *,
    entity_type: str,
) -> tuple[list[str], list[str], list[str]]:
    reasons = _content_plan_source_shortfall_reasons(ctx)
    if not reasons:
        return [], [], []
    if not _workflow_allows_partial_content(ctx):
        return [], [], [
            f"{entity_id}: {reason}; workflowPolicy.allowPartialContent is not true"
            for entity_id, reason in sorted(reasons.items())
        ]
    state = load_workflow_state(ctx.task_id, ctx.batch_id)
    active_entities = [entity for entity in ctx.entity_ids if entity not in _abandoned_entity_ids(state)]
    try:
        min_entities = int((ctx.spec.get("acceptance") or {}).get("minEntities") or len(active_entities))
    except (TypeError, ValueError):
        min_entities = len(active_entities)
    needed = max(0, min_entities - (len(active_entities) - len(reasons)))
    activated_all: list[str] = []
    rejected_all: list[str] = []
    reserve_count = len(
        [
            target for target in ((ctx.spec.get("scope") or {}).get("reserveCoverageTargets") or [])
            if isinstance(target, Mapping) and str(target.get("name") or "").strip()
        ]
    )
    max_waves = max(1, min(30, reserve_count + len(reasons) + 1))
    for wave_index in range(max_waves):
        remaining = max(0, needed - len(activated_all))
        if remaining <= 0:
            break
        if len(_next_replacement_candidates(ctx, needed=remaining)) < remaining:
            _top_up_reserve_targets_from_discovery(ctx, needed=remaining)
        if not _next_replacement_candidates(ctx, needed=1):
            break
        activated, rejected, _report = _screen_replacement_targets(
            ctx,
            entity_type=entity_type,
            reason="keep target count after content_plan source shortfall",
            needed=remaining,
            scope=f"content_plan_source_shortfall_{wave_index + 1}",
        )
        activated_all.extend(item for item in activated if item not in activated_all)
        rejected_all.extend(item for item in rejected if item not in rejected_all)
        if not activated and not rejected:
            break
    if len(activated_all) < needed:
        return activated_all, rejected_all, [
            "content_plan source shortfall replacement capacity insufficient "
            f"(needed={needed}, activated={len(activated_all)}, rejected={len(rejected_all)}): "
            + "; ".join(issues[:8])
        ]
    abandoned: list[str] = []
    for entity_id, reason in reasons.items():
        result = mark_abandoned_entities(
            ctx.task_id,
            ctx.batch_id,
            [entity_id],
            stage="content_plan",
            reason=f"content_plan source shortfall: {reason}",
        )
        abandoned.extend(str(item) for item in result.get("added") or [])
    _apply_abandoned_entities(
        ctx,
        load_workflow_state(ctx.task_id, ctx.batch_id),
        activate_replacements=False,
    )
    _clean_content_plan_outputs(ctx)
    return abandoned, activated_all, []


def _record_download_repair(ctx: PipelineContext, issues: list[str]) -> Path:
    """把真实抓取门失败转成下一轮 Agent 可消费的对象级 repair packet。"""
    from _common.download_diagnostics import entity_download_diagnostics
    from _common.source_unit import resolve_entity_object_dir

    etype = _coverage_entity_type(ctx.spec)
    entities: list[dict[str, Any]] = []
    root = batch_root(ctx.task_id, ctx.batch_id)
    result_root = root / "task_download" / "results"
    path = _download_repair_path(ctx)
    previous_by_entity: dict[str, dict[str, Any]] = {}
    if path.is_file():
        try:
            previous_packet = read_json(path)
        except (OSError, ValueError, TypeError):
            previous_packet = {}
        previous_by_entity = {
            str(item.get("entityId") or ""): item
            for item in (previous_packet.get("entities") or [])
            if isinstance(item, dict)
        }
    issue_entity_hits: dict[str, list[str]] = {
        entity_id: [
            str(issue) for issue in issues if entity_id and entity_id in str(issue)
        ]
        for entity_id in ctx.entity_ids
    }
    general_issues = [
        str(issue)
        for issue in issues
        if not any(str(issue) in rows for rows in issue_entity_hits.values())
    ]
    for entity_id in ctx.entity_ids:
        entity_issues = list(issue_entity_hits.get(entity_id) or [])
        if not entity_issues and len(ctx.entity_ids) == 1:
            entity_issues.extend(general_issues)
        if not entity_issues:
            continue
        plan_dir = (
            resolve_entity_object_dir(
                ctx.task_id,
                ctx.batch_id,
                entity_id,
                etype_hint=etype,
            )
            / "1.download"
        )
        lane_paths = [
            plan_dir / name
            for name in (
                "homepage_source_plan.json",
                "article_source_plan.json",
                "image_source_plan.json",
            )
        ]
        existing_lane_paths = [path for path in lane_paths if path.is_file()]
        legacy_path = plan_dir / "source_plan.json"
        plan_paths = existing_lane_paths or ([legacy_path] if legacy_path.is_file() else lane_paths)
        source_plan_mtime_ns = max(
            (_source_plan_mtime_ns(path) for path in plan_paths),
            default=0,
        )
        research_lane_issues = {
            lane: _download_research_lane_issues(ctx, entity_id, etype, lane)
            for lane in ("homepage", "article", "image")
        }
        diagnostics = entity_download_diagnostics(root, entity_id)
        image_repair_hints = _download_issue_repair_hints(entity_issues, entity_id=entity_id)
        image_repair_hints.extend(_research_image_repair_hints(ctx, entity_id, etype))
        image_repair_hints.extend(
            _download_diagnostic_image_repair_hints(diagnostics, entity_id=entity_id)
        )
        previous = previous_by_entity.get(entity_id) or {}
        same_plan = int(previous.get("sourcePlanMtimeNs") or 0) == source_plan_mtime_ns
        probe_repair = {
            "entityId": entity_id,
            "issues": entity_issues,
            "sourcePlanMtimeNs": source_plan_mtime_ns,
            "downloadDiagnostics": diagnostics,
            "researchLaneIssues": {
                lane: lane_issues
                for lane, lane_issues in research_lane_issues.items()
                if lane_issues
            },
            "imageRepairHints": image_repair_hints,
            "fetchRetryCount": (
                int(previous.get("fetchRetryCount") or 0)
                if same_plan
                else 0
            ),
        }
        fetch_retry_count = 0
        if _download_repair_fetch_only_retryable(probe_repair):
            fetch_retry_count = int(probe_repair.get("fetchRetryCount") or 0) + 1
        entities.append(
            {
                "entityId": entity_id,
                "issues": entity_issues,
                "sourcePlanPath": str(plan_paths[0]),
                "sourcePlanPaths": [str(path) for path in plan_paths],
                "sourcePlanMtimeNs": source_plan_mtime_ns,
                "fetchRetryCount": fetch_retry_count,
                "reportPaths": [
                    str(result_root / "entity_source_bundle_gate" / f"{entity_id}.json"),
                    str(result_root / "image_fetch_gate" / f"{entity_id}.json"),
                    str(result_root / "image_rights_gate" / f"{entity_id}.json"),
                ],
                "downloadDiagnostics": diagnostics,
                "researchLaneIssues": {
                    lane: lane_issues
                    for lane, lane_issues in research_lane_issues.items()
                    if lane_issues
                },
                "imageRepairHints": image_repair_hints,
            }
        )
    write_json(
        path,
        {
            "schemaVersion": "quwoquan.download_repair",
            "taskId": ctx.task_id,
            "batchId": ctx.batch_id,
            "createdAt": store.now_iso(),
            "entities": entities,
        },
    )
    return path


def _download_fast_fail_reasons(ctx: PipelineContext, issues: list[str]) -> dict[str, str]:
    """Classify deterministic source-unavailable entities before launching Agents.

    The classifier is intentionally narrow. First attempts still go through the
    normal download repair loop. If retained-source shortfalls survive a repair
    rewind, the entity is source-unavailable for this batch and should be
    replaced instead of blocking downstream stages.
    """
    from _common.download_diagnostics import entity_download_diagnostics
    from download.gate import download_requirements

    root = batch_root(ctx.task_id, ctx.batch_id)
    min_images = int(download_requirements(ctx.task_id).get("minImages") or 0)
    state = load_workflow_state(ctx.task_id, ctx.batch_id)
    react_rewinds = state.get("reactRewinds") if isinstance(state.get("reactRewinds"), Mapping) else {}
    download_fetch_rewinds = int((react_rewinds or {}).get("download_fetch") or 0)
    repaired_once = download_fetch_rewinds >= max(0, MAX_REACT_REWINDS - 1)
    reasons: dict[str, str] = {}
    for entity_id in ctx.entity_ids:
        entity_issues = [str(issue) for issue in issues if entity_id in str(issue)]
        if not entity_issues:
            continue
        issue_text = "；".join(entity_issues)
        retained_shortfall = (
            "retained sources" in issue_text
            or "baseDraft-ready sources" in issue_text
            or "text-qualified base sources" in issue_text
            or "article base sources" in issue_text
        )
        if repaired_once and retained_shortfall:
            reasons[entity_id] = (
                "source_unavailable: download retained-source shortfall survived repair "
                f"({entity_issues[0]})"
            )
            continue
        if "unique publishable image" not in issue_text:
            continue
        if retained_shortfall:
            continue
        diagnostics = entity_download_diagnostics(root, entity_id)
        downloaded = int(diagnostics.get("downloadedImages") or 0)
        rejected_by = diagnostics.get("rejectedByCategory") if isinstance(diagnostics, dict) else {}
        duplicate_rejects = int((rejected_by or {}).get("duplicate") or 0)
        rights_rejects = int((rejected_by or {}).get("rights") or 0)
        safety_rejects = int((rejected_by or {}).get("safety_or_watermark") or 0)
        fetch_rejects = int((rejected_by or {}).get("fetch_or_non_image") or 0)
        if (
            min_images > 0
            and downloaded < min_images
            and duplicate_rejects >= 1
            and not (rights_rejects or safety_rejects or fetch_rejects)
        ):
            reasons[entity_id] = (
                "source_unavailable: deterministic discovery produced only "
                f"{downloaded} unique publishable image(s) after dedupe "
                f"(need >= {min_images}); target replacement or authorized gallery required"
            )
    return reasons


def _apply_download_fast_fail(ctx: PipelineContext, issues: list[str]) -> list[str]:
    reasons = _download_fast_fail_reasons(ctx, issues)
    if not reasons:
        return issues
    if not _workflow_allows_partial_content(ctx):
        return [
            (
                f"{entity_id}: {reason}; "
                "workflowPolicy.allowPartialContent is not true"
            )
            for entity_id, reason in sorted(reasons.items())
        ]
    replacement_capacity, active_count, min_entities, requires_replacement = _replacement_capacity_for_abandon(ctx)
    if requires_replacement and replacement_capacity < len(reasons):
        return [
            (
                f"{entity_id}: {reason}; replacement capacity exhausted "
                f"(needed={len(reasons)}, available={replacement_capacity}, "
                f"active={active_count}, minEntities={min_entities})"
            )
            for entity_id, reason in sorted(reasons.items())
        ]
    for entity_id, reason in reasons.items():
        print(f"[task run] fast-fail abandon download entity: {entity_id} ({reason})")
        mark_abandoned_entities(
            ctx.task_id,
            ctx.batch_id,
            [entity_id],
            stage="download_fetch",
            reason=reason,
        )
    _apply_abandoned_entities(ctx, load_workflow_state(ctx.task_id, ctx.batch_id))
    from download.gate import gate_download

    return gate_download(ctx.task_id, ctx.batch_id, target_entities=set(ctx.entity_ids))


def _download_plan_unresolved_entities(ctx: PipelineContext) -> dict[str, dict[str, list[str]]]:
    etype = _coverage_entity_type(ctx.spec)
    unresolved: dict[str, dict[str, list[str]]] = {}
    abandoned = _abandoned_entity_ids(load_workflow_state(ctx.task_id, ctx.batch_id))
    for entity in ctx.entity_ids:
        if entity in abandoned:
            continue
        lane_issues = {
            lane: issues
            for lane in ("homepage", "article", "image")
            if (issues := _download_research_lane_issues(ctx, entity, etype, lane))
        }
        if lane_issues:
            unresolved[entity] = lane_issues
    return unresolved


_DETERMINISTIC_DOWNLOAD_ISSUE_MARKERS = (
    "unsupported license",
    "imageRights",
    "missing rights",
    "authorization",
    "blocked source",
    "blocked platform",
    "sourceUseMode=blocked",
    "weak entity match",
    "probe page",
    "not fetchable",
    "manual_authorized_gallery_or_target_replacement",
    "授权不兼容",
    "弱匹配",
    "不可抓",
)


def _download_plan_issue_is_deterministic(issue: str) -> bool:
    text = str(issue or "")
    lowered = text.casefold()
    return any(marker.casefold() in lowered for marker in _DETERMINISTIC_DOWNLOAD_ISSUE_MARKERS)


def _deterministic_download_plan_unresolved(
    unresolved: Mapping[str, Mapping[str, list[str]]],
) -> dict[str, dict[str, list[str]]]:
    deterministic: dict[str, dict[str, list[str]]] = {}
    for entity_id, lanes in unresolved.items():
        matched: dict[str, list[str]] = {}
        for lane, issues in lanes.items():
            lane_hits = [str(issue) for issue in issues if _download_plan_issue_is_deterministic(str(issue))]
            if lane_hits:
                matched[str(lane)] = lane_hits
        if matched:
            deterministic[str(entity_id)] = matched
    return deterministic


def _flatten_download_plan_issues(lanes: Mapping[str, list[str]]) -> list[str]:
    rows: list[str] = []
    for lane, issues in lanes.items():
        for issue in issues:
            text = str(issue or "").strip()
            if text:
                rows.append(f"{lane}: {text}")
    return rows


def _normalized_download_issue_reason(issue: str) -> str:
    text = str(issue or "").split(":", 1)[-1].strip()
    text = re.sub(r"=\d+", "=N", text)
    text = re.sub(r"\d+", "N", text)
    return text


def _entity_ids_from_issue_messages(entity_ids: list[str], issues: list[str]) -> list[str]:
    """Return entities explicitly named in checkpoint issue rows, preserving task order."""

    rows = [str(issue or "") for issue in issues if str(issue or "").strip()]
    if not rows:
        return []
    out: list[str] = []
    for entity_id in entity_ids:
        if any(row.startswith(f"{entity_id}:") or entity_id in row for row in rows):
            out.append(entity_id)
    return out


def _build_prepare_homepage_unresolved_entities(ctx: PipelineContext) -> dict[str, dict[str, list[str]]]:
    """Map build_prepare homepage base-draft failures back to homepage source repair.

    `build_prepare` is the first deterministic stage that can inspect fetched
    homepage source units and decide whether the chosen encyclopedia/official
    base draft has enough usable facts. When it fails, the next download_plan
    pass must repair the homepage lane for only those entities; otherwise the
    workflow can claim the source plan is ready and loop back into the same
    downstream gate.
    """

    state = load_workflow_state(ctx.task_id, ctx.batch_id)
    rows = [str(item or "") for item in (state.get("failedObjects") or []) if str(item or "").strip()]
    if not rows:
        return {}
    markers = (
        "homepage baseDraft",
        "entity homepage baseDraft",
        "homepage baseDraft.text",
        "baseDraft.sourceRef",
    )
    unresolved: dict[str, dict[str, list[str]]] = {}
    for entity_id in ctx.entity_ids:
        hits = [
            row for row in rows
            if entity_id in row and any(marker in row for marker in markers)
        ]
        if not hits:
            continue
        lane_issues = unresolved.setdefault(entity_id, {}).setdefault("homepage", [])
        for hit in hits:
            text = f"build_prepare homepage base draft repair required: {hit}"
            if text not in lane_issues:
                lane_issues.append(text)
    return unresolved


def _write_download_plan_availability(
    ctx: PipelineContext,
    unresolved: Mapping[str, Mapping[str, list[str]]],
    *,
    source: str = "lane_verdict",
) -> dict[str, Any]:
    state = load_workflow_state(ctx.task_id, ctx.batch_id)
    abandoned = _abandoned_entity_ids(state)
    active = [entity for entity in ctx.entity_ids if entity not in abandoned]
    merged_unresolved: dict[str, dict[str, list[str]]] = {
        str(entity_id): {
            str(lane): [str(issue) for issue in issues if str(issue).strip()]
            for lane, issues in (lanes or {}).items()
        }
        for entity_id, lanes in unresolved.items()
        if str(entity_id).strip()
    }
    for entity_id, lanes in _pending_download_repair_unresolved(ctx).items():
        entity_lanes = merged_unresolved.setdefault(entity_id, {})
        for lane, issues in lanes.items():
            entity_lanes.setdefault(lane, [])
            for issue in issues:
                text = str(issue or "").strip()
                if text and text not in entity_lanes[lane]:
                    entity_lanes[lane].append(text)
    ineligible: list[dict[str, Any]] = []
    deterministic = _deterministic_download_plan_unresolved(merged_unresolved)
    for entity_id in active:
        lanes = merged_unresolved.get(entity_id) or {}
        if not lanes:
            continue
        issues = _flatten_download_plan_issues(lanes)
        deterministic_lanes = deterministic.get(entity_id) or {}
        status = "replacement_needed" if deterministic_lanes else "repairable"
        ineligible.append(
            {
                "entityId": entity_id,
                "status": status,
                "lanes": sorted(str(lane) for lane in lanes),
                "issues": issues,
                "issueReasons": sorted({_normalized_download_issue_reason(issue) for issue in issues}),
                "nextActions": (
                    ["target_replacement_or_manual_authorization"]
                    if deterministic_lanes
                    else ["source_repair"]
                ),
                "deterministic": bool(deterministic_lanes),
                "deterministicLanes": sorted(str(lane) for lane in deterministic_lanes),
            }
        )
    ineligible_ids = {str(item.get("entityId") or "") for item in ineligible}
    ready = [entity for entity in active if entity not in ineligible_ids]
    report = {
        "schemaVersion": "quwoquan.download.source_availability",
        "taskId": ctx.task_id,
        "batchId": ctx.batch_id,
        "source": source,
        "updatedAt": store.now_iso(),
        "readyTargets": ready,
        "readyTargetCount": len(ready),
        "ineligibleTargets": ineligible,
        "ineligibleTargetCount": len(ineligible),
        "abandonedTargets": sorted(abandoned),
    }
    write_json(batch_root(ctx.task_id, ctx.batch_id) / "_shared" / "source_unavailable_targets.json", report)
    _sync_auto_research_availability(ctx, report)
    return report


def _pending_download_repair_unresolved(ctx: PipelineContext) -> dict[str, dict[str, list[str]]]:
    """Expose pending download repair as source-availability ineligible rows.

    A source plan can look lane-complete while the last fetch gate still proves
    its sources were rejected or underfilled. Availability must reflect that
    pending repair, otherwise target selection and scale audit will treat the
    object as ready and move failure pressure downstream.
    """
    repair_path = _download_repair_path(ctx)
    if not repair_path.is_file():
        return {}
    try:
        repair = read_json(repair_path)
    except (OSError, ValueError, TypeError):
        return {}
    abandoned = _abandoned_entity_ids(load_workflow_state(ctx.task_id, ctx.batch_id))
    scoped_entities = {str(entity_id) for entity_id in ctx.entity_ids}
    unresolved: dict[str, dict[str, list[str]]] = {}
    for row in repair.get("entities") or []:
        if not isinstance(row, dict) or not _download_repair_entry_pending(row):
            continue
        entity_id = str(row.get("entityId") or "").strip()
        if not entity_id or entity_id in abandoned or entity_id not in scoped_entities:
            continue
        lanes = _download_repair_lanes(row) or {"download"}
        active_issues = _download_repair_active_issues(ctx, row)
        if not active_issues:
            continue
        for lane in lanes:
            unresolved.setdefault(entity_id, {}).setdefault(str(lane), [])
            for issue in active_issues:
                text = f"download_repair required: {issue}"
                if text not in unresolved[entity_id][str(lane)]:
                    unresolved[entity_id][str(lane)].append(text)
    return unresolved


def _format_download_unresolved(
    unresolved: Mapping[str, Mapping[str, list[str]]],
    *,
    prefix: str,
) -> list[str]:
    rows: list[str] = []
    for entity_id, lanes in sorted(unresolved.items()):
        lane_summary = "; ".join(
            f"{lane}: {', '.join(str(item) for item in issues[:3])}"
            for lane, issues in lanes.items()
        )
        rows.append(f"{entity_id}: {prefix}: {lane_summary}")
    return rows


def _auto_research_plan_path(ctx: PipelineContext) -> Path:
    return batch_root(ctx.task_id, ctx.batch_id) / "_shared" / "auto_research_plan.json"


def _auto_research_wave_summary(
    report: Mapping[str, Any],
    *,
    scope: str,
    entity_ids: list[str],
) -> dict[str, Any]:
    throughput = report.get("throughput") if isinstance(report.get("throughput"), Mapping) else {}
    availability = (
        report.get("sourceAvailability")
        if isinstance(report.get("sourceAvailability"), Mapping)
        else {}
    )
    return {
        "scope": scope,
        "entityIds": list(entity_ids),
        "entityCount": len(entity_ids),
        "issueCount": len(report.get("issues") or []),
        "sourceUnavailableCount": len(report.get("sourceUnavailable") or []),
        "updatedCount": len(report.get("updated") or []),
        "readyTargetCount": int((availability or {}).get("readyTargetCount") or 0),
        "ineligibleTargetCount": int((availability or {}).get("ineligibleTargetCount") or 0),
        "elapsedSeconds": float((throughput or {}).get("elapsedSeconds") or 0),
        "entitiesPerMinute": float((throughput or {}).get("entitiesPerMinute") or 0),
        "maxWorkers": int((throughput or {}).get("maxWorkers") or 0),
        "recordedAt": store.now_iso(),
    }


def _aggregate_auto_research_throughput(waves: list[Mapping[str, Any]]) -> dict[str, Any]:
    entity_count = sum(int(wave.get("entityCount") or 0) for wave in waves)
    elapsed = sum(float(wave.get("elapsedSeconds") or 0) for wave in waves)
    workers = max((int(wave.get("maxWorkers") or 0) for wave in waves), default=0)
    return {
        "maxWorkers": workers,
        "entityCount": entity_count,
        "elapsedSeconds": round(elapsed, 3),
        "entitiesPerMinute": round(entity_count / elapsed * 60, 3) if elapsed > 0 else 0,
        "waveCount": len(waves),
    }


def _write_auto_research_report(
    ctx: PipelineContext,
    wave_report: Mapping[str, Any],
    *,
    scope: str,
    entity_ids: list[str],
) -> dict[str, Any]:
    path = _auto_research_plan_path(ctx)
    existing: dict[str, Any] = {}
    if scope != "primary" and path.is_file():
        try:
            existing = read_json(path)
        except (OSError, ValueError, TypeError):
            existing = {}
    if scope == "primary" or not existing:
        aggregate: dict[str, Any] = dict(wave_report)
        aggregate["waves"] = []
    else:
        aggregate = dict(existing)
        aggregate["latestWaveSourceAvailability"] = wave_report.get("sourceAvailability") or {}
        for key in ("updated", "issues", "candidates", "imageCollections", "sourceUnavailable"):
            aggregate[key] = list(aggregate.get(key) or []) + list(wave_report.get(key) or [])
    wave = _auto_research_wave_summary(wave_report, scope=scope, entity_ids=entity_ids)
    waves = list(aggregate.get("waves") or [])
    waves.append(wave)
    aggregate["waves"] = waves
    aggregate["latestWave"] = wave
    aggregate["waveCount"] = len(waves)
    aggregate["throughput"] = _aggregate_auto_research_throughput(waves)
    if scope == "primary":
        aggregate["sourceAvailability"] = wave_report.get("sourceAvailability") or {}
    aggregate["updatedAt"] = store.now_iso()
    write_json(path, aggregate)
    return aggregate


def _sync_auto_research_availability(ctx: PipelineContext, availability: Mapping[str, Any]) -> None:
    path = _auto_research_plan_path(ctx)
    if not path.is_file():
        return
    try:
        report = read_json(path)
    except (OSError, ValueError, TypeError):
        return
    report["sourceAvailability"] = dict(availability)
    report["sourceAvailabilitySyncedAt"] = store.now_iso()
    write_json(path, report)


def _abandon_unresolved_download_plan_entities(
    ctx: PipelineContext,
    unresolved: Mapping[str, Mapping[str, list[str]]],
    *,
    reason_prefix: str,
) -> list[str]:
    active_entities = [entity for entity in ctx.entity_ids if entity not in _abandoned_entity_ids(load_workflow_state(ctx.task_id, ctx.batch_id))]
    scope = ctx.spec.get("scope") or {}
    reserve_names = {
        str(target.get("name") or "").strip()
        for target in (scope.get("reserveCoverageTargets") or [])
        if isinstance(target, Mapping) and str(target.get("name") or "").strip()
    }
    state = load_workflow_state(ctx.task_id, ctx.batch_id)
    replacement_capacity = len(
        reserve_names
        - set(active_entities)
        - _abandoned_entity_ids(state)
        - _replacement_entity_ids(state)
    )
    if not unresolved:
        return []
    if len(unresolved) >= len(active_entities) and replacement_capacity < len(unresolved):
        return []
    added: list[str] = []
    for entity_id, lanes in unresolved.items():
        lane_summary = "; ".join(
            f"{lane}: {', '.join(str(item) for item in issues[:3])}"
            for lane, issues in lanes.items()
        )
        result = mark_abandoned_entities(
            ctx.task_id,
            ctx.batch_id,
            [entity_id],
            stage="download_plan",
            reason=f"{reason_prefix}: {lane_summary}",
        )
        added.extend(str(item) for item in result.get("added") or [])
    return added


def _abandon_source_unavailable_entities(
    ctx: PipelineContext,
    report: Mapping[str, Any],
    *,
    reason_prefix: str,
) -> list[str]:
    """Fast-fail entities that deterministic source discovery marks unrecoverable.

    Agent repair is still useful for category gaps or a missing guide source.
    It should not spend retries on targets whose current public-source lane has
    no publishable image rights and explicitly needs manual authorization or
    target replacement.
    """

    availability = report.get("sourceAvailability") if isinstance(report, Mapping) else None
    if not isinstance(availability, Mapping):
        availability = (
            report
            if isinstance(report, Mapping) and isinstance(report.get("ineligibleTargets"), list)
            else {}
        )
    ineligible = availability.get("ineligibleTargets") if isinstance(availability, Mapping) else []
    if not isinstance(ineligible, list):
        return []
    state = load_workflow_state(ctx.task_id, ctx.batch_id)
    abandoned = _abandoned_entity_ids(state)
    active_entities = [entity for entity in ctx.entity_ids if entity not in abandoned]
    scope = ctx.spec.get("scope") or {}
    reserve_names = {
        str(target.get("name") or "").strip()
        for target in (scope.get("reserveCoverageTargets") or [])
        if isinstance(target, Mapping) and str(target.get("name") or "").strip()
    }
    used_names = set(active_entities) | abandoned
    used_names.update(_replacement_entity_ids(state))
    replacement_capacity = len(reserve_names - used_names)
    to_abandon: list[tuple[str, str]] = []
    for raw in ineligible:
        if not isinstance(raw, Mapping):
            continue
        entity_id = str(raw.get("entityId") or "").strip()
        if not entity_id or entity_id in abandoned:
            continue
        issues = [str(item) for item in (raw.get("issues") or []) if str(item).strip()]
        blockers = raw.get("blockers") or []
        next_actions = [str(item) for item in (raw.get("nextActions") or []) if str(item).strip()]
        for blocker in blockers:
            if isinstance(blocker, Mapping):
                action = str(blocker.get("nextAction") or "").strip()
                reason = str(blocker.get("reason") or "").strip()
                if action:
                    next_actions.append(action)
                if reason:
                    issues.append(reason)
        combined = " ; ".join([*issues, *next_actions])
        unrecoverable = (
            "manual_authorized_gallery_or_target_replacement" in combined
            or "manual_homepage_seed_source_or_target_replacement" in combined
            or "homepage has no encyclopedia/official seed source" in combined
            or "no rights-compatible" in combined
            or "no single-author/single-file rights-cleared image collection" in combined
        )
        if unrecoverable:
            reason = "; ".join(issues[:4]) or "source availability marked unrecoverable"
            to_abandon.append((entity_id, reason))
    if not to_abandon:
        return []
    if replacement_capacity < len(to_abandon):
        _top_up_reserve_targets_from_discovery(ctx, needed=len(to_abandon) - replacement_capacity)
        scope = ctx.spec.get("scope") or {}
        reserve_names = {
            str(target.get("name") or "").strip()
            for target in (scope.get("reserveCoverageTargets") or [])
            if isinstance(target, Mapping) and str(target.get("name") or "").strip()
        }
        used_names = set(active_entities) | abandoned
        used_names.update(_replacement_entity_ids(load_workflow_state(ctx.task_id, ctx.batch_id)))
        replacement_capacity = len(reserve_names - used_names)
    if len(to_abandon) >= len(active_entities) and replacement_capacity < len(to_abandon):
        return []
    if not _workflow_allows_partial_content(ctx):
        return []
    policy = ctx.spec.get("workflowPolicy") if isinstance(ctx.spec.get("workflowPolicy"), Mapping) else {}
    acceptance = ctx.spec.get("acceptance") if isinstance(ctx.spec.get("acceptance"), Mapping) else {}
    try:
        min_entities = int((acceptance or {}).get("minEntities") or 0)
    except (TypeError, ValueError):
        min_entities = 0
    requires_replacement = (
        str((policy or {}).get("deliveryMode") or "") == "partial_with_replacement_report"
        or min_entities >= len(active_entities)
    )
    if requires_replacement and replacement_capacity < len(to_abandon):
        return []
    added: list[str] = []
    for entity_id, reason in to_abandon:
        result = mark_abandoned_entities(
            ctx.task_id,
            ctx.batch_id,
            [entity_id],
            stage="download_plan",
            reason=f"{reason_prefix}: {reason}",
        )
        added.extend(str(item) for item in result.get("added") or [])
    return added


def _auto_report_needs_target_replacement(report: Mapping[str, Any]) -> bool:
    availability = report.get("sourceAvailability") if isinstance(report, Mapping) else None
    if not isinstance(availability, Mapping):
        availability = (
            report
            if isinstance(report, Mapping) and isinstance(report.get("ineligibleTargets"), list)
            else {}
        )
    ineligible = availability.get("ineligibleTargets") if isinstance(availability, Mapping) else []
    if not isinstance(ineligible, list):
        return False
    replacement_markers = (
        "manual_authorized_gallery_or_target_replacement",
        "manual_homepage_seed_source_or_target_replacement",
        "homepage has no encyclopedia/official seed source",
        "no rights-compatible",
        "no single-author/single-file rights-cleared image collection",
    )
    for raw in ineligible:
        if not isinstance(raw, Mapping):
            continue
        if bool(raw.get("deterministic")) or str(raw.get("status") or "") == "replacement_needed":
            return True
        parts: list[str] = []
        parts.extend(str(item) for item in (raw.get("issues") or []) if str(item).strip())
        parts.extend(str(item) for item in (raw.get("nextActions") or []) if str(item).strip())
        for blocker in raw.get("blockers") or []:
            if isinstance(blocker, Mapping):
                parts.append(str(blocker.get("reason") or ""))
                parts.append(str(blocker.get("nextAction") or ""))
        combined = " ; ".join(parts)
        if any(marker in combined for marker in replacement_markers):
            return True
    return False


def _run_download_auto_research(
    ctx: PipelineContext,
    entity_ids: list[str],
    *,
    entity_type: str,
    force: bool = False,
    scope: str = "primary",
) -> dict[str, Any]:
    from download.research_plan import write_auto_research_plans

    auto_report = write_auto_research_plans(
        ctx.task_id,
        ctx.batch_id,
        entity_ids,
        entity_type=entity_type,
        force=force,
        max_workers=max(1, min(int(ctx.max_workers or 1), 8)),
        progress_callback=_download_auto_research_progress_callback(ctx),
    )
    _write_auto_research_report(ctx, auto_report, scope=scope, entity_ids=entity_ids)
    return auto_report


def _refresh_stale_source_plans_for_fetch(
    ctx: PipelineContext,
    entity_ids: list[str],
) -> list[str]:
    """Refresh retry-scope source plans when rules changed after checkpoint.

    A completed download_plan checkpoint is durable state, but source registry,
    rights policy, and research code are executable contract inputs. When those
    files change while a batch is stuck at download_fetch, retrying the fetch
    against old plans just repeats the same failure. Refresh only the scoped
    repair entities before fetching so upstream rules are applied upstream.
    """
    stale_entities = _stale_source_plan_entities(ctx, entity_ids=entity_ids)
    stale_ids = [str(item.get("entityId") or "") for item in stale_entities if item.get("entityId")]
    if not stale_ids:
        return entity_ids
    from download.prepare import prepare_source_plan

    etype = _coverage_entity_type(ctx.spec)
    prepare_source_plan(
        ctx.task_id,
        ctx.batch_id,
        [{"entityId": entity_id, "canonicalName": entity_id, "entityType": etype} for entity_id in stale_ids],
    )
    _run_download_auto_research(
        ctx,
        stale_ids,
        entity_type=etype,
        force=True,
        scope="download_fetch_stale_source_plan",
    )
    return entity_ids


def _source_plan_filled_for_entities(
    ctx: PipelineContext,
    entity_ids: list[str],
) -> tuple[bool, list[str]]:
    scoped = copy.copy(ctx)
    scoped.entity_ids = list(entity_ids)
    try:
        return _source_plan_filled(scoped, include_download_repair=False)
    except TypeError:
        # Tests may monkeypatch _source_plan_filled with the historical one-arg
        # callable. Keep that seam compatible while production skips batch-wide
        # download repair scans for scoped replacement screening.
        return _source_plan_filled(scoped)


def _workflow_policy_int(ctx: PipelineContext, key: str, default: int, *, minimum: int = 1) -> int:
    policy = ctx.spec.get("workflowPolicy") if isinstance(ctx.spec.get("workflowPolicy"), Mapping) else {}
    raw = policy.get(key, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)


def _replacement_screening_limits(ctx: PipelineContext) -> tuple[int, int, int]:
    return (
        _workflow_policy_int(ctx, "maxReplacementWaves", REPLACEMENT_MAX_WAVES),
        _workflow_policy_int(ctx, "maxReplacementCandidatesPerWave", REPLACEMENT_MAX_CANDIDATES_PER_WAVE),
        _workflow_policy_int(ctx, "maxReplacementScreenedPerRun", REPLACEMENT_MAX_SCREENED_PER_RUN),
    )


def _screen_replacement_targets(
    ctx: PipelineContext,
    *,
    entity_type: str,
    reason: str,
    needed: int,
    scope: str,
) -> tuple[list[str], list[str], dict[str, Any]]:
    """Prepare and gate replacement candidates before making them active."""
    from download.prepare import prepare_source_plan

    _max_waves, max_per_wave, max_total = _replacement_screening_limits(ctx)
    state = load_workflow_state(ctx.task_id, ctx.batch_id)
    screened_count = len(_replacement_entity_ids(state))
    remaining_budget = max_total - screened_count
    if remaining_budget <= 0:
        existing_policy = (
            state.get("replacementPolicy")
            if isinstance(state.get("replacementPolicy"), Mapping)
            else {}
        )
        state["replacementPolicy"] = {
            **existing_policy,
            "screenedReplacementCount": screened_count,
            "maxReplacementScreenedPerRun": max_total,
            "screeningStoppedReason": "replacement_screening_limit",
        }
        state["nextAction"] = (
            f"replacement screening stopped: screenedReplacementCount={screened_count} "
            f">= maxReplacementScreenedPerRun={max_total}"
        )
        save_workflow_state(state)
        return [], [], {
            "sourceAvailability": {
                "readyTargets": [],
                "ineligibleTargets": [],
                "screeningStoppedReason": "replacement_screening_limit",
            }
        }
    capped_needed = max(1, min(int(needed or 1), max_per_wave, remaining_budget))
    candidates = _next_replacement_candidates(ctx, needed=capped_needed)
    if not candidates:
        return [], [], {}
    candidate_ids = [item["entityId"] for item in candidates]
    prepare_source_plan(
        ctx.task_id,
        ctx.batch_id,
        [
            {
                "entityId": item["entityId"],
                "canonicalName": item["entityId"],
                "entityType": item["entityType"],
            }
            for item in candidates
        ],
    )
    report = _run_download_auto_research(
        ctx,
        candidate_ids,
        entity_type=entity_type,
        force=False,
        scope=scope,
    )
    activated: list[str] = []
    rejected: list[str] = []
    for item in candidates:
        entity_id = item["entityId"]
        candidate_type = item["entityType"]
        ok, missing = _source_plan_filled_for_entities(ctx, [entity_id])
        if ok:
            _append_replacement_row(
                ctx,
                entity_id=entity_id,
                entity_type=candidate_type,
                status="active",
                reason=reason,
                source_gate_status="passed",
            )
            if entity_id not in ctx.entity_ids:
                ctx.entity_ids.append(entity_id)
            activated.append(entity_id)
            continue
        _append_replacement_row(
            ctx,
            entity_id=entity_id,
            entity_type=candidate_type,
            status="rejected",
            reason=reason,
            source_gate_status="failed",
            issues=missing,
        )
        mark_abandoned_entities(
            ctx.task_id,
            ctx.batch_id,
            [entity_id],
            stage="download_plan",
            reason=f"{reason}: replacement source gate failed: {'; '.join(missing[:4])}",
        )
        rejected.append(entity_id)
    if activated:
        state = load_workflow_state(ctx.task_id, ctx.batch_id)
        active_count = len([entity for entity in ctx.entity_ids if entity not in _abandoned_entity_ids(state)])
        state["replacementPolicy"] = {
            "mode": "partial_with_replacement_report",
            "minEntities": int((ctx.spec.get("acceptance") or {}).get("minEntities") or active_count),
            "activeTargetCount": active_count,
            "screenedReplacementCount": len(_replacement_entity_ids(state)),
        }
        state["nextAction"] = f"activated gated replacement targets: {', '.join(activated[:8])}"
        save_workflow_state(state)
    return activated, rejected, report


def _rerun_auto_research_with_replacements(
    ctx: PipelineContext,
    auto_report: Mapping[str, Any],
    *,
    entity_type: str,
    reason_prefix: str,
) -> tuple[bool, list[str], list[str], dict[str, Any]]:
    """Repeat source-unavailable replacement waves while reserve capacity exists."""
    scope = ctx.spec.get("scope") if isinstance(ctx.spec.get("scope"), Mapping) else {}
    reserve_count = len(
        [
            target for target in (scope.get("reserveCoverageTargets") or [])
            if isinstance(target, Mapping) and str(target.get("name") or "").strip()
        ]
    )
    configured_max_waves, _max_per_wave, _max_total = _replacement_screening_limits(ctx)
    max_waves = max(1, min(reserve_count + 1, configured_max_waves))
    abandoned_all: list[str] = []
    current_report: dict[str, Any] = dict(auto_report)
    missing: list[str] = []
    replacement_shortfall = False
    for _wave_index in range(max_waves):
        if replacement_shortfall:
            abandoned = ["replacement_shortfall"]
        else:
            abandoned = _abandon_source_unavailable_entities(
                ctx,
                current_report,
                reason_prefix=reason_prefix,
            )
        if not abandoned:
            break
        if not replacement_shortfall:
            abandoned_all.extend(abandoned)
        _apply_abandoned_entities(
            ctx,
            load_workflow_state(ctx.task_id, ctx.batch_id),
            activate_replacements=False,
        )
        activated, rejected, current_report = _screen_replacement_targets(
            ctx,
            entity_type=entity_type,
            reason="keep target count after abandoned source-unavailable entity",
            needed=max(1, len(abandoned)),
            scope=f"replacement_wave_{_wave_index + 1}",
        )
        if not activated and not rejected:
            _write_download_plan_availability(
                ctx,
                _download_plan_unresolved_entities(ctx),
                source=f"replacement_wave_{_wave_index + 1}_no_new_target",
            )
            _ok, missing = _source_plan_filled(ctx)
            break
        ok_after_wave, missing_after_wave = _source_plan_filled(ctx)
        _write_download_plan_availability(
            ctx,
            _download_plan_unresolved_entities(ctx),
            source=f"replacement_wave_{_wave_index + 1}",
        )
        missing = missing_after_wave
        if ok_after_wave:
            return True, abandoned_all, [], current_report
        replacement_shortfall = bool(rejected and not activated)
    if not missing:
        _ok, missing = _source_plan_filled(ctx)
    return False, abandoned_all, missing, current_report


def _homepages_done(ctx: PipelineContext) -> tuple[bool, list[str]]:
    """build_homepage checkpoint：coverage 实体三件套是否物化（用 build validate 复核）。"""
    from build.homepage import validate_entity_pages
    issues = validate_entity_pages(ctx.task_id, ctx.batch_id, _active_spec(ctx))
    return (not issues), issues


def _homepage_pending_entities(ctx: PipelineContext) -> list[str]:
    """Return only active homepage objects that still fail per-entity validate.

    Managed retries must not re-run already accepted homepage triplets; otherwise
    a single slow/failed Cursor job can multiply token cost and overwrite stable
    evidence. The validator remains the source of truth, not Agent self-report.
    """
    from build.homepage import region_keys, season_keys, validate_entity_page

    region_set = set(region_keys())
    season_set = set(season_keys())
    pending: list[str] = []
    for target in ((_active_spec(ctx).get("scope") or {}).get("coverageTargets") or []):
        name = str(target.get("name") or "").strip()
        if not name:
            continue
        domain, etype = require_domain_etype(
            target.get("entityType"),
            context=f"coverageTargets[{name}]",
        )
        issues = validate_entity_page(
            ctx.task_id,
            ctx.batch_id,
            domain,
            etype,
            name,
            region_set=region_set,
            season_set=season_set,
        )
        if issues:
            pending.append(name)
    return pending


def _content_plan_done(ctx: PipelineContext) -> tuple[bool, list[str]]:
    """content_plan checkpoint：篇目包+注册+brief 是否就绪。"""
    from _common.content_plan import validate_content_plan

    _prune_content_plan_extra_briefs(ctx)
    issues = validate_content_plan(ctx.task_id, ctx.batch_id, _active_spec(ctx))
    return (not issues), issues


def _prune_content_plan_extra_briefs(ctx: PipelineContext) -> list[str]:
    """Remove filesystem brief objects that are no longer registered.

    Agent repairs may rewrite content_plan_packet/index while leaving old
    posts/**/3.compose/brief.json trees behind. Downstream produce must consume
    only the packet/index truth source, so stale object trees are pruned before
    validating the checkpoint.
    """

    from _common.content_object import BRIEF_FILE, content_object_stage_dir, load_index
    from _common.paths import STAGE_COMPOSE

    root = batch_root(ctx.task_id, ctx.batch_id)
    posts_root = root / "posts"
    if not posts_root.is_dir():
        return []
    index = load_index(ctx.task_id, ctx.batch_id)
    expected: set[Path] = set()
    for ref in index:
        try:
            expected.add((content_object_stage_dir(ctx.task_id, ctx.batch_id, ref, STAGE_COMPOSE) / BRIEF_FILE).resolve())
        except (KeyError, OSError, ValueError):
            continue
    actual = {
        path.resolve()
        for path in posts_root.glob(f"*/*/*/*/{STAGE_COMPOSE}/{BRIEF_FILE}")
        if path.is_file()
    }
    removed: list[str] = []
    for brief_path in sorted(actual - expected):
        object_dir = brief_path.parents[1]
        rel = object_dir.relative_to(root).as_posix() if object_dir.is_relative_to(root) else object_dir.as_posix()
        shutil.rmtree(object_dir)
        removed.append(rel)
    if removed:
        print(
            "[task run] Pruned stale content_plan brief object(s): "
            + ", ".join(removed[:12])
            + (" ..." if len(removed) > 12 else "")
        )
    return removed


def _drafts_authored(ctx: PipelineContext) -> tuple[bool, list[str]]:
    """produce_author checkpoint：compose 后的 prose drafts 是否被 Agent 创作。

    Image works are structural source-collection objects. They do not require
    article drafts and must not block the author checkpoint.
    """
    from _common import content_object
    from _common.draft_io import is_placeholder, iter_draft_articles
    from _common.paths import STAGE_REVIEW
    state = load_workflow_state(ctx.task_id, ctx.batch_id)
    abandoned_refs = _abandoned_content_refs(state)
    content_refs = content_object.iter_content_refs(ctx.task_id, ctx.batch_id)
    active_article_refs = [
        ref for ref in content_refs
        if ref not in abandoned_refs
        and (content_object.content_coords(ctx.task_id, ctx.batch_id, ref) or {}).get("contentType") != "image"
    ]
    if not content_refs:
        return False, ["(no content objects; run compose-brief first)"]
    if not active_article_refs:
        return True, []
    articles = [
        (ref, art)
        for ref, art in iter_draft_articles(ctx.task_id, ctx.batch_id)
        if ref in set(active_article_refs)
    ]
    if not articles:
        return False, ["(no article drafts; run compose-brief first)"]
    pending: list[str] = []
    for ref, art in articles:
        if ref in abandoned_refs:
            continue
        draft_needs_agent = False
        if is_placeholder(art.read_text(encoding="utf-8")):
            draft_needs_agent = True
        else:
            try:
                review_dir = content_object.content_object_stage_dir(
                    ctx.task_id, ctx.batch_id, ref, STAGE_REVIEW
                )
            except KeyError:
                review_dir = None
            if review_dir is not None:
                repair_report = review_dir / "repair_report.json"
                if repair_report.is_file():
                    try:
                        draft_needs_agent = repair_report.stat().st_mtime >= art.stat().st_mtime
                    except OSError:
                        draft_needs_agent = True
        if draft_needs_agent:
            pending.append(ref)
    return (not pending), pending


def _content_issue_matchers(
    ctx: PipelineContext,
    *,
    exclude_refs: set[str] | None = None,
) -> dict[str, set[str]]:
    from _common import content_object

    exclude_refs = exclude_refs or set()
    matchers: dict[str, set[str]] = {}
    for ref in content_object.iter_content_refs(ctx.task_id, ctx.batch_id):
        if ref in exclude_refs:
            continue
        tokens = {ref}
        try:
            rel = content_object.content_object_rel(ctx.task_id, ctx.batch_id, ref)
        except KeyError:
            matchers[ref] = tokens
            continue
        tokens.add(rel)
        if rel.startswith("posts/"):
            tokens.add(rel[len("posts/"):])
        matchers[ref] = {token for token in tokens if token}
    return matchers


def _produce_review_retry_refs(ctx: PipelineContext, issues: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    """Map review failures to refs without invalidating current green objects."""
    from _common import content_object

    abandoned_refs = _abandoned_content_refs(load_workflow_state(ctx.task_id, ctx.batch_id))
    matchers = _content_issue_matchers(ctx, exclude_refs=abandoned_refs)
    affected: set[str] = set()
    issue_map: dict[str, list[str]] = {}
    saw_object_gate = False
    for ref in content_object.iter_content_refs(ctx.task_id, ctx.batch_id):
        if ref in abandoned_refs:
            continue
        try:
            gate_path = (
                content_object.content_object_dir(ctx.task_id, ctx.batch_id, ref)
                / "5.review"
                / "review_gate.json"
            )
        except KeyError:
            continue
        if not gate_path.is_file():
            continue
        saw_object_gate = True
        envelope = read_json(gate_path)
        payload = envelope.get("payload") or envelope
        if payload.get("passed") is False:
            affected.add(ref)
            issue_map[ref] = [str(item) for item in (payload.get("issues") or [])]

    # Object gates are the latest and most precise verdict. Batch/release issues
    # often mention every object path and must not widen a two-ref repair to all.
    if saw_object_gate and affected:
        return sorted(affected), issue_map
    if saw_object_gate:
        reducer_path = batch_root(ctx.task_id, ctx.batch_id) / "_shared" / "batch_reducer_gate.json"
        if reducer_path.is_file():
            reducer = read_json(reducer_path)
            reducer_refs = [
                str(ref)
                for ref in (reducer.get("affectedRefs") or [])
                if str(ref) in matchers
            ]
            if reducer_refs:
                reducer_issues = [str(item) for item in (reducer.get("issues") or issues or [])]
                return sorted(set(reducer_refs)), {
                    ref: list(reducer_issues) for ref in reducer_refs
                }
        if not issues:
            return [], {}

    unmatched: list[str] = []
    for raw_issue in issues or []:
        issue = str(raw_issue)
        matched_refs = [
            ref
            for ref, tokens in matchers.items()
            if any(token and token in issue for token in tokens)
        ]
        if not matched_refs:
            unmatched.append(issue)
            continue
        for ref in matched_refs:
            affected.add(ref)
            issue_map.setdefault(ref, []).append(issue)

    if not affected and not saw_object_gate:
        affected = {
            ref
            for ref in content_object.iter_content_refs(ctx.task_id, ctx.batch_id)
            if ref not in abandoned_refs
        }
    if not affected:
        return [], {}

    refs = sorted(affected)
    for ref in refs:
        issue_map.setdefault(ref, [])
    if unmatched:
        for ref in refs:
            issue_map[ref].extend(unmatched)
    return refs, issue_map


def _invalidate_ref_for_retry(ctx: PipelineContext, ref: str) -> bool:
    """清理旧草稿/旧成品，让 rewound workflow 真正回到待重写状态。"""
    from _common import content_object
    from _common.draft_io import draft_package_dir, write_placeholder_draft

    try:
        obj_dir = content_object.content_object_dir(ctx.task_id, ctx.batch_id, ref)
        draft_dir = draft_package_dir(ctx.task_id, ctx.batch_id, ref)
    except KeyError:
        return False

    write_placeholder_draft(ctx.task_id, ctx.batch_id, ref)

    author_self_check = draft_dir / "author_self_check.json"
    if author_self_check.is_file():
        author_self_check.unlink()

    review_dir = obj_dir / "5.review"
    for name in ("ref_review_gate.json", "provenance.json", "review_ledger.json", "review_entities.json"):
        path = review_dir / name
        if path.is_file():
            path.unlink()

    for name in ("article.md", "gallery.md", "manifest.json", "_object.json"):
        path = obj_dir / name
        if path.is_file():
            path.unlink()

    assets_dir = obj_dir / "assets"
    if assets_dir.is_dir():
        shutil.rmtree(assets_dir)

    content_object.write_content_object_index(ctx.task_id, ctx.batch_id, ref)
    return True


def _purge_author_queue_for_stale_workflow(
    ctx: PipelineContext,
    *,
    refs: list[str] | None = None,
    reason: str,
) -> None:
    from task import object_queue as oq

    result = oq.purge_jobs(ctx.task_id, ctx.batch_id, stage="author", refs=refs)
    removed = result.get("removed") or []
    if removed:
        print(
            f"[task run] 已清理过期 author queue ({reason}): "
            + ", ".join(removed[:12])
            + (" ..." if len(removed) > 12 else "")
        )


def _write_retry_reports_for_refs(
    ctx: PipelineContext,
    *,
    refs: list[str],
    issue_map: dict[str, list[str]],
    target_stage: str,
) -> None:
    from _common.stage_reports import write_repair_report

    fallback_stage = "download" if target_stage == "download_plan" else "agent_compose"
    rerun_chain = (
        ["download", "quality_analysis", "compose-brief", "review", "materialize"]
        if fallback_stage == "download"
        else ["agent_compose", "review", "materialize"]
    )
    for ref in refs:
        write_repair_report(
            task_id=ctx.task_id,
            batch_id=ctx.batch_id,
            command="produce",
            ref=ref,
            failed_stage="review",
            failed_gate="post_verify",
            issues=issue_map.get(ref) or ["produce_review gate failed; inspect current batch issues"],
            fallback_stage=fallback_stage,
            rerun_chain=rerun_chain,
        )


def _prepare_produce_review_retry(ctx: PipelineContext, result: StageResult, target_stage: str) -> bool:
    from task import object_queue as oq
    from _common.draft_io import read_writing_pack

    refs, issue_map = _produce_review_retry_refs(ctx, result.issues)
    abandoned_refs = _abandoned_content_refs(load_workflow_state(ctx.task_id, ctx.batch_id))
    refs = [ref for ref in refs if ref not in abandoned_refs]
    if not refs:
        return False
    _write_retry_reports_for_refs(ctx, refs=refs, issue_map=issue_map, target_stage=target_stage)
    if target_stage == "download_plan":
        _purge_author_queue_for_stale_workflow(ctx, reason="produce_review->download_plan")
        return True
    total_refs = max(1, len(_content_issue_matchers(ctx, exclude_refs=abandoned_refs)))
    bulk_limit = max(5, int(total_refs * 0.2))
    if len(refs) > bulk_limit:
        if os.environ.get("QWQ_PRODUCE_REVIEW_ALLOW_BULK_REPAIR", "0") != "1":
            print(
                "[task run] produce_review bulk failure; "
                f"{len(refs)}/{total_refs} refs exceed retry limit {bulk_limit}. "
                "Keeping drafts intact and requiring gate/prompt diagnosis.",
                file=sys.stderr,
            )
            return False
        print(
            "[task run] produce_review bulk repair override enabled; "
            f"resetting {len(refs)}/{total_refs} failed refs",
            file=sys.stderr,
        )
    _purge_author_queue_for_stale_workflow(ctx, refs=refs, reason="produce_review->produce_compose")
    reset = [ref for ref in refs if _invalidate_ref_for_retry(ctx, ref)]
    requeued = oq.requeue_refs(ctx.task_id, ctx.batch_id, reset, "author", reason="produce_review_retry") if reset else []
    missing = [ref for ref in reset if ref not in set(requeued)]
    for ref in missing:
        pack = read_writing_pack(ctx.task_id, ctx.batch_id, ref) or {}
        oq.enqueue_ref_job(
            ctx.task_id,
            ctx.batch_id,
            ref,
            "author",
            mutex_key=str(pack.get("baseSourceRef") or ref),
        )
    if reset:
        print(
            "[task run] 已为 produce_review 回退重置待重写 ref: "
            + ", ".join(reset[:12])
            + (" ..." if len(reset) > 12 else "")
        )
    return bool(reset)


# ─── 确定性 stage 执行（复用既有 handler）─────────────────────────────
def _run_download_fetch(ctx: PipelineContext) -> StageResult:
    from download.handler import handle_download
    from download.gate import gate_download
    retry_entity_ids = _download_retry_entity_ids(ctx)
    refresh_before_fetch_ids: list[str] = []
    if retry_entity_ids:
        target_entity_ids = retry_entity_ids
        refresh_before_fetch_ids = retry_entity_ids
    else:
        fetch_stale_ids = set(_download_fetch_stale_entity_ids(ctx))
        shortfall_ids = set(_content_plan_source_shortfall_entity_ids(ctx))
        target_ids = fetch_stale_ids | shortfall_ids
        target_entity_ids = [entity_id for entity_id in ctx.entity_ids if entity_id in target_ids]
        refresh_before_fetch_ids = [entity_id for entity_id in ctx.entity_ids if entity_id in shortfall_ids]
    if not target_entity_ids:
        return StageResult(
            "download_fetch",
            AUTO,
            "done",
            "current persisted download gate already passes",
        )
    if refresh_before_fetch_ids:
        _refresh_stale_source_plans_for_fetch(ctx, refresh_before_fetch_ids)
    if target_entity_ids != ctx.entity_ids:
        print(
            "[task run] download object repair/refresh: "
            + ", ".join(target_entity_ids)
        )
    download_lane = _download_retry_lane(ctx, target_entity_ids)
    if download_lane != "all":
        print(f"[task run] download lane-scoped repair: lane={download_lane}")
    ns = argparse.Namespace(
        task=ctx.task_id, batch=ctx.batch_id,
        entity_ids=",".join(target_entity_ids),
        entity_type=(ctx.spec.get("scope") or {}).get("entityTypes", [""])[0]
        if (ctx.spec.get("scope") or {}).get("entityTypes") else "",
        lane=download_lane,
        max_workers=max(1, int(ctx.max_workers or 1)),
    )
    try:
        handle_download(ns)
    except SystemExit as exc:
        code = int(getattr(exc, "code", 1) or 0)
        if code not in (0,):
            issues = gate_download(ctx.task_id, ctx.batch_id, target_entities=set(ctx.entity_ids))
            stage_issues = _download_stage_gate_issues(ctx, entity_ids=target_entity_ids)
            seen_issues = set(str(issue) for issue in issues)
            for issue in stage_issues:
                if str(issue) not in seen_issues:
                    issues.append(str(issue))
                    seen_issues.add(str(issue))
            if not issues:
                issues = [f"download handler exited non-zero ({code}) without persisted gate issues"]
            issues = _apply_download_fast_fail(ctx, issues)
            if not issues:
                repair_path = _download_repair_path(ctx)
                if repair_path.is_file():
                    repair_path.unlink()
                return StageResult(
                    "download_fetch",
                    AUTO,
                    "done",
                    "fetched sources after abandoning deterministic source-unavailable entities",
                )
            _record_download_repair(ctx, issues)
            message = f"download gate failed with exit code {code}"
            if issues:
                message += ": " + "; ".join(issues[:5])
            return StageResult(
                "download_fetch",
                AUTO,
                "failed",
                message,
                fallback_stage="download_plan",
                issues=issues,
            )
    except Exception as exc:  # noqa: BLE001
        _record_download_repair(ctx, [str(exc)])
        return StageResult(
            "download_fetch",
            AUTO,
            "failed",
            f"download handler failed: {exc}",
            fallback_stage="download_plan",
            issues=[str(exc)],
        )

    issues = gate_download(ctx.task_id, ctx.batch_id, target_entities=set(ctx.entity_ids))
    seen_issues = set(str(issue) for issue in issues)
    for issue in _download_stage_gate_issues(ctx, entity_ids=target_entity_ids):
        if str(issue) not in seen_issues:
            issues.append(str(issue))
            seen_issues.add(str(issue))
    if issues:
        issues = _apply_download_fast_fail(ctx, issues)
        if not issues:
            repair_path = _download_repair_path(ctx)
            if repair_path.is_file():
                repair_path.unlink()
            return StageResult(
                "download_fetch",
                AUTO,
                "done",
                "fetched sources after abandoning deterministic source-unavailable entities",
            )
        _record_download_repair(ctx, issues)
        return StageResult(
            "download_fetch",
            AUTO,
            "failed",
            "download gate failed:\n  - " + "\n  - ".join(issues[:10]),
            fallback_stage="download_plan",
            issues=issues,
        )
    repair_path = _download_repair_path(ctx)
    if repair_path.is_file():
        repair_path.unlink()
    return StageResult(
        "download_fetch",
        AUTO,
        "done",
        "fetched sources for " + ", ".join(target_entity_ids),
    )


def _run_build_prepare(ctx: PipelineContext) -> StageResult:
    from build.homepage import prepare_entity_pages, validate_entity_page_inputs

    active_spec = _active_spec(ctx)
    inputs_dir, refs = prepare_entity_pages(ctx.task_id, ctx.batch_id, active_spec)
    issues = validate_entity_page_inputs(ctx.task_id, ctx.batch_id, active_spec)
    if issues:
        return StageResult(
            "build_prepare",
            AUTO,
            "failed",
            "主页输入未就绪，需回到 download_plan/download_fetch 修复上游来源:\n  - "
            + "\n  - ".join(issues[:10]),
            fallback_stage="download_plan",
            issues=issues,
        )
    return StageResult("build_prepare", AUTO, "done", f"下发 {len(refs)} 个主页产出契约 -> {inputs_dir}")


def _run_build_validate(ctx: PipelineContext) -> StageResult:
    from build.homepage import validate_entity_pages
    issues = validate_entity_pages(ctx.task_id, ctx.batch_id, _active_spec(ctx))
    if issues:
        return StageResult("build_validate", AUTO, "failed",
                           "主页采纳门未过:\n  - " + "\n  - ".join(issues[:10]),
                           fallback_stage="build_homepage", issues=issues)
    return StageResult("build_validate", AUTO, "done", "所有 coverage 实体主页达标")


# 角度 → plan intent 映射（task.content.angles → blueprint intent）。
# 编排器默认每实体取首个 angle 生成 1 篇代表作，控制单批产量；
# 全角度扩产由独立 batch 串跑（refs 显式扩展），不在单次 run 内放大成 N×M。
_DEFAULT_ANGLE = "攻略"


def _entity_type_kind(entity_type: str) -> str:
    """scope.entityTypes 形如 '地点/景区' → plan 的 kind '景区'。"""
    return str(entity_type or "").split("/")[-1] or "景区"


def _run_produce_plan(ctx: PipelineContext) -> StageResult:
    """校验 content_plan 已物化 brief；无 quotas 时 legacy 每实体自动 brief。"""
    from _common.content_plan import (
        content_plan_quotas_required,
        load_content_plan_packet,
        validate_content_plan,
    )

    active_spec = _active_spec(ctx)
    if content_plan_quotas_required(active_spec):
        issues = validate_content_plan(ctx.task_id, ctx.batch_id, active_spec)
        if issues:
            return StageResult(
                "produce_plan",
                AUTO,
                "failed",
                "content_plan 未就绪:\n  - " + "\n  - ".join(issues[:10]),
                fallback_stage="content_plan",
                issues=issues,
            )
        packet = load_content_plan_packet(ctx.task_id, ctx.batch_id) or {}
        n = len(packet.get("items") or [])
        return StageResult(
            "produce_plan",
            AUTO,
            "done",
            f"content_plan 已物化 {n} 篇 brief，跳过自动 produce_plan",
        )

    from plan.brief import resolve_compose_brief
    from plan.handler import ENTITY_KIND_MAP
    from template.registry import TemplateRegistry
    from template.router import RouteRequest
    from _common.content_object import write_brief_object

    registry = TemplateRegistry.load()
    angles = (active_spec.get("content") or {}).get("angles") or [_DEFAULT_ANGLE]
    intent = str(angles[0])
    vertical = "campus" if str(active_spec.get("vertical")) == "campus" else "travel"

    written: list[str] = []
    for target in (active_spec.get("scope") or {}).get("coverageTargets") or []:
        name = str(target.get("name") or "").strip()
        if not name:
            continue
        etype = str(target.get("entityType") or "").strip()
        require_domain_etype(etype, context=f"coverageTargets[{name}]")
        kind = _entity_type_kind(etype)
        subject_type = ENTITY_KIND_MAP.get(kind, etype)
        entity_ref = f"/entity/{etype}/{name}"
        request = RouteRequest(
            vertical=vertical,
            subject_kind="entity",
            subject_type=subject_type,
            intent=intent,
        )
        brief = resolve_compose_brief(
            registry, request, title=f"{name}·{intent}", entity_refs=[entity_ref]
        )
        ref = f"{etype}__{name}".replace("/", "_")
        write_brief_object(ctx.task_id, ctx.batch_id, ref, brief, content_type="article")
        written.append(ref)
    return StageResult("produce_plan", AUTO, "done",
                       f"解析 {len(written)} 个实体 compose brief(intent={intent}) -> posts/.../3.compose/brief.json")


def _clear_compose_base_draft_assignments(
    ledger: dict[str, Any],
    selected_refs: list[str],
    overrides: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], list[str], bool]:
    """Clear stale base-draft assignments for refs/sources that will be recomposed.

    Re-runs must be driven by the current content plan, not by half-written state
    from an earlier attempt.  The source-side clear matters when an old ref used
    to occupy the source that the current content plan now assigns to another ref.
    """
    selected = set(selected_refs)
    selected_sources: dict[str, str] = {}
    duplicate_sources: list[str] = []
    for ref in selected_refs:
        override = overrides.get(ref) or {}
        source_ref = str(override.get("baseSourceRef") or "").strip()
        if not source_ref:
            continue
        previous = selected_sources.get(source_ref)
        if previous and previous != ref:
            duplicate_sources.append(f"{source_ref} -> {previous}, {ref}")
        selected_sources[source_ref] = ref

    current = dict(ledger.get("assignments") or {})
    assignments = {
        source_ref: post_ref
        for source_ref, post_ref in current.items()
        if post_ref not in selected and source_ref not in selected_sources
    }
    changed = assignments != current
    cleaned = dict(ledger)
    cleaned["assignments"] = assignments
    return cleaned, duplicate_sources, changed


def _run_produce_compose(ctx: PipelineContext) -> StageResult:
    from produce.handler import handle_produce
    from _common.content_object import BRIEF_FILE, content_object_stage_dir, iter_content_refs
    from _common.content_plan import load_writing_intent_overrides
    from _common.draft_io import (
        draft_article_path,
        is_placeholder,
        prompt_path,
        writing_pack_path,
    )
    from _common.io import read_json
    from _common.paths import STAGE_COMPOSE

    overrides = load_writing_intent_overrides(ctx.task_id, ctx.batch_id)
    expected_refs = list(iter_content_refs(ctx.task_id, ctx.batch_id))
    pending_refs: list[str] = []
    for ref in expected_refs:
        needs_prepare = False
        wp = writing_pack_path(ctx.task_id, ctx.batch_id, ref)
        prompt = prompt_path(ctx.task_id, ctx.batch_id, ref)
        draft = draft_article_path(ctx.task_id, ctx.batch_id, ref)
        if not wp.is_file() or not prompt.is_file() or not draft.is_file():
            needs_prepare = True
        else:
            try:
                if is_placeholder(draft.read_text(encoding="utf-8")):
                    needs_prepare = True
            except OSError:
                needs_prepare = True
        override = overrides.get(ref) or {}
        if override:
            brief_path = (
                content_object_stage_dir(ctx.task_id, ctx.batch_id, ref, STAGE_COMPOSE)
                / BRIEF_FILE
            )
            try:
                brief = read_json(brief_path) if brief_path.is_file() else {}
            except (OSError, ValueError, TypeError):
                brief = {}
            for field in (
                "writingIntent",
                "baseSourceRef",
                "carrier",
                "sourceCollectionId",
                "assetRefs",
            ):
                if field in override and override.get(field) not in (None, ""):
                    if brief.get(field) != override.get(field):
                        needs_prepare = True
                        break
        if needs_prepare:
            pending_refs.append(ref)
    if expected_refs and not pending_refs:
        return StageResult(
            "produce_compose",
            AUTO,
            "done",
            "all writing packs and authored drafts already present",
        )
    selected_refs = pending_refs
    if selected_refs:
        print(
            "[task run] compose object repair: "
            + ", ".join(selected_refs)
        )
        from _common.base_draft import load_base_draft_ledger, save_base_draft_ledger

        ledger = load_base_draft_ledger(ctx.task_id, ctx.batch_id)
        ledger, duplicate_sources, ledger_changed = _clear_compose_base_draft_assignments(
            ledger, selected_refs, overrides
        )
        if duplicate_sources:
            return StageResult(
                "produce_compose",
                AUTO,
                "failed",
                "content_plan declares duplicate baseSourceRef: "
                + "; ".join(duplicate_sources[:5]),
                fallback_stage="content_plan",
            )
        if ledger_changed:
            save_base_draft_ledger(ctx.task_id, ctx.batch_id, ledger)
    ns = argparse.Namespace(
        task=ctx.task_id, batch=ctx.batch_id, type="article",
        stage="compose-brief", refs=",".join(selected_refs), batch_size=1,
        allow_partial=False, materialize=False,
    )
    handle_produce(ns)
    return StageResult(
        "produce_compose",
        AUTO,
        "done",
        "compose-brief 写出 writing_pack + prompt"
        + (f" ({len(selected_refs)} repaired refs)" if selected_refs else ""),
    )


def _run_produce_annotate(ctx: PipelineContext) -> StageResult:
    from produce.handler import handle_produce
    from _common import content_object

    state = load_workflow_state(ctx.task_id, ctx.batch_id)
    abandoned_refs = _abandoned_content_refs(state)
    active_refs = [
        ref for ref in content_object.iter_content_refs(ctx.task_id, ctx.batch_id)
        if ref not in abandoned_refs
    ]
    ns = argparse.Namespace(
        task=ctx.task_id, batch=ctx.batch_id, type="article",
        stage="annotate-entities", refs=",".join(active_refs), batch_size=1,
        allow_partial=True, materialize=False,
    )
    handle_produce(ns)
    return StageResult("produce_annotate", AUTO, "done", "实体 inline 标注完成")


def _approved_review_refs(ctx: PipelineContext, *, refs: set[str] | None = None) -> list[str]:
    from _common import content_object

    approved: list[str] = []
    for ref in content_object.iter_content_refs(ctx.task_id, ctx.batch_id):
        if refs is not None and ref not in refs:
            continue
        try:
            gate_path = (
                content_object.content_object_dir(ctx.task_id, ctx.batch_id, ref)
                / "5.review"
                / "review_gate.json"
            )
        except KeyError:
            continue
        if not gate_path.is_file():
            continue
        envelope = read_json(gate_path)
        payload = envelope.get("payload") or envelope
        if payload.get("passed") is True:
            approved.append(ref)
    return approved


def _batch_reducer_payload(ctx: PipelineContext, *, refs: set[str] | None = None) -> list[dict[str, str]]:
    from _common import content_object
    from _common.draft_io import read_draft_article, read_writing_pack

    payload: list[dict[str, str]] = []
    for ref in _approved_review_refs(ctx, refs=refs):
        coords = content_object.content_coords(ctx.task_id, ctx.batch_id, ref) or {}
        if coords.get("contentType") != "article":
            continue
        article = read_draft_article(ctx.task_id, ctx.batch_id, ref)
        pack = read_writing_pack(ctx.task_id, ctx.batch_id, ref) or {}
        if not article:
            continue
        payload.append(
            {
                "ref": ref,
                "article": article,
                "writingIntent": str(pack.get("writingIntent") or ""),
                "baseSourceRef": str(pack.get("baseSourceRef") or ""),
                "baseSourceReusePolicy": str(pack.get("baseSourceReusePolicy") or ""),
            }
        )
    return payload


def _aggregate_review_fallback(ctx: PipelineContext, *, refs: set[str] | None = None) -> str | None:
    """聚合 produce review gate reports 的 fallbackStage（ReAct 回退指针）。

    只有来源文件确实缺失/不可读时才回 download。事实表达、必含事实、
    文体或载体失败都属于单作品 compose 修复，不能让整批回退重抓来源。
    """
    from _common.stage_reports import iter_stage_envelopes
    saw_failure = False
    download_issue_markers = (
        "source file missing",
        "source path missing",
        "sourcepath missing",
        "source bundle missing",
        "evidence file missing",
        "evidenceref missing",
        "unreadable source",
        "cannot read source",
        "来源文件缺失",
        "来源不可读",
        "证据文件缺失",
    )
    for _ref, rep in iter_stage_envelopes(ctx.task_id, ctx.batch_id, "produce", "review_gate"):
        if refs is not None and _ref not in refs:
            continue
        payload = rep.get("payload") or rep
        if payload.get("passed") is True:
            continue
        issues = [str(issue) for issue in payload.get("issues") or []]
        fallback = str(payload.get("fallbackStage") or "")
        if not issues and not fallback:
            continue
        saw_failure = True
        issue_text = "\n".join(issues).lower()
        if fallback == "download" and any(marker in issue_text for marker in download_issue_markers):
            return "download"
    return "compose" if saw_failure else None


def _run_produce_review(ctx: PipelineContext) -> StageResult:
    from produce.handler import handle_produce
    from produce.gate import gate_produce
    from _common import content_object
    from _common.handoff import build_batch_reducer_gate, write_batch_reducer_gate
    from produce.materialize import prune_materialized_refs
    refs = content_object.iter_content_refs(ctx.task_id, ctx.batch_id)
    abandoned_refs = _abandoned_content_refs(load_workflow_state(ctx.task_id, ctx.batch_id))
    active_refs = [ref for ref in refs if ref not in abandoned_refs]
    if abandoned_refs:
        prune_materialized_refs(ctx.task_id, ctx.batch_id, abandoned_refs)
    all_green = bool(active_refs)
    stale_review_refs: list[str] = []
    for ref in refs:
        if ref in abandoned_refs:
            continue
        gate_path = (
            content_object.content_object_dir(ctx.task_id, ctx.batch_id, ref)
            / "5.review"
            / "review_gate.json"
        )
        if not gate_path.is_file():
            all_green = False
            stale_review_refs.append(ref)
            continue
        envelope = read_json(gate_path)
        if (envelope.get("payload") or envelope).get("passed") is not True:
            all_green = False
            stale_review_refs.append(ref)
    initial_issues: list[str] = []
    review_refs = active_refs
    if all_green:
        initial_issues = gate_produce(ctx.task_id, ctx.batch_id, "article", refs=active_refs)
        if not initial_issues:
            return StageResult(
                "produce_review",
                AUTO,
                "done",
                "existing review + materialized packages still pass current gates",
            )
        matched_refs, _issue_map = _produce_review_retry_refs(ctx, initial_issues)
        if not matched_refs:
            return StageResult(
                "produce_review",
                AUTO,
                "failed",
                "发布门未过但无法映射到对象级 ref:\n  - " + "\n  - ".join(initial_issues[:10]),
                fallback_stage="produce_compose",
                issues=initial_issues,
            )
        review_refs = [ref for ref in matched_refs if ref in active_refs]
    elif stale_review_refs:
        review_refs = sorted(set(stale_review_refs))
    ns = argparse.Namespace(
        task=ctx.task_id, batch=ctx.batch_id, type="article",
        stage="review", refs=",".join(review_refs), batch_size=1,
        allow_partial=True, materialize=True,
    )
    handle_produce(ns)
    issues = gate_produce(ctx.task_id, ctx.batch_id, "article", refs=active_refs)
    for ref in refs:
        if ref in abandoned_refs:
            continue
        gate_path = (
            content_object.content_object_dir(ctx.task_id, ctx.batch_id, ref)
            / "5.review"
            / "review_gate.json"
        )
        if not gate_path.is_file():
            issues.append(f"{ref}: review_gate.json missing")
            continue
        envelope = read_json(gate_path)
        payload = envelope.get("payload") or envelope
        if payload.get("passed") is not True:
            ref_issues = [str(item) for item in (payload.get("issues") or [])]
            issues.append(
                f"{ref}: review_gate failed"
                + (": " + "; ".join(ref_issues[:5]) if ref_issues else "")
            )
    refs_payload = _batch_reducer_payload(ctx, refs=set(active_refs))
    batch_gate = build_batch_reducer_gate(refs_payload) if refs_payload else {
        "schemaVersion": "quwoquan_data.batch_reducer_gate/1",
        "passed": False,
        "issues": ["batchReducer: no draft payloads available after produce_review"],
        "affectedRefs": [],
        "sourceReuse": {},
        "intentDistribution": {},
        "imageCoverage": {},
    }
    write_batch_reducer_gate(ctx.task_id, ctx.batch_id, batch_gate)
    if batch_gate.get("passed") is False:
        issues.extend([str(issue) for issue in (batch_gate.get("issues") or [])])
    if issues:
        fb = _aggregate_review_fallback(ctx, refs=set(active_refs)) or "produce_compose"
        return StageResult("produce_review", AUTO, "failed",
                           "发布门未过:\n  - " + "\n  - ".join(issues[:10]),
                           fallback_stage=fb, issues=issues)
    return StageResult("produce_review", AUTO, "done", "review + materialize approved，发布门通过")


def _clean_content_plan_outputs(ctx: PipelineContext) -> None:
    root = batch_root(ctx.task_id, ctx.batch_id)
    for rel in ("posts/article", "posts/image"):
        path = root / rel
        if path.exists():
            shutil.rmtree(path)
    for rel in ("_shared/content_plan_packet.json", "_shared/content_object_index.json"):
        path = root / rel
        if path.exists():
            path.unlink()
    state = load_workflow_state(ctx.task_id, ctx.batch_id)
    if state.get("abandonedContentObjects"):
        state["abandonedContentObjects"] = []
        state["nextAction"] = "content_plan outputs cleaned; abandoned content refs reset"
        save_workflow_state(state)


def _article_source_quality_sort_key(row: Mapping[str, Any]) -> tuple[int, int, int, str]:
    """Quality-first article candidate ordering without platform/source-class bias."""
    source_quality = int(float(row.get("sourceQualityScore") or row.get("qualityScore") or 0) * 1000)
    image_count = len(row.get("rows") or []) if isinstance(row.get("rows"), list) else 0
    text_len = int(row.get("textLen") or 0)
    source_id = str(row.get("sourceId") or "")
    return (-source_quality, -text_len, -image_count, source_id)


def _auto_content_plan(ctx: PipelineContext, active_spec: Mapping[str, Any]) -> list[str]:
    """Build exact per-entity content_plan from validated source units.

    This is the production default for source-ready batches. Agent planning is
    kept only as a repair fallback when deterministic source capacity is truly
    insufficient.
    """
    from _common.base_draft import load_base_draft_text
    from _common.content_object import write_brief_object
    from _common.image_safety import assess_image_publish_prefilter
    from _common.content_plan import (
        ARTICLE_MIN_BASE_DRAFT_CHARS,
        CONTENT_PLAN_SCHEMA,
        allow_content_quota_shortfall,
        validate_content_plan,
    )
    from _common.paths import batch_content_plan_packet_path, relative_batch_ref
    from _common.source_unit import resolve_entity_object_dir

    intent_titles = {
        "planning_consultation": "行前怎么安排",
        "decision_experience": "值不值得去",
        "route_transport": "怎么去与动线",
        "seasonal_timing": "什么时候去最好",
    }
    required_angles = [
        str(angle).strip()
        for angle in ((active_spec.get("acceptance") or {}).get("requiredAngles") or [])
        if str(angle).strip()
    ]
    article_intents = [
        angle for angle in required_angles
        if angle not in {"image", "imagePost", "gallery"}
    ]
    quotas = (active_spec.get("content") or {}).get("quotas") or {}
    per_target_articles = int(quotas.get("entityArticlesPerTarget") or 0)
    per_target_images = int(quotas.get("imageWorksPerTarget") or 0)
    if per_target_articles <= 0 and per_target_images <= 0:
        return ["content quotas are empty; auto content_plan skipped"]
    if not article_intents:
        article_intents = [
            "planning_consultation",
            "decision_experience",
            "route_transport",
            "seasonal_timing",
        ][:per_target_articles]
    article_intents = article_intents[:per_target_articles]
    if per_target_articles and len(article_intents) != per_target_articles:
        return [
            f"required article intents {len(article_intents)} do not match "
            f"entityArticlesPerTarget={per_target_articles}"
        ]
    _clean_content_plan_outputs(ctx)

    root = batch_root(ctx.task_id, ctx.batch_id)
    etype = _coverage_entity_type(active_spec)
    targets = [
        str(target.get("name") or "").strip()
        for target in ((active_spec.get("scope") or {}).get("coverageTargets") or [])
        if str(target.get("name") or "").strip()
    ]
    task_region = str(((active_spec.get("scope") or {}).get("region") or "")).strip()
    condition_context = (
        {"region": {"name": task_region, "label": task_region}}
        if task_region
        else {}
    )
    used_asset_refs: set[str] = set()
    used_asset_shas: set[str] = set()
    used_collection_ids: set[str] = set()
    used_article_source_refs: set[str] = set()
    items: list[dict[str, Any]] = []
    issues: list[str] = []
    abandoned_content: dict[str, str] = {}
    source_diagnostics: dict[str, dict[str, Any]] = {}
    quota_shortfall_allowed = allow_content_quota_shortfall(active_spec)

    def _asset_rows(source_dir: Path) -> list[dict[str, Any]]:
        index_path = source_dir / "assets" / "index.json"
        if not index_path.is_file():
            return []
        try:
            rows = read_json(index_path).get("assets") or []
        except (OSError, ValueError, TypeError):
            rows = []
        return [row for row in rows if isinstance(row, dict)]

    def _asset_ref(source_dir: Path, row: Mapping[str, Any]) -> str:
        file_name = str(row.get("fileName") or "").strip()
        if not file_name:
            return ""
        return relative_batch_ref(source_dir / "assets" / file_name, ctx.task_id, ctx.batch_id)

    def _asset_sha(row: Mapping[str, Any]) -> str:
        return str(row.get("sha256") or "").removeprefix("sha256:").strip().lower()

    def _source_ref(source_dir: Path) -> str:
        return relative_batch_ref(source_dir / "source.md", ctx.task_id, ctx.batch_id)

    for target in targets:
        object_dir = resolve_entity_object_dir(ctx.task_id, ctx.batch_id, target, etype_hint=etype)
        sources_dir = object_dir / "1.download" / "sources"
        if not sources_dir.is_dir():
            issues.append(f"{target}: sources directory missing")
            continue
        article_candidates: list[dict[str, Any]] = []
        image_candidates: list[dict[str, Any]] = []
        article_raw_count = 0
        image_raw_count = 0
        image_rejects: dict[str, int] = defaultdict(int)
        image_reject_examples: dict[str, list[str]] = defaultdict(list)
        article_rejects: dict[str, int] = defaultdict(int)
        article_reject_examples: dict[str, list[str]] = defaultdict(list)

        def _reject_article(reason: str, source_id: str, detail: str = "") -> None:
            article_rejects[reason] += 1
            examples = article_reject_examples[reason]
            if len(examples) < 5:
                examples.append(f"{source_id}{(': ' + detail) if detail else ''}")

        def _reject_image(reason: str, source_id: str, detail: str = "") -> None:
            image_rejects[reason] += 1
            examples = image_reject_examples[reason]
            if len(examples) < 5:
                examples.append(f"{source_id}{(': ' + detail) if detail else ''}")

        for source_dir in sorted(path for path in sources_dir.iterdir() if path.is_dir()):
            meta_path = source_dir / "meta.json"
            if not meta_path.is_file() or not (source_dir / "source.md").is_file():
                continue
            try:
                meta = read_json(meta_path)
            except (OSError, ValueError, TypeError):
                meta = {}
            source_id = str(meta.get("sourceId") or source_dir.name).strip()
            lane = str(meta.get("researchLane") or "").strip()
            rows = _asset_rows(source_dir)
            if lane == "article":
                if str(meta.get("sourceRole") or "") != "base":
                    continue
                if "support" in source_id.lower() or "support" in source_dir.name.lower():
                    continue
                article_raw_count += 1
                source_ref = _source_ref(source_dir)
                text_len = len(re.sub(r"\s+", "", load_base_draft_text(ctx.task_id, ctx.batch_id, source_ref)))
                if text_len < ARTICLE_MIN_BASE_DRAFT_CHARS:
                    _reject_article("text_too_short", source_id, f"{text_len}<{ARTICLE_MIN_BASE_DRAFT_CHARS}")
                    continue
                if not rows:
                    _reject_article("no_source_assets", source_id)
                    continue
                article_candidates.append(
                    {
                        "sourceDir": source_dir,
                        "sourceRef": source_ref,
                        "sourceId": source_id,
                        "title": str(meta.get("title") or source_id),
                        "sourceUseMode": str(meta.get("sourceUseMode") or "factual_reference_only"),
                        "sourceClass": str(meta.get("sourceClass") or meta.get("category") or ""),
                        "sourceQualityScore": float(
                            meta.get("sourceQualityScore")
                            or meta.get("qualityScore")
                            or meta.get("score")
                            or 0
                        ),
                        "textLen": text_len,
                    "rows": rows,
                }
            )
            elif lane == "image":
                for row in rows:
                    image_raw_count += 1
                    asset_ref = _asset_ref(source_dir, row)
                    collection_id = str(row.get("sourceCollectionId") or "").strip()
                    if not asset_ref:
                        _reject_image("missing_asset_ref", source_id)
                        continue
                    if not collection_id:
                        _reject_image("missing_source_collection_id", source_id, asset_ref)
                        continue
                    asset_path = root / asset_ref
                    if not asset_path.is_file():
                        _reject_image("asset_file_missing", source_id, asset_ref)
                        continue
                    verdict = assess_image_publish_prefilter(asset_path)
                    if verdict.blocks_image_publish:
                        _reject_image(
                            "image_safety_blocked",
                            source_id,
                            f"{asset_ref}:{'/'.join(verdict.reasons) or verdict.status}",
                        )
                        continue
                    image_candidates.append(
                        {
                            "sourceDir": source_dir,
                            "sourceRef": _source_ref(source_dir),
                            "sourceId": source_id,
                            "assetRef": asset_ref,
                            "assetSha": _asset_sha(row),
                            "collectionId": collection_id,
                            "caption": str(row.get("caption") or target),
                            "title": str(meta.get("title") or row.get("caption") or target),
                        }
                    )
        article_candidates.sort(key=_article_source_quality_sort_key)
        image_candidates.sort(key=lambda row: (str(row["collectionId"]), str(row["assetRef"])))

        def _image_claims(candidate: Mapping[str, Any]) -> tuple[list[str], list[str], list[str]]:
            return (
                [str(candidate.get("assetRef") or "").strip()],
                [str(candidate.get("assetSha") or "").strip()],
                [str(candidate.get("collectionId") or "").strip()],
            )

        def _article_asset_claims(candidate: Mapping[str, Any]) -> tuple[list[str], list[str], list[str]]:
            refs: list[str] = []
            shas: list[str] = []
            collections: list[str] = []
            source_dir = candidate.get("sourceDir")
            if not isinstance(source_dir, Path):
                return refs, shas, collections
            for row in candidate.get("rows") or []:
                if not isinstance(row, Mapping):
                    continue
                ref = _asset_ref(source_dir, row)
                sha = _asset_sha(row)
                collection_id = str(row.get("sourceCollectionId") or "").strip()
                if ref:
                    refs.append(ref)
                if sha:
                    shas.append(sha)
                if collection_id:
                    collections.append(collection_id)
            return refs, shas, collections

        def _claims_conflict(
            refs: list[str],
            shas: list[str],
            collections: list[str],
            *,
            claimed_refs: set[str],
            claimed_shas: set[str],
            claimed_collections: set[str],
        ) -> bool:
            return (
                any(ref in claimed_refs for ref in refs if ref)
                or any(sha in claimed_shas for sha in shas if sha)
                or any(cid in claimed_collections for cid in collections if cid)
            )

        def _claim(
            refs: list[str],
            shas: list[str],
            collections: list[str],
            *,
            claimed_refs: set[str],
            claimed_shas: set[str],
            claimed_collections: set[str],
        ) -> None:
            claimed_refs.update(ref for ref in refs if ref)
            claimed_shas.update(sha for sha in shas if sha)
            claimed_collections.update(cid for cid in collections if cid)

        picked_articles: list[dict[str, Any]] = []
        for candidate in article_candidates:
            source_ref = str(candidate.get("sourceRef") or "").strip()
            dedupe_reasons: list[str] = []
            if source_ref in used_article_source_refs:
                dedupe_reasons.append("source_ref_reused")
            asset_refs, asset_shas, asset_collections = _article_asset_claims(candidate)
            if _claims_conflict(
                asset_refs,
                asset_shas,
                asset_collections,
                claimed_refs=used_asset_refs,
                claimed_shas=used_asset_shas,
                claimed_collections=used_collection_ids,
            ):
                dedupe_reasons.append("source_asset_reused")
            if dedupe_reasons:
                for reason in dedupe_reasons:
                    _reject_article(reason, str(candidate["sourceId"]))
                continue
            picked_articles.append(candidate)
            if source_ref:
                used_article_source_refs.add(source_ref)
            _claim(
                asset_refs,
                asset_shas,
                asset_collections,
                claimed_refs=used_asset_refs,
                claimed_shas=used_asset_shas,
                claimed_collections=used_collection_ids,
            )
            if len(picked_articles) >= per_target_articles:
                break
        if len(picked_articles) < per_target_articles:
            reject_summary = ", ".join(
                f"{key}={value}" for key, value in sorted(article_rejects.items())
            ) or "none"
            for intent in article_intents[len(picked_articles):per_target_articles]:
                abandoned_content[f"{target}_{intent}"] = (
                    f"source_unavailable: usable article base sources "
                    f"{len(picked_articles)} < {per_target_articles}; raw={article_raw_count}; "
                    f"qualified={len(article_candidates)}; rejects={{ {reject_summary} }}; "
                    f"missing writingIntent={intent}"
                )
        picked_images: list[dict[str, Any]] = []
        for candidate in image_candidates:
            refs, shas, collections = _image_claims(candidate)
            if _claims_conflict(
                refs,
                shas,
                collections,
                claimed_refs=used_asset_refs,
                claimed_shas=used_asset_shas,
                claimed_collections=used_collection_ids,
            ):
                _reject_image(
                    "source_asset_reused",
                    str(candidate.get("sourceId") or candidate.get("sourceRef") or ""),
                    str(candidate.get("assetRef") or ""),
                )
                continue
            picked_images.append(candidate)
            _claim(
                refs,
                shas,
                collections,
                claimed_refs=used_asset_refs,
                claimed_shas=used_asset_shas,
                claimed_collections=used_collection_ids,
            )
            if len(picked_images) >= per_target_images:
                break
        if len(picked_images) < per_target_images:
            for index in range(len(picked_images) + 1, per_target_images + 1):
                ref = f"{target}_image" if per_target_images == 1 else f"{target}_image_{index}"
                abandoned_content[ref] = (
                    f"source_unavailable: usable image collections "
                    f"{len(picked_images)} < {per_target_images}"
                )
        source_diagnostics[target] = {
            "rawArticleBaseSources": article_raw_count,
            "qualifiedArticleBaseSources": len(article_candidates),
            "pickedArticleBaseSources": len(picked_articles),
            "rawImageAssets": image_raw_count,
            "qualifiedImageAssets": len(image_candidates),
            "pickedImageSources": len(picked_images),
            "articleRejects": dict(sorted(article_rejects.items())),
            "articleRejectExamples": {
                key: values for key, values in sorted(article_reject_examples.items())
            },
            "imageRejects": dict(sorted(image_rejects.items())),
            "imageRejectExamples": {
                key: values for key, values in sorted(image_reject_examples.items())
            },
        }
        for intent, candidate in zip(article_intents, picked_articles):
            ref = f"{target}_{intent}"
            source_title = str(candidate["title"]).strip()
            title = f"{target}·{intent_titles.get(intent, intent)}"
            if source_title and not source_title.startswith("article_"):
                title += f"：{source_title[:40]}"
            entity_ref = f"/entity/{etype}/{target}"
            brief = {
                "titleHint": title,
                "carrier": "article",
                "entityRefs": [entity_ref],
                    "mustIncludeFacts": [
                        f"{target} 来源提及 {intent_titles.get(intent, intent)}",
                        f"{target} 文字底稿来自 {source_title or candidate['sourceId']}；图片资产如使用，必须来自独立授权资产链",
                    ],
                "templateId": "travel.entity.guide",
                "writingIntent": intent,
                "baseSourceRef": candidate["sourceRef"],
                "conditionContext": condition_context,
            }
            write_brief_object(ctx.task_id, ctx.batch_id, ref, brief, content_type="article")
            items.append(
                {
                    "ref": ref,
                    "kind": "entity",
                    "carrier": "article",
                    "researchLane": "article",
                    "title": title,
                    "entityRefs": [entity_ref],
                    "evidenceRefs": [candidate["sourceRef"]],
                    "rationale": f"确定性选择 sourceRole=base、正文≥{ARTICLE_MIN_BASE_DRAFT_CHARS} 的 article text source；图片资产单独按 image lane 权利链校验",
                    "mustIncludeFacts": brief["mustIncludeFacts"],
                    "writingIntent": intent,
                    "baseSourceRef": candidate["sourceRef"],
                    "sourceUseMode": candidate["sourceUseMode"],
                }
            )
        if not picked_images:
            continue
        image_caption_keys = [
            re.sub(
                r"\s+",
                "",
                (str(candidate.get("caption") or "").strip()[:60] or "图库作品"),
            ).strip()
            for candidate in picked_images
        ]
        image_caption_counts = Counter(key for key in image_caption_keys if key)
        image_caption_seen: dict[str, int] = defaultdict(int)
        for index, candidate in enumerate(picked_images, start=1):
            ref = f"{target}_image" if per_target_images == 1 else f"{target}_image_{index}"
            caption_title = str(candidate["caption"] or "").strip()[:60] or "图库作品"
            caption_key = re.sub(r"\s+", "", caption_title).strip()
            if caption_key and image_caption_counts.get(caption_key, 0) > 1:
                image_caption_seen[caption_key] += 1
                caption_title = f"{caption_title}·视角{image_caption_seen[caption_key]}"
            title = f"{target}·{caption_title}"
            entity_ref = f"/entity/{etype}/{target}"
            brief = {
                "titleHint": title,
                "carrier": "image",
                "entityRefs": [entity_ref],
                "mustIncludeFacts": [
                    f"{target} 开放许可图片作品",
                    "图片来自同一授权来源集合，禁止跨作者或跨页面混图",
                ],
                "templateId": "travel.entity.gallery",
                "sourceCollectionId": candidate["collectionId"],
                "assetRefs": [candidate["assetRef"]],
                "caption": candidate["caption"][:300],
                "conditionContext": condition_context,
            }
            write_brief_object(ctx.task_id, ctx.batch_id, ref, brief, content_type="image")
            items.append(
                {
                    "ref": ref,
                    "kind": "entity",
                    "carrier": "image",
                    "researchLane": "image",
                    "title": title,
                    "caption": candidate["caption"][:300],
                    "entityRefs": [entity_ref],
                    "evidenceRefs": [candidate["sourceRef"]],
                    "rationale": "确定性选择 image research lane 下同一 sourceCollectionId 的授权图片集合",
                    "sourceCollectionId": candidate["collectionId"],
                    "assetRefs": [candidate["assetRef"]],
                }
            )
    write_json(
        root / "_shared" / "content_plan_source_diagnostics.json",
        {
            "schemaVersion": "quwoquan_data.content_plan_source_diagnostics/1",
            "taskId": ctx.task_id,
            "batchId": ctx.batch_id,
            "targets": source_diagnostics,
        },
    )
    if abandoned_content and not quota_shortfall_allowed:
        _clean_content_plan_outputs(ctx)
        return [
            f"{ref}: {reason}; workflowPolicy.allowContentQuotaShortfall is not true"
            for ref, reason in sorted(abandoned_content.items())
        ]
    if abandoned_content:
        for ref, reason in abandoned_content.items():
            mark_abandoned_content_refs(
                ctx.task_id,
                ctx.batch_id,
                [ref],
                stage="content_plan",
                reason=reason,
            )
    if issues:
        _clean_content_plan_outputs(ctx)
        return issues
    if not items:
        _clean_content_plan_outputs(ctx)
        return ["auto content_plan produced no items"]
    write_json(
        batch_content_plan_packet_path(ctx.task_id, ctx.batch_id),
        {
            "schemaVersion": CONTENT_PLAN_SCHEMA,
            "taskId": ctx.task_id,
            "batchId": ctx.batch_id,
            "generatedBy": "deterministic_source_ready_planner",
            "items": items,
        },
    )
    return validate_content_plan(ctx.task_id, ctx.batch_id, active_spec)


# ─── checkpoint 指引 ──────────────────────────────────────────────────
def _checkpoint_download_plan(ctx: PipelineContext) -> StageResult:
    ok, missing = _source_plan_filled(ctx)
    current_unresolved = _download_plan_unresolved_entities(ctx)
    build_prepare_unresolved = _build_prepare_homepage_unresolved_entities(ctx)
    unresolved_ids = [
        entity_id for entity_id in ctx.entity_ids
        if entity_id in current_unresolved
    ]
    build_prepare_ids = [
        entity_id for entity_id in ctx.entity_ids
        if entity_id in build_prepare_unresolved
    ]
    retry_ids = _download_retry_entity_ids(ctx)
    missing_ids = _entity_ids_from_issue_messages(ctx.entity_ids, missing)
    repair_scope = unresolved_ids or retry_ids or missing_ids or build_prepare_ids
    if not repair_scope and len(ctx.entity_ids) == 1:
        repair_scope = list(ctx.entity_ids)
    stale_entities = (
        _stale_source_plan_entities(ctx, entity_ids=repair_scope)
        if repair_scope
        else []
    )
    if ok and not stale_entities:
        if build_prepare_unresolved:
            missing = _format_download_unresolved(
                build_prepare_unresolved,
                prefix="build_prepare",
            )
        else:
            _write_download_plan_availability(ctx, {})
            return StageResult("download_plan", CHECKPOINT, "done", "三路 research plan 已就绪")
    if stale_entities:
        stale_ids = [str(item.get("entityId") or "") for item in stale_entities if item.get("entityId")]
        missing = [
            f"{entity_id}: source_plan predates source registry/rights policy; force auto research"
            for entity_id in stale_ids
        ]
    # 预置 homepage/article/image 三路计划骨架，由独立 Agent 填充。
    from download.prepare import prepare_source_plan
    etype = _coverage_entity_type(ctx.spec)
    stale_ids = [
        str(item.get("entityId") or "") for item in stale_entities
        if item.get("entityId")
    ]
    auto_scope_ids = set(stale_ids)
    if not auto_scope_ids:
        auto_scope_ids.update(repair_scope)
    elif unresolved_ids:
        auto_scope_ids.update(unresolved_ids)
    elif build_prepare_ids:
        auto_scope_ids.update(build_prepare_ids)
    if not auto_scope_ids and not ok:
        auto_scope_ids.update(ctx.entity_ids)
    auto_entity_ids = [entity_id for entity_id in ctx.entity_ids if entity_id in auto_scope_ids]
    entities = [{"entityId": e, "canonicalName": e, "entityType": etype} for e in auto_entity_ids]
    prepare_source_plan(ctx.task_id, ctx.batch_id, entities)
    if os.environ.get("QWQ_DOWNLOAD_AUTO_RESEARCH", "1") != "0":
        try:
            auto_report = _run_download_auto_research(
                ctx,
                auto_entity_ids,
                entity_type=etype,
                force=bool(stale_entities or unresolved_ids or build_prepare_ids),
            )
        except Exception as exc:  # noqa: BLE001
            write_json(
                batch_root(ctx.task_id, ctx.batch_id) / "_shared" / "auto_research_plan.json",
                {
                    "schemaVersion": "quwoquan.download.auto_research_plan",
                    "taskId": ctx.task_id,
                    "batchId": ctx.batch_id,
                    "error": f"{type(exc).__name__}: {exc}",
                },
            )
        else:
            ok_after_auto, missing_after_auto = _source_plan_filled(ctx)
            stale_after_auto = (
                _stale_source_plan_entities(ctx, entity_ids=auto_entity_ids)
                if ok_after_auto
                else []
            )
            if ok_after_auto and not stale_after_auto:
                _write_download_plan_availability(ctx, {})
                message = "三路 research plan 已由 CLI 自动检索就绪"
                if stale_entities:
                    message += "；过期 source_plan 已按 source registry/rights policy 重算: " + ", ".join(auto_entity_ids[:8])
                return StageResult("download_plan", CHECKPOINT, "done", message)
            if stale_after_auto:
                missing_after_auto = list(missing_after_auto) + [
                    f"{item.get('entityId')}: source_plan still predates source registry/rights policy"
                    for item in stale_after_auto
                    if item.get("entityId")
                ]
            if _auto_report_needs_target_replacement(auto_report):
                ok_after_replacement, abandoned, missing_after_replacement, auto_report = (
                    _rerun_auto_research_with_replacements(
                        ctx,
                        auto_report,
                        entity_type=etype,
                        reason_prefix="source_unavailable_after_auto_research",
                    )
                )
                if abandoned:
                    if ok_after_replacement:
                        _write_download_plan_availability(ctx, {})
                        return StageResult(
                            "download_plan",
                            CHECKPOINT,
                            "done",
                            "三路 research plan 已就绪；source-unavailable 对象已快速放弃: "
                            + ", ".join(abandoned[:8]),
                        )
                    missing = missing_after_replacement
                else:
                    missing = missing_after_auto
            else:
                missing = missing_after_auto
    unresolved = _download_plan_unresolved_entities(ctx)
    for entity_id, lanes in build_prepare_unresolved.items():
        entity_lanes = unresolved.setdefault(entity_id, {})
        for lane, issues in lanes.items():
            lane_rows = entity_lanes.setdefault(lane, [])
            for issue in issues:
                if issue not in lane_rows:
                    lane_rows.append(issue)
    _write_download_plan_availability(ctx, unresolved)
    full_missing = _format_download_unresolved(unresolved, prefix="source_plan")
    if full_missing:
        missing = full_missing
    deterministic = _deterministic_download_plan_unresolved(unresolved)
    if deterministic:
        if not _workflow_allows_partial_content(ctx):
            return StageResult(
                "download_plan",
                CHECKPOINT,
                "failed",
                "download_plan 存在确定性 source-unavailable，严格任务禁止替补",
                issues=[
                    item + "; workflowPolicy.allowPartialContent is not true"
                    for item in _format_download_unresolved(
                        deterministic,
                        prefix="deterministic_source_unavailable",
                    )
                ],
            )
        abandoned = _abandon_unresolved_download_plan_entities(
            ctx,
            deterministic,
            reason_prefix="deterministic_source_unavailable",
        )
        if abandoned:
            _apply_abandoned_entities(ctx, load_workflow_state(ctx.task_id, ctx.batch_id))
            etype = _coverage_entity_type(ctx.spec)
            entities = [{"entityId": e, "canonicalName": e, "entityType": etype} for e in ctx.entity_ids]
            prepare_source_plan(ctx.task_id, ctx.batch_id, entities)
            if os.environ.get("QWQ_DOWNLOAD_AUTO_RESEARCH", "1") != "0":
                try:
                    from download.research_plan import write_auto_research_plans

                    auto_report = write_auto_research_plans(
                        ctx.task_id,
                        ctx.batch_id,
                        ctx.entity_ids,
                        entity_type=etype,
                        force=False,
                        max_workers=max(1, min(int(ctx.max_workers or 1), 8)),
                        progress_callback=_download_auto_research_progress_callback(ctx),
                    )
                    write_json(
                        batch_root(ctx.task_id, ctx.batch_id) / "_shared" / "auto_research_plan.json",
                        auto_report,
                    )
                except Exception as exc:  # noqa: BLE001
                    write_json(
                        batch_root(ctx.task_id, ctx.batch_id) / "_shared" / "auto_research_plan.json",
                        {
                            "schemaVersion": "quwoquan.download.auto_research_plan",
                            "taskId": ctx.task_id,
                            "batchId": ctx.batch_id,
                            "error": f"{type(exc).__name__}: {exc}",
                        },
                    )
            ok_after_replacement, missing_after_replacement = _source_plan_filled(ctx)
            unresolved_after_replacement = _download_plan_unresolved_entities(ctx)
            _write_download_plan_availability(ctx, unresolved_after_replacement)
            unresolved = unresolved_after_replacement
            if ok_after_replacement:
                return StageResult(
                    "download_plan",
                    CHECKPOINT,
                    "done",
                    "三路 research plan 已就绪；确定性 source-unavailable 对象已替补: "
                    + ", ".join(abandoned[:8]),
                )
            missing = (
                _format_download_unresolved(unresolved_after_replacement, prefix="source_plan")
                or missing_after_replacement
            )
    quotas = ((ctx.spec.get("content") or {}).get("quotas") or {})
    image_works = max(1, int(quotas.get("imageWorksPerTarget") or 0))
    hint = (
        f"[CHECKPOINT download_plan] 三类独立 Agent 检索真实素材，为以下实体写满足规模化门的 research plan：\n"
        f"  待补实体: {missing}\n"
        f"  写入: entities/<domain>/<type>/<entityId>/1.download/"
        "{homepage,article,image}_source_plan.json\n"
        f"  homepage/article/image 三路互不共用计划；图片按 sourceCollectionId 组织，"
        f"每组授权链完整，足够形成 {image_works} 个各含 1..20 张图的作品。\n"
        f"  完成后: qwq-data data workflow run --task {ctx.task_id} --batch {ctx.batch_id} --resume"
    )
    return StageResult(
        "download_plan",
        CHECKPOINT,
        "waiting",
        "等待三路 research Agent",
        hint,
        issues=list(missing),
    )


def _checkpoint_content_plan(ctx: PipelineContext) -> StageResult:
    ok, issues = _content_plan_done(ctx)
    if ok:
        return StageResult("content_plan", CHECKPOINT, "done", "证据驱动篇目已就绪")
    from _common.content_plan import content_plan_quotas_required

    active_spec = _active_spec(ctx)
    if content_plan_quotas_required(active_spec):
        _clean_content_plan_outputs(ctx)
        auto_issues = _auto_content_plan(ctx, active_spec)
        if not auto_issues:
            return StageResult(
                "content_plan",
                CHECKPOINT,
                "done",
                "证据驱动篇目已由 CLI 确定性规划就绪",
            )
        issues = auto_issues
        if _strict_source_unavailable_issues(ctx, issues):
            abandoned, activated, replacement_issues = _replace_content_plan_source_shortfall_entities(
                ctx,
                issues,
                entity_type=_coverage_entity_type(active_spec),
            )
            if abandoned and activated:
                return StageResult(
                    "content_plan",
                    CHECKPOINT,
                    "failed",
                    "content_plan 源短缺实体已快速放弃并激活替补；回到 download_plan 完成新目标证据链",
                    issues=[
                        "content_plan source shortfall abandoned entities: " + ", ".join(abandoned[:8]),
                        "activated replacement entities: " + ", ".join(activated[:8]),
                    ],
                    fallback_stage="download_plan",
                )
            if replacement_issues:
                return StageResult(
                    "content_plan",
                    CHECKPOINT,
                    "failed",
                    "content_plan 源短缺实体无法完成足额替补，严格任务停止",
                    issues=replacement_issues,
                )
            return StageResult(
                "content_plan",
                CHECKPOINT,
                "failed",
                "content_plan 存在确定性 source-unavailable，严格任务禁止继续消耗 Agent",
                issues=issues,
                fallback_stage="download_plan",
            )
    quotas = (active_spec.get("content") or {}).get("quotas") or {}
    acceptance = active_spec.get("acceptance") or {}
    required_angles = [str(a) for a in (acceptance.get("requiredAngles") or []) if str(a)]
    per_target_entity = int(quotas.get("entityArticlesPerTarget") or 0)
    per_target_image = int(quotas.get("imageWorksPerTarget") or 0)
    active_targets = [
        str(target.get("name") or "").strip()
        for target in (active_spec.get("scope") or {}).get("coverageTargets") or []
        if str(target.get("name") or "").strip()
    ]
    entity_q = (
        per_target_entity * len(active_targets)
        if per_target_entity
        else int(quotas.get("entityArticles") or 0)
    ) if content_plan_quotas_required(active_spec) else 0
    route_q = int(quotas.get("routeArticles") or 0) if content_plan_quotas_required(active_spec) else 0
    image_q = (
        per_target_image * len(active_targets)
        if per_target_image
        else 0
    ) if content_plan_quotas_required(active_spec) else 0
    hint = (
        f"[CHECKPOINT content_plan] Agent 通读已下载来源，证据驱动规划 "
        f"{entity_q} 篇文章 + {image_q} 个图片作品 + {route_q} 篇线路：\n"
        f"  产出: batches/{ctx.batch_id}/_shared/content_plan_packet.json\n"
        f"  每条: ref, kind(entity|route), title, entityRefs, evidenceRefs(相对batch路径), rationale, mustIncludeFacts,\n"
        f"        writingIntent(按 acceptance.requiredAngles，单篇唯一主线: {required_angles}),\n"
        f"        article 写 baseSourceRef；image 写 sourceCollectionId/assetRefs，可选 title/caption\n"
        f"  并 register_content_object + 写 posts/.../3.compose/brief.json（禁止预置营销 ref；brief 写入 writingIntent/baseSourceRef）\n"
        f"  未过项:\n    - " + "\n    - ".join(issues[:12]) + "\n"
        f"  完成后: qwq-data data workflow run --task {ctx.task_id} --batch {ctx.batch_id} --resume"
    )
    return StageResult("content_plan", CHECKPOINT, "waiting", "等待 Agent 证据驱动篇目规划", hint)


def _strict_source_unavailable_issues(ctx: PipelineContext, issues: list[str]) -> bool:
    """True when issues are deterministic source gaps that the stage Agent cannot fix."""
    if not issues or _workflow_allows_content_quota_shortfall(ctx):
        return False
    deterministic = [
        str(issue)
        for issue in issues
        if "source_unavailable" in str(issue)
        and (
            "workflowPolicy.allowContentQuotaShortfall is not true" in str(issue)
            or "workflowPolicy.allowPartialContent is not true" in str(issue)
        )
    ]
    return bool(deterministic) and len(deterministic) == len(issues)


def _checkpoint_build_homepage(ctx: PipelineContext) -> StageResult:
    ok, issues = _homepages_done(ctx)
    if ok:
        return StageResult("build_homepage", CHECKPOINT, "done", "实体主页三件套已就绪")
    materialize_issues: list[str] = []
    try:
        from build.homepage import materialize_entity_pages

        materialize_issues = materialize_entity_pages(ctx.task_id, ctx.batch_id, _active_spec(ctx))
    except Exception as exc:  # noqa: BLE001
        materialize_issues = [f"deterministic homepage materialize failed: {type(exc).__name__}: {exc}"]
    ok, issues = _homepages_done(ctx)
    if ok:
        return StageResult(
            "build_homepage",
            CHECKPOINT,
            "done",
            "实体主页三件套已由确定性 builder 物化并通过采纳门",
        )
    combined_issues = list(materialize_issues or []) + list(issues)
    hint = (
        f"[CHECKPOINT build_homepage] Agent 按 SOP 为 coverage 实体物化主页三件套：\n"
        f"  契约: entities/<domain>/<type>/<name>/3.compose/entity_page_input.json\n"
        f"  产出: page.md(≥800字) + _entity.json(含 conditionProfile) + manifest.json\n"
        f"  采纳门未过项:\n    - " + "\n    - ".join(issues[:10]) + "\n"
        f"  完成后: qwq-data data workflow run --task {ctx.task_id} --batch {ctx.batch_id} --resume"
    )
    return StageResult("build_homepage", CHECKPOINT, "waiting", "等待 Agent 写实体主页", hint, issues=combined_issues)


def _checkpoint_produce_author(ctx: PipelineContext) -> StageResult:
    ok, pending = _drafts_authored(ctx)
    if ok:
        return StageResult("produce_author", CHECKPOINT, "done", "正文已由 Agent 创作")
    hint = (
        f"[CHECKPOINT produce_author] Agent 逐篇创作正文(generator=agent)：\n"
        f"  草稿目录: posts/<type>/<angle>/<title>/<seq>/4.draft/\n"
        f"  读 <ref>/prompt.md + <ref>/writing_pack.json，写回 <ref>/draft.article.md\n"
        f"  draft_meta 记 model/styleFamily/openingStrategy/extractedEntities\n"
        f"  待创作: {pending}\n"
        f"  完成后: qwq-data data workflow run --task {ctx.task_id} --batch {ctx.batch_id} --resume"
    )
    return StageResult("produce_author", CHECKPOINT, "waiting", "等待 Agent 创作正文", hint)


def _workflow_release_id(task_id: str, batch_id: str) -> str:
    task_slug = task_id.replace("/", "__")
    return f"{task_slug}__{batch_id}"


def _run_publish(ctx: PipelineContext) -> StageResult:
    from _common import content_object
    from _common.publish_materialization import materialize_task_publish_inputs
    from publish.handler import handle_publish
    from ship.handler import write_release_only_ship_report
    from task import object_queue as oq
    summary = materialize_task_publish_inputs(ctx.task_id, ctx.batch_id)
    if summary["entityCount"] <= 0 or summary["postCount"] <= 0:
        return StageResult(
            "publish",
            AUTO,
            "failed",
            "publish 前未物化出完整任务级输入",
            fallback_stage="produce_review",
        )
    ns = argparse.Namespace(
        task=ctx.task_id,
        batch=ctx.batch_id,
        release_id=_workflow_release_id(ctx.task_id, ctx.batch_id),
        push_to_service=None,
    )
    try:
        handle_publish(ns)
    except SystemExit as exc:
        code = int(getattr(exc, "code", 1) or 0)
        return StageResult(
            "publish",
            AUTO,
            "failed",
            f"release package assemble/gate failed with exit code {code}",
            fallback_stage="produce_review",
        )
    if ctx.managed or ctx.release_only:
        from verify.gate import gate_verify

        release_id = _workflow_release_id(ctx.task_id, ctx.batch_id)
        _roots, verify_issues = gate_verify(release=release_id)
        if verify_issues:
            return StageResult(
                "publish",
                AUTO,
                "failed",
                "release verify failed:\n  - " + "\n  - ".join(verify_issues[:10]),
                fallback_stage="produce_review",
                issues=verify_issues,
            )
        write_release_only_ship_report(
            task_id=ctx.task_id,
            batch_id=ctx.batch_id,
            release_id=release_id,
            summary=summary,
        )
        state = load_workflow_state(ctx.task_id, ctx.batch_id)
        state["releaseId"] = release_id
        state["releaseEvidencePath"] = str(release_root(release_id))
        state["shipReportPath"] = str(batch_root(ctx.task_id, ctx.batch_id) / "_shared" / "ship_report.json")
        save_workflow_state(state)
    authored_refs = content_object.iter_content_refs(ctx.task_id, ctx.batch_id)
    reconciled = oq.reconcile_completed_refs(
        ctx.task_id,
        ctx.batch_id,
        authored_refs,
        "author",
        reason="publish_succeeded",
    )
    _purge_author_queue_for_stale_workflow(ctx, reason="publish_succeeded")
    return StageResult(
        "publish",
        AUTO,
        "done",
        "release package assembled and gated "
        f"(entities={summary['entityCount']}, posts={summary['postCount']}, "
        f"tags={summary['tagCount']}, relations={summary['relationCount']}, "
        f"authorQueueReconciled={len(reconciled)})",
    )


# ─── DAG 定义 ─────────────────────────────────────────────────────────
# (stage_name, kind, runner)
DAG: list[tuple[str, str, Callable[[PipelineContext], StageResult]]] = [
    ("download_plan", CHECKPOINT, _checkpoint_download_plan),
    ("download_fetch", AUTO, _run_download_fetch),
    ("build_prepare", AUTO, _run_build_prepare),
    ("build_homepage", CHECKPOINT, _checkpoint_build_homepage),
    ("build_validate", AUTO, _run_build_validate),
    ("content_plan", CHECKPOINT, _checkpoint_content_plan),
    ("produce_plan", AUTO, _run_produce_plan),
    ("produce_compose", AUTO, _run_produce_compose),
    ("produce_author", CHECKPOINT, _checkpoint_produce_author),
    ("produce_annotate", AUTO, _run_produce_annotate),
    ("produce_review", AUTO, _run_produce_review),
    ("publish", AUTO, _run_publish),
]

STAGE_NAMES = [s[0] for s in DAG]


def _rewind_to(completed: set[str], target_stage: str) -> set[str]:
    """ReAct 回退：把 target_stage 及其后所有 stage 从 completed 移除，强制重跑。"""
    if target_stage not in STAGE_NAMES:
        return completed
    idx = STAGE_NAMES.index(target_stage)
    keep = set(STAGE_NAMES[:idx])
    return {s for s in completed if s in keep}


def _completed_until_revalidation(ctx: PipelineContext, stage_name: str) -> tuple[bool, list[str]]:
    """Re-check a previously completed --until checkpoint before crossing it."""
    if stage_name == "download_plan":
        ok, issues = _source_plan_filled(ctx)
        repair_scope = _download_retry_entity_ids(ctx) or _entity_ids_from_issue_messages(ctx.entity_ids, issues)
        if not repair_scope and len(ctx.entity_ids) == 1:
            repair_scope = list(ctx.entity_ids)
        stale_entities = _stale_source_plan_entities(ctx, entity_ids=repair_scope) if ok and repair_scope else []
        if stale_entities:
            issues = list(issues) + [
                f"{item.get('entityId')}: source_plan predates source registry/rights policy"
                for item in stale_entities
                if item.get("entityId")
            ]
        return ok and not stale_entities, issues
    return _checkpoint_is_done(ctx, stage_name)


def _stop_at_until(
    ctx: PipelineContext,
    state: dict,
    completed: set[str],
    *,
    next_stage: str | None,
) -> int:
    state["completed"] = sorted(completed)
    state["waitingCheckpoint"] = None
    state["status"] = "stopped_at_until"
    state["stoppedAtStage"] = ctx.until
    state["nextAction"] = next_stage or "workflow complete"
    state["heartbeatAt"] = store.now_iso()
    save_workflow_state(state)
    print(f"[task run] stopped at --until {ctx.until}")
    return 0


def _react_rewind(ctx: PipelineContext, state: dict, completed: set[str],
                  result: StageResult) -> tuple[set[str], bool]:
    """处理 failed 的 ReAct 回退。返回 (新 completed, 是否成功回退)。

    回退账本记 reactRewinds[stage] 计数；超 MAX_REACT_REWINDS 则不再回退（转人工）。
    """
    raw_fb = result.fallback_stage
    target = FALLBACK_DAG_STAGE.get(raw_fb, raw_fb) if raw_fb else None
    if not target or target not in STAGE_NAMES:
        return completed, False
    rewinds = state.setdefault("reactRewinds", {})
    key = result.stage
    used = int(rewinds.get(key, 0))
    if used >= MAX_REACT_REWINDS:
        print(f"[task run] ReAct 回退已达上限({MAX_REACT_REWINDS}) @ {result.stage}; 转人工", file=sys.stderr)
        return completed, False
    rewinds[key] = used + 1
    # 写 repair_report（反思账本：失败 stage → 回退链）
    from _common.stage_reports import write_repair_report
    write_repair_report(
        task_id=ctx.task_id, batch_id=ctx.batch_id, command="workflow_run",
        ref=result.stage, failed_stage=result.stage, failed_gate=f"{result.stage}_gate",
        issues=result.issues or [result.message], fallback_stage=target,
        rerun_chain=STAGE_NAMES[STAGE_NAMES.index(target):STAGE_NAMES.index(result.stage) + 1],
    )
    if result.stage == "produce_review":
        prepared = _prepare_produce_review_retry(ctx, result, target)
        if target == "produce_compose" and not prepared:
            print(
                "[task run] produce_review failed only at batch/release packaging; "
                "no content object will be invalidated",
                file=sys.stderr,
            )
            return completed, False
    new_completed = _rewind_to(completed, target)
    state["reactRewinds"] = rewinds
    state["completed"] = sorted(new_completed)
    save_workflow_state(state)
    print(f"[task run] ⟲ ReAct 回退 {result.stage} → {target} (第{used + 1}/{MAX_REACT_REWINDS}次)\n"
          f"           归因: {result.message.splitlines()[0]}")
    return new_completed, True


def _stage_exception_fallback(stage_name: str) -> str | None:
    if stage_name == "produce_compose":
        return "content_plan"
    if stage_name == "produce_author":
        return "produce_compose"
    if stage_name == "build_validate":
        return "build_homepage"
    if stage_name == "produce_review":
        return "produce_compose"
    return None


def _managed_agent_process_alive(ctx: PipelineContext) -> bool:
    """Best-effort check for a local managed Cursor/task-run process."""
    try:
        proc = subprocess.run(
            ["ps", "-ax", "-o", "command="],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except Exception:  # noqa: BLE001
        return True
    workspace_text = str(Path.cwd())
    for line in proc.stdout.splitlines():
        if "cursor-sdk-bridge" in line and workspace_text in line:
            return True
        if (
            "scripts/cli.py" in line
            and "task run" in line
            and (ctx.batch_id in line or ctx.task_id in line)
        ):
            return True
    return False


def _recover_stale_agent_scheduler(ctx: PipelineContext, state: dict[str, Any]) -> bool:
    """Clear orphaned waiting_agent state left by interrupted managed-local runs."""
    scheduler = state.get("activeAgentScheduler")
    if not isinstance(scheduler, Mapping):
        return False
    if str(scheduler.get("runtime") or ctx.runtime) != "local":
        return False
    if str(state.get("status") or "") != "waiting_agent":
        return False
    heartbeat = _parse_iso_seconds(
        state.get("heartbeatAt") or scheduler.get("updatedAt") or scheduler.get("startedAt")
    )
    now = _parse_iso_seconds(store.now_iso())
    if heartbeat is not None and now is not None and now - heartbeat < MANAGED_SCHEDULER_STALE_SECONDS:
        return False
    if _managed_agent_process_alive(ctx):
        return False
    stage = str(scheduler.get("stage") or state.get("waitingCheckpoint") or "")
    recovered = {
        "stage": stage,
        "reason": "stale managed-local scheduler heartbeat without live Cursor/task-run process",
        "previous": dict(scheduler),
        "recoveredAt": store.now_iso(),
    }
    history = state.setdefault("schedulerRecoveryActions", [])
    if isinstance(history, list):
        history.append(recovered)
        state["schedulerRecoveryActions"] = history[-20:]
    state.pop("activeAgentScheduler", None)
    state["waitingCheckpoint"] = stage or state.get("waitingCheckpoint")
    state["status"] = "running"
    state["nextAction"] = (
        f"recovered stale managed scheduler at {stage or '<unknown>'}; "
        "resume will revalidate checkpoint"
    )
    state["heartbeatAt"] = store.now_iso()
    state["failedObjects"] = []
    save_workflow_state(state)
    return True


def _download_auto_research_progress_callback(ctx: PipelineContext) -> Callable[[dict[str, Any]], None]:
    def _callback(progress: dict[str, Any]) -> None:
        state = load_workflow_state(ctx.task_id, ctx.batch_id)
        state["status"] = "running"
        state["waitingCheckpoint"] = None
        state["heartbeatAt"] = store.now_iso()
        completed_count = int(progress.get("completedCount") or 0)
        entity_count = int(progress.get("entityCount") or 0)
        state["nextAction"] = (
            f"download_plan auto_research {completed_count}/{entity_count}: "
            f"{progress.get('message') or progress.get('status') or 'running'}"
        )
        state["activeAutoResearch"] = {
            "stage": "download_plan",
            "status": progress.get("status"),
            "entityId": progress.get("entityId"),
            "entityCount": entity_count,
            "completedCount": completed_count,
            "remainingCount": progress.get("remainingCount"),
            "workers": progress.get("workers"),
            "entitiesPerMinute": progress.get("entitiesPerMinute"),
            "progressPath": str(batch_root(ctx.task_id, ctx.batch_id) / "_shared" / "auto_research_progress.json"),
            "updatedAt": progress.get("updatedAt"),
        }
        save_workflow_state(state)
        print(f"[task run] {state['nextAction']}", flush=True)

    return _callback


def run_pipeline(ctx: PipelineContext) -> int:
    """按 DAG 顺序执行；遇 waiting checkpoint 停（10），failed 走 ReAct 回退或停（1）。"""
    if ctx.baseline_packet is None or ctx.baseline_packet_path is None:
        raise RuntimeError("workflow run requires baseline freeze packet")
    state = load_workflow_state(ctx.task_id, ctx.batch_id)
    if _recover_stale_agent_scheduler(ctx, state):
        state = load_workflow_state(ctx.task_id, ctx.batch_id)
    skipped_abandoned = _apply_abandoned_entities(ctx, state)
    if skipped_abandoned:
        state["abandonedObjectsSkipped"] = skipped_abandoned
    if not ctx.entity_ids:
        state["status"] = "manual_required"
        state["failedObjects"] = ["all coverage targets are abandoned; nothing left to run"]
        save_workflow_state(state)
        print("[task run] FAILED: all coverage targets are abandoned", file=sys.stderr)
        return 1
    state["status"] = "running"
    state["owner"] = "managed-local" if ctx.managed else "workflow-cli"
    if not state.get("startedAt") and not state.get("completed"):
        state["startedAt"] = store.now_iso()
    state["heartbeatAt"] = store.now_iso()
    state["nextAction"] = None
    completed = set(state.get("completed") or [])
    ensure_batch_layout(ctx.task_id, ctx.batch_id, "workflow_run")
    state["baselinePacketPath"] = str(ctx.baseline_packet_path)
    state["baselinePacketSummary"] = ctx.baseline_packet.get("summary") or {}
    save_workflow_state(state)
    # 批次级公共信息上提（规格 §4/§14）：任务定义快照 + 受控来源类目，不在对象目录重复。
    from _common.batch_manifest import write_batch_manifest, write_source_catalog, write_task_manifest
    active_spec = _active_spec(ctx)
    write_task_manifest(ctx.task_id, active_spec)
    write_batch_manifest(
        ctx.task_id, ctx.batch_id,
        coverage_targets=(active_spec.get("scope") or {}).get("coverageTargets") or [],
        command="workflow_run",
    )
    write_source_catalog(ctx.task_id, ctx.batch_id)

    if ctx.until and ctx.until in completed:
        until_index = STAGE_NAMES.index(ctx.until)
        until_stage, until_kind, _until_runner = DAG[until_index]
        next_stage = STAGE_NAMES[until_index + 1] if until_index + 1 < len(STAGE_NAMES) else None
        if until_kind == CHECKPOINT:
            ok, issues = _completed_until_revalidation(ctx, until_stage)
            if ok:
                return _stop_at_until(ctx, state, completed, next_stage=next_stage)
            completed = _rewind_to(completed, until_stage)
            state = load_workflow_state(ctx.task_id, ctx.batch_id)
            state["completed"] = sorted(completed)
            state["waitingCheckpoint"] = None
            state["status"] = "running"
            state["nextAction"] = f"revalidate completed --until {until_stage}"
            state["failedObjects"] = list(issues)
            state["heartbeatAt"] = store.now_iso()
            save_workflow_state(state)
            print(
                f"[task run] revalidating completed --until {until_stage}: "
                f"{'; '.join(str(issue) for issue in issues[:5])}",
                flush=True,
            )
        else:
            return _stop_at_until(ctx, state, completed, next_stage=next_stage)

    # 外层循环支持 ReAct 回退后重新遍历 DAG
    for _ in range(MAX_REACT_REWINDS * len(DAG) + len(DAG) + 1):
        progressed = False
        for stage_index, (stage_name, kind, runner) in enumerate(DAG):
            if stage_name in completed:
                continue
            next_stage = STAGE_NAMES[stage_index + 1] if stage_index + 1 < len(STAGE_NAMES) else None
            try:
                result = runner(ctx)
            except Exception as exc:  # noqa: BLE001
                result = StageResult(
                    stage_name,
                    kind,
                    "failed",
                    f"{stage_name} raised {type(exc).__name__}: {exc}",
                    issues=[f"{type(exc).__name__}: {exc}"],
                    fallback_stage=_stage_exception_fallback(stage_name),
                )
            # Stage runners may persist execution-state deltas such as
            # abandoned objects, content refs, agent summaries or retry
            # ledgers. Use the persisted state as the base before the outer
            # loop records stage status; otherwise an older in-memory copy can
            # silently erase object-level fast-fail decisions.
            state = load_workflow_state(ctx.task_id, ctx.batch_id)
            if result.status == "waiting":
                state["completed"] = sorted(completed)
                state["waitingCheckpoint"] = stage_name
                state["status"] = "waiting_agent"
                state["heartbeatAt"] = store.now_iso()
                state["nextAction"] = result.checkpoint_hint
                state["failedObjects"] = list(result.issues or [])
                save_workflow_state(state)
                _write_workflow_packet(
                    ctx,
                    stage_name=stage_name,
                    kind=kind,
                    result=result,
                    completed=sorted(completed),
                    next_stage=next_stage,
                    state=state,
                )
                print(f"[task run] PAUSED at checkpoint '{stage_name}'\n")
                print(result.checkpoint_hint)
                return 10
            if result.status == "failed":
                completed, rewound = _react_rewind(ctx, state, completed, result)
                _write_workflow_packet(
                    ctx,
                    stage_name=stage_name,
                    kind=kind,
                    result=result,
                    completed=sorted(completed),
                    next_stage=next_stage,
                    state=state,
                )
                if rewound:
                    progressed = True
                    break  # 回 DAG 头重跑回退目标
                state["completed"] = sorted(completed)
                state["waitingCheckpoint"] = None
                state["lastFailedStage"] = stage_name
                state["status"] = "manual_required"
                state["failedObjects"] = list(result.issues)
                state["nextAction"] = result.message
                save_workflow_state(state)
                print(f"[task run] FAILED at '{stage_name}': {result.message}", file=sys.stderr)
                return 1
            # done / skipped
            completed.add(stage_name)
            progressed = True
            state["completed"] = sorted(completed)
            state["waitingCheckpoint"] = None
            state["status"] = "running"
            state["heartbeatAt"] = store.now_iso()
            state["nextAction"] = next_stage
            state["failedObjects"] = []
            retry_counts = state.setdefault("retryCounts", {})
            retry_counts.pop(stage_name, None)
            state["retryCounts"] = retry_counts
            infrastructure_retries = state.setdefault("infrastructureRetryCounts", {})
            infrastructure_retries.pop(stage_name, None)
            state["infrastructureRetryCounts"] = infrastructure_retries
            react_rewinds = state.setdefault("reactRewinds", {})
            react_rewinds.pop(stage_name, None)
            state["reactRewinds"] = react_rewinds
            save_workflow_state(state)
            _write_workflow_packet(
                ctx,
                stage_name=stage_name,
                kind=kind,
                result=result,
                completed=sorted(completed),
                next_stage=next_stage,
                state=state,
            )
            print(f"[task run] ✓ {stage_name} ({kind}): {result.message}")
            if ctx.until and stage_name == ctx.until:
                state = load_workflow_state(ctx.task_id, ctx.batch_id)
                return _stop_at_until(ctx, state, completed, next_stage=next_stage)
        else:
            # DAG 全遍历无 break → 全部 stage 完成
            completion_issues = _workflow_completion_issues(ctx, state)
            if completion_issues:
                state["completed"] = sorted(completed)
                state["waitingCheckpoint"] = None
                state["status"] = "manual_required"
                state["failedObjects"] = completion_issues
                state["nextAction"] = "workflow completion gate failed"
                state["heartbeatAt"] = store.now_iso()
                save_workflow_state(state)
                print(
                    f"[task run] FAILED completion gate — {ctx.task_id} / {ctx.batch_id}",
                    file=sys.stderr,
                )
                for issue in completion_issues[:50]:
                    print(f"  - {issue}", file=sys.stderr)
                return 1
            print(f"[task run] WORKFLOW COMPLETE — {ctx.task_id} / {ctx.batch_id}")
            state["status"] = "succeeded"
            state["heartbeatAt"] = store.now_iso()
            state["nextAction"] = None
            _write_workflow_execution_metrics(ctx, state)
            save_workflow_state(state)
            return 0
        if not progressed:
            break
    print(f"[task run] FAILED: ReAct 回退耗尽未收敛 — {ctx.task_id} / {ctx.batch_id}", file=sys.stderr)
    return 1


def _workflow_completion_issues(ctx: PipelineContext, state: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if state.get("waitingCheckpoint"):
        issues.append(f"workflow still waiting at {state.get('waitingCheckpoint')}")
    failed_objects = state.get("failedObjects") or []
    if failed_objects:
        issues.append(f"workflow has failedObjects={len(failed_objects)}")
    last_agent = state.get("lastAgentRun") or {}
    if isinstance(last_agent, dict) and last_agent:
        abandoned_refs = _abandoned_content_refs(state)
        run_refs = {
            str(ref)
            for ref in (last_agent.get("refs") or [])
            if str(ref).strip()
        }
        if not run_refs:
            run_refs = {
                str(out.get("ref") or "")
                for out in (last_agent.get("outcomes") or [])
                if isinstance(out, dict) and str(out.get("ref") or "").strip()
            }
        stale_abandoned_run = bool(run_refs) and run_refs <= abandoned_refs
        if not stale_abandoned_run:
            job_count = int(last_agent.get("jobCount") or 0)
            started = int(last_agent.get("startedCount") or 0)
            finished = int(last_agent.get("finishedCount") or 0)
            infra = int(last_agent.get("infrastructureFailures") or 0)
            if infra:
                issues.append(f"lastAgentRun.infrastructureFailures={infra}")
            if job_count and started <= 0:
                issues.append("lastAgentRun has jobs but no started workers")
            if job_count and finished < job_count:
                issues.append(f"lastAgentRun finishedCount={finished} < jobCount={job_count}")
    if ctx.managed:
        try:
            from task.target_selection import audit_managed_batch

            audit_state = dict(state)
            audit_state["status"] = "succeeded"
            audit_state["waitingCheckpoint"] = None
            audit_state["failedObjects"] = []
            audit_state["nextAction"] = None
            audit = audit_managed_batch(
                ctx.task_id,
                ctx.batch_id,
                workflow_state_override=audit_state,
            )
        except Exception as exc:  # noqa: BLE001
            issues.append(f"managed batch audit unavailable: {exc}")
        else:
            failed_lane_count = int(audit.get("failedLaneCount") or 0)
            if failed_lane_count:
                issues.append(f"managed batch audit failedLaneCount={failed_lane_count}")
            lane_passed = audit.get("lanePassed") or {}
            target_count = int(audit.get("targetCount") or 0)
            for lane in ("homepage", "article", "image"):
                passed = int(lane_passed.get(lane) or 0)
                if target_count and passed != target_count:
                    issues.append(f"managed lane {lane} passed {passed}/{target_count}")
    return issues


def _parse_iso_seconds(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def _estimate_tokens(*parts: object) -> int:
    text = "\n".join(str(part or "") for part in parts if part is not None)
    compact_len = len(re.sub(r"\s+", "", text))
    # Chinese-heavy prompts average below one token per visible character, but
    # use a conservative integer estimate so scale reports are not optimistic.
    return max(1, int((compact_len + 1) / 1.5))


def _read_text_if_file(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _batch_file_elapsed_seconds(root: Path) -> float | None:
    mtimes: list[float] = []
    if not root.is_dir():
        return None
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            mtimes.append(path.stat().st_mtime)
        except OSError:
            continue
    if len(mtimes) < 2:
        return None
    elapsed = max(mtimes) - min(mtimes)
    return elapsed if elapsed > 0 else None


def _review_repaired_refs(ctx: PipelineContext) -> set[str]:
    from _common import content_object

    repaired: set[str] = set()
    root = batch_root(ctx.task_id, ctx.batch_id)
    ref_by_dir = {
        str(content_object.content_object_dir(ctx.task_id, ctx.batch_id, ref)): ref
        for ref in content_object.iter_content_refs(ctx.task_id, ctx.batch_id)
    }
    for path in root.rglob("5.review/repair_report.json"):
        ref = ref_by_dir.get(str(path.parent.parent))
        if ref:
            repaired.add(ref)
    return repaired


def _agent_run_key(row: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    scheduler = row.get("scheduler") if isinstance(row.get("scheduler"), Mapping) else {}
    refs = ",".join(sorted(str(ref) for ref in (row.get("refs") or []) if str(ref).strip()))
    return (
        str(row.get("stage") or ""),
        str((scheduler or {}).get("startedAt") or ""),
        str(row.get("finishedAt") or (scheduler or {}).get("finishedAt") or ""),
        str(row.get("plannedJobCount") or row.get("jobCount") or ""),
        refs,
    )


def _dedupe_agent_runs(rows: list[Any]) -> list[Mapping[str, Any]]:
    seen: set[tuple[str, str, str, str, str]] = set()
    unique: list[Mapping[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        key = _agent_run_key(row)
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def _agent_active_throughput(state: Mapping[str, Any]) -> dict[str, Any]:
    runs: list[Any] = list(state.get("agentRunHistory") or [])
    last = state.get("lastAgentRun")
    if isinstance(last, Mapping):
        runs.append(last)
    agent_runs = _dedupe_agent_runs(runs)
    author_runs = [row for row in agent_runs if str(row.get("stage") or "") == "produce_author"]
    elapsed = 0.0
    finished = 0
    infra_failures = 0
    planned = 0
    for row in author_runs:
        scheduler = row.get("scheduler") if isinstance(row.get("scheduler"), Mapping) else {}
        try:
            elapsed += float((scheduler or {}).get("elapsedSeconds") or 0)
        except (TypeError, ValueError):
            pass
        finished += int(row.get("finishedCount") or 0)
        infra_failures += int(row.get("infrastructureFailures") or 0)
        planned += int(row.get("plannedJobCount") or row.get("jobCount") or 0)
    return {
        "measurementMode": "agent_run_history",
        "authorRunCount": len(author_runs),
        "authorActiveSeconds": round(elapsed, 3),
        "plannedAuthorJobs": planned,
        "finishedAuthorJobs": finished,
        "infrastructureFailures": infra_failures,
        "finishedAuthorJobsPerHour": round((finished / elapsed) * 3600, 4) if elapsed > 0 else 0.0,
    }


def _write_workflow_execution_metrics(ctx: PipelineContext, state: dict[str, Any]) -> None:
    """Persist production-readiness metrics derived from actual batch artifacts.

    The local Cursor SDK path does not expose authoritative billing usage in
    every run.  Until SDK usage is available, the ledger is explicitly marked
    as artifact-estimated and is used for capacity projection, not billing.
    """
    from _common import content_object
    from _common.draft_io import draft_article_path, prompt_path, writing_pack_path
    from _common.release_integrity import scan_runtime_batch_integrity
    from task.production_contracts import build_token_ledger_entry

    if isinstance(state.get("agentRunHistory"), list):
        state["agentRunHistory"] = list(_dedupe_agent_runs(state["agentRunHistory"]))[-20:]

    root = batch_root(ctx.task_id, ctx.batch_id)
    shared = root / "_shared"
    shared.mkdir(parents=True, exist_ok=True)
    abandoned_refs = _abandoned_content_refs(state)
    refs = [
        ref for ref in content_object.iter_content_refs(ctx.task_id, ctx.batch_id)
        if ref not in abandoned_refs
    ]
    entries: list[dict[str, Any]] = []
    default_budget = int(((ctx.spec.get("tokenBudget") or {}).get("perObjectTokens") or 12000))
    for ref in refs:
        coords = content_object.content_coords(ctx.task_id, ctx.batch_id, ref) or {}
        prompt = _read_text_if_file(prompt_path(ctx.task_id, ctx.batch_id, ref))
        pack = _read_text_if_file(writing_pack_path(ctx.task_id, ctx.batch_id, ref))
        draft = _read_text_if_file(draft_article_path(ctx.task_id, ctx.batch_id, ref))
        used = _estimate_tokens(prompt, pack, draft)
        entries.append(
            build_token_ledger_entry(
                supply_task_id=ctx.task_id,
                batch_id=ctx.batch_id,
                job_id=f"artifact:{ref}",
                creator_profile_id=str((ctx.spec.get("creatorProfileId") or "system_editor")),
                content_type=str(coords.get("contentType") or "article"),
                budget_tokens=max(default_budget, used),
                used_tokens=used,
                cache_hits={
                    "sopSummary": False,
                    "creatorProfileSummary": False,
                    "evidencePackSummary": bool(pack),
                },
                cost_usd=0.0,
            )
        )
    total_tokens = sum(int(entry.get("usedTokens") or 0) for entry in entries)
    ledger = {
        "schemaVersion": "quwoquan.token_ledger",
        "taskId": ctx.task_id,
        "batchId": ctx.batch_id,
        "measurementMode": "estimated_from_artifacts",
        "entries": entries,
        "summary": {
            "entryCount": len(entries),
            "usedTokens": total_tokens,
            "averageUsedTokens": round(total_tokens / len(entries), 2) if entries else 0,
            "costUsd": 0.0,
            "unitPassedCostUsd": 0.0,
        },
    }
    write_json(shared / "token_ledger.json", ledger)

    runtime_report = scan_runtime_batch_integrity(ctx.task_id, ctx.batch_id)
    stats = runtime_report.get("stats") if isinstance(runtime_report, Mapping) else {}
    post_count = int((stats or {}).get("postCount") or 0)
    start = _parse_iso_seconds(state.get("startedAt"))
    end = _parse_iso_seconds(store.now_iso())
    elapsed_seconds = max(1.0, (end - start) if start and end else 1.0)
    file_elapsed = _batch_file_elapsed_seconds(root)
    if file_elapsed and file_elapsed > elapsed_seconds:
        elapsed_seconds = file_elapsed
    objects_per_hour = round((post_count / elapsed_seconds) * 3600, 4) if post_count else 0.0
    state["throughput"] = {
        "measurementMode": "wall_clock_current_batch",
        "elapsedSeconds": round(elapsed_seconds, 3),
        "postCount": post_count,
        "objectsPerHour": objects_per_hour,
        "maxWorkers": int(ctx.max_workers or 1),
        "agentActive": _agent_active_throughput(state),
    }
    repaired = _review_repaired_refs(ctx)
    total_reviewed = len(refs)
    first_pass = (
        round((total_reviewed - len(repaired)) / total_reviewed, 4)
        if total_reviewed
        else 0.0
    )
    state["quality"] = {
        "firstPassRate": first_pass,
        "reviewedRefs": total_reviewed,
        "repairedRefs": len(repaired),
        "measurementMode": "repair_report_derived",
    }


def _managed_preflight(task_id: str, batch_id: str, spec: dict, args: argparse.Namespace) -> list[str]:
    """托管任务启动前失败快返；不创建 batch/runtime。"""
    issues: list[str] = []
    if str(spec.get("status") or "") != "active":
        issues.append(f"task status must be active for --managed, got {spec.get('status')!r}")
    targets = (spec.get("scope") or {}).get("coverageTargets") or []
    if not targets:
        issues.append("scope.coverageTargets must not be empty")
    quotas = ((spec.get("content") or {}).get("quotas") or {})
    for field, expected_min in (
        ("entityArticlesPerTarget", 1),
        ("entityHomepagesPerTarget", 1),
    ):
        if int(quotas.get(field) or 0) < expected_min:
            issues.append(f"content.quotas.{field} must be >= {expected_min}")
    if int(quotas.get("galleryPostsPerTarget") or 0) or int(quotas.get("galleryPosts") or 0):
        issues.append(
            "galleryPosts/galleryPostsPerTarget are retired for --managed; "
            "use content.quotas.imageWorksPerTarget"
        )
    image_quota = int(quotas.get("imageWorksPerTarget") or 0)
    if image_quota < 1:
        issues.append("content.quotas.imageWorksPerTarget must be >= 1")
    content = spec.get("content") or {}
    if str(content.get("modalityContract") or "") != "separated_research":
        issues.append("content.modalityContract must be separated_research for --managed")
    research = content.get("research") or {}
    if set(research.get("lanes") or []) != {"homepage", "article", "image"}:
        issues.append("content.research.lanes must contain homepage, article and image")
    if bool(research.get("allowAiImages", True)):
        issues.append("content.research.allowAiImages must be false")
    if str(getattr(args, "runtime", "local")) != "local":
        issues.append("--managed production runs require --runtime local")
    try:
        from _common.python_runtime import environment_preflight

        env_report = environment_preflight(require_cursor_key=True, check_network=True)
    except Exception as exc:  # noqa: BLE001
        env_report = {
            "schemaVersion": "quwoquan_data.env_preflight",
            "ready": False,
            "issues": [f"environment preflight unavailable: {exc}"],
        }
        setattr(args, "_env_preflight_report", env_report)
        issues.append(f"environment preflight unavailable: {exc}")
    else:
        setattr(args, "_env_preflight_report", env_report)
        issues.extend([str(item) for item in (env_report.get("issues") or [])])
    if not task_baseline_freeze_packet_path(task_id).is_file() and not getattr(args, "baseline_packet", None):
        issues.append("baseline freeze packet missing")
    return issues


def _write_managed_env_ready_report(ctx: PipelineContext, args: argparse.Namespace) -> Path:
    report = getattr(args, "_env_preflight_report", None)
    if not isinstance(report, Mapping):
        report = {"ready": False, "issues": ["managed preflight report missing"]}
    payload = {
        "schemaVersion": "quwoquan_data.env_ready_report",
        "taskId": ctx.task_id,
        "batchId": ctx.batch_id,
        "recordedAt": store.now_iso(),
        "ready": bool(report.get("ready")),
        "preflight": dict(report),
    }
    path = batch_root(ctx.task_id, ctx.batch_id) / "_shared" / "env_ready_report.json"
    write_json(path, payload)
    return path


def _cursor_bridge_error_is_retryable(
    message: str,
    *,
    code: str | None = None,
    explicit_retryable: bool = False,
) -> bool:
    """Classify Cursor bridge startup/discovery failures as infra retryable."""
    lowered = str(message or "").casefold()
    code_lower = str(code or "").casefold()
    retry_markers = (
        "connection refused",
        "connecterror",
        "connection reset",
        "bridge request failed",
        "exited before discovery",
        "failed before discovery",
        "cursor-sdk-bridge failed",
        "tool-callback-auth-token",
        "internal error",
    )
    return (
        bool(explicit_retryable)
        or code_lower == "internal"
        or any(marker in lowered for marker in retry_markers)
    )


def _cursor_safe_auth_token_factory(original: Callable[[], str]) -> Callable[[], str]:
    """Wrap Cursor SDK callback token generation for argv parsers.

    The bundled Cursor bridge accepts `--tool-callback-auth-token <value>`.
    `secrets.token_urlsafe(...)` may legally return a value beginning with `-`;
    the bridge parser can then treat the token as another flag and fail with
    "Missing value for --tool-callback-auth-token". Keep the token random, but
    prefix the rare leading-dash case before it reaches argv.
    """

    def _factory() -> str:
        token = str(original() or "")
        if token.startswith("-"):
            return "qwq_" + token.lstrip("-")
        return token

    setattr(_factory, "_qwq_safe_token_factory", True)
    return _factory


def _patch_cursor_sdk_tool_callback_token() -> None:
    try:
        import cursor_sdk._tool_callback as tool_callback  # type: ignore
    except Exception:  # noqa: BLE001
        return
    original = getattr(tool_callback, "_new_auth_token", None)
    if not callable(original) or getattr(original, "_qwq_safe_token_factory", False):
        return
    setattr(tool_callback, "_new_auth_token", _cursor_safe_auth_token_factory(original))


@contextmanager
def _cursor_bridge_launch_guard():
    """Serialize Cursor bridge discovery across isolated worker processes."""
    lock_path = Path(
        os.environ.get(
            "QWQ_CURSOR_BRIDGE_LAUNCH_LOCK",
            str(Path(tempfile.gettempdir()) / "qwq-cursor-bridge-launch.lock"),
        )
    )
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import fcntl  # type: ignore
    except Exception:  # noqa: BLE001
        yield
        return
    with lock_path.open("a", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
            if _CURSOR_BRIDGE_LAUNCH_COOLDOWN_SECONDS:
                time.sleep(_CURSOR_BRIDGE_LAUNCH_COOLDOWN_SECONDS)
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _terminate_workspace_cursor_bridges(workspace: Path) -> None:
    """Best-effort cleanup for half-started Cursor SDK bridges in this workspace."""
    try:
        proc = subprocess.run(
            ["ps", "-ax", "-o", "pid=,command="],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except Exception:  # noqa: BLE001
        return
    workspace_text = str(workspace)
    current_pid = os.getpid()
    for line in proc.stdout.splitlines():
        if "cursor-sdk-bridge" not in line or workspace_text not in line:
            continue
        parts = line.strip().split(maxsplit=1)
        if not parts:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        if pid <= 0 or pid == current_pid:
            continue
        _terminate_pid_if_alive(pid)


def _default_managed_agent_runner(ctx: PipelineContext, prompt: str) -> dict[str, Any]:
    """在当前 workspace 启动一个本地 Cursor Agent；只返回终态，推进由父进程校验。"""
    try:
        from cursor_sdk import (  # type: ignore
            Agent,
            AgentOptions,
            Client,
            CursorAgentError,
            LocalAgentOptions,
        )
    except Exception as exc:  # noqa: BLE001
        return {"started": False, "status": "error", "error": f"cursor_sdk unavailable: {exc}"}
    key = os.environ.get("CURSOR_API_KEY")
    if not key:
        return {"started": False, "status": "error", "error": "CURSOR_API_KEY missing"}
    _patch_cursor_sdk_tool_callback_token()
    result = None
    last_error: dict[str, Any] | None = None
    workspace = Path.cwd()
    for attempt in range(3):
        client = None
        bridge_pids: list[int] = []
        try:
            if attempt > 0 and str(ctx.runtime) == "local" and MANAGED_LOCAL_CURSOR_MAX_WORKERS == 1:
                _terminate_workspace_cursor_bridges(workspace)
            with _cursor_bridge_launch_guard():
                client = Client.launch_bridge(
                    workspace=str(workspace),
                    max_retries=3,
                    allow_api_key_env_fallback=True,
                )
            owned_bridge = getattr(client, "_owned_bridge", None)
            endpoint = getattr(owned_bridge, "endpoint", None)
            process = getattr(owned_bridge, "process", None)
            for pid in (
                getattr(process, "pid", None),
                getattr(endpoint, "pid", None),
            ):
                if isinstance(pid, int) and pid > 0 and pid not in bridge_pids:
                    bridge_pids.append(pid)
            result = Agent.prompt(
                prompt,
                AgentOptions(
                    api_key=key,
                    model=ctx.model,
                    local=LocalAgentOptions(cwd=str(Path.cwd())),
                ),
                client=client,
            )
            break
        except CursorAgentError as exc:
            message = getattr(exc, "message", str(exc))
            retryable_bridge = _cursor_bridge_error_is_retryable(
                message,
                code=str(getattr(exc, "code", "") or ""),
                explicit_retryable=bool(getattr(exc, "is_retryable", False)),
            )
            last_error = {
                "started": False,
                "status": "error",
                "error": message,
                "retryable": retryable_bridge,
                "errorCode": getattr(exc, "code", None),
                "requestId": getattr(exc, "request_id", None),
                    "attempts": attempt + 1,
                }
            if attempt < 2 and retryable_bridge:
                if str(ctx.runtime) == "local" and MANAGED_LOCAL_CURSOR_MAX_WORKERS == 1:
                    _terminate_workspace_cursor_bridges(workspace)
                time.sleep(max(_CURSOR_BRIDGE_LAUNCH_COOLDOWN_SECONDS, 2.0) + 0.5 * (attempt + 1))
                continue
            return last_error
        except RuntimeError as exc:
            message = f"{type(exc).__name__}: {exc}"
            lowered = message.casefold()
            retryable_bridge = (
                "client has been closed" in lowered
                or _cursor_bridge_error_is_retryable(message)
            )
            last_error = {
                "started": False,
                "status": "error",
                "error": message,
                "retryable": retryable_bridge,
                "attempts": attempt + 1,
            }
            if attempt < 2 and retryable_bridge:
                if str(ctx.runtime) == "local" and MANAGED_LOCAL_CURSOR_MAX_WORKERS == 1:
                    _terminate_workspace_cursor_bridges(workspace)
                time.sleep(max(_CURSOR_BRIDGE_LAUNCH_COOLDOWN_SECONDS, 2.0) + 0.5 * (attempt + 1))
                continue
            return last_error
        except Exception as exc:  # noqa: BLE001
            last_error = {
                "started": False,
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "retryable": False,
                "attempts": attempt + 1,
            }
            return last_error
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:  # noqa: BLE001
                    pass
            for pid in bridge_pids:
                _terminate_pid_if_alive(pid)
    if result is None:
        return last_error or {
            "started": False,
            "status": "error",
            "error": "Cursor isolated bridge retry exhausted without a run result",
            "retryable": True,
        }
    status = str(getattr(result, "status", "error"))
    result_text = str(getattr(result, "result", "") or "").strip()
    return {
        "started": True,
        "status": status,
        "error": None if status == "finished" else (
            f"agent status={status}: {result_text[:1600]}" if result_text else f"agent status={status}"
        ),
        "result": result_text[:4000],
        "agentId": getattr(result, "agent_id", None),
        "runId": getattr(result, "id", None),
        "durationMs": int(getattr(result, "duration_ms", 0) or 0),
    }


def _redact_managed_secret(text: str) -> str:
    text = re.sub(r"crsr_[A-Za-z0-9]+", "<redacted-cursor-key>", str(text or ""))
    text = re.sub(
        r"(--tool-callback-auth-token\s+)[^\s]+",
        r"\1<redacted-token>",
        text,
    )
    return text


def _managed_agent_worker_main() -> None:
    """Subprocess entrypoint for one real Cursor job.

    Parent orchestration cannot cancel a thread blocked inside Agent.prompt, so
    production managed runs execute each SDK call in a short-lived subprocess.
    Fake test runners still bypass this path through ctx.agent_runner.
    """
    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    ctx_payload = payload.get("ctx") or {}
    ctx = PipelineContext(
        task_id=str(ctx_payload.get("taskId") or ""),
        batch_id=str(ctx_payload.get("batchId") or ""),
        entity_ids=[str(item) for item in (ctx_payload.get("entityIds") or [])],
        spec=ctx_payload.get("spec") or {},
        managed=True,
        runtime=str(ctx_payload.get("runtime") or "local"),
        max_workers=int(ctx_payload.get("maxWorkers") or 1),
        model=str(ctx_payload.get("model") or "composer-2.5"),
        release_only=bool(ctx_payload.get("releaseOnly")),
    )
    outcome = _default_managed_agent_runner(ctx, str(payload.get("prompt") or ""))
    output_path.write_text(json.dumps(outcome, ensure_ascii=False, indent=2), encoding="utf-8")


def _default_managed_agent_runner_isolated(ctx: PipelineContext, prompt: str) -> dict[str, Any]:
    """Run the real Cursor SDK worker in a killable subprocess with a hard deadline."""
    with tempfile.TemporaryDirectory(prefix="qwq-managed-agent-") as tmp:
        tmp_path = Path(tmp)
        input_path = tmp_path / "input.json"
        output_path = tmp_path / "output.json"
        input_path.write_text(
            json.dumps(
                {
                    "ctx": {
                        "taskId": ctx.task_id,
                        "batchId": ctx.batch_id,
                        "entityIds": ctx.entity_ids,
                        "spec": ctx.spec,
                        "runtime": ctx.runtime,
                        "maxWorkers": ctx.max_workers,
                        "model": ctx.model,
                        "releaseOnly": ctx.release_only,
                    },
                    "prompt": prompt,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        scripts_dir = str(Path(__file__).resolve().parents[1])
        env = os.environ.copy()
        env["PYTHONPATH"] = (
            scripts_dir
            if not env.get("PYTHONPATH")
            else scripts_dir + os.pathsep + str(env.get("PYTHONPATH"))
        )
        proc = subprocess.Popen(
            [
                sys.executable,
                "-c",
                (
                    "from task.run import _managed_agent_worker_main; "
                    "_managed_agent_worker_main()"
                ),
                str(input_path),
                str(output_path),
            ],
            cwd=str(Path.cwd()),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=MANAGED_AGENT_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except OSError:
                pass
            try:
                stdout, stderr = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except OSError:
                    pass
                stdout, stderr = proc.communicate()
            return {
                "started": False,
                "status": "error",
                "error": f"agent subprocess timed out after {MANAGED_AGENT_TIMEOUT_SECONDS}s",
                "retryable": True,
                "errorType": "timeout",
                "stdoutTail": _redact_managed_secret(stdout)[-1200:],
                "stderrTail": _redact_managed_secret(stderr)[-1200:],
            }
        if output_path.is_file():
            try:
                outcome = json.loads(output_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError) as exc:
                return {
                    "started": False,
                    "status": "error",
                    "error": f"agent subprocess wrote unreadable output: {exc}",
                    "retryable": True,
                }
            if isinstance(outcome, dict):
                if outcome.get("error"):
                    outcome["error"] = _redact_managed_secret(str(outcome.get("error") or ""))
                return outcome
        return {
            "started": False,
            "status": "error",
            "error": (
                f"agent subprocess exited {proc.returncode} without outcome; "
                f"stderr={_redact_managed_secret(stderr)[-1200:]}"
            ),
            "retryable": proc.returncode not in (0,),
            "stdoutTail": _redact_managed_secret(stdout)[-1200:],
        }


def _terminate_pid_if_alive(pid: int) -> None:
    """Best-effort cleanup for Cursor bridge node children orphaned by the shell wrapper."""
    if pid <= 0:
        return
    try:
        os.kill(pid, 0)
    except OSError:
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.kill(pid, sig)
        except OSError:
            return
        time.sleep(0.2)
        try:
            os.kill(pid, 0)
        except OSError:
            return


def _checkpoint_prompts(ctx: PipelineContext, stage: str) -> list[str]:
    """把 checkpoint 拆为可并发且写集互斥的 Agent 任务。"""
    from _common.content_source_registry import render_lane_source_prompt

    base = (
        "你是 quwoquan_data 托管工作流的执行 Agent。只完成本提示指定的 checkpoint，"
        "不要递归运行整条 workflow，不要发布到 publish/，不要修改其它 task/batch。"
        f"\n任务: {ctx.task_id}\n批次: {ctx.batch_id}\n"
    )
    if stage == "download_plan":
        from _common.source_unit import resolve_entity_object_dir

        etype = _coverage_entity_type(ctx.spec)
        quotas = ((ctx.spec.get("content") or {}).get("quotas") or {})
        per_target_articles = max(1, int(quotas.get("entityArticlesPerTarget") or 0))
        per_target_image_works = max(1, int(quotas.get("imageWorksPerTarget") or 0))
        acceptance = ctx.spec.get("acceptance") or {}
        required_angles = [
            str(angle).strip()
            for angle in (acceptance.get("requiredAngles") or [])
            if str(angle).strip()
        ]
        article_intents = [
            angle for angle in required_angles
            if angle not in {"image", "imagePost", "gallery"}
        ] or ["planning_consultation", "decision_experience"]
        done, issues = _source_plan_filled(ctx)
        if done:
            return []
        vertical = str(ctx.spec.get("vertical") or "travel")
        pending_lanes_by_entity: dict[str, dict[str, list[str]]] = {}
        for entity in ctx.entity_ids:
            lane_issues = {
                lane: found
                for lane in ("homepage", "article", "image")
                if (found := _download_research_lane_issues(ctx, entity, etype, lane))
            }
            if lane_issues:
                pending_lanes_by_entity[entity] = lane_issues
        repair_by_entity: dict[str, dict[str, Any]] = {}
        repair_path = _download_repair_path(ctx)
        if repair_path.is_file():
            repair_packet = read_json(repair_path)
            repair_by_entity = {
                str(item.get("entityId") or ""): item
                for item in (repair_packet.get("entities") or [])
                if isinstance(item, dict)
            }
        prompts = []
        for entity in ctx.entity_ids:
            repair = repair_by_entity.get(entity) or {}
            repair_active_issues = _download_repair_active_issues(ctx, repair) if repair else []
            repair_pending = (
                bool(repair)
                and _download_repair_entry_pending(repair)
                and bool(repair_active_issues)
            )
            missing_lanes = dict(pending_lanes_by_entity.get(entity) or {})
            for lane in sorted(_download_repair_lanes(repair) if repair_pending else set()):
                repair_lane_issues = (
                    ((repair.get("researchLaneIssues") or {}).get(lane) or [])
                    if isinstance(repair.get("researchLaneIssues"), dict)
                    else []
                )
                if not repair_lane_issues:
                    repair_lane_issues = repair_active_issues or ["download_repair required"]
                missing_lanes.setdefault(lane, [str(item) for item in repair_lane_issues])
            if not missing_lanes:
                continue
            object_dir = resolve_entity_object_dir(
                ctx.task_id, ctx.batch_id, entity, etype_hint=etype
            )
            if repair and not repair_pending:
                repair = {}
            repair_hint = ""
            lane_hint = "\n当前缺口：\n- " + "\n- ".join(
                f"{lane}: {'; '.join(items[:4])}" for lane, items in missing_lanes.items()
            )
            if repair:
                diagnostics = repair.get("downloadDiagnostics") or {}
                rejected_by_category = diagnostics.get("rejectedByCategory") if isinstance(diagnostics, dict) else {}
                diagnostic_hint = ""
                if rejected_by_category:
                    non_zero = [
                        f"{key}={value}"
                        for key, value in rejected_by_category.items()
                        if int(value or 0)
                    ]
                    if non_zero:
                        diagnostic_hint = "\n下载失败分类：" + ", ".join(non_zero)
                image_hint_rows: list[str] = []
                for hint in repair.get("imageRepairHints") or []:
                    if not isinstance(hint, dict):
                        continue
                    if str(hint.get("lane") or "") not in missing_lanes:
                        continue
                    candidate = str(hint.get("sameSourceHighResCandidate") or "").strip()
                    candidate_text = f"，同源高清候选: {candidate}" if candidate else ""
                    image_hint_rows.append(
                        f"{hint.get('lane')}/{hint.get('sourceId')}#{hint.get('imageIndex')}: "
                        f"{hint.get('action')}，{hint.get('issue')}{candidate_text}"
                    )
                    if len(image_hint_rows) >= 8:
                        break
                image_repair_hint = (
                    "\n源图修复指令：\n- " + "\n- ".join(image_hint_rows)
                    if image_hint_rows
                    else ""
                )
                repair_hint = (
                    "\n这是 download_repair，不是首次规划。先读取以下真实 gate 报告并逐项修复：\n- "
                    + "\n- ".join(str(item) for item in (repair.get("reportPaths") or []))
                    + "\n当前失败摘要："
                    + "; ".join(str(item) for item in (repair.get("issues") or []))
                    + diagnostic_hint
                    + image_repair_hint
                    + "\n替换抓取失败、正文为空、探针页、误相关或图片不足的条目；"
                    "不要只改描述字段。完成后必须让 source_plan 文件 mtime 更新。"
                )
            repair_hint += lane_hint
            homepage_path = object_dir / "1.download" / "homepage_source_plan.json"
            article_path = object_dir / "1.download" / "article_source_plan.json"
            image_path = object_dir / "1.download" / "image_source_plan.json"
            if "homepage" in missing_lanes:
                prompts.append(
                    "[AGENT_LANE:homepage]\n"
                    + base
                    + f"\n对象: {entity}\n写入: {homepage_path}\n"
                    + repair_hint
                    + render_lane_source_prompt(
                        "homepage",
                        vertical=vertical,
                        per_target_articles=per_target_articles,
                        per_target_image_works=per_target_image_works,
                    )
                    + "至少保留 2 个真实可抓取来源。普通网页一律 "
                    "factual_reference_only；只有明确许可才能 licensed_adaptation。"
                    "主页图片必须来自这些主页来源自身的 imageUrls，逐图填写许可、署名、条款、授权快照、"
                    "usageScope、width、height 和具体相关性；实际图片必须可下载，宽≥640、高≥426、长边≥800，"
                    "不要使用缩略图/压缩图/探针图。不得读取或修改 article/image 计划。",
                )
            if "article" in missing_lanes:
                prompts.append(
                    "[AGENT_LANE:article]\n"
                    + base
                    + f"\n对象: {entity}\n写入: {article_path}\n"
                    + repair_hint
                    + render_lane_source_prompt(
                        "article",
                        vertical=vertical,
                        per_target_articles=per_target_articles,
                        per_target_image_works=per_target_image_works,
                        article_intents=article_intents,
                    )
                    + "每条写 "
                    "source_id/platform/url/sourceUseMode 和权利字段；每个可作为文章底稿的 source "
                    "必须带该页面自身可发布的 imageUrls（含 license/credit/termsUrl/licenseSnapshot/"
                    "authorizationProof/usageScope/width/height/relevance），源图是文章底稿的一部分；"
                    "sourceUseMode 是文字来源权利模式，不是图片许可；imageUrls[].license 严禁填写 "
                    "factual_reference_only/licensed_adaptation/blocked，必须是明确图片许可或授权类型 "
                    "（如 CC BY-SA 4.0、CC BY 4.0、Public domain、photographer_authorized、"
                    "scenic_official_authorized 等），否则替换整条 source unit 或换同源可授权图片；"
                    "实际图片必须可下载，宽≥640、高≥426、长边≥800，禁止使用 r_720x480、600x600、缩略图、"
                    "平台压缩图或无独立授权证明的图片。不得复用 homepage 计划 URL，"
                    "不得读取或修改 image 计划。",
                )
            if "image" in missing_lanes:
                prompts.append(
                    "[AGENT_LANE:image]\n"
                    + base
                    + f"\n对象: {entity}\n写入: {image_path}\n"
                    + repair_hint
                    + render_lane_source_prompt(
                        "image",
                        vertical=vertical,
                        per_target_articles=per_target_articles,
                        per_target_image_works=per_target_image_works,
                    )
                    + "输出 collections；每组必须有 sourceCollectionId、creator、collectionPageUrl、"
                    "license、termsUrl、licenseSnapshot、authorizationProof、usageScope 和 images。"
                    "license 必须是明确图片许可或授权类型，严禁使用 factual_reference_only/"
                    "licensed_adaptation/blocked 这类 sourceUseMode 名称冒充图片许可。"
                    "每张图必须填写 width/height，实际可下载，宽≥640、高≥426、长边≥800，"
                    "并直接呈现该景区；本批禁止 AI 图。"
                    f"至少形成 {per_target_image_works} 个图片作品的容量，"
                    "每个作品可选同一集合内 1..20 张，禁止跨作者/页面/专辑/授权凭证混图。"
                    "不得读取或修改 homepage/article 计划。",
                )
        return prompts
    if stage == "build_homepage":
        from _common.source_unit import resolve_entity_object_dir

        etype = _coverage_entity_type(ctx.spec)
        prompts = []
        pending_entities = _homepage_pending_entities(ctx)
        for entity in pending_entities:
            obj = resolve_entity_object_dir(ctx.task_id, ctx.batch_id, entity, etype_hint=etype)
            prompts.append(
                base
                + f"\n对象: {entity}\n对象目录: {obj}\n"
                "读取 3.compose/entity_page_input.json、已下载 source.md/source.clean.md、SOP 和图片资产，"
                "只为该实体完成 page.md、_entity.json、manifest.json 以及要求的 4.draft/5.review 证据。"
                "主页必须多来源事实综合、独立表达，不得轻改百科原文；至少引用一张已过权利和安全门的真实图。"
                "运行该实体适用的 build validate/review，修复到 validator 通过。"
            )
        return prompts
    if stage == "content_plan":
        prompt_spec = _active_spec(ctx)
        quotas = ((prompt_spec.get("content") or {}).get("quotas") or {})
        acceptance = prompt_spec.get("acceptance") or {}
        required_angles = [
            str(angle).strip()
            for angle in (acceptance.get("requiredAngles") or [])
            if str(angle).strip()
        ]
        content = prompt_spec.get("content") or {}
        active_targets = [
            str(target.get("name") or "").strip()
            for target in (prompt_spec.get("scope") or {}).get("coverageTargets") or []
            if str(target.get("name") or "").strip()
        ]
        return [
            base
            + "\n为 activeCoverageTargets 完成证据驱动 content_plan；abandoned 对象不得再规划、注册或写 brief。"
            f"\nactiveCoverageTargets={json.dumps(active_targets, ensure_ascii=False)}"
            f"\n这是 workflow effective spec，不是只读 task.yaml；必须以这里为准: {json.dumps({'scope': prompt_spec.get('scope') or {}, 'content': content, 'acceptance': acceptance}, ensure_ascii=False)}"
            f"\n精确配额: {json.dumps(quotas, ensure_ascii=False)}；requiredAngles={required_angles}。"
            "\n每个 coverageTarget 必须恰好满足 entityArticlesPerTarget 篇文章和 imageWorksPerTarget 个 image work，"
            "不得沿用旧 2+2 示例。若现有 content_plan_packet 与配额冲突，直接重写。"
            "\n类型按底稿形态路由："
            "实体主页主底稿来自 Wiki/百科/知识图谱/官网等实体介绍源，政府/文旅/媒体只作 supporting evidence；"
            "文章底稿是 article_research 的图文混合来源，UGC、社区、媒体、官方和垂类专业文章同等按质量与权利筛选，源图也是底稿的一部分，article 写 baseSourceRef 且一稿一用；"
            "图片作品底稿是 image_research 的图片集合，carrier=image，只写 sourceCollectionId/assetRefs，"
            "同一作品只能使用同一作者/页面/专辑/授权凭证下 1..20 张图，标题<=80字且可空，配文<=300字且可空。"
            "\n文章只能引用 article_research；图片只能引用 image_research；homepage 来源不得拿来当文章/图片底稿。"
            "同一 baseSourceRef 在整个批次只能被一篇文章使用，严禁输出 baseSourceReusePolicy 或 "
            "multi_intent_source_bundle；如果可用 article base 不足，必须停留在 content_plan 修复，不能复用底稿凑数。"
            "写 _shared/content_plan_packet.json（schemaVersion=quwoquan_data.content_plan_packet），"
            "注册 content_object，并写每项 3.compose/brief.json。"
            "ref/title 必须由证据归纳；evidenceRefs 必须存在，blocked/reject 来源不可引用。"
            "\n完成后运行 content_plan validator 并修复到无问题。"
        ]
    if stage == "produce_author":
        from _common.draft_io import (
            draft_article_path,
            draft_meta_path,
            prompt_path,
            read_writing_pack,
            writing_pack_path,
        )

        _ok, pending = _drafts_authored(ctx)
        return [
            base
            + (
                "\n[AGENT_LANE:image]"
                if str((read_writing_pack(ctx.task_id, ctx.batch_id, ref) or {}).get("carrier") or "") in ("image", "gallery")
                else "\n[AGENT_LANE:article]"
            )
            + f"\n内容 ref: {ref}\n读取: {prompt_path(ctx.task_id, ctx.batch_id, ref)}"
            + f"\n读取: {writing_pack_path(ctx.task_id, ctx.batch_id, ref)}"
            + f"\n写入: {draft_article_path(ctx.task_id, ctx.batch_id, ref)}"
            + f"\n写入: {draft_meta_path(ctx.task_id, ctx.batch_id, ref)}"
            + "\n严格依据证据独立创作；普通网页只取事实，不复现原句/原结构；授权来源按许可改编并保留归因。"
            "若对象 5.review/repair_report.json 存在，必须先逐项修复其中问题。逐条覆盖 writing_pack 的 "
            "mustIncludeFacts；article 载体必须有连贯散文段落和至少三个结构层次；image 载体只生成"
            "可选标题/整组配文和结构化选图，不得创作长文。"
            "article 载体的正文必须显式落下 review 可识别的编辑信号：首段用所选 openingStrategy 的真实钩子开场"
            "（例如 conclusion_first 用“先说结论/直接说/一句话”，question_hook 用真实问题，scene_immersion 用具体时间/天气/动作），"
            "正文必须分别出现具体喜欢/打动点，以及不足/遗憾/劝退/不建议/失望/踩雷等负向取舍表达，并至少写 2 处“如果你…建议…”式决策判断。"
            "禁止把取舍判断写成固定小标题，尤其不要使用“它到底适合谁/这条线适合谁/这趟适合谁/到底适合谁/适合谁”。"
            "收尾必须从本篇底稿的一个具体细节自然落下，不得使用同批通用总结句、口号式劝行、固定适配人群段或统一结论模板。"
            "image 载体正文只允许标题和一段整组配文，配文控制在 260 个中文字符以内，不写二级标题、不写长段落、不输出自检表格。"
            "除非 writing_pack 明确证明为允许公开的官方号码，否则正文不得写电话号码。"
            "只引用 writing_pack 中的 assetId 和 sourcePath。draft_meta 必须 generator=agent，记录 model、"
            "citedSourcePaths、coveredFacts、styleFamily、openingStrategy、creativePlan、selfCritique。"
            "creativePlan 必须先列 2-3 个候选构思并说明 selectedPlanId/selectionReason；selfCritique 必须覆盖 "
            "readerPromise、titlePromise、informationDensity、evidenceBoundary、personaBoundary。完成后做自检，但不要运行批次发布。"
            for ref in pending
        ]
    return []


def _checkpoint_is_done(ctx: PipelineContext, stage: str) -> tuple[bool, list[str]]:
    checkers: dict[str, Callable[[PipelineContext], tuple[bool, list[str]]]] = {
        "download_plan": _source_plan_filled,
        "build_homepage": _homepages_done,
        "content_plan": _content_plan_done,
        "produce_author": _drafts_authored,
    }
    checker = checkers.get(stage)
    return checker(ctx) if checker else (False, [f"unsupported managed checkpoint {stage}"])


def _managed_author_ref(prompt: str) -> str:
    for line in prompt.splitlines():
        prefix = "内容 ref:"
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return ""


def _managed_author_failure_refs(outcomes: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for outcome in outcomes:
        if str(outcome.get("status")) == "finished":
            continue
        ref = str(outcome.get("ref") or "").strip()
        if not ref or ref in seen:
            continue
        seen.add(ref)
        refs.append(ref)
    return refs


def _managed_prompt_entity(prompt: str) -> str:
    for line in prompt.splitlines():
        prefix = "对象:"
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return ""


def _managed_prompt_lane(prompt: str) -> str:
    match = re.search(r"\[AGENT_LANE:(homepage|article|image)\]", prompt)
    return match.group(1) if match else "default"


def _managed_checkpoint_job_issues(
    ctx: PipelineContext,
    *,
    stage: str,
    prompt: str,
) -> list[str]:
    if stage == "download_plan":
        lane = _managed_prompt_lane(prompt)
        entity = _managed_prompt_entity(prompt)
        if lane not in {"homepage", "article", "image"} or not entity:
            return [f"download_plan prompt missing target lane/entity: lane={lane!r}, entity={entity!r}"]
        etype = _coverage_entity_type(ctx.spec)
        issues = list(_download_research_lane_issues(ctx, entity, etype, lane))
        pending_repair = _pending_download_repair_unresolved(ctx).get(entity) or {}
        for repair_lane in (lane, "download"):
            for issue in pending_repair.get(repair_lane) or []:
                text = str(issue or "").strip()
                if text and text not in issues:
                    issues.append(text)
        return issues
    return []


def _finalize_managed_author_outputs(
    ctx: PipelineContext,
    prompts: list[str],
    outcomes: list[dict[str, Any]],
) -> None:
    """用确定性 helper 补齐 Agent 草稿的 run ID 和四类 provenance hash。"""
    from _common.draft_io import (
        compute_draft_provenance_facts,
        draft_article_path,
        draft_meta_path,
        is_placeholder,
        read_draft_meta,
        read_writing_pack,
    )

    for outcome in outcomes:
        if str(outcome.get("status")) != "finished":
            continue
        job_index = int(outcome.get("jobIndex", -1))
        if job_index < 0 or job_index >= len(prompts):
            continue
        ref = _managed_author_ref(prompts[job_index])
        if not ref:
            continue
        article_path = draft_article_path(ctx.task_id, ctx.batch_id, ref)
        if not article_path.is_file():
            continue
        article = article_path.read_text(encoding="utf-8")
        if is_placeholder(article):
            continue
        meta = read_draft_meta(ctx.task_id, ctx.batch_id, ref) or {}
        pack = read_writing_pack(ctx.task_id, ctx.batch_id, ref) or {}
        cited_paths = meta.get("citedSourcePaths") or pack.get("sourcePaths") or []
        facts = compute_draft_provenance_facts(
            ctx.task_id,
            ctx.batch_id,
            ref,
            article_markdown=article,
            cited_source_paths=[str(item) for item in cited_paths],
        )
        enriched_meta = dict(meta)
        enriched_meta.update(
            {
                "ref": ref,
                "generator": meta.get("generator") or "agent",
                "model": meta.get("model") or ctx.model,
                "agentRunId": outcome.get("runId") or meta.get("agentRunId"),
                "agentId": outcome.get("agentId") or meta.get("agentId"),
                "citedSourcePaths": [str(item) for item in cited_paths],
                "promptSha256": facts.get("promptSha256"),
                "writingPackSha256": facts.get("writingPackSha256"),
                "sourceBundleSha256": facts.get("sourceBundleSha256"),
                "draftSha256": facts.get("draftSha256"),
                "updatedAt": store.now_iso(),
            }
        )
        write_json(draft_meta_path(ctx.task_id, ctx.batch_id, ref), enriched_meta)


def _run_managed_checkpoint(ctx: PipelineContext, stage: str) -> bool:
    prompts = _checkpoint_prompts(ctx, stage)
    if not prompts:
        return False
    worker_count = _managed_checkpoint_worker_count(ctx, len(prompts))
    checkpoint_started_at = store.now_iso()
    checkpoint_started_mono = time.monotonic()
    estimated_waves = (len(prompts) + max(worker_count, 1) - 1) // max(worker_count, 1)
    state = load_workflow_state(ctx.task_id, ctx.batch_id)
    state["status"] = "waiting_agent"
    state["owner"] = f"managed-local:{stage}"
    state["heartbeatAt"] = store.now_iso()
    state["nextAction"] = f"running {len(prompts)} agent job(s) for {stage}"
    state["failedObjects"] = []
    state["activeAgentScheduler"] = {
        "stage": stage,
        "requestedMaxWorkers": int(ctx.max_workers or 1),
        "effectiveWorkerCount": worker_count,
        "localCursorMaxWorkers": int(MANAGED_LOCAL_CURSOR_MAX_WORKERS),
        "runtime": str(ctx.runtime),
        "promptCount": len(prompts),
        "estimatedMinWaves": estimated_waves,
        "laneLimits": dict(MANAGED_LANE_LIMITS),
        "startedAt": checkpoint_started_at,
    }
    previous_agent_run = state.get("lastAgentRun")
    if isinstance(previous_agent_run, Mapping):
        history = state.setdefault("agentRunHistory", [])
        if isinstance(history, list):
            history.append(dict(previous_agent_run))
            state["agentRunHistory"] = list(_dedupe_agent_runs(history))[-20:]
    state.pop("lastAgentRun", None)
    save_workflow_state(state)
    runner = ctx.agent_runner or (lambda prompt: _default_managed_agent_runner_isolated(ctx, prompt))
    queued = list(range(len(prompts)))
    futures: dict[Any, tuple[int, str, float]] = {}
    active_by_lane: dict[str, int] = defaultdict(int)
    job_timings: dict[int, dict[str, Any]] = {}
    outcomes: list[dict[str, Any]] = []
    pool = ThreadPoolExecutor(max_workers=worker_count)
    interrupted = False
    force_abort_pool = False
    try:
        while queued or futures:
            submitted = True
            while queued and len(futures) < worker_count and submitted:
                submitted = False
                for position, index in enumerate(queued):
                    lane = _managed_prompt_lane(prompts[index])
                    cap = MANAGED_LANE_LIMITS.get(lane, worker_count)
                    if active_by_lane[lane] >= cap:
                        continue
                    future = pool.submit(runner, prompts[index])
                    futures[future] = (index, lane, time.monotonic())
                    job_timings[index] = {
                        "lane": lane,
                        "submittedAt": store.now_iso(),
                    }
                    active_by_lane[lane] += 1
                    queued.pop(position)
                    submitted = True
                    break
                if submitted:
                    continue
                # Borrow a lane's idle quota only after that lane has no queued
                # work and fewer active jobs than its reservation.
                queued_lanes = {_managed_prompt_lane(prompts[index]) for index in queued}
                idle_slots = sum(
                    max(0, cap - active_by_lane.get(lane, 0))
                    for lane, cap in MANAGED_LANE_LIMITS.items()
                    if lane not in queued_lanes
                )
                if idle_slots and queued:
                    index = queued.pop(0)
                    lane = _managed_prompt_lane(prompts[index])
                    future = pool.submit(runner, prompts[index])
                    futures[future] = (index, lane, time.monotonic())
                    job_timings[index] = {
                        "lane": lane,
                        "submittedAt": store.now_iso(),
                        "borrowedIdleLaneQuota": True,
                    }
                    active_by_lane[lane] += 1
                    submitted = True
            if not futures:
                break
            done, _pending = wait(set(futures), timeout=10)
            for future in done:
                index, lane, _started_at = futures.pop(future)
                active_by_lane[lane] = max(0, active_by_lane[lane] - 1)
                timing = dict(job_timings.get(index) or {})
                timing["finishedAt"] = store.now_iso()
                timing["durationSeconds"] = round(max(0.0, time.monotonic() - _started_at), 3)
                try:
                    outcome = future.result()
                except Exception as exc:  # noqa: BLE001
                    outcome = {
                        "started": False,
                        "status": "error",
                        "error": f"{type(exc).__name__}: {exc}",
                        "retryable": False,
                    }
                outcome["jobIndex"] = index
                outcome["timing"] = timing
                if stage == "produce_author":
                    outcome["ref"] = _managed_author_ref(prompts[index])
                if str(outcome.get("status")) == "finished":
                    gate_issues = _managed_checkpoint_job_issues(
                        ctx,
                        stage=stage,
                        prompt=prompts[index],
                    )
                    if gate_issues:
                        outcome["status"] = "error"
                        outcome["error"] = (
                            "agent finished but checkpoint lane gate still fails: "
                            + "; ".join(str(item) for item in gate_issues[:8])
                        )
                        outcome["retryable"] = True
                        outcome["gateIssues"] = [str(item) for item in gate_issues[:20]]
                outcomes.append(outcome)
            now = time.monotonic()
            expired = [
                (future, index, lane, started_at)
                for future, (index, lane, started_at) in list(futures.items())
                if now - started_at > MANAGED_AGENT_TIMEOUT_SECONDS + MANAGED_AGENT_FUTURE_GRACE_SECONDS
            ]
            for future, index, lane, started_at in expired:
                futures.pop(future, None)
                active_by_lane[lane] = max(0, active_by_lane[lane] - 1)
                future.cancel()
                force_abort_pool = True
                timing = dict(job_timings.get(index) or {})
                timing["finishedAt"] = store.now_iso()
                timing["durationSeconds"] = round(max(0.0, now - started_at), 3)
                outcomes.append(
                    {
                        "started": False,
                        "status": "error",
                        "error": (
                            f"managed agent future timed out after "
                            f"{int(now - started_at)}s for {stage}/{lane}"
                        ),
                        "retryable": True,
                        "errorType": "future_timeout",
                        "jobIndex": index,
                        "timing": timing,
                        **({"ref": _managed_author_ref(prompts[index])} if stage == "produce_author" else {}),
                    }
                )
                if str(ctx.runtime) == "local":
                    _terminate_workspace_cursor_bridges(Path.cwd())
            state = load_workflow_state(ctx.task_id, ctx.batch_id)
            state["heartbeatAt"] = store.now_iso()
            state["nextAction"] = (
                f"{stage}: {len(outcomes)}/{len(prompts)} agent job(s) finished; "
                f"active={dict(active_by_lane)}"
            )
            save_workflow_state(state)
    except KeyboardInterrupt:
        interrupted = True
        queued.clear()
        for future in futures:
            future.cancel()
        state = load_workflow_state(ctx.task_id, ctx.batch_id)
        state.pop("activeAgentScheduler", None)
        state["status"] = "manual_required"
        state["failedObjects"] = [f"{stage}: interrupted; cancelled queued managed agent jobs"]
        state["nextAction"] = f"{stage}: interrupted"
        state["heartbeatAt"] = store.now_iso()
        interrupted_at = store.now_iso()
        partial_record = {
            "stage": stage,
            "status": "interrupted",
            "jobCount": len(outcomes),
            "plannedJobCount": len(prompts),
            "scheduler": {
                "requestedMaxWorkers": int(ctx.max_workers or 1),
                "effectiveWorkerCount": worker_count,
                "localCursorMaxWorkers": int(MANAGED_LOCAL_CURSOR_MAX_WORKERS),
                "runtime": str(ctx.runtime),
                "promptCount": len(prompts),
                "estimatedMinWaves": estimated_waves,
                "laneLimits": dict(MANAGED_LANE_LIMITS),
                "startedAt": checkpoint_started_at,
                "interruptedAt": interrupted_at,
                "elapsedSeconds": round(max(0.0, time.monotonic() - checkpoint_started_mono), 3),
            },
            "startedCount": sum(bool(out.get("started")) for out in outcomes),
            "infrastructureFailures": sum(not bool(out.get("started")) for out in outcomes),
            "outcomes": outcomes,
            "finishedAt": interrupted_at,
        }
        history = state.setdefault("agentRunHistory", [])
        if isinstance(history, list):
            history.append(partial_record)
            state["agentRunHistory"] = list(_dedupe_agent_runs(history))[-20:]
        state["lastAgentRun"] = partial_record
        save_workflow_state(state)
        raise
    finally:
        pool.shutdown(wait=not (interrupted or force_abort_pool), cancel_futures=True)
    outcomes.sort(key=lambda item: int(item.get("jobIndex", 0)))
    if stage == "produce_author":
        _finalize_managed_author_outputs(ctx, prompts, outcomes)
    started_count = sum(bool(out.get("started")) for out in outcomes)
    finished_count = sum(str(out.get("status")) == "finished" for out in outcomes)
    infrastructure_failures = sum(not bool(out.get("started")) for out in outcomes)
    finished_at = store.now_iso()
    state = load_workflow_state(ctx.task_id, ctx.batch_id)
    state.pop("activeAgentScheduler", None)
    agent_run_record = {
        "stage": stage,
        "jobCount": len(outcomes),
        "plannedJobCount": len(prompts),
        "scheduler": {
            "requestedMaxWorkers": int(ctx.max_workers or 1),
            "effectiveWorkerCount": worker_count,
            "localCursorMaxWorkers": int(MANAGED_LOCAL_CURSOR_MAX_WORKERS),
            "runtime": str(ctx.runtime),
            "promptCount": len(prompts),
            "estimatedMinWaves": estimated_waves,
            "laneLimits": dict(MANAGED_LANE_LIMITS),
            "startedAt": checkpoint_started_at,
            "finishedAt": finished_at,
            "elapsedSeconds": round(max(0.0, time.monotonic() - checkpoint_started_mono), 3),
        },
        "refs": [
            str(out.get("ref"))
            for out in outcomes
            if str(out.get("ref") or "").strip()
        ],
        "startedCount": started_count,
        "finishedCount": finished_count,
        "infrastructureFailures": infrastructure_failures,
        "outcomes": outcomes,
        "finishedAt": finished_at,
    }
    history = state.setdefault("agentRunHistory", [])
    if isinstance(history, list):
        history.append(agent_run_record)
        state["agentRunHistory"] = list(_dedupe_agent_runs(history))[-20:]
    state["lastAgentRun"] = agent_run_record
    save_workflow_state(state)
    failures = [out for out in outcomes if str(out.get("status")) != "finished"]
    if failures:
        state = load_workflow_state(ctx.task_id, ctx.batch_id)
        state["status"] = "repairing"
        state["failedObjects"] = [str(out.get("error") or "agent failed") for out in failures]
        save_workflow_state(state)
        return False
    ok, issues = _checkpoint_is_done(ctx, stage)
    state = load_workflow_state(ctx.task_id, ctx.batch_id)
    state["owner"] = "managed-local"
    state["heartbeatAt"] = store.now_iso()
    state["failedObjects"] = list(issues)
    state["status"] = "running" if ok else "repairing"
    state["nextAction"] = None if ok else f"repair {stage}: {issues[:5]}"
    save_workflow_state(state)
    return ok


def _managed_checkpoint_worker_count(ctx: PipelineContext, prompt_count: int) -> int:
    worker_count = max(1, min(ctx.max_workers, prompt_count))
    if ctx.agent_runner is None and str(ctx.runtime) == "local":
        worker_count = min(worker_count, MANAGED_LOCAL_CURSOR_MAX_WORKERS)
    return worker_count


def run_managed_pipeline(ctx: PipelineContext) -> int:
    """父进程消费全部 Agent checkpoint，直到 release verify 通过或转人工。"""
    while True:
        code = run_pipeline(ctx)
        if code == 0:
            return 0
        if code != 10:
            return code
        state = load_workflow_state(ctx.task_id, ctx.batch_id)
        stage = str(state.get("waitingCheckpoint") or "")
        retries = state.setdefault("retryCounts", {})
        used = int(retries.get(stage, 0))
        if used >= MAX_REACT_REWINDS:
            _ok, issues = _checkpoint_is_done(ctx, stage)
            state["status"] = "manual_required"
            state["failedObjects"] = list(issues)
            state["nextAction"] = (
                f"{stage} failed validation after {used} managed attempts"
                + (f"; unresolved={len(issues)}" if issues else "")
            )
            save_workflow_state(state)
            return 1
        state["status"] = "repairing" if used else "waiting_agent"
        save_workflow_state(state)
        if _run_managed_checkpoint(ctx, stage):
            state = load_workflow_state(ctx.task_id, ctx.batch_id)
            infra = state.setdefault("infrastructureRetryCounts", {})
            infra.pop(stage, None)
            state["infrastructureRetryCounts"] = infra
            save_workflow_state(state)
            continue

        state = load_workflow_state(ctx.task_id, ctx.batch_id)
        last_run = state.get("lastAgentRun") or {}
        infrastructure_failures = int(last_run.get("infrastructureFailures") or 0)
        if infrastructure_failures:
            infra = state.setdefault("infrastructureRetryCounts", {})
            infra_used = int(infra.get(stage, 0)) + 1
            infra[stage] = infra_used
            state["infrastructureRetryCounts"] = infra
            if infra_used >= MAX_MANAGED_INFRA_RETRIES:
                ok_after_failures, issues_after_failures = _checkpoint_is_done(ctx, stage)
                if ok_after_failures:
                    state["status"] = "running"
                    state["failedObjects"] = []
                    state["nextAction"] = (
                        f"continue {stage}: checkpoint gate passed despite "
                        f"{infrastructure_failures} infrastructure failure(s)"
                    )
                    state["heartbeatAt"] = store.now_iso()
                    save_workflow_state(state)
                    continue
                if stage == "download_plan":
                    unresolved = _download_plan_unresolved_entities(ctx)
                    _write_download_plan_availability(ctx, unresolved, source="managed_infra_retry")
                    deterministic = _deterministic_download_plan_unresolved(unresolved)
                    reason_prefix = f"source_unavailable_after_agent_infra_retries_{infra_used}"
                    strict_unresolved = deterministic if deterministic else unresolved
                    if strict_unresolved and not _workflow_allows_partial_content(ctx):
                        state["status"] = "manual_required"
                        state["failedObjects"] = [
                            item + "; workflowPolicy.allowPartialContent is not true"
                            for item in _format_download_unresolved(
                                strict_unresolved,
                                prefix=reason_prefix,
                            )
                        ]
                        state["nextAction"] = (
                            f"{stage} infrastructure failed after {infra_used} attempts; "
                            "strict task cannot abandon source-unavailable entities"
                        )
                        state["heartbeatAt"] = store.now_iso()
                        save_workflow_state(state)
                        return 1
                    abandoned = _abandon_unresolved_download_plan_entities(
                        ctx,
                        deterministic if deterministic else unresolved,
                        reason_prefix=reason_prefix,
                    )
                    if abandoned:
                        _apply_abandoned_entities(ctx, load_workflow_state(ctx.task_id, ctx.batch_id))
                        state = load_workflow_state(ctx.task_id, ctx.batch_id)
                        state["status"] = "running"
                        state["failedObjects"] = []
                        state["nextAction"] = (
                            "continue after fast-failing source-unavailable "
                            f"entities: {', '.join(abandoned[:8])}"
                        )
                        state["heartbeatAt"] = store.now_iso()
                        save_workflow_state(state)
                        continue
                failed_refs = _managed_author_failure_refs(
                    list((last_run.get("outcomes") or []) if isinstance(last_run, Mapping) else [])
                ) if stage == "produce_author" else []
                state["status"] = "manual_required"
                state["failedObjects"] = [
                    f"{stage}:{ref}: infrastructure did not start"
                    for ref in failed_refs
                ] or list(state.get("failedObjects") or [])
                state["nextAction"] = (
                    f"{stage} infrastructure failed after {infra_used} attempts; "
                    f"{infrastructure_failures} agent job(s) did not start"
                )
                if issues_after_failures:
                    state["failedObjects"] = list(issues_after_failures)
                save_workflow_state(state)
                return 1
            state["nextAction"] = (
                f"retry {stage} infrastructure: attempt "
                f"{infra_used + 1}/{MAX_MANAGED_INFRA_RETRIES}"
            )
            save_workflow_state(state)
            time.sleep(min(30, 5 * infra_used))
            continue

        retries = state.setdefault("retryCounts", {})
        retries[stage] = used + 1
        state["retryCounts"] = retries
        save_workflow_state(state)
        time.sleep(min(2 ** used, 5))

def _handle_run_fanout(args: argparse.Namespace) -> None:
    """--mode fanout：走冻结计划建 task/batch + enqueue 叶子 + 展开 assignment（幂等）。

    单模式（--mode single）= 现状 DAG；fanout 把每分区/叶子下沉到 object_queue，
    由 cursor-sdk 外部 runner 解 CHECKPOINT 接缝。--concurrency 1 即退化等价单模式。
    """
    from _common import fanout_plan as fp
    from task import fanout_dispatch as fd

    if not getattr(args, "plan", None):
        print("[task run] ERROR: --mode fanout 需要 --plan <planId>", file=sys.stderr)
        raise SystemExit(2)
    plan = fp.load_plan(args.plan)
    if plan is None:
        print(f"[task run] ERROR: 计划不存在: {args.plan}（先跑 qwq-data task decompose）", file=sys.stderr)
        raise SystemExit(2)
    if str(plan.get("status")) != "frozen":
        print(
            f"[task run] ERROR: 计划未冻结 (status={plan.get('status')})；"
            f"先 qwq-data task decompose --plan {args.plan} --freeze --confirm",
            file=sys.stderr,
        )
        raise SystemExit(2)
    try:
        report = fd.dispatch(
            plan,
            strategy=getattr(args, "strategy", None),
            concurrency=getattr(args, "concurrency", None),
            batch_size=getattr(args, "batch_size", None),
        )
    except (ValueError, RuntimeError) as exc:
        print(f"[task run] ERROR: dispatch failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
    totals = report["totals"]
    print(
        f"[task run --mode fanout] plan={report['planId']} strategy={report['strategy']} "
        f"concurrency={report['concurrency']}"
    )
    for part in report["perPartition"]:
        print(
            f"  - {'/'.join(part['partitionPath'])} -> task={part['taskId']} "
            f"batch={part['batchId']} enqueued={part['enqueued']} created={part['taskCreated']}"
        )
    print(
        f"[task run --mode fanout] partitions={totals['partitions']} tasksCreated={totals['tasksCreated']} "
        f"leavesEnqueued={totals['leavesEnqueued']} assignments={totals['assignments']}"
    )
    print(
        "[task run --mode fanout] 叶子已入队。外部并行执行（by-partition 默认先跑分区 orchestrator "
        "推进 download_plan/build_homepage/content_plan 三个 checkpoint，再分发叶子 author）："
        f"\n  本机多 agent: python3 quwoquan_data/scripts/cli.py task scaled-e2e author-runner --plan {report['planId']} --strategy {report['strategy']} --runtime local --max-workers {report['concurrency']} --orchestrate"
        f"\n  云端 VM:     python3 quwoquan_data/scripts/cli.py task scaled-e2e author-runner --plan {report['planId']} --strategy {report['strategy']} --runtime cloud --max-workers {report['concurrency']} --orchestrate"
        "\n  首次运行先执行: python3 quwoquan_data/scripts/cli.py env ready"
        "\n  （两者都需 export CURSOR_API_KEY；或会话内逐分区 qwq-data data workflow run --task <taskId> --batch <batchId> --managed 解 checkpoint）"
        " + qwq-data object-queue lease-next --task <taskId> --batch <batchId> --worker <id>（叶子）"
    )


def handle_run(args: argparse.Namespace) -> None:
    if getattr(args, "mode", "single") == "fanout":
        _handle_run_fanout(args)
        return

    task_id = args.task
    if not task_id:
        print("[task run] ERROR: --mode single 需要 --task <taskId>", file=sys.stderr)
        raise SystemExit(2)
    batch_id = args.batch
    spec = store.load_spec(task_id)
    entity_ids = _coverage_entity_ids(spec)
    if not entity_ids:
        print(f"[task run] ERROR: {task_id} 无 coverageTargets，无实体可编排", file=sys.stderr)
        raise SystemExit(2)

    managed = bool(getattr(args, "managed", False))
    if managed:
        preflight_issues = _managed_preflight(task_id, batch_id, spec, args)
        if preflight_issues:
            print("[task run] managed preflight FAILED:", file=sys.stderr)
            for issue in preflight_issues:
                print(f"  - {issue}", file=sys.stderr)
            raise SystemExit(2)

    if args.reset_state:
        p = _state_path(task_id, batch_id)
        if p.exists():
            p.unlink()
            print(f"[task run] reset workflow state: {p}")
        _purge_author_queue_for_stale_workflow(
            PipelineContext(
                task_id=task_id,
                batch_id=batch_id,
                entity_ids=[],
                spec={},
            ),
            reason="reset_state",
        )
    elif bool(getattr(args, "resume", False)):
        _clear_manual_repair_rewind_if_resuming(task_id, batch_id)

    until = args.until if getattr(args, "until", None) else None
    if until and until not in STAGE_NAMES:
        print(f"[task run] ERROR: --until 须为 {STAGE_NAMES}", file=sys.stderr)
        raise SystemExit(2)

    try:
        baseline_packet_path, baseline_packet = _load_baseline_packet(
            task_id,
            Path(args.baseline_packet) if getattr(args, "baseline_packet", None) else None,
        )
    except RuntimeError as exc:
        print(f"[task run] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)

    ctx = PipelineContext(
        task_id=task_id, batch_id=batch_id, entity_ids=entity_ids,
        spec=spec, baseline_packet=baseline_packet, baseline_packet_path=baseline_packet_path,
        until=until,
        managed=managed,
        runtime=str(getattr(args, "runtime", "local") or "local"),
        max_workers=int(getattr(args, "max_workers", 3) or 3),
        model=str(getattr(args, "model", "composer-2.5") or "composer-2.5"),
        release_only=bool(getattr(args, "release_only", False)),
        agent_runner=getattr(args, "agent_runner", None),
    )
    if managed:
        _write_managed_env_ready_report(ctx, args)
    code = run_managed_pipeline(ctx) if managed else run_pipeline(ctx)
    if code != 0:
        raise SystemExit(code)


def register_run_parser(sub: argparse._SubParsersAction) -> None:
    pr = sub.add_parser("run", help="无人值守 workflow 编排：单模式 DAG / fanout 分区叶子调度")
    pr.add_argument(
        "--mode",
        choices=["single", "fanout"],
        default="single",
        help="single=会话内单 agent 跑 DAG（默认，现状）；fanout=按冻结计划分区/叶子调度",
    )
    pr.add_argument("--task", help="Task ID（single 模式必填）")
    pr.add_argument("--batch", default="run_1", help="Batch ID")
    pr.add_argument("--plan", help="fanout 模式：冻结计划 planId")
    pr.add_argument(
        "--strategy",
        choices=["by-partition", "flat-pool", "by-leaf", "by-batch"],
        help="fanout 模式：拉起策略（默认取计划 defaults.strategy）",
    )
    pr.add_argument("--concurrency", type=int, help="fanout 模式：并发度（设 1 即退化等价 single）")
    pr.add_argument("--batch-size", dest="batch_size", type=int, help="fanout by-batch 策略：每块叶子数")
    pr.add_argument("--resume", action="store_true",
                    help="从上次 checkpoint 继续（默认即 resume 语义：跳过已完成 stage）")
    pr.add_argument("--reset-state", dest="reset_state", action="store_true",
                    help="清空 workflow_state 从头跑")
    pr.add_argument(
        "--baseline-packet",
        help="baseline freeze packet path（默认 task/_shared/baseline_freeze_packet.json）",
    )
    pr.add_argument("--until", help=f"跑到指定 stage 即停: {STAGE_NAMES}")
    pr.add_argument("--managed", action="store_true", help="自动消费全部 Agent checkpoint 并续跑")
    pr.add_argument("--runtime", choices=["local", "cloud"], default="local")
    pr.add_argument("--max-workers", dest="max_workers", type=int, default=10)
    pr.add_argument("--model", default="composer-2.5")
    pr.add_argument(
        "--release-only",
        dest="release_only",
        action="store_true",
        help="仅组装隔离 release，不写 publish/ 或运行库（当前 managed 正式模式要求）",
    )
    pr.set_defaults(handler=handle_run)
