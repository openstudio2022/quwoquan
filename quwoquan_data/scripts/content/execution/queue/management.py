"""Typed administrative queue transitions and immutable snapshots."""
from __future__ import annotations

from typing import Iterable

from core.control_types import (
    QueueFailureKind,
    QueueJobStage,
    QueueJobState,
    QueueTimelineEvent,
)
from core.data_issue import DataRecoveryAction
from content.execution import store
from content.execution.queue.core import (
    STATE_DEAD,
    STATE_FAILED,
    STATE_LEASED,
    STATE_QUEUED,
    _job_path,
    _load_jobs,
    _now,
    _read_job,
    _write_job,
    stable_job_id,
)
from content.execution.queue.model import QueueJob, QueueLease


def _queue_stage(value: QueueJobStage | str) -> QueueJobStage:
    try:
        return QueueJobStage(str(value))
    except ValueError as exc:
        raise ValueError(f"unsupported object queue stage: {value!r}") from exc


def dead_jobs(execution_id: str) -> list[dict[str, object]]:
    """Return presentation projections of jobs requiring operator action."""
    return [
        {
            "jobId": job.job_id,
            "ref": job.ref,
            "stage": job.stage.value,
            "attempt": job.attempt,
            "lastIssue": job.last_issue.as_dict() if job.last_issue else None,
        }
        for job in _load_jobs(execution_id)
        if job.state is STATE_DEAD
    ]


def block_job(execution_id: str, job_id: str, *, reason: str) -> QueueJob:
    job = _read_job(execution_id, job_id)
    issue = job.issue(
        kind=QueueFailureKind.GOVERNANCE,
        message=reason,
        recovery=DataRecoveryAction.STOP,
    )
    blocked = job.with_timing(
        QueueTimelineEvent.BLOCKED,
        at=store.now_iso(),
        attributes={"reason": reason},
        state=QueueJobState.BLOCKED,
        lease=QueueLease(),
        last_issue=issue,
    )
    _write_job(blocked)
    return blocked


def requeue_refs(
    execution_id: str,
    refs: Iterable[str],
    stage: QueueJobStage | str,
    *,
    reason: str,
) -> list[str]:
    """Explicit operator transition that resets a selected current execution job."""
    queue_stage = _queue_stage(stage)
    touched: list[str] = []
    for ref in refs:
        job_id = stable_job_id(execution_id, ref, queue_stage.value)
        path = _job_path(execution_id, job_id)
        if not path.is_file():
            continue
        job = _read_job(execution_id, job_id)
        requeued = job.with_timing(
            QueueTimelineEvent.REQUEUED,
            at=store.now_iso(),
            attributes={"reason": reason},
            state=STATE_QUEUED,
            lease=QueueLease(),
            not_before_epoch=0.0,
            same_run_retryable=True,
            startup_failure_count=0,
            last_issue=None,
            failure_fingerprints=(),
            stuck_detected=False,
        )
        _write_job(requeued)
        touched.append(job.ref)
    return touched


def purge_jobs(
    execution_id: str,
    *,
    stage: QueueJobStage | str | None = None,
    refs: Iterable[str] | None = None,
) -> dict[str, object]:
    """Delete derived jobs invalidated by a typed upstream reset."""
    queue_stage = _queue_stage(stage) if stage is not None else None
    ref_filter = {str(ref) for ref in refs} if refs is not None else None
    removed: list[str] = []
    for job in _load_jobs(execution_id):
        if queue_stage is not None and job.stage is not queue_stage:
            continue
        if ref_filter is not None and job.ref not in ref_filter:
            continue
        try:
            _job_path(execution_id, job.job_id).unlink()
        except FileNotFoundError:
            continue
        removed.append(job.ref)
    return {"removed": sorted(removed), "summary": queue_summary(execution_id)}


def queue_summary(execution_id: str) -> dict[str, object]:
    jobs = _load_jobs(execution_id)
    by_state: dict[str, list[str]] = {}
    by_backend: dict[str, int] = {}
    for job in jobs:
        by_state.setdefault(job.state.value, []).append(job.ref)
        by_backend[job.backend.value] = by_backend.get(job.backend.value, 0) + 1
    return {
        "total": len(jobs),
        "byState": {key: sorted(values) for key, values in sorted(by_state.items())},
        "byBackend": dict(sorted(by_backend.items())),
    }


def queue_runtime_snapshot(
    execution_id: str,
    *,
    stage: QueueJobStage | str | None = None,
    refs: Iterable[str] | None = None,
    now: float | None = None,
) -> dict[str, object]:
    """Describe leaseability from typed job state without mutating documents."""
    queue_stage = _queue_stage(stage) if stage is not None else None
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
        if queue_stage is not None and job.stage is not queue_stage:
            continue
        if ref_filter is not None and job.ref not in ref_filter:
            continue
        by_state[job.state.value] = by_state.get(job.state.value, 0) + 1
        if job.state is STATE_QUEUED:
            waitable_live += 1
            leaseable_now += 1
            continue
        if job.state is STATE_LEASED:
            waitable_live += 1
            if job.lease.expires_epoch and job.lease.expires_epoch <= current:
                leaseable_now += 1
            elif job.lease.expires_epoch:
                next_lease_expiry_epoch = min(
                    value
                    for value in (next_lease_expiry_epoch, job.lease.expires_epoch)
                    if value is not None
                )
            if job.lease.deadline_epoch:
                next_deadline_epoch = min(
                    value
                    for value in (next_deadline_epoch, job.lease.deadline_epoch)
                    if value is not None
                )
            continue
        if job.state is not STATE_FAILED or not job.same_run_retryable:
            continue
        waitable_live += 1
        if job.not_before_epoch <= current:
            leaseable_now += 1
        else:
            failed_backoff_same_run += 1
            next_retry_epoch = min(
                value for value in (next_retry_epoch, job.not_before_epoch) if value is not None
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
