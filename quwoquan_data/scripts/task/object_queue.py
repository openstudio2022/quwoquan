"""Object-stage job 队列：单篇隔离的 Subagent 并行调度基础设施。

与 task/queue.py（task-batch 级 job）不同，本模块把队列粒度下沉到
"一个内容对象的一个 stage"（如 ref=阿坝神山三沟五日联线, stage=author），
让多个 Subagent 并行创作不同 ref，但彼此隔离、互不读对方正文。

工程保证（整改计划第六阶段 开发专家视角）：
- 稳定 jobId = sha1(taskId|batchId|ref|stage)：同 ref+stage 幂等，重复 enqueue 不产生重复 job。
- lease 租约：worker 取 job 时写入 lease token + 到期时间；只有持锁 worker 能 complete/fail。
- 崩溃恢复：lease 过期（now > leaseExpiresEpoch）的 leased job 可被重新 acquire。
- 同源互斥：同一 mutexKey（默认 baseSourceRef 或实体）同时只允许一个 job 在跑，
  避免同底稿文章并行派生导致雷同。
- stage timing：记录 leasedAt/finishedAt/durationMs，落入 job 文件供 run_journal 观测。

存储：batches/{batch}/_shared/object_queue/{jobId}.json，单文件即状态机，无外部依赖。
状态：queued | leased | succeeded | failed | blocked | dead。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

from _common.io import read_json, write_json
from _common.paths import batch_root
from task import store
from task import production_contracts as pc

STATE_QUEUED = "queued"
STATE_LEASED = "leased"
STATE_SUCCEEDED = "succeeded"
STATE_FAILED = "failed"
STATE_BLOCKED = "blocked"
STATE_DEAD = "dead"
STATE_SPILLED = "spilled"  # dead job 已 spillover 到独立修复批，留痕不再调度

DEFAULT_LEASE_TTL_SECONDS = 1800
DEFAULT_MAX_ATTEMPTS = 2  # 第 3 次 ReAct 失败 → dead → 人工编辑队列
DEFAULT_MAX_STARTUP_FAILURES = 3  # bridge / sdk 启动异常单独预算，不消耗正文质量重试
# 逐 job 墙钟硬上限（Ralph 自纠环默认 20min）：lease 时计算 deadlineEpoch，reaper 超时强制 fail。
DEFAULT_MAX_WALL_CLOCK_SECONDS = 1200
# 失败重取的指数退避 + jitter（防惊群），仅作用于 failed→可重取的间隔。
BACKOFF_BASE_SECONDS = 30
BACKOFF_CAP_SECONDS = 600
# Ralph 断路器：同一失败指纹连续 N 轮不变 → 判定卡死，直接 dead + notify（不再空耗 attempts）。
DEFAULT_STUCK_THRESHOLD = 3
# 执行合约（harness 执行合约 5 要素之一）：Subagent 默认最小工具集 allow-list。
DEFAULT_TOOL_PERMISSIONS: tuple[str, ...] = (
    "read_ref_packet",      # 读本 ref 的 packet/SOP/source
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
    task_id: str,
    batch_id: str,
    job_id: str,
    ref: str,
    stage: str,
    partition_key: str,
) -> dict[str, Any]:
    """Declarative bridge payload for quwoquan_service/runtime/reliabletask.

    The data repo keeps local files as the small-batch truth source, but a
    production job now carries the reliabletask routing contract so a service
    adapter can dispatch it through MongoStore + RedisReadyIndex without
    changing job IDs or queue semantics.
    """
    return {
        "taskType": RELIABLETASK_TASK_TYPE,
        "queue": RELIABLETASK_QUEUE,
        "dedupeKey": f"{task_id}|{batch_id}|{job_id}",
        "partitionKey": partition_key,
        "payloadAllowlist": "object_job",
        "payload": {
            "schemaVersion": OBJECT_JOB_SCHEMA,
            "jobId": job_id,
            "taskId": task_id,
            "batchId": batch_id,
            "ref": ref,
            "stage": stage,
            "partitionKey": partition_key,
        },
    }


def _backoff_seconds(attempt: int) -> float:
    base = min(BACKOFF_BASE_SECONDS * (2 ** max(0, int(attempt) - 1)), BACKOFF_CAP_SECONDS)
    return base + random.uniform(0.0, base * 0.25)


def _notifications_path(task_id: str, batch_id: str) -> Path:
    return queue_dir(task_id, batch_id) / "_notifications.jsonl"


def _emit_notification(task_id: str, batch_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """断路器/超时/预算等需要人工关注的事件落 notifications.jsonl（编排循环可订阅）。"""
    record = {"at": store.now_iso(), **dict(payload)}
    path = _notifications_path(task_id, batch_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def list_notifications(task_id: str, batch_id: str) -> list[dict[str, Any]]:
    path = _notifications_path(task_id, batch_id)
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


def queue_dir(task_id: str, batch_id: str) -> Path:
    return batch_root(task_id, batch_id) / "_shared" / "object_queue"


def stable_job_id(task_id: str, batch_id: str, ref: str, stage: str) -> str:
    raw = f"{task_id}|{batch_id}|{ref}|{stage}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def _job_path(task_id: str, batch_id: str, job_id: str) -> Path:
    return queue_dir(task_id, batch_id) / f"{job_id}.json"


def _now() -> float:
    return time.time()


def enqueue_ref_job(
    task_id: str,
    batch_id: str,
    ref: str,
    stage: str,
    *,
    mutex_key: str | None = None,
    fallback_stage: str | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    max_startup_failures: int = DEFAULT_MAX_STARTUP_FAILURES,
    max_wall_clock_seconds: int = DEFAULT_MAX_WALL_CLOCK_SECONDS,
    stuck_threshold: int = DEFAULT_STUCK_THRESHOLD,
    permissions: Iterable[str] | None = None,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    cost_budget_usd: float = DEFAULT_COST_BUDGET_USD,
    meta: Mapping[str, Any] | None = None,
    queue_backend: str | None = None,
) -> dict[str, Any]:
    """入队一个 ref+stage job（幂等）。已存在的非终态 job 直接返回，不重置 attempt。"""
    job_id = stable_job_id(task_id, batch_id, ref, stage)
    path = _job_path(task_id, batch_id, job_id)
    if path.is_file():
        existing = read_json(path)
        if existing.get("state") not in (STATE_SUCCEEDED,):
            return existing
    backend = _backend_name(queue_backend or (meta or {}).get("queueBackend"))
    partition_key = str((meta or {}).get("partitionKey") or mutex_key or ref)
    reliable_ref = (
        _reliabletask_ref(
            task_id=task_id,
            batch_id=batch_id,
            job_id=job_id,
            ref=ref,
            stage=stage,
            partition_key=partition_key,
        )
        if backend == QUEUE_BACKEND_RELIABLETASK
        else None
    )
    payload = {
        "schemaVersion": OBJECT_JOB_SCHEMA,
        "jobId": job_id,
        "taskId": task_id,
        "batchId": batch_id,
        "ref": ref,
        "stage": stage,
        "queueBackend": backend,
        "partitionKey": partition_key,
        "reliableTaskRef": reliable_ref,
        "resultEnvelopeRequired": backend == QUEUE_BACKEND_RELIABLETASK or bool((meta or {}).get("resultEnvelopeRequired")),
        "resultEnvelopeRef": None,
        "gateVerdicts": [],
        "tokenLedger": [],
        "creatorProfileId": (meta or {}).get("creatorProfileId"),
        "creatorArchetype": (meta or {}).get("creatorArchetype"),
        "contentType": (meta or {}).get("contentType"),
        "state": STATE_QUEUED,
        "attempt": 0,
        "maxAttempts": int(max_attempts),
        "maxStartupFailures": int(max_startup_failures),
        "maxWallClockSeconds": int(max_wall_clock_seconds),
        "stuckThreshold": int(stuck_threshold),
        "permissions": list(permissions) if permissions is not None else list(DEFAULT_TOOL_PERMISSIONS),
        "tokenBudget": int(token_budget),
        "costBudgetUsd": float(cost_budget_usd),
        "usage": {"tokens": 0, "costUsd": 0.0},
        "failureFingerprints": [],
        "mutexKey": mutex_key or ref,
        "fallbackStage": fallback_stage,
        "lease": None,
        "leaseExpiresEpoch": 0,
        "deadlineEpoch": 0,  # lease 时按 maxWallClockSeconds 计算
        "notBeforeEpoch": 0,  # 失败退避：到期前不可重取
        "sameRunRetryable": True,  # 当前 fanout runner 是否应继续等待该 failed job 的下一次 lease
        "startupFailureCount": 0,
        "timings": [],
        "lastError": None,
        "meta": dict(meta or {}),
        "createdAt": store.now_iso(),
        "updatedAt": store.now_iso(),
    }
    write_json(path, payload)
    return payload


def enqueue_ref_jobs(
    task_id: str,
    batch_id: str,
    items: Iterable[Mapping[str, Any]],
    stage: str,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    max_startup_failures: int = DEFAULT_MAX_STARTUP_FAILURES,
    max_wall_clock_seconds: int = DEFAULT_MAX_WALL_CLOCK_SECONDS,
    queue_backend: str | None = None,
) -> list[dict[str, Any]]:
    """批量入队。items 每条至少含 ref，可选 baseSourceRef/fallbackStage/meta。"""
    jobs: list[dict[str, Any]] = []
    for item in items:
        ref = str(item.get("ref") or "").strip()
        if not ref:
            continue
        jobs.append(
            enqueue_ref_job(
                task_id,
                batch_id,
                ref,
                stage,
                mutex_key=str(item.get("baseSourceRef") or "") or ref,
                fallback_stage=item.get("fallbackStage"),
                max_attempts=max_attempts,
                max_startup_failures=max_startup_failures,
                max_wall_clock_seconds=max_wall_clock_seconds,
                queue_backend=queue_backend or (item.get("meta") or {}).get("queueBackend"),
                meta=item.get("meta"),
            )
        )
    return jobs


def _load_jobs(task_id: str, batch_id: str) -> list[dict[str, Any]]:
    base = queue_dir(task_id, batch_id)
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


def acquire_lease(
    task_id: str,
    batch_id: str,
    *,
    worker: str,
    stage: str | None = None,
    ref: str | None = None,
    ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
) -> dict[str, Any] | None:
    """取一个可执行 job 并加租约。尊重同源互斥与崩溃恢复（过期 lease 可重取）。

    ref 非空时只租该 ref（by-leaf / per-ref worker 精确寻址）。
    返回被租约的 job dict，或 None（无可执行 job）。
    """
    now = _now()
    jobs = _load_jobs(task_id, batch_id)
    active = _active_mutex_keys(jobs, now)
    for job in jobs:
        if stage and job.get("stage") != stage:
            continue
        if ref and job.get("ref") != ref:
            continue
        state = job.get("state")
        expired_lease = state == STATE_LEASED and float(job.get("leaseExpiresEpoch") or 0) <= now
        if state not in (STATE_QUEUED, STATE_FAILED) and not expired_lease:
            continue
        if float(job.get("notBeforeEpoch") or 0) > now:
            continue  # 失败退避中，未到可重取时刻
        mutex = str(job.get("mutexKey") or job.get("ref"))
        if mutex in active:
            continue  # 同源已有 job 在跑，互斥跳过
        wall_clock = int(job.get("maxWallClockSeconds") or DEFAULT_MAX_WALL_CLOCK_SECONDS)
        job["state"] = STATE_LEASED
        job["lease"] = f"{worker}:{int(now)}"
        job["leaseExpiresEpoch"] = now + ttl_seconds
        job["deadlineEpoch"] = now + wall_clock
        job["attempt"] = int(job.get("attempt") or 0) + 1
        job.setdefault("timings", []).append({"event": "leased", "at": store.now_iso(), "worker": worker})
        job["updatedAt"] = store.now_iso()
        write_json(_job_path(task_id, batch_id, job["jobId"]), job)
        return job
    return None


def _load_owned(task_id: str, batch_id: str, job_id: str, lease: str) -> dict[str, Any]:
    path = _job_path(task_id, batch_id, job_id)
    job = read_json(path)
    if job.get("lease") != lease:
        raise RuntimeError(f"lease mismatch for {job_id}: holder={job.get('lease')!r} caller={lease!r}")
    return job


def renew_lease(task_id: str, batch_id: str, job_id: str, lease: str, *, ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS) -> dict[str, Any]:
    job = _load_owned(task_id, batch_id, job_id, lease)
    job["leaseExpiresEpoch"] = _now() + ttl_seconds
    job["updatedAt"] = store.now_iso()
    write_json(_job_path(task_id, batch_id, job_id), job)
    return job


def complete_job(task_id: str, batch_id: str, job_id: str, lease: str) -> dict[str, Any]:
    job = _load_owned(task_id, batch_id, job_id, lease)
    if bool(job.get("resultEnvelopeRequired")) and not job.get("resultEnvelopeRef"):
        raise RuntimeError(f"result envelope required before completing job {job_id}")
    job["state"] = STATE_SUCCEEDED
    job["lease"] = None
    job["leaseExpiresEpoch"] = 0
    job["deadlineEpoch"] = 0
    job["notBeforeEpoch"] = 0
    job["sameRunRetryable"] = False
    job["lastError"] = None
    job["timings"].append({"event": "succeeded", "at": store.now_iso()})
    job["updatedAt"] = store.now_iso()
    write_json(_job_path(task_id, batch_id, job_id), job)
    return job


def _stored_envelope_ref(envelope_path: Path, *, root: Path) -> str:
    try:
        return str(envelope_path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(envelope_path)


def complete_job_with_envelope(
    task_id: str,
    batch_id: str,
    job_id: str,
    lease: str,
    *,
    envelope_path: str | Path,
    workspace_root: str | Path | None = None,
) -> dict[str, Any]:
    """Complete a job only after validating an AgentResultEnvelope.

    This is the production admission path: files must exist, hashes must match,
    and every gate must have exactly one passing final verdict.
    """
    job = _load_owned(task_id, batch_id, job_id, lease)
    root = Path(workspace_root) if workspace_root is not None else batch_root(task_id, batch_id)
    path = Path(envelope_path)
    if not path.is_absolute():
        path = root / path
    try:
        envelope = read_json(path)
    except Exception as exc:  # noqa: BLE001
        issues = [f"result envelope unreadable: {exc}"]
        return fail_job(
            task_id,
            batch_id,
            job_id,
            lease,
            error="; ".join(issues),
            fingerprint=pc.stable_failure_fingerprint(issues),
            same_run_retryable=True,
        )
    issues = pc.validate_agent_result_envelope(envelope, workspace_root=root)
    issues.extend(pc.assert_envelope_matches_job(envelope, job))
    if issues:
        return fail_job(
            task_id,
            batch_id,
            job_id,
            lease,
            error="; ".join(issues),
            fingerprint=pc.stable_failure_fingerprint(issues),
            same_run_retryable=True,
        )

    job["resultEnvelopeRef"] = _stored_envelope_ref(path, root=root)
    job["gateVerdicts"] = list(envelope.get("gates") or [])
    job.setdefault("timings", []).append({"event": "envelope_accepted", "at": store.now_iso(), "envelope": job["resultEnvelopeRef"]})
    job["updatedAt"] = store.now_iso()
    write_json(_job_path(task_id, batch_id, job_id), job)
    return complete_job(task_id, batch_id, job_id, lease)


def reconcile_completed_refs(
    task_id: str,
    batch_id: str,
    refs: Iterable[str],
    stage: str,
    *,
    reason: str = "artifact_completed",
) -> list[str]:
    """把已在对象产物/工作流侧确认完成的 ref 对齐为 succeeded。

    用于 fanout 历史残留清理：例如 author 曾 startup_failed/dead，但后续通过
    finalize/manual rerun 已产出 approved 成品。此时 object_queue 不应继续把计划
    聚合拖回 failed/dead。
    """
    touched: list[str] = []
    wanted = {str(ref).strip() for ref in refs if str(ref).strip()}
    if not wanted:
        return touched
    for ref in sorted(wanted):
        job_id = stable_job_id(task_id, batch_id, ref, stage)
        path = _job_path(task_id, batch_id, job_id)
        if not path.is_file():
            continue
        job = read_json(path)
        if str(job.get("stage") or "") != stage:
            continue
        if str(job.get("state") or "") == STATE_SUCCEEDED:
            continue
        job["state"] = STATE_SUCCEEDED
        job["lease"] = None
        job["leaseExpiresEpoch"] = 0
        job["deadlineEpoch"] = 0
        job["notBeforeEpoch"] = 0
        job["sameRunRetryable"] = False
        job["lastError"] = None
        job.setdefault("timings", []).append(
            {"event": "reconciled", "at": store.now_iso(), "reason": reason}
        )
        job["updatedAt"] = store.now_iso()
        write_json(path, job)
        touched.append(ref)
    return touched


def _is_stuck(job: dict[str, Any], fingerprint: str | None) -> bool:
    """断路器：同一失败指纹连续 stuckThreshold 次不变 → 卡死（同 issues 反复修不动）。"""
    if not fingerprint:
        return False
    threshold = int(job.get("stuckThreshold") or DEFAULT_STUCK_THRESHOLD)
    prints = list(job.get("failureFingerprints") or [])
    prints.append(fingerprint)
    job["failureFingerprints"] = prints[-threshold:]
    recent = job["failureFingerprints"]
    return len(recent) >= threshold and len(set(recent)) == 1


def _apply_failure(
    job: dict[str, Any],
    error: str,
    *,
    fingerprint: str | None = None,
    same_run_retryable: bool = True,
    startup_failure: bool = False,
) -> dict[str, Any]:
    """失败状态机（fail_job 与 reaper 共用）：

    - 同一失败指纹连续 stuckThreshold 次不变 → 直接 dead（stuck，不再空耗 attempts）；
    - 未超 maxAttempts → failed + 指数退避；超出 → dead。
    """
    now = _now()
    attempt = int(job.get("attempt") or 0)
    startup_failure_count = int(job.get("startupFailureCount") or 0)
    if startup_failure:
        startup_failure_count += 1
        job["startupFailureCount"] = startup_failure_count
    job["lastError"] = error
    job["lease"] = None
    job["sameRunRetryable"] = bool(same_run_retryable)
    job.setdefault("timings", []).append({"event": "failed", "at": store.now_iso(), "error": error})
    stuck = _is_stuck(job, fingerprint)
    exhausted = (
        startup_failure_count >= int(job.get("maxStartupFailures") or DEFAULT_MAX_STARTUP_FAILURES)
        if startup_failure
        else attempt >= int(job.get("maxAttempts") or 1)
    )
    if stuck or exhausted:
        job["state"] = STATE_DEAD
        job["notBeforeEpoch"] = 0
        if stuck:
            job["stuckDetected"] = True
            _emit_notification(
                job.get("taskId", ""),
                job.get("batchId", ""),
                {
                    "event": "stuck",
                    "ref": job.get("ref"),
                    "jobId": job.get("jobId"),
                    "fingerprint": fingerprint,
                    "stuckThreshold": job.get("stuckThreshold"),
                    "lastError": error,
                },
            )
    else:
        job["state"] = STATE_FAILED
        job["notBeforeEpoch"] = now + _backoff_seconds(startup_failure_count if startup_failure else attempt)
    job["updatedAt"] = store.now_iso()
    return job


def fail_job(
    task_id: str,
    batch_id: str,
    job_id: str,
    lease: str,
    *,
    error: str,
    fingerprint: str | None = None,
    same_run_retryable: bool = True,
    startup_failure: bool = False,
) -> dict[str, Any]:
    """失败处理：未超 maxAttempts → 退回 failed(退避后可重取)；超出 / 卡死 → dead(转人工)。

    fingerprint：本轮失败的 issues 指纹（如 review_gate.issues 排序后 sha1），
    用于断路器识别"同 issues 反复修不动"。
    same_run_retryable=False：仅写 failed+backoff 留待下一次 fanout 运行，不要求当前进程继续等待。
    startup_failure=True：用于 startup failure 等“未真正执行”的场景，单独累计 startupFailureCount，
    不消耗内容质量重试预算 attempt。
    """
    job = _load_owned(task_id, batch_id, job_id, lease)
    _apply_failure(
        job,
        error,
        fingerprint=fingerprint,
        same_run_retryable=same_run_retryable,
        startup_failure=startup_failure,
    )
    write_json(_job_path(task_id, batch_id, job_id), job)
    return job


def revive_dead_startup_jobs(
    task_id: str,
    batch_id: str,
    *,
    refs: Iterable[str] | None = None,
    stage: str | None = None,
) -> dict[str, Any]:
    """把仅因 startup failure 卡住的 job 恢复为 queued，继续同一批次主线。

    兼容两种真实现场：
    - 已耗尽 startup budget，落到 `dead`
    - 非 retryable startup 失败，暂留在 `failed`

    两者在“当前 draft 仍是占位稿、需要重新 author”这一语义上等价，都应允许
    后续 `sync_content_author_jobs()` 把 job 拉回 `queued`。
    """
    ref_filter = {str(ref) for ref in refs} if refs is not None else None
    revived: list[str] = []
    for job in _load_jobs(task_id, batch_id):
        if job.get("state") not in (STATE_DEAD, STATE_FAILED):
            continue
        if stage and job.get("stage") != stage:
            continue
        ref = str(job.get("ref") or "")
        if ref_filter is not None and ref not in ref_filter:
            continue
        last_error = str(job.get("lastError") or "")
        if not last_error.startswith("startup:"):
            continue
        job["state"] = STATE_QUEUED
        job["lease"] = None
        job["leaseExpiresEpoch"] = 0
        job["deadlineEpoch"] = 0
        job["notBeforeEpoch"] = 0
        job["sameRunRetryable"] = True
        job["startupFailureCount"] = 0
        job["lastError"] = None
        job["failureFingerprints"] = []
        job.pop("stuckDetected", None)
        job.setdefault("timings", []).append({"event": "revived", "at": store.now_iso(), "reason": "startup_failure_retry"})
        job["updatedAt"] = store.now_iso()
        write_json(_job_path(task_id, batch_id, str(job["jobId"])), job)
        revived.append(ref)
    return {"revived": sorted(revived), "summary": queue_summary(task_id, batch_id)}


def issues_fingerprint(issues: Iterable[str]) -> str:
    """把一组 review issues 归一化为稳定指纹（供断路器比对"同 issues 反复修不动"）。"""
    norm = sorted({str(i).strip() for i in issues if str(i).strip()})
    return hashlib.sha1("\u0000".join(norm).encode("utf-8")).hexdigest()[:16]


def record_usage(
    task_id: str,
    batch_id: str,
    job_id: str,
    lease: str,
    *,
    tokens: int = 0,
    cost_usd: float = 0.0,
) -> dict[str, Any]:
    """累计 token/cost 用量；超 tokenBudget/costBudgetUsd（>0 时）→ 强制 dead（budget_exceeded）。"""
    job = _load_owned(task_id, batch_id, job_id, lease)
    usage = dict(job.get("usage") or {"tokens": 0, "costUsd": 0.0})
    usage["tokens"] = int(usage.get("tokens", 0)) + int(tokens)
    usage["costUsd"] = float(usage.get("costUsd", 0.0)) + float(cost_usd)
    job["usage"] = usage
    job.setdefault("tokenLedger", []).append(
        pc.build_token_ledger_entry(
            supply_task_id=str((job.get("meta") or {}).get("supplyTaskId") or job.get("taskId") or ""),
            batch_id=batch_id,
            job_id=job_id,
            creator_profile_id=str(job.get("creatorProfileId") or (job.get("meta") or {}).get("creatorProfileId") or "unknown"),
            content_type=str(job.get("contentType") or (job.get("meta") or {}).get("contentType") or job.get("stage") or "unknown"),
            budget_tokens=int(job.get("tokenBudget") or 0),
            used_tokens=int(usage.get("tokens") or 0),
            cost_usd=float(usage.get("costUsd") or 0.0),
        )
    )
    token_budget = int(job.get("tokenBudget") or 0)
    cost_budget = float(job.get("costBudgetUsd") or 0.0)
    over_token = token_budget > 0 and usage["tokens"] > token_budget
    over_cost = cost_budget > 0 and usage["costUsd"] > cost_budget
    if over_token or over_cost:
        reason = (
            f"budget_exceeded: tokens={usage['tokens']}/{token_budget} costUsd={usage['costUsd']}/{cost_budget}"
        )
        # 预算耗尽是硬停（不重试）：强制 dead + notify。
        job["attempt"] = int(job.get("maxAttempts") or 1)
        _apply_failure(job, reason)
        _emit_notification(
            task_id,
            batch_id,
            {"event": "budget_exceeded", "ref": job.get("ref"), "jobId": job_id, "usage": usage},
        )
    else:
        job["updatedAt"] = store.now_iso()
    write_json(_job_path(task_id, batch_id, job_id), job)
    return job


def reap_jobs(task_id: str, batch_id: str) -> dict[str, Any]:
    """主动 reaper（业界 stuck-job recovery）：
    - 超 deadlineEpoch（墙钟硬上限）的 leased job → 强制 fail（timeout），按 maxAttempts 升级 dead；
    - lease 过期但未超 deadline（崩溃/无心跳）的 leased job → 回收为 queued，可被重取。
    """
    now = _now()
    timed_out: list[str] = []
    reclaimed: list[str] = []
    for job in _load_jobs(task_id, batch_id):
        if job.get("state") != STATE_LEASED:
            continue
        deadline = float(job.get("deadlineEpoch") or 0)
        lease_exp = float(job.get("leaseExpiresEpoch") or 0)
        if deadline and now > deadline:
            _apply_failure(job, f"timeout: exceeded maxWallClock ({job.get('maxWallClockSeconds')}s)")
            job["deadlineEpoch"] = 0
            write_json(_job_path(task_id, batch_id, job["jobId"]), job)
            timed_out.append(str(job.get("ref")))
        elif lease_exp and now > lease_exp:
            job["state"] = STATE_QUEUED
            job["lease"] = None
            job["leaseExpiresEpoch"] = 0
            job["deadlineEpoch"] = 0
            job.setdefault("timings", []).append({"event": "reclaimed", "at": store.now_iso(), "reason": "lease_expired"})
            job["updatedAt"] = store.now_iso()
            write_json(_job_path(task_id, batch_id, job["jobId"]), job)
            reclaimed.append(str(job.get("ref")))
    return {"timedOut": sorted(timed_out), "reclaimed": sorted(reclaimed)}


def dead_jobs(task_id: str, batch_id: str) -> list[dict[str, Any]]:
    """列出 dead job（转人工修复队列），含最后错误与尝试数。"""
    out: list[dict[str, Any]] = []
    for job in _load_jobs(task_id, batch_id):
        if job.get("state") != STATE_DEAD:
            continue
        out.append(
            {
                "jobId": job.get("jobId"),
                "ref": job.get("ref"),
                "stage": job.get("stage"),
                "attempt": job.get("attempt"),
                "lastError": job.get("lastError"),
            }
        )
    return out


def spillover_dead(task_id: str, batch_id: str, *, target_batch_id: str, stage: str | None = None) -> dict[str, Any]:
    """把 dead job 溢出到独立修复批（不阻塞当前批）：
    在 target_batch 重新入队为全新 job（attempt 归零），原 dead job 标记 spilled 留痕。
    """
    spilled_refs: list[str] = []
    for job in _load_jobs(task_id, batch_id):
        if job.get("state") != STATE_DEAD:
            continue
        if stage and job.get("stage") != stage:
            continue
        enqueue_ref_job(
            task_id,
            target_batch_id,
            str(job.get("ref")),
            str(job.get("stage")),
            mutex_key=str(job.get("mutexKey") or job.get("ref")),
            fallback_stage=job.get("fallbackStage"),
            max_attempts=int(job.get("maxAttempts") or DEFAULT_MAX_ATTEMPTS),
            max_wall_clock_seconds=int(job.get("maxWallClockSeconds") or DEFAULT_MAX_WALL_CLOCK_SECONDS),
            meta={**dict(job.get("meta") or {}), "spilledFromBatch": batch_id, "spilledLastError": job.get("lastError")},
        )
        job["state"] = STATE_SPILLED
        job.setdefault("timings", []).append({"event": "spilled", "at": store.now_iso(), "toBatch": target_batch_id})
        job["updatedAt"] = store.now_iso()
        write_json(_job_path(task_id, batch_id, job["jobId"]), job)
        spilled_refs.append(str(job.get("ref")))
    return {"spilled": sorted(spilled_refs), "targetBatch": target_batch_id}


def build_lease_packet(job: Mapping[str, Any]) -> dict[str, Any]:
    """把租到的 job 转成 Subagent 可直接消费的 handoff packet（含 Ralph 自纠环出口约束）。"""
    meta = dict(job.get("meta") or {})
    return {
        "schemaVersion": "quwoquan_data.lease_packet/1",
        "jobId": job.get("jobId"),
        "taskId": job.get("taskId"),
        "batchId": job.get("batchId"),
        "ref": job.get("ref"),
        "stage": job.get("stage"),
        "queueBackend": job.get("queueBackend") or QUEUE_BACKEND_LOCAL,
        "partitionKey": job.get("partitionKey") or job.get("mutexKey") or job.get("ref"),
        "creatorProfileId": job.get("creatorProfileId") or meta.get("creatorProfileId"),
        "creatorArchetype": job.get("creatorArchetype") or meta.get("creatorArchetype"),
        "contentType": job.get("contentType") or meta.get("contentType"),
        "resultEnvelopeRequired": bool(job.get("resultEnvelopeRequired")),
        "resultEnvelopeContract": {
            "schemaVersion": pc.AGENT_RESULT_ENVELOPE_SCHEMA,
            "required": bool(job.get("resultEnvelopeRequired")),
            "completionCommand": "qwq-data object-queue complete-envelope --task <task> --batch <batch> --job <jobId> --lease <lease> --envelope <path>",
            "rules": [
                "AgentResultEnvelope.files[].path 必须是 batch root 下相对路径",
                "AgentResultEnvelope.files[].sha256 必须与真实文件一致",
                "AgentResultEnvelope.gates[] 必须是唯一 final verdict 且全部 passed/approved",
            ],
        },
        "lease": job.get("lease"),
        "mutexKey": job.get("mutexKey"),
        "attempt": job.get("attempt"),
        "maxAttempts": job.get("maxAttempts"),
        "leaseExpiresEpoch": job.get("leaseExpiresEpoch"),
        "deadlineEpoch": job.get("deadlineEpoch"),
        "maxWallClockSeconds": job.get("maxWallClockSeconds"),
        "objectPacketRefs": {
            "contentObjectDir": meta.get("contentObjectDir"),
            "authorJobPacket": "4.draft/author_job_packet.json",
            "writingPack": "3.compose/writing_pack.json",
            "draft": "4.draft/draft.article.md",
            "selfCheck": "4.draft/author_self_check.json",
        },
        # 执行合约 5 要素（harness execution contract）：把模糊 LLM 调用收成有界 agent 调用。
        "executionContract": {
            "inputs": [
                "4.draft/author_job_packet.json",
                "3.compose/writing_pack.json",
                "2.quality/*（证据/source）",
                "5.review/repair_report.json",
            ],
            "budget": {
                "maxWallClockSeconds": job.get("maxWallClockSeconds"),
                "maxAttempts": job.get("maxAttempts"),
                "maxStartupFailures": job.get("maxStartupFailures"),
                "stuckThreshold": job.get("stuckThreshold"),
                "tokenBudget": job.get("tokenBudget"),
                "costBudgetUsd": job.get("costBudgetUsd"),
            },
            "permissions": list(job.get("permissions") or DEFAULT_TOOL_PERMISSIONS),
            "completionConditions": [
                "4.draft/draft.article.md 已写且非占位",
                "4.draft/author_self_check.json 存在",
                "ref_review_gate.passed == true (reviewDecision == approved)",
            ],
            "outputPaths": [
                "4.draft/draft.article.md",
                "4.draft/author_self_check.json",
                "5.review/ref_review_gate.json",
            ],
        },
        "ralphLoop": (
            "draft → 跑单 ref review 门 → 读 issues 自修 → 循环，直到 ref_review_gate.passed=approved；"
            "周期 heartbeat 续租；超 deadlineEpoch 则由 reaper 标 timeout 失败（交 spillover），不得假装完成"
        ),
        "isolation": "single-ref: 只读本 ref 的 packet/SOP/source，禁止读取同批其它文章正文作为底稿",
        "meta": meta,
    }


def block_job(task_id: str, batch_id: str, job_id: str, *, reason: str) -> dict[str, Any]:
    path = _job_path(task_id, batch_id, job_id)
    job = read_json(path)
    job["state"] = STATE_BLOCKED
    job["lease"] = None
    job["lastError"] = reason
    job["updatedAt"] = store.now_iso()
    write_json(path, job)
    return job


def requeue_refs(
    task_id: str,
    batch_id: str,
    refs: Iterable[str],
    stage: str,
    *,
    reason: str = "reducer_fail",
) -> list[str]:
    """把指定 ref 重新入队为 queued（同批重跑，不新建 repair batch）。

    适用于：
    - reducer 跨篇门失败后，只回退受影响 ref；
    - 人工/Agent 已修复对象产物后，把 dead/failed ref 拉回当前批次继续跑。
    """
    touched: list[str] = []
    for ref in refs:
        job_id = stable_job_id(task_id, batch_id, ref, stage)
        path = _job_path(task_id, batch_id, job_id)
        if not path.is_file():
            continue
        job = read_json(path)
        job["state"] = STATE_QUEUED
        job["lease"] = None
        job["leaseExpiresEpoch"] = 0
        job["deadlineEpoch"] = 0
        job["notBeforeEpoch"] = 0
        job["sameRunRetryable"] = True
        job["startupFailureCount"] = 0
        job["lastError"] = None
        job["failureFingerprints"] = []
        job.pop("stuckDetected", None)
        job["timings"].append({"event": "requeued", "at": store.now_iso(), "reason": reason})
        job["updatedAt"] = store.now_iso()
        write_json(path, job)
        touched.append(ref)
    return touched


def refresh_job_definition(
    task_id: str,
    batch_id: str,
    ref: str,
    stage: str,
    *,
    mutex_key: str | None = None,
    fallback_stage: str | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    max_startup_failures: int = DEFAULT_MAX_STARTUP_FAILURES,
    max_wall_clock_seconds: int = DEFAULT_MAX_WALL_CLOCK_SECONDS,
    stuck_threshold: int = DEFAULT_STUCK_THRESHOLD,
    permissions: Iterable[str] | None = None,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    cost_budget_usd: float = DEFAULT_COST_BUDGET_USD,
    meta: Mapping[str, Any] | None = None,
    queue_backend: str | None = None,
) -> dict[str, Any] | None:
    """刷新现有 job 的配置定义，但不重置运行态/尝试历史。"""
    job_id = stable_job_id(task_id, batch_id, ref, stage)
    path = _job_path(task_id, batch_id, job_id)
    if not path.is_file():
        return None
    job = read_json(path)
    job["mutexKey"] = mutex_key or ref
    job["fallbackStage"] = fallback_stage
    job["maxAttempts"] = int(max_attempts)
    job["maxStartupFailures"] = int(max_startup_failures)
    job["maxWallClockSeconds"] = int(max_wall_clock_seconds)
    job["stuckThreshold"] = int(stuck_threshold)
    job["permissions"] = list(permissions) if permissions is not None else list(DEFAULT_TOOL_PERMISSIONS)
    job["tokenBudget"] = int(token_budget)
    job["costBudgetUsd"] = float(cost_budget_usd)
    job["meta"] = dict(meta or {})
    if queue_backend is not None:
        backend = _backend_name(queue_backend)
        partition_key = str(job.get("partitionKey") or mutex_key or ref)
        job["queueBackend"] = backend
        job["resultEnvelopeRequired"] = backend == QUEUE_BACKEND_RELIABLETASK or bool((meta or {}).get("resultEnvelopeRequired"))
        job["reliableTaskRef"] = (
            _reliabletask_ref(
                task_id=task_id,
                batch_id=batch_id,
                job_id=job_id,
                ref=ref,
                stage=stage,
                partition_key=partition_key,
            )
            if backend == QUEUE_BACKEND_RELIABLETASK
            else None
        )
    job["updatedAt"] = store.now_iso()
    write_json(path, job)
    return job


def purge_jobs(
    task_id: str,
    batch_id: str,
    *,
    stage: str | None = None,
    refs: Iterable[str] | None = None,
) -> dict[str, Any]:
    """硬清理匹配 job（reset_state / 上游回退后丢弃过期 stage 队列）。

    object_queue 是 workflow 下游派生物，不是发布契约真相源；当 workflow 明确回到
    download/content_plan/compose 之前时，旧 author job 已经失效，必须整体丢弃。
    """
    ref_filter = {str(ref) for ref in refs} if refs is not None else None
    removed: list[str] = []
    for job in _load_jobs(task_id, batch_id):
        if stage and job.get("stage") != stage:
            continue
        ref = str(job.get("ref") or "")
        if ref_filter is not None and ref not in ref_filter:
            continue
        path = _job_path(task_id, batch_id, str(job.get("jobId") or ""))
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        removed.append(ref)
    return {"removed": sorted(removed), "summary": queue_summary(task_id, batch_id)}


def queue_summary(task_id: str, batch_id: str) -> dict[str, Any]:
    jobs = _load_jobs(task_id, batch_id)
    by_state: dict[str, list[str]] = {}
    by_backend: dict[str, int] = {}
    for job in jobs:
        by_state.setdefault(str(job.get("state")), []).append(str(job.get("ref")))
        backend = str(job.get("queueBackend") or QUEUE_BACKEND_LOCAL)
        by_backend[backend] = by_backend.get(backend, 0) + 1
    return {
        "total": len(jobs),
        "byState": {k: sorted(v) for k, v in sorted(by_state.items())},
        "byBackend": dict(sorted(by_backend.items())),
    }


def queue_runtime_snapshot(
    task_id: str,
    batch_id: str,
    *,
    stage: str | None = None,
    refs: Iterable[str] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """调度期快照：给 runner 判断“当前真无活”还是“只是退避/互斥空窗”。

    refs=None 表示不过滤；refs 非空时只统计 assignment 负责的 ref 范围。
    sameRunRetryable=False 的 failed job（例如 startup 失败）保留给下一次 run，不要求当前进程继续等待。
    """
    current = _now() if now is None else float(now)
    ref_filter = {str(ref) for ref in refs} if refs is not None else None
    by_state: dict[str, int] = {}
    waitable_live = 0
    leaseable_now = 0
    failed_backoff_same_run = 0
    next_retry_epoch: float | None = None
    next_lease_expiry_epoch: float | None = None
    next_deadline_epoch: float | None = None
    for job in _load_jobs(task_id, batch_id):
        if stage and job.get("stage") != stage:
            continue
        ref = str(job.get("ref") or "")
        if ref_filter is not None and ref not in ref_filter:
            continue
        state = str(job.get("state") or "")
        by_state[state] = by_state.get(state, 0) + 1
        if state == STATE_QUEUED:
            waitable_live += 1
            leaseable_now += 1
            continue
        if state == STATE_LEASED:
            waitable_live += 1
            lease_exp = float(job.get("leaseExpiresEpoch") or 0)
            if lease_exp and lease_exp <= current:
                leaseable_now += 1
            elif lease_exp:
                next_lease_expiry_epoch = (
                    lease_exp if next_lease_expiry_epoch is None else min(next_lease_expiry_epoch, lease_exp)
                )
            deadline = float(job.get("deadlineEpoch") or 0)
            if deadline:
                next_deadline_epoch = deadline if next_deadline_epoch is None else min(next_deadline_epoch, deadline)
            continue
        if state != STATE_FAILED:
            continue
        if not bool(job.get("sameRunRetryable", True)):
            continue
        waitable_live += 1
        not_before = float(job.get("notBeforeEpoch") or 0)
        if not_before <= current:
            leaseable_now += 1
        else:
            failed_backoff_same_run += 1
            next_retry_epoch = not_before if next_retry_epoch is None else min(next_retry_epoch, not_before)
    return {
        "total": sum(by_state.values()),
        "byState": dict(sorted(by_state.items())),
        "waitableLive": waitable_live,
        "leaseableNow": leaseable_now,
        "failedBackoffSameRun": failed_backoff_same_run,
        "nextRetryEpoch": next_retry_epoch,
        "nextLeaseExpiryEpoch": next_lease_expiry_epoch,
        "nextDeadlineEpoch": next_deadline_epoch,
    }


def register_object_queue_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("object-queue", help="单篇隔离的 object-stage job 队列（Subagent 并行调度）")
    sub = p.add_subparsers(dest="object_queue_command")

    def _emit(payload: Any) -> None:
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    pe = sub.add_parser("enqueue", help="把 content_plan_packet 各 ref 入队为 author job")
    pe.add_argument("--task", required=True)
    pe.add_argument("--batch", required=True)
    pe.add_argument("--stage", default="author")
    pe.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    pe.add_argument("--max-wall-clock", type=int, default=DEFAULT_MAX_WALL_CLOCK_SECONDS, help="逐 job 墙钟硬上限（秒，默认 1200=20min）")
    pe.add_argument("--backend", choices=SUPPORTED_QUEUE_BACKENDS, default=None, help="队列后端：local_file 小批；reliabletask 生产桥")

    def _do_enqueue(args: argparse.Namespace) -> None:
        from _common.content_plan import load_content_plan_packet

        packet = load_content_plan_packet(args.task, args.batch) or {}
        items = [
            {
                "ref": i.get("ref"),
                "baseSourceRef": i.get("baseSourceRef"),
                "meta": {
                    "writingIntent": i.get("writingIntent"),
                    "contentType": i.get("contentType") or i.get("carrier"),
                    "creatorProfileId": i.get("creatorProfileId"),
                    "creatorArchetype": i.get("creatorArchetype"),
                },
            }
            for i in (packet.get("items") or [])
            if i.get("ref")
        ]
        jobs = enqueue_ref_jobs(
            args.task, args.batch, items, args.stage,
            max_attempts=args.max_attempts,
            max_startup_failures=DEFAULT_MAX_STARTUP_FAILURES,
            max_wall_clock_seconds=args.max_wall_clock,
            queue_backend=args.backend,
        )
        _emit({"enqueued": len(jobs), "summary": queue_summary(args.task, args.batch)})

    pe.set_defaults(handler=_do_enqueue)

    pl = sub.add_parser("list", help="队列状态汇总")
    pl.add_argument("--task", required=True)
    pl.add_argument("--batch", required=True)
    pl.set_defaults(handler=lambda a: _emit(queue_summary(a.task, a.batch)))

    pln = sub.add_parser("lease-next", help="租一个可执行 job 并打印 handoff packet（供 Subagent 直接消费）")
    pln.add_argument("--task", required=True)
    pln.add_argument("--batch", required=True)
    pln.add_argument("--worker", required=True)
    pln.add_argument("--stage", default=None)
    pln.add_argument("--ref", default=None, help="只租该 ref（by-leaf / per-ref worker 精确寻址）")
    pln.add_argument("--ttl", type=int, default=DEFAULT_LEASE_TTL_SECONDS, help="lease 租约 TTL（秒），心跳前的可见性超时")

    def _do_lease_next(args: argparse.Namespace) -> None:
        job = acquire_lease(args.task, args.batch, worker=args.worker, stage=args.stage, ref=args.ref, ttl_seconds=args.ttl)
        if job is None:
            _emit({"leased": False, "summary": queue_summary(args.task, args.batch)})
            return
        _emit({"leased": True, "packet": build_lease_packet(job)})

    pln.set_defaults(handler=_do_lease_next)

    pc = sub.add_parser("complete", help="标记 job 成功（需持有 lease）")
    pc.add_argument("--task", required=True)
    pc.add_argument("--batch", required=True)
    pc.add_argument("--job", required=True)
    pc.add_argument("--lease", required=True)
    pc.set_defaults(handler=lambda a: _emit(complete_job(a.task, a.batch, a.job, a.lease)))

    pce = sub.add_parser("complete-envelope", help="校验 AgentResultEnvelope 后标记 job 成功（生产路径）")
    pce.add_argument("--task", required=True)
    pce.add_argument("--batch", required=True)
    pce.add_argument("--job", required=True)
    pce.add_argument("--lease", required=True)
    pce.add_argument("--envelope", required=True, help="AgentResultEnvelope JSON；相对 batch root 或绝对路径")
    pce.add_argument("--workspace-root", default=None, help="校验文件 hash 的根目录；默认 batch root")
    pce.set_defaults(
        handler=lambda a: _emit(
            complete_job_with_envelope(
                a.task,
                a.batch,
                a.job,
                a.lease,
                envelope_path=a.envelope,
                workspace_root=a.workspace_root,
            )
        )
    )

    pf = sub.add_parser("fail", help="标记 job 失败（未超 maxAttempts 退避重取，超出/卡死转 dead）")
    pf.add_argument("--task", required=True)
    pf.add_argument("--batch", required=True)
    pf.add_argument("--job", required=True)
    pf.add_argument("--lease", required=True)
    pf.add_argument("--error", required=True)
    pf.add_argument("--fingerprint", default=None, help="本轮 issues 指纹（断路器识别同 issues 反复修不动）")
    pf.add_argument("--startup-failure", action="store_true", help="startup 等未真正执行场景：累计 startupFailureCount，不消耗内容重试预算")
    pf.set_defaults(
        handler=lambda a: _emit(
            fail_job(
                a.task,
                a.batch,
                a.job,
                a.lease,
                error=a.error,
                fingerprint=a.fingerprint,
                startup_failure=bool(a.startup_failure),
            )
        )
    )

    pu = sub.add_parser("usage", help="累计 token/cost 用量（超预算强制 dead）")
    pu.add_argument("--task", required=True)
    pu.add_argument("--batch", required=True)
    pu.add_argument("--job", required=True)
    pu.add_argument("--lease", required=True)
    pu.add_argument("--tokens", type=int, default=0)
    pu.add_argument("--cost-usd", type=float, default=0.0)
    pu.set_defaults(handler=lambda a: _emit(record_usage(a.task, a.batch, a.job, a.lease, tokens=a.tokens, cost_usd=a.cost_usd)))

    pn = sub.add_parser("notifications", help="列出断路器/超时/预算事件（编排循环订阅）")
    pn.add_argument("--task", required=True)
    pn.add_argument("--batch", required=True)
    pn.set_defaults(handler=lambda a: _emit({"notifications": list_notifications(a.task, a.batch)}))

    ph = sub.add_parser("heartbeat", help="续租（renew lease），长任务周期调用避免被 reaper 回收")
    ph.add_argument("--task", required=True)
    ph.add_argument("--batch", required=True)
    ph.add_argument("--job", required=True)
    ph.add_argument("--lease", required=True)
    ph.add_argument("--ttl", type=int, default=DEFAULT_LEASE_TTL_SECONDS)
    ph.set_defaults(handler=lambda a: _emit(renew_lease(a.task, a.batch, a.job, a.lease, ttl_seconds=a.ttl)))

    pr = sub.add_parser("reap", help="reaper：回收过期 lease（崩溃）+ 强制 timeout 超墙钟 job")
    pr.add_argument("--task", required=True)
    pr.add_argument("--batch", required=True)
    pr.set_defaults(handler=lambda a: _emit(reap_jobs(a.task, a.batch)))

    pd = sub.add_parser("dead-list", help="列出 dead job（转人工修复队列）")
    pd.add_argument("--task", required=True)
    pd.add_argument("--batch", required=True)
    pd.set_defaults(handler=lambda a: _emit({"dead": dead_jobs(a.task, a.batch)}))

    prq = sub.add_parser("requeue", help="把指定 ref 重新入队（同批修复后继续跑）")
    prq.add_argument("--task", required=True)
    prq.add_argument("--batch", required=True)
    prq.add_argument("--stage", default="author")
    prq.add_argument("--refs", required=True, help="逗号分隔的 ref 列表")
    prq.add_argument("--reason", default="manual_repair")

    def _do_requeue(args: argparse.Namespace) -> None:
        refs = [str(item).strip() for item in str(args.refs).split(",") if str(item).strip()]
        if not refs:
            raise SystemExit("object-queue requeue requires at least one ref")
        touched = requeue_refs(args.task, args.batch, refs, args.stage, reason=args.reason)
        _emit({"requeued": touched, "summary": queue_summary(args.task, args.batch)})

    prq.set_defaults(handler=_do_requeue)

    ps = sub.add_parser("spillover", help="把 dead job 溢出到独立修复批（不阻塞当前批）")
    ps.add_argument("--task", required=True)
    ps.add_argument("--batch", required=True)
    ps.add_argument("--target-batch", required=True)
    ps.add_argument("--stage", default=None)
    ps.set_defaults(handler=lambda a: _emit(spillover_dead(a.task, a.batch, target_batch_id=a.target_batch, stage=a.stage)))

    prv = sub.add_parser("revive-startup-dead", help="把仅因 startup failure 而 dead 的 job 恢复为 queued")
    prv.add_argument("--task", required=True)
    prv.add_argument("--batch", required=True)
    prv.add_argument("--stage", default=None)
    prv.add_argument("--refs", default=None, help="逗号分隔，仅恢复指定 ref")
    prv.set_defaults(
        handler=lambda a: _emit(
            revive_dead_startup_jobs(
                a.task,
                a.batch,
                refs=[x.strip() for x in str(a.refs or "").split(",") if x.strip()] or None,
                stage=a.stage,
            )
        )
    )

    def _dispatch(args: argparse.Namespace) -> None:
        if not getattr(args, "object_queue_command", None):
            p.print_help()
            raise SystemExit(1)

    p.set_defaults(handler=_dispatch)
