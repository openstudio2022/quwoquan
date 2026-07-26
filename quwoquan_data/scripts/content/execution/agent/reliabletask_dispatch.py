"""Dispatch declared ReliableTask jobs through the service-owned fleet."""
from __future__ import annotations

from dataclasses import dataclass

from core.control_types import (
    ExecutionStage,
    QueueBackend,
    QueueFailureKind,
    QueueJobStage,
    QueueJobState,
    ReliableTaskDispatchStatus,
)
from core.data_issue import (
    DataIssue,
    DataIssueCode,
    DataIssueStage,
    DataRecoveryAction,
)
from content.execution.context import ExecutionContext
from content.execution.queue.core import _load_jobs
from content.execution.queue.model import QueueJob
from content.execution.queue.runtime import record_reliabletask_failure
from content.execution.reliabletask_jobs import uses_reliabletask


_CHECKPOINT_QUEUE_STAGE = {
    ExecutionStage.BUILD_HOMEPAGE: QueueJobStage.AUTHOR,
    ExecutionStage.POST_AUTHOR: QueueJobStage.AUTHOR,
    ExecutionStage.PUBLISH: QueueJobStage.PUBLISH,
}


@dataclass(frozen=True, slots=True)
class ReliableTaskDispatchResult:
    stage: ExecutionStage
    queue_stage: QueueJobStage
    status: ReliableTaskDispatchStatus
    attempted_count: int
    completed_count: int
    issues: tuple[DataIssue, ...] = ()

    @property
    def can_continue(self) -> bool:
        return self.status is ReliableTaskDispatchStatus.COMPLETED


def _queue_stage_for(stage: ExecutionStage) -> QueueJobStage | None:
    return _CHECKPOINT_QUEUE_STAGE.get(stage)


def _failure_recovery(queue_stage: QueueJobStage) -> DataRecoveryAction:
    return (
        DataRecoveryAction.RETRY_AGENT
        if queue_stage is QueueJobStage.AUTHOR
        else DataRecoveryAction.STOP
    )


def _remaining_jobs(
    execution_id: str,
    queue_stage: QueueJobStage,
) -> tuple[QueueJob, ...]:
    return tuple(
        job
        for job in _load_jobs(execution_id)
        if job.backend is QueueBackend.RELIABLE_TASK
        and job.stage is queue_stage
        and job.state is not QueueJobState.SUCCEEDED
    )


def _declared_jobs(
    execution_id: str,
    queue_stage: QueueJobStage,
) -> tuple[QueueJob, ...]:
    return tuple(
        job
        for job in _load_jobs(execution_id)
        if job.backend is QueueBackend.RELIABLE_TASK
        and job.stage is queue_stage
    )


def _contract_issue(stage: ExecutionStage, message: str) -> DataIssue:
    return DataIssue(
        code=DataIssueCode.CONTRACT_INVALID,
        stage=DataIssueStage(stage.value),
        message=message,
        recovery=DataRecoveryAction.STOP,
    )


def _project_fleet_outcomes(
    execution_id: str,
    stage: ExecutionStage,
    queue_stage: QueueJobStage,
    *,
    outcomes: tuple[object, ...],
) -> tuple[DataIssue, ...]:
    jobs = {job.job_id: job for job in _declared_jobs(execution_id, queue_stage)}
    outcome_ids = {str(getattr(outcome, "job_id", "")) for outcome in outcomes}
    if outcome_ids != set(jobs):
        return (_contract_issue(stage, "ReliableTask fleet receipt does not match declared jobs"),)
    issues: list[DataIssue] = []
    for outcome in outcomes:
        job_id = str(getattr(outcome, "job_id", ""))
        status = str(getattr(outcome, "status", ""))
        job = jobs[job_id]
        if status == "succeeded":
            if job.job_id in {item.job_id for item in _remaining_jobs(execution_id, queue_stage)}:
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
        issue = job.issue(
            QueueFailureKind.EXECUTION,
            message="ReliableTask fleet exhausted the job retry policy",
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


def _dispatch_fleet(
    ctx: ExecutionContext,
    stage: ExecutionStage,
    queue_stage: QueueJobStage,
) -> ReliableTaskDispatchResult:
    from core.runtime_policy import active_runtime_policy
    from content.execution.reliabletask_fleet import run_reliabletask_fleet

    policy = active_runtime_policy()
    try:
        report = run_reliabletask_fleet(
            ctx.execution_id,
            queue_stage,
            workers=ctx.max_workers,
            completion_grace_seconds=policy.managed_future_grace_seconds,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        issue = DataIssue(
            code=DataIssueCode.ENVIRONMENT_NOT_READY,
            stage=DataIssueStage(stage.value),
            message=f"ReliableTask fleet unavailable: {type(exc).__name__}: {exc}",
            recovery=DataRecoveryAction.STOP,
        )
        return ReliableTaskDispatchResult(
            stage=stage,
            queue_stage=queue_stage,
            status=ReliableTaskDispatchStatus.BLOCKED,
            attempted_count=0,
            completed_count=0,
            issues=(issue,),
        )
    issues = _project_fleet_outcomes(
        ctx.execution_id,
        stage,
        queue_stage,
        outcomes=report.outcomes,
    )
    remaining = _remaining_jobs(ctx.execution_id, queue_stage)
    terminal = any(
        job.state in {QueueJobState.BLOCKED, QueueJobState.DEAD} for job in remaining
    )
    return ReliableTaskDispatchResult(
        stage=stage,
        queue_stage=queue_stage,
        status=(
            ReliableTaskDispatchStatus.BLOCKED
            if terminal or issues
            else ReliableTaskDispatchStatus.COMPLETED
            if not remaining
            else ReliableTaskDispatchStatus.WAITING
        ),
        attempted_count=sum(int(getattr(outcome, "attempts", 0)) for outcome in report.outcomes),
        completed_count=sum(
            1 for outcome in report.outcomes if getattr(outcome, "status", "") == "succeeded"
        ),
        issues=issues,
    )


def dispatch_reliabletask_checkpoint(
    ctx: ExecutionContext,
    stage: ExecutionStage,
) -> ReliableTaskDispatchResult | None:
    """Run the current checkpoint through the sole service-owned executor."""
    if not uses_reliabletask(ctx):
        return None
    queue_stage = _queue_stage_for(stage)
    if queue_stage is None:
        return None
    declared = _declared_jobs(ctx.execution_id, queue_stage)
    if not declared or all(job.state is QueueJobState.SUCCEEDED for job in declared):
        return None
    return _dispatch_fleet(ctx, stage, queue_stage)


__all__ = [
    "ReliableTaskDispatchResult",
    "dispatch_reliabletask_checkpoint",
]
