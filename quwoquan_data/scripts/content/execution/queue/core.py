"""Object queue constants, storage paths, locks, and governance helpers."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import random
import time
from pathlib import Path
from typing import Any, Mapping

from core import ops_governance as og
from core.control_types import QueueBackend, QueueJobState
from core.io import read_json, write_json
from core.runtime_policy import active_runtime_policy
from content.execution import production_contracts as pc
from content.execution import store
from content.execution.queue.model import QueueJob

STATE_QUEUED = QueueJobState.QUEUED
STATE_LEASED = QueueJobState.LEASED
STATE_SUCCEEDED = QueueJobState.SUCCEEDED
STATE_FAILED = QueueJobState.FAILED
STATE_BLOCKED = QueueJobState.BLOCKED
STATE_DEAD = QueueJobState.DEAD

_RUNTIME_POLICY = active_runtime_policy()
DEFAULT_LEASE_TTL_SECONDS = _RUNTIME_POLICY.queue_lease_ttl_seconds
DEFAULT_MAX_ATTEMPTS = _RUNTIME_POLICY.queue_max_attempts
DEFAULT_MAX_STARTUP_FAILURES = _RUNTIME_POLICY.queue_max_startup_failures
# 逐 job 墙钟硬上限（Ralph 自纠环默认 20min）：lease 时计算 deadlineEpoch，reaper 超时强制 fail。
DEFAULT_MAX_WALL_CLOCK_SECONDS = _RUNTIME_POLICY.queue_max_wall_clock_seconds
# 失败重取的指数退避 + jitter（防惊群），仅作用于 failed→可重取的间隔。
BACKOFF_BASE_SECONDS = _RUNTIME_POLICY.queue_backoff_base_seconds
BACKOFF_CAP_SECONDS = _RUNTIME_POLICY.queue_backoff_cap_seconds
# Ralph 断路器：同一失败指纹连续 N 轮不变 → 判定卡死，直接 dead + notify（不再空耗 attempts）。
DEFAULT_STUCK_THRESHOLD = _RUNTIME_POLICY.queue_stuck_threshold
# 执行合约（harness 执行合约 5 要素之一）：Subagent 默认最小工具集 allow-list。
DEFAULT_TOOL_PERMISSIONS: tuple[str, ...] = (
    "read_ref_packet",      # 读本 ref 的 packet/template/source
    "search_web",           # 联网检索证据/配图（CC/PD）
    "write_draft",          # 写 4.draft 草稿与 self-check
    "run_review_gate",      # 跑单 ref review 门
)
# Token budget is part of the single runtime policy. Queue creation must never
# silently turn a configured limit into an unbounded execution.
DEFAULT_TOKEN_BUDGET = _RUNTIME_POLICY.default_object_token_budget
# Cost accounting is recorded when supplied by the provider. Its ceiling is
# owned by the same runtime policy as token budgets.
DEFAULT_COST_BUDGET_USD = _RUNTIME_POLICY.default_object_cost_budget_usd

OBJECT_JOB_SCHEMA = pc.OBJECT_JOB_SCHEMA
QUEUE_BACKEND_LOCAL = QueueBackend.LOCAL_FILE
QUEUE_BACKEND_RELIABLETASK = QueueBackend.RELIABLE_TASK
SUPPORTED_QUEUE_BACKENDS = tuple(QueueBackend)
RELIABLETASK_QUEUE = "reliabletask.data.content_supply"
RELIABLETASK_TASK_TYPE = "data.content_object.execute"


def _backend_name(backend: str | QueueBackend | None = None) -> QueueBackend:
    value = str(backend or "").strip() or str(
        os.environ.get("QWQ_OBJECT_QUEUE_BACKEND") or QUEUE_BACKEND_LOCAL
    )
    try:
        return QueueBackend(value)
    except ValueError as exc:
        raise ValueError(f"unsupported object queue backend: {value}") from exc


def _reliabletask_ref(
    *,
    execution_id: str,
    job_id: str,
    ref: str,
    stage: str,
    partition_key: str,
    entity_ref: str,
    carrier: str,
    source_revision: str,
) -> dict[str, Any]:
    """Declarative bridge payload for quwoquan_service/runtime/reliabletask.

    The data repo keeps local files as the small-batch truth source, but a
    production job now carries the reliabletask routing contract so a service
    adapter can dispatch it through MongoStore + RedisReadyIndex without
    changing job IDs or queue semantics.
    """
    execution_id = str(execution_id or "").strip()
    entity_ref = str(entity_ref or "").strip()
    carrier = str(carrier or "").strip()
    source_revision = str(source_revision or "").strip()
    stage = str(stage or "").strip()
    if not execution_id or not entity_ref or not carrier or not source_revision or not stage:
        raise ValueError(
            "reliabletask idempotency requires "
            "executionId + entityRef + carrier + sourceRevision + stage"
        )
    # 必须与 runtime/reliabletask.DataContentJob.IdempotencyKey 完全同构。
    # 新 execution 即便复用同一来源，也不能与旧执行共享死信或作者证据。
    idempotency_key = (
        f"{execution_id}|{entity_ref}|{carrier}|{source_revision}|{stage}"
    )
    return {
        "taskType": RELIABLETASK_TASK_TYPE,
        "queue": RELIABLETASK_QUEUE,
        "dedupeKey": idempotency_key,
        "idempotencyKey": idempotency_key,
        "partitionKey": partition_key,
        "payloadAllowlist": "object_job",
        "payload": {
            "schema": OBJECT_JOB_SCHEMA,
            "jobId": job_id,
            "executionId": execution_id,
            "ref": ref,
            "stage": stage,
            "partitionKey": partition_key,
            "entityRef": entity_ref,
            "carrier": carrier,
            "sourceRevision": source_revision,
            "idempotencyKey": idempotency_key,
        },
    }


def _backoff_seconds(attempt: int) -> float:
    base = min(BACKOFF_BASE_SECONDS * (2 ** max(0, int(attempt) - 1)), BACKOFF_CAP_SECONDS)
    return base + random.uniform(0.0, base * 0.25)


def _notifications_path(execution_id: str) -> Path:
    return queue_dir(execution_id) / "_notifications.jsonl"


def _emit_notification(execution_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """断路器/超时/预算等需要人工关注的事件落 notifications.jsonl（编排循环可订阅）。"""
    record = {"at": store.now_iso(), **dict(payload)}
    path = _notifications_path(execution_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def list_notifications(execution_id: str) -> list[dict[str, Any]]:
    path = _notifications_path(execution_id)
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def queue_dir(execution_id: str) -> Path:
    return store.execution_root(execution_id) / "_shared" / "object_queue"


@contextmanager
def _queue_lock(execution_id: str):
    """Serialize local-file queue read/modify/write operations per execution."""
    base = queue_dir(execution_id)
    base.mkdir(parents=True, exist_ok=True)
    path = base / ".queue.lock"
    with path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def stable_job_id(execution_id: str, ref: str, stage: str) -> str:
    raw = f"{execution_id}|{ref}|{stage}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def _job_path(execution_id: str, job_id: str) -> Path:
    return queue_dir(execution_id) / f"{job_id}.json"


def _now() -> float:
    return time.time()

def _job_governance_issues(job: QueueJob) -> tuple[str, ...]:
    return job.governance_issues()


def _envelope_governance_issues(job: QueueJob, envelope: Mapping[str, Any]) -> list[str]:
    issues = list(_job_governance_issues(job))
    if not job.require_governance:
        return issues
    agent = envelope.get("agent") if isinstance(envelope.get("agent"), Mapping) else {}
    envelope_controller = str(envelope.get("controllerRunId") or agent.get("controllerRunId") or "")
    if envelope_controller and envelope_controller != job.controller_run_id:
        issues.append("envelope.controllerRunId does not match job.controllerRunId")
    allowed_write_roots = [item.rstrip("/") for item in job.allowed_write_roots if item]
    if allowed_write_roots:
        for item in envelope.get("files") or []:
            if not isinstance(item, Mapping):
                continue
            raw_path = str(item.get("path") or "").strip()
            if raw_path and not any(raw_path == root or raw_path.startswith(root + "/") for root in allowed_write_roots):
                issues.append(f"envelope file outside assignment write roots: {raw_path}")
    return issues


def _load_jobs(execution_id: str) -> list[QueueJob]:
    base = queue_dir(execution_id)
    if not base.is_dir():
        return []
    out: list[QueueJob] = []
    for path in sorted(base.glob("*.json")):
        try:
            out.append(QueueJob.from_document(read_json(path)))
        except (OSError, ValueError, TypeError) as exc:
            raise RuntimeError(f"object queue document is invalid: {path}: {exc}") from exc
    return out


def _write_job(job: QueueJob) -> None:
    write_json(_job_path(job.execution_id, job.job_id), job.to_document())


def _read_job(execution_id: str, job_id: str) -> QueueJob:
    return QueueJob.from_document(read_json(_job_path(execution_id, job_id)))


def _active_mutex_keys(jobs: list[QueueJob], now: float) -> set[str]:
    active: set[str] = set()
    for job in jobs:
        if job.state is STATE_LEASED and not job.lease.is_expired(now):
            active.add(job.mutex_key)
    return active

__all__ = [name for name in globals() if not name.startswith("__")]
