"""Administrative queue operations and read-only runtime snapshots."""
from __future__ import annotations

from typing import Any, Iterable

from core.io import read_json, write_json
from content.execution import store
from content.execution.queue.core import (
    QUEUE_BACKEND_LOCAL,
    STATE_BLOCKED,
    STATE_DEAD,
    STATE_FAILED,
    STATE_LEASED,
    STATE_QUEUED,
    _job_path,
    _load_jobs,
    _now,
    stable_job_id,
)


def dead_jobs(execution_id: str) -> list[dict[str, Any]]:
    """Return dead jobs that require an explicit operator decision."""
    return [
        {
            "jobId": job.get("jobId"),
            "ref": job.get("ref"),
            "stage": job.get("stage"),
            "attempt": job.get("attempt"),
            "lastError": job.get("lastError"),
        }
        for job in _load_jobs(execution_id)
        if job.get("state") == STATE_DEAD
    ]


def block_job(execution_id: str, job_id: str, *, reason: str) -> dict[str, Any]:
    path = _job_path(execution_id, job_id)
    job = read_json(path)
    job["state"] = STATE_BLOCKED
    job["lease"] = None
    job["lastError"] = reason
    job["updatedAt"] = store.now_iso()
    write_json(path, job)
    return job


def requeue_refs(
    execution_id: str,
    refs: Iterable[str],
    stage: str,
    *,
    reason: str = "reducer_fail",
) -> list[str]:
    """Requeue selected refs in the current execution with an audit event."""
    touched: list[str] = []
    for ref in refs:
        job_id = stable_job_id(execution_id, ref, stage)
        path = _job_path(execution_id, job_id)
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
        job["timings"].append(
            {"event": "requeued", "at": store.now_iso(), "reason": reason}
        )
        job["updatedAt"] = store.now_iso()
        write_json(path, job)
        touched.append(ref)
    return touched


def purge_jobs(
    execution_id: str,
    *,
    stage: str | None = None,
    refs: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Delete derived jobs invalidated by an explicit upstream reset."""
    ref_filter = {str(ref) for ref in refs} if refs is not None else None
    removed: list[str] = []
    for job in _load_jobs(execution_id):
        if stage and job.get("stage") != stage:
            continue
        ref = str(job.get("ref") or "")
        if ref_filter is not None and ref not in ref_filter:
            continue
        path = _job_path(execution_id, str(job.get("jobId") or ""))
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        removed.append(ref)
    return {"removed": sorted(removed), "summary": queue_summary(execution_id)}


def queue_summary(execution_id: str) -> dict[str, Any]:
    jobs = _load_jobs(execution_id)
    by_state: dict[str, list[str]] = {}
    by_backend: dict[str, int] = {}
    for job in jobs:
        by_state.setdefault(str(job.get("state")), []).append(str(job.get("ref")))
        backend = str(job.get("queueBackend") or QUEUE_BACKEND_LOCAL)
        by_backend[backend] = by_backend.get(backend, 0) + 1
    return {
        "total": len(jobs),
        "byState": {key: sorted(values) for key, values in sorted(by_state.items())},
        "byBackend": dict(sorted(by_backend.items())),
    }


def queue_runtime_snapshot(
    execution_id: str,
    *,
    stage: str | None = None,
    refs: Iterable[str] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Describe current leaseability without mutating queue state."""
    current = _now() if now is None else float(now)
    ref_filter = {str(ref) for ref in refs} if refs is not None else None
    by_state: dict[str, int] = {}
    waitable_live = 0
    leaseable_now = 0
    failed_backoff_same_run = 0
    next_retry_epoch: float | None = None
    next_lease_expiry_epoch: float | None = None
    next_deadline_epoch: float | None = None
    for job in _load_jobs(execution_id):
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
            lease_expiry = float(job.get("leaseExpiresEpoch") or 0)
            if lease_expiry and lease_expiry <= current:
                leaseable_now += 1
            elif lease_expiry:
                next_lease_expiry_epoch = min(
                    value for value in (next_lease_expiry_epoch, lease_expiry) if value is not None
                )
            deadline = float(job.get("deadlineEpoch") or 0)
            if deadline:
                next_deadline_epoch = min(
                    value for value in (next_deadline_epoch, deadline) if value is not None
                )
            continue
        if state != STATE_FAILED or not bool(job.get("sameRunRetryable", True)):
            continue
        waitable_live += 1
        not_before = float(job.get("notBeforeEpoch") or 0)
        if not_before <= current:
            leaseable_now += 1
        else:
            failed_backoff_same_run += 1
            next_retry_epoch = min(
                value for value in (next_retry_epoch, not_before) if value is not None
            )
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
