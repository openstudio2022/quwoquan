"""Typed queue recovery and stable failure fingerprint helpers."""
from __future__ import annotations

import hashlib
from typing import Iterable

from core.control_types import (
    QueueJobStage,
    QueueJobState,
    QueueTimelineEvent,
)
from core.data_issue import DataIssue, DataIssueCode
from content.execution import store
from content.execution.queue.core import (
    STATE_DEAD,
    STATE_FAILED,
    STATE_QUEUED,
    _load_jobs,
    _write_job,
)
from content.execution.queue.management import queue_summary
from content.execution.queue.model import QueueLease


def _queue_stage(value: QueueJobStage | str) -> QueueJobStage:
    try:
        return QueueJobStage(str(value))
    except ValueError as exc:
        raise ValueError(f"unsupported object queue stage: {value!r}") from exc


def revive_dead_startup_jobs(
    execution_id: str,
    *,
    refs: Iterable[str] | None = None,
    stage: QueueJobStage | str | None = None,
) -> dict[str, object]:
    """Retry only jobs whose typed failure kind is startup."""
    queue_stage = _queue_stage(stage) if stage is not None else None
    ref_filter = {str(ref) for ref in refs} if refs is not None else None
    revived: list[str] = []
    for job in _load_jobs(execution_id):
        if job.state not in (STATE_DEAD, STATE_FAILED):
            continue
        if queue_stage is not None and job.stage is not queue_stage:
            continue
        if ref_filter is not None and job.ref not in ref_filter:
            continue
        if (
            job.last_issue is None
            or job.last_issue.code is not DataIssueCode.QUEUE_STARTUP_FAILED
        ):
            continue
        queued = job.with_timing(
            QueueTimelineEvent.REVIVED,
            at=store.now_iso(),
            attributes={"reason": "startup_failure_retry"},
            state=STATE_QUEUED,
            lease=QueueLease(),
            not_before_epoch=0.0,
            same_run_retryable=True,
            startup_failure_count=0,
            last_issue=None,
            failure_fingerprints=(),
            stuck_detected=False,
        )
        _write_job(queued)
        revived.append(queued.ref)
    return {"revived": sorted(revived), "summary": queue_summary(execution_id)}


def issues_fingerprint(issues: Iterable[DataIssue]) -> str:
    """Fingerprint stable issue identity, never parse human-facing messages."""
    normalized = sorted(
        {
            "|".join(
                (
                    issue.code.value,
                    issue.stage.value,
                    issue.ref,
                    issue.recovery.value,
                    ";".join(f"{key}={value}" for key, value in issue.attributes),
                )
            )
            for issue in issues
        }
    )
    return hashlib.sha1("\u0000".join(normalized).encode("utf-8")).hexdigest()[:16]


__all__ = ["issues_fingerprint", "revive_dead_startup_jobs"]
