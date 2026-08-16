"""Outcome projections for ReliableTask dispatch."""

from __future__ import annotations

from content.execution.agent.reliabletask_dispatch import (
    DataIssue,
    ExecutionStage,
    QueueFailureKind,
    QueueJob,
    QueueJobStage,
    QueueJobState,
    _contract_issue,
    _declared_jobs,
    _failure_recovery,
    _read_job,
    record_reliabletask_failure,
    record_reliabletask_stale_terminal_outcome,
)


def _project_local_success_evidence(job: QueueJob) -> bool:
    """Recover a remote success only from the exact local completion envelope."""
    refreshed = _read_job(job.execution_id, job.job_id)
    if refreshed.state is QueueJobState.SUCCEEDED:
        return True
    if refreshed.stage is not QueueJobStage.AUTHOR or not refreshed.content_object_dir:
        return False

    from core.paths import OUTPUT_ROOT

    from content.execution.queue.reliabletask.projection import (
        record_reliabletask_completion,
    )
    from content.execution.workspace import execution_root

    envelope = (
        execution_root(refreshed.execution_id)
        / refreshed.content_object_dir
        / "4.draft"
        / "agent_result_envelope.json"
    )
    if not envelope.is_file():
        return False
    from content.execution.queue.reliabletask.author import (
        author_envelope_requires_reauthoring,
    )

    if author_envelope_requires_reauthoring(refreshed, envelope):
        return False
    record_reliabletask_completion(
        refreshed.execution_id,
        refreshed.job_id,
        evidence_path=envelope,
        evidence_root=OUTPUT_ROOT,
        envelope_workspace_root=envelope.parent,
    )
    return True


def _project_fleet_outcomes(
    execution_id: str,
    stage: ExecutionStage,
    queue_stage: QueueJobStage,
    *,
    expected_job_ids: frozenset[str],
    outcomes: tuple[object, ...],
) -> tuple[DataIssue, ...]:
    jobs = {job.job_id: job for job in _declared_jobs(execution_id, queue_stage)}
    outcome_ids = {str(getattr(outcome, "job_id", "")) for outcome in outcomes}
    if outcome_ids != expected_job_ids or not outcome_ids.issubset(jobs):
        return (
            _contract_issue(
                stage,
                "ReliableTask fleet receipt does not match dispatched jobs",
            ),
        )
    issues: list[DataIssue] = []
    for outcome in outcomes:
        job_id = str(getattr(outcome, "job_id", ""))
        status = str(getattr(outcome, "status", ""))
        job = jobs[job_id]
        if job.state is QueueJobState.SUCCEEDED and status == "dead":
            record_reliabletask_stale_terminal_outcome(
                execution_id,
                job_id,
                attempts=int(getattr(outcome, "attempts", 0)),
                failure_code=str(getattr(outcome, "failure_code", "")).strip(),
            )
            continue
        if status == "succeeded":
            # Local SUCCEEDED is written only after the worker validates and
            # binds the exact result envelope. A later fleet receipt is merely
            # transport acknowledgement; re-reading mutable draft files here
            # can falsely invalidate already-admitted completion after the
            # controller advances into review/repair.
            if job.state is QueueJobState.SUCCEEDED:
                continue
            try:
                projected = _project_local_success_evidence(job)
            except (OSError, TypeError, ValueError) as exc:
                issues.append(
                    _contract_issue(
                        stage,
                        "ReliableTask local completion evidence is invalid: "
                        f"{type(exc).__name__}: {exc}",
                    )
                )
                continue
            if not projected:
                issues.append(
                    _contract_issue(
                        stage,
                        "ReliableTask success receipt lacks local completion evidence",
                    )
                )
            continue
        if status != "dead":
            # A fleet may return after its derived batch budget with valid
            # ready/processing jobs still owned by Mongo+Redis. The next
            # controller resume must continue that durable queue, not turn a
            # recoverable wait into a false terminal failure.
            continue
        failure_code = str(getattr(outcome, "failure_code", "")).strip()
        failure_detail = f" (failureCode={failure_code})" if failure_code else ""
        issue = job.issue(
            QueueFailureKind.EXECUTION,
            message=(
                f"ReliableTask fleet exhausted the job retry policy{failure_detail}"
            ),
            recovery=_failure_recovery(queue_stage),
        )
        record_reliabletask_failure(
            execution_id,
            job_id,
            attempts=int(getattr(outcome, "attempts", 0)),
            issue=issue,
        )
        issues.append(issue)
    return tuple(issues)
