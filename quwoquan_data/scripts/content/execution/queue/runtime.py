"""Typed object-queue runtime state machine, leases, failures, and recovery."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Iterable, Mapping

from core import ops_governance as og
from core.control_types import (
    QueueFailureKind,
    QueueJobStage,
    QueueJobState,
    QueueTimelineEvent,
)
from core.data_issue import DataIssue, DataIssueCode, DataRecoveryAction
from core.io import read_json
from content.execution import production_contracts as pc
from content.execution import store
from content.execution.queue.core import (
    DEFAULT_LEASE_TTL_SECONDS,
    STATE_BLOCKED,
    STATE_DEAD,
    STATE_FAILED,
    STATE_LEASED,
    STATE_QUEUED,
    STATE_SUCCEEDED,
    _active_mutex_keys,
    _backoff_seconds,
    _emit_notification,
    _envelope_governance_issues,
    _job_governance_issues,
    _job_path,
    _load_jobs,
    _now,
    _queue_lock,
    _read_job,
    _write_job,
    stable_job_id,
)
from content.execution.queue.completion import author_completion_issues
from content.execution.queue.model import QueueJob, QueueLease
from content.execution.queue.jobs import enqueue_ref_job
from content.execution.queue.recovery import (
    issues_fingerprint,
    revive_dead_startup_jobs,
)


def _clock_now() -> float:
    return _now()


def _queue_stage(value: QueueJobStage | str) -> QueueJobStage:
    try:
        return QueueJobStage(str(value))
    except ValueError as exc:
        raise ValueError(f"unsupported object queue stage: {value!r}") from exc


def _failure_category(issue: DataIssue) -> str:
    return {
        DataRecoveryAction.MANUAL_REVIEW: og.FAILURE_MANUAL_REVIEW,
        DataRecoveryAction.STOP: og.FAILURE_GATE_BLOCK,
        DataRecoveryAction.RETRY_SOURCE_DISCOVERY: og.FAILURE_DATA_RETRY,
        DataRecoveryAction.REPLACE_SOURCE: og.FAILURE_DATA_RETRY,
        DataRecoveryAction.REPLACE_MEDIA: og.FAILURE_DATA_RETRY,
        DataRecoveryAction.REWIND_DOWNLOAD: og.FAILURE_DATA_RETRY,
        DataRecoveryAction.REWIND_COMPOSE: og.FAILURE_QUALITY_REPAIR,
        DataRecoveryAction.RETRY_AGENT: og.FAILURE_DATA_RETRY,
    }[issue.recovery]


def _record_failure(job: QueueJob, issue: DataIssue) -> None:
    og.append_failure(
        job.execution_id,
        ref=job.ref,
        stage=job.stage.value,
        reason=issue.message,
        category=_failure_category(issue),
        owner=job.owner,
    )


def acquire_lease(
    execution_id: str,
    *,
    worker: str,
    stage: QueueJobStage | str | None = None,
    ref: str | None = None,
    ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
) -> QueueJob | None:
    """Lease one eligible typed job while respecting mutex and backoff state."""
    queue_stage = _queue_stage(stage) if stage is not None else None
    with _queue_lock(execution_id):
        now = _clock_now()
        jobs = _load_jobs(execution_id)
        active_mutexes = _active_mutex_keys(jobs, now)
        for job in jobs:
            if queue_stage is not None and job.stage is not queue_stage:
                continue
            if ref is not None and job.ref != ref:
                continue
            lease_expired = job.state is STATE_LEASED and job.lease.is_expired(now)
            if job.state not in (STATE_QUEUED, STATE_FAILED) and not lease_expired:
                continue
            if job.state is STATE_FAILED and not job.same_run_retryable:
                continue
            if job.not_before_epoch > now:
                continue
            governance_issues = _job_governance_issues(job)
            if governance_issues:
                reason = "; ".join(governance_issues)
                issue = job.issue(
                    QueueFailureKind.GOVERNANCE,
                    message=reason,
                    recovery=DataRecoveryAction.STOP,
                )
                blocked = job.with_timing(
                    QueueTimelineEvent.BLOCKED,
                    at=store.now_iso(),
                    attributes={"issueCode": issue.code.value},
                    state=QueueJobState.BLOCKED,
                    lease=QueueLease(),
                    last_issue=issue,
                )
                _write_job(blocked)
                _record_failure(blocked, issue)
                continue
            if job.mutex_key in active_mutexes:
                continue
            holder = f"{worker}:{int(now)}"
            leased = job.with_timing(
                QueueTimelineEvent.LEASED,
                at=store.now_iso(),
                attributes={"worker": worker},
                state=STATE_LEASED,
                lease=QueueLease(
                    holder=holder,
                    expires_epoch=now + ttl_seconds,
                    deadline_epoch=now + job.max_wall_clock_seconds,
                ),
                attempt=job.attempt + 1,
            )
            _write_job(leased)
            return leased
    return None


def _load_owned(execution_id: str, job_id: str, lease: str) -> QueueJob:
    job = _read_job(execution_id, job_id)
    if job.lease.holder != lease:
        raise RuntimeError(
            f"lease mismatch for {job_id}: holder={job.lease.holder!r} caller={lease!r}"
        )
    return job


def renew_lease(
    execution_id: str,
    job_id: str,
    lease: str,
    *,
    ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
) -> QueueJob:
    job = _load_owned(execution_id, job_id, lease)
    renewed = replace(
        job,
        lease=replace(job.lease, expires_epoch=_clock_now() + ttl_seconds),
        updated_at=store.now_iso(),
    )
    _write_job(renewed)
    return renewed


def complete_job(execution_id: str, job_id: str, lease: str) -> QueueJob:
    job = _load_owned(execution_id, job_id, lease)
    if job.result_envelope_required and not job.result_envelope_ref:
        raise RuntimeError(f"result envelope required before completing job {job_id}")
    completion_issues = author_completion_issues(job)
    if completion_issues:
        return fail_job(
            execution_id,
            job_id,
            lease,
            issue=completion_issues[0],
            fingerprint=issues_fingerprint(completion_issues),
            same_run_retryable=True,
        )
    completed = job.with_timing(
        QueueTimelineEvent.SUCCEEDED,
        at=store.now_iso(),
        state=STATE_SUCCEEDED,
        lease=QueueLease(),
        not_before_epoch=0.0,
        same_run_retryable=False,
        last_issue=None,
    )
    _write_job(completed)
    return completed


def _stored_envelope_ref(envelope_path: Path, *, root: Path) -> str:
    try:
        return str(envelope_path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(envelope_path)


def complete_job_with_envelope(
    execution_id: str,
    job_id: str,
    lease: str,
    *,
    envelope_path: str | Path,
    workspace_root: str | Path | None = None,
) -> QueueJob:
    """Validate the adapter envelope, then transition through normal completion."""
    job = _load_owned(execution_id, job_id, lease)
    root = Path(workspace_root) if workspace_root is not None else store.execution_root(execution_id)
    path = Path(envelope_path)
    if not path.is_absolute():
        path = root / path
    try:
        envelope = read_json(path)
    except (OSError, ValueError) as exc:
        issue = job.issue(
            QueueFailureKind.RESULT_ENVELOPE,
            message=f"result envelope unreadable: {exc}",
            recovery=DataRecoveryAction.REWIND_COMPOSE,
        )
        return fail_job(execution_id, job_id, lease, issue=issue, fingerprint=issues_fingerprint((issue,)))
    if not isinstance(envelope, Mapping):
        issue = job.issue(
            QueueFailureKind.RESULT_ENVELOPE,
            message="result envelope must be an object",
            recovery=DataRecoveryAction.REWIND_COMPOSE,
        )
        return fail_job(execution_id, job_id, lease, issue=issue, fingerprint=issues_fingerprint((issue,)))
    errors = pc.validate_agent_result_envelope(envelope, workspace_root=root)
    errors.extend(pc.assert_envelope_matches_job(envelope, job.to_document()))
    errors.extend(_envelope_governance_issues(job, envelope))
    if errors:
        issue = job.issue(
            QueueFailureKind.RESULT_ENVELOPE,
            message="; ".join(str(error) for error in errors),
            recovery=DataRecoveryAction.REWIND_COMPOSE,
        )
        return fail_job(execution_id, job_id, lease, issue=issue, fingerprint=issues_fingerprint((issue,)))
    gate_verdicts = envelope.get("gates")
    if not isinstance(gate_verdicts, list):
        issue = job.issue(
            QueueFailureKind.RESULT_ENVELOPE,
            message="result envelope gates must be an array",
            recovery=DataRecoveryAction.REWIND_COMPOSE,
        )
        return fail_job(execution_id, job_id, lease, issue=issue, fingerprint=issues_fingerprint((issue,)))
    accepted = job.with_timing(
        QueueTimelineEvent.ENVELOPE_ACCEPTED,
        at=store.now_iso(),
        attributes={"envelope": _stored_envelope_ref(path, root=root)},
        result_envelope_ref=_stored_envelope_ref(path, root=root),
        gate_verdicts_json=json.dumps(gate_verdicts, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    )
    _write_job(accepted)
    return complete_job(execution_id, job_id, lease)


def record_reliabletask_completion(
    execution_id: str,
    job_id: str,
    *,
    evidence_path: str | Path,
    evidence_root: str | Path,
    envelope_workspace_root: str | Path | None = None,
) -> QueueJob:
    """Mirror a fenced Mongo task result into the local execution evidence view."""
    with _queue_lock(execution_id):
        job = _read_job(execution_id, job_id)
        if job.backend.value != "reliabletask":
            raise ValueError(
                f"external ReliableTask completion requires reliabletask backend: {job_id}"
            )
        if job.state is STATE_SUCCEEDED:
            return job
        root = Path(evidence_root)
        path = Path(evidence_path)
        if not path.is_absolute():
            path = root / path
        try:
            evidence = read_json(path)
        except (OSError, ValueError) as exc:
            raise ValueError(f"ReliableTask result evidence unreadable: {exc}") from exc
        if not isinstance(evidence, Mapping):
            raise ValueError("ReliableTask result evidence must be an object")
        gate_verdicts: list[object] = []
        agent_run_id = job.agent_run_id
        if job.stage is QueueJobStage.AUTHOR:
            workspace = (
                Path(envelope_workspace_root)
                if envelope_workspace_root is not None
                else path.parent
            )
            errors = pc.validate_agent_result_envelope(
                evidence,
                workspace_root=workspace,
            )
            errors.extend(pc.assert_envelope_matches_job(evidence, job.to_document()))
            errors.extend(_envelope_governance_issues(job, evidence))
            completion_issues = author_completion_issues(job)
            errors.extend(issue.message for issue in completion_issues)
            if errors:
                raise ValueError(
                    "ReliableTask AgentResultEnvelope invalid: " + "; ".join(errors)
                )
            raw_gates = evidence.get("gates")
            if not isinstance(raw_gates, list):
                raise ValueError("ReliableTask AgentResultEnvelope.gates must be an array")
            gate_verdicts = list(raw_gates)
            agent = evidence.get("agent")
            if isinstance(agent, Mapping):
                agent_run_id = str(agent.get("runId") or "").strip()
        elif job.stage is QueueJobStage.PUBLISH:
            if (
                evidence.get("schema") != "quwoquan_data.object_transaction_apply"
                or evidence.get("status") != "applied"
                or str(evidence.get("executionId") or "") != execution_id
            ):
                raise ValueError(
                    "ReliableTask publish completion requires bound applied transaction"
                )
        else:
            raise ValueError(
                f"ReliableTask external completion unsupported for {job.stage.value}"
            )
        stored_ref = _stored_envelope_ref(path, root=root)
        now = store.now_iso()
        accepted = job.with_timing(
            QueueTimelineEvent.ENVELOPE_ACCEPTED,
            at=now,
            attributes={"envelope": stored_ref, "source": "reliabletask"},
            result_envelope_ref=stored_ref,
            gate_verdicts_json=json.dumps(
                gate_verdicts,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            agent_run_id=agent_run_id,
        )
        completed = accepted.with_timing(
            QueueTimelineEvent.SUCCEEDED,
            at=store.now_iso(),
            attributes={"source": "reliabletask"},
            state=STATE_SUCCEEDED,
            lease=QueueLease(),
            not_before_epoch=0.0,
            same_run_retryable=False,
            last_issue=None,
        )
        _write_job(completed)
        return completed


def record_reliabletask_failure(
    execution_id: str,
    job_id: str,
    *,
    attempts: int,
    issue: DataIssue,
) -> QueueJob:
    """Project a terminal service-fleet failure into the execution queue."""
    if attempts < 1:
        raise ValueError("ReliableTask terminal failure requires positive attempts")
    with _queue_lock(execution_id):
        job = _read_job(execution_id, job_id)
        if job.backend.value != "reliabletask":
            raise ValueError(
                f"external ReliableTask failure requires reliabletask backend: {job_id}"
            )
        if job.state is STATE_SUCCEEDED:
            raise ValueError(
                f"ReliableTask terminal failure conflicts with completed job: {job_id}"
            )
        observed = replace(job, attempt=attempts, lease=QueueLease())
        failed = _apply_failure(
            observed,
            issue,
            fingerprint=issue.code.value,
        )
        _record_failure(failed, issue)
        _write_job(failed)
        return failed


def reconcile_completed_refs(
    execution_id: str,
    refs: Iterable[str],
    stage: QueueJobStage | str,
    *,
    reason: str,
) -> list[str]:
    """Align derived queue state with independently verified object completion."""
    queue_stage = _queue_stage(stage)
    touched: list[str] = []
    for ref in sorted({str(item).strip() for item in refs if str(item).strip()}):
        job_id = stable_job_id(execution_id, ref, queue_stage.value)
        path = _job_path(execution_id, job_id)
        if not path.is_file():
            continue
        job = _read_job(execution_id, job_id)
        if job.state is STATE_SUCCEEDED:
            continue
        completed = job.with_timing(
            QueueTimelineEvent.RECONCILED,
            at=store.now_iso(),
            attributes={"reason": reason},
            state=STATE_SUCCEEDED,
            lease=QueueLease(),
            not_before_epoch=0.0,
            same_run_retryable=False,
            last_issue=None,
        )
        _write_job(completed)
        touched.append(job.ref)
    return touched


def _with_failure_fingerprint(
    job: QueueJob,
    fingerprint: str | None,
) -> tuple[QueueJob, bool]:
    if not fingerprint:
        return job, False
    fingerprints = (*job.failure_fingerprints, fingerprint)[-job.stuck_threshold :]
    updated = replace(job, failure_fingerprints=fingerprints)
    is_stuck = len(fingerprints) >= updated.stuck_threshold and len(set(fingerprints)) == 1
    return updated, is_stuck


# 质量类失败直接丢弃：批次靠过采候选池补足配额，重试同一个不达标对象只会
# 空耗 worker。基础设施类失败（启动、超时）仍消耗 queueMaxAttempts 重试预算。
DISCARDED_ISSUE_CODES = frozenset(
    {
        DataIssueCode.QUEUE_EXECUTION_FAILED,
        DataIssueCode.QUEUE_RESULT_ENVELOPE_INVALID,
    }
)


def _apply_failure(
    job: QueueJob,
    issue: DataIssue,
    *,
    fingerprint: str | None = None,
    same_run_retryable: bool = True,
    startup_failure: bool = False,
) -> QueueJob:
    """Apply one typed failure transition and calculate retry/dead state."""
    now = _clock_now()
    startup_count = job.startup_failure_count + (1 if startup_failure else 0)
    discarded = not startup_failure and issue.code in DISCARDED_ISSUE_CODES
    candidate = replace(
        job,
        lease=QueueLease(),
        same_run_retryable=same_run_retryable and not discarded,
        startup_failure_count=startup_count,
        last_issue=issue,
    )
    candidate, stuck = _with_failure_fingerprint(candidate, fingerprint)
    exhausted = (
        startup_count >= candidate.max_startup_failures
        if startup_failure
        else candidate.attempt >= candidate.max_attempts
    )
    if stuck or exhausted or discarded:
        failed = candidate.with_timing(
            QueueTimelineEvent.FAILED,
            at=store.now_iso(),
            attributes={
                "issueCode": issue.code.value,
                "terminal": True,
                "disposition": "discarded" if discarded else "exhausted",
            },
            state=STATE_DEAD,
            not_before_epoch=0.0,
            stuck_detected=stuck,
        )
        if stuck:
            _emit_notification(
                failed.execution_id,
                {
                    "event": "stuck",
                    "ref": failed.ref,
                    "jobId": failed.job_id,
                    "fingerprint": fingerprint,
                    "stuckThreshold": failed.stuck_threshold,
                    "issue": issue.as_dict(),
                },
            )
        return failed
    return candidate.with_timing(
        QueueTimelineEvent.FAILED,
        at=store.now_iso(),
        attributes={
            "issueCode": issue.code.value,
            "terminal": False,
            "disposition": "retryable",
        },
        state=STATE_FAILED,
        not_before_epoch=now + _backoff_seconds(startup_count if startup_failure else candidate.attempt),
    )


def fail_job(
    execution_id: str,
    job_id: str,
    lease: str,
    *,
    issue: DataIssue,
    fingerprint: str | None = None,
    same_run_retryable: bool = True,
    startup_failure: bool = False,
) -> QueueJob:
    """Transition one leased job by a typed ``DataIssue``; text never drives flow."""
    job = _load_owned(execution_id, job_id, lease)
    failed = _apply_failure(
        job,
        issue,
        fingerprint=fingerprint,
        same_run_retryable=same_run_retryable,
        startup_failure=startup_failure,
    )
    _record_failure(failed, issue)
    _write_job(failed)
    return failed


def reap_jobs(execution_id: str) -> dict[str, list[str]]:
    """Recover expired leases or fail wall-clock timeouts using typed transitions."""
    now = _clock_now()
    timed_out: list[str] = []
    reclaimed: list[str] = []
    for job in _load_jobs(execution_id):
        if job.state is not STATE_LEASED:
            continue
        if job.lease.deadline_epoch and now > job.lease.deadline_epoch:
            issue = job.issue(
                QueueFailureKind.TIMEOUT,
                message="queue wall-clock deadline exceeded",
                recovery=DataRecoveryAction.REWIND_COMPOSE,
            )
            failed = _apply_failure(job, issue)
            _record_failure(failed, issue)
            _write_job(failed)
            timed_out.append(job.ref)
        elif job.lease.is_expired(now):
            reclaimed_job = job.with_timing(
                QueueTimelineEvent.RECLAIMED,
                at=store.now_iso(),
                attributes={"reason": "lease_expired"},
                state=STATE_QUEUED,
                lease=QueueLease(),
            )
            _write_job(reclaimed_job)
            reclaimed.append(job.ref)
    return {"timedOut": sorted(timed_out), "reclaimed": sorted(reclaimed)}


__all__ = [
    "acquire_lease",
    "complete_job",
    "complete_job_with_envelope",
    "enqueue_ref_job",
    "fail_job",
    "issues_fingerprint",
    "reap_jobs",
    "reconcile_completed_refs",
    "record_reliabletask_failure",
    "renew_lease",
    "revive_dead_startup_jobs",
]
