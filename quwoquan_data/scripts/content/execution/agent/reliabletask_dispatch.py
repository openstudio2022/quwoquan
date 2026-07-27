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
from content.execution.queue.runtime import DISCARDED_ISSUE_CODES, record_reliabletask_failure
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
    discarded: tuple[DataIssue, ...] = ()

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


_TERMINAL_JOB_STATES = frozenset({QueueJobState.BLOCKED, QueueJobState.DEAD})


def _succeeded_count(execution_id: str, queue_stage: QueueJobStage) -> int:
    """跨轮次统计本阶段累计达标作业数；单轮 fleet receipt 不足以表达恢复后的进度。"""
    return sum(
        1
        for job in _declared_jobs(execution_id, queue_stage)
        if job.state is QueueJobState.SUCCEEDED
    )


def _active_jobs(
    execution_id: str,
    queue_stage: QueueJobStage,
) -> tuple[QueueJob, ...]:
    """仍可被下一轮 fleet 继续推进的作业；终态丢弃作业不在其中。"""
    return tuple(
        job
        for job in _remaining_jobs(execution_id, queue_stage)
        if job.state not in _TERMINAL_JOB_STATES
    )


def _quota_reached(execution_id: str, queue_stage: QueueJobStage) -> bool:
    from content.execution.spec_contract import approved_quota

    return _succeeded_count(execution_id, queue_stage) >= approved_quota(execution_id)


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
    # 对象级质量失败由过采候选池吸收；批次级问题（receipt 与声明作业不一致、
    # fleet 不可用）不属于任何对象，永远不可被配额吸收。未知问题码按批次级处理，
    # 宁可阻断也不静默放行。
    discarded = tuple(issue for issue in issues if issue.code in DISCARDED_ISSUE_CODES)
    blocking = tuple(issue for issue in issues if issue.code not in DISCARDED_ISSUE_CODES)
    active = _active_jobs(ctx.execution_id, queue_stage)
    if blocking:
        status = ReliableTaskDispatchStatus.BLOCKED
    elif active:
        status = ReliableTaskDispatchStatus.WAITING
    elif _quota_reached(ctx.execution_id, queue_stage):
        status = ReliableTaskDispatchStatus.COMPLETED
    else:
        # 候选池已全部终态但达标数不足配额：过采系数偏低或区域供给不足，
        # 必须让运行者看见，而不是继续空转。
        from content.execution.spec_contract import approved_quota

        status = ReliableTaskDispatchStatus.BLOCKED
        blocking = (
            _contract_issue(
                stage,
                f"候选池耗尽但未达准出配额："
                f"达标 {_succeeded_count(ctx.execution_id, queue_stage)}"
                f"/{approved_quota(ctx.execution_id)}，"
                f"丢弃 {len(discarded)}；需提高 oversampleFactor 或扩充区域实体供给",
            ),
        )
    return ReliableTaskDispatchResult(
        stage=stage,
        queue_stage=queue_stage,
        status=status,
        attempted_count=sum(int(getattr(outcome, "attempts", 0)) for outcome in report.outcomes),
        completed_count=_succeeded_count(ctx.execution_id, queue_stage),
        issues=blocking,
        discarded=discarded,
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
    if not declared:
        return None
    # 已达配额且无可推进作业时本 checkpoint 即完成：剩余作业都是终态丢弃对象，
    # 再次派发只会让批次重新撞上同一批不达标对象。
    if not _active_jobs(ctx.execution_id, queue_stage) and _quota_reached(
        ctx.execution_id, queue_stage
    ):
        return None
    return _dispatch_fleet(ctx, stage, queue_stage)


__all__ = [
    "ReliableTaskDispatchResult",
    "dispatch_reliabletask_checkpoint",
]
