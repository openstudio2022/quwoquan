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
from core.io import read_json, write_json
from core.runtime_policy import active_runtime_policy
from content.execution import production_contracts as pc
from content.execution import store

STATE_QUEUED = "queued"
STATE_LEASED = "leased"
STATE_SUCCEEDED = "succeeded"
STATE_FAILED = "failed"
STATE_BLOCKED = "blocked"
STATE_DEAD = "dead"

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
# token/cost 预算（0 = 不限，>0 = SDK runner 侧硬上限，超出强制 dead）。
DEFAULT_TOKEN_BUDGET = 0
DEFAULT_COST_BUDGET_USD = 0.0

OBJECT_JOB_SCHEMA = pc.OBJECT_JOB_SCHEMA
QUEUE_BACKEND_LOCAL = "local_file"
QUEUE_BACKEND_RELIABLETASK = "reliabletask"
SUPPORTED_QUEUE_BACKENDS = (QUEUE_BACKEND_LOCAL, QUEUE_BACKEND_RELIABLETASK)
RELIABLETASK_QUEUE = "reliabletask.data.content_supply"
RELIABLETASK_TASK_TYPE = "data.content_object.execute"


def _backend_name(backend: str | None = None) -> str:
    value = str(backend or "").strip() or str(os.environ.get("QWQ_OBJECT_QUEUE_BACKEND") or QUEUE_BACKEND_LOCAL)
    if value not in SUPPORTED_QUEUE_BACKENDS:
        raise ValueError(f"unsupported object queue backend: {value}")
    return value


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
    entity_ref = str(entity_ref or "").strip()
    carrier = str(carrier or "").strip()
    source_revision = str(source_revision or "").strip()
    if not entity_ref or not carrier or not source_revision:
        raise ValueError(
            "reliabletask idempotency requires entityRef + carrier + sourceRevision"
        )
    idempotency_key = f"{entity_ref}|{carrier}|{source_revision}"
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

def _job_governance_issues(job: Mapping[str, Any]) -> list[str]:
    if not bool(job.get("requireGovernance")):
        return []
    issues: list[str] = []
    if not str(job.get("controllerRunId") or "").strip():
        issues.append("controllerRunId required")
    if not str(job.get("assignmentId") or "").strip():
        issues.append("assignmentId required")
    if not isinstance(job.get("assignmentPath"), list) or not job.get("assignmentPath"):
        issues.append("assignmentPath required")
    if not str(job.get("owner") or "").strip():
        issues.append("owner required")
    if bool(job.get("sourceUnitIdRequired")) and not str(job.get("sourceUnitId") or "").strip():
        issues.append("sourceUnitId required")
    return issues


def _envelope_governance_issues(job: Mapping[str, Any], envelope: Mapping[str, Any]) -> list[str]:
    issues = _job_governance_issues(job)
    if not bool(job.get("requireGovernance")):
        return issues
    agent = envelope.get("agent") if isinstance(envelope.get("agent"), Mapping) else {}
    envelope_controller = str(envelope.get("controllerRunId") or agent.get("controllerRunId") or "")
    if envelope_controller and envelope_controller != str(job.get("controllerRunId") or ""):
        issues.append("envelope.controllerRunId does not match job.controllerRunId")
    allowed_write_roots = [str(item).strip().rstrip("/") for item in (job.get("allowedWriteRoots") or []) if str(item).strip()]
    if allowed_write_roots:
        for item in envelope.get("files") or []:
            if not isinstance(item, Mapping):
                continue
            raw_path = str(item.get("path") or "").strip()
            if raw_path and not any(raw_path == root or raw_path.startswith(root + "/") for root in allowed_write_roots):
                issues.append(f"envelope file outside assignment write roots: {raw_path}")
    return issues


def _load_jobs(execution_id: str) -> list[dict[str, Any]]:
    base = queue_dir(execution_id)
    if not base.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(base.glob("*.json")):
        try:
            out.append(read_json(path))
        except (OSError, ValueError):
            continue
    return out


def _active_mutex_keys(jobs: list[dict[str, Any]], now: float) -> set[str]:
    active: set[str] = set()
    for job in jobs:
        if job.get("state") == STATE_LEASED and float(job.get("leaseExpiresEpoch") or 0) > now:
            active.add(str(job.get("mutexKey") or job.get("ref")))
    return active

__all__ = [name for name in globals() if not name.startswith("__")]
