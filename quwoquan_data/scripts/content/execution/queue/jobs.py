"""Object queue job definition enqueue and refresh operations."""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from core import ops_governance as og
from governance.creators.assignment import creator_assignment_issues
from core.io import read_json, write_json
from content.execution import store
from content.execution.queue.core import (
    DEFAULT_COST_BUDGET_USD,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_MAX_STARTUP_FAILURES,
    DEFAULT_MAX_WALL_CLOCK_SECONDS,
    DEFAULT_STUCK_THRESHOLD,
    DEFAULT_TOKEN_BUDGET,
    DEFAULT_TOOL_PERMISSIONS,
    OBJECT_JOB_SCHEMA,
    QUEUE_BACKEND_RELIABLETASK,
    STATE_QUEUED,
    _backend_name,
    _job_path,
    _reliabletask_ref,
    stable_job_id,
)

def enqueue_ref_job(
    execution_id: str,
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
    """入队一个 ref+stage job（幂等）。

    已存在 job 一律返回，尤其不能把 STATE_SUCCEEDED 回退为 queued。
    同一 execution 内显式重跑必须走带审计语义的 requeue_refs；跨 execution 重试由
    content execution 入口创建新的 executionId 并写 retryOf。
    """
    job_id = stable_job_id(execution_id, ref, stage)
    path = _job_path(execution_id, job_id)
    if path.is_file():
        return read_json(path)
    raw_meta = dict(meta or {})
    content_type_for_creator = str(raw_meta.get("contentType") or raw_meta.get("carrier") or "").strip()
    if stage == "author" and content_type_for_creator in {"article", "image", "video"}:
        creator_issues = creator_assignment_issues(
            raw_meta,
            carrier=content_type_for_creator,
            prefix=f"objectJob[{ref}].creatorAssignment",
        )
        if creator_issues:
            raise ValueError("; ".join(creator_issues))
    backend = _backend_name(queue_backend or raw_meta.get("queueBackend"))
    partition_key = str(raw_meta.get("partitionKey") or mutex_key or ref)
    assignment = raw_meta.get("assignment") if isinstance(raw_meta.get("assignment"), Mapping) else {}
    strict_governance = bool(raw_meta.get("requireGovernance"))
    assignment_issues = og.validate_assignment_payload(assignment) if assignment else []
    if strict_governance and (not assignment or assignment_issues):
        details = "; ".join(assignment_issues or ["assignment required"])
        raise ValueError(f"object job governance assignment invalid for {ref}/{stage}: {details}")
    reliable_ref = (
        _reliabletask_ref(
            execution_id=execution_id,
            job_id=job_id,
            ref=ref,
            stage=stage,
            partition_key=partition_key,
            entity_ref=str(raw_meta.get("entityRef") or raw_meta.get("targetRef") or ref),
            carrier=str(raw_meta.get("carrier") or raw_meta.get("contentType") or ""),
            source_revision=str(raw_meta.get("sourceRevision") or ""),
        )
        if backend == QUEUE_BACKEND_RELIABLETASK
        else None
    )
    payload = {
        "schema": OBJECT_JOB_SCHEMA,
        "jobId": job_id,
        "executionId": execution_id,
        "ref": ref,
        "stage": stage,
        "queueBackend": backend,
        "partitionKey": partition_key,
        "controllerRunId": str(raw_meta.get("controllerRunId") or assignment.get("controllerRunId") or ""),
        "assignmentId": str(raw_meta.get("assignmentId") or assignment.get("assignmentId") or ""),
        "assignmentPath": list(raw_meta.get("assignmentPath") or assignment.get("assignmentPath") or []),
        "owner": str(raw_meta.get("owner") or assignment.get("role") or ""),
        "allowedReadRoots": list(raw_meta.get("allowedReadRoots") or assignment.get("allowedReadRoots") or []),
        "allowedWriteRoots": list(raw_meta.get("allowedWriteRoots") or assignment.get("allowedWriteRoots") or []),
        "sourceUnitId": str(raw_meta.get("sourceUnitId") or ""),
        "requireGovernance": strict_governance,
        "sourceUnitIdRequired": bool(raw_meta.get("sourceUnitIdRequired")),
        "reliableTaskRef": reliable_ref,
        "resultEnvelopeRequired": backend == QUEUE_BACKEND_RELIABLETASK or bool((meta or {}).get("resultEnvelopeRequired")),
        "resultEnvelopeRef": None,
        "gateVerdicts": [],
        "tokenLedger": [],
        "creatorProfileId": (meta or {}).get("creatorProfileId"),
        "authorId": (meta or {}).get("authorId"),
        "creatorArchetype": (meta or {}).get("creatorArchetype"),
        "creatorProfileVersion": (meta or {}).get("creatorProfileVersion"),
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
        "meta": raw_meta,
        "createdAt": store.now_iso(),
        "updatedAt": store.now_iso(),
    }
    write_json(path, payload)
    return payload


def enqueue_ref_jobs(
    execution_id: str,
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
                execution_id,
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

def refresh_job_definition(
    execution_id: str,
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
    job_id = stable_job_id(execution_id, ref, stage)
    path = _job_path(execution_id, job_id)
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
    raw_meta = dict(meta or {})
    assignment = raw_meta.get("assignment") if isinstance(raw_meta.get("assignment"), Mapping) else {}
    strict_governance = bool(raw_meta.get("requireGovernance"))
    assignment_issues = og.validate_assignment_payload(assignment) if assignment else []
    if strict_governance and (not assignment or assignment_issues):
        details = "; ".join(assignment_issues or ["assignment required"])
        raise ValueError(f"object job governance assignment invalid for {ref}/{stage}: {details}")
    job["controllerRunId"] = str(raw_meta.get("controllerRunId") or assignment.get("controllerRunId") or job.get("controllerRunId") or "")
    job["assignmentId"] = str(raw_meta.get("assignmentId") or assignment.get("assignmentId") or job.get("assignmentId") or "")
    job["assignmentPath"] = list(raw_meta.get("assignmentPath") or assignment.get("assignmentPath") or job.get("assignmentPath") or [])
    job["owner"] = str(raw_meta.get("owner") or assignment.get("role") or job.get("owner") or "")
    job["allowedReadRoots"] = list(raw_meta.get("allowedReadRoots") or assignment.get("allowedReadRoots") or job.get("allowedReadRoots") or [])
    job["allowedWriteRoots"] = list(raw_meta.get("allowedWriteRoots") or assignment.get("allowedWriteRoots") or job.get("allowedWriteRoots") or [])
    job["sourceUnitId"] = str(raw_meta.get("sourceUnitId") or job.get("sourceUnitId") or "")
    job["requireGovernance"] = strict_governance
    job["sourceUnitIdRequired"] = bool(raw_meta.get("sourceUnitIdRequired") or job.get("sourceUnitIdRequired"))
    job["meta"] = raw_meta
    if queue_backend is not None:
        backend = _backend_name(queue_backend)
        partition_key = str(job.get("partitionKey") or mutex_key or ref)
        job["queueBackend"] = backend
        job["resultEnvelopeRequired"] = backend == QUEUE_BACKEND_RELIABLETASK or bool((meta or {}).get("resultEnvelopeRequired"))
        job["reliableTaskRef"] = (
            _reliabletask_ref(
                execution_id=execution_id,
                job_id=job_id,
                ref=ref,
                stage=stage,
                partition_key=partition_key,
                entity_ref=str(raw_meta.get("entityRef") or raw_meta.get("targetRef") or ref),
                carrier=str(raw_meta.get("carrier") or raw_meta.get("contentType") or ""),
                source_revision=str(raw_meta.get("sourceRevision") or ""),
            )
            if backend == QUEUE_BACKEND_RELIABLETASK
            else None
        )
    job["updatedAt"] = store.now_iso()
    write_json(path, job)
    return job

__all__ = [name for name in globals() if not name.startswith("__")]
