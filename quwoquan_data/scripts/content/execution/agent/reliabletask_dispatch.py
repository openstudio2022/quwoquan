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
from content.execution.queue.backend import ReliableTaskJobSetCollisionError
from content.execution.queue.core import _load_jobs, _read_job
from content.execution.queue.model import QueueJob
from content.execution.queue.reliabletask.jobs import uses_reliabletask
from content.execution.queue.reliabletask.projection import (
    record_reliabletask_failure,
    record_reliabletask_stale_terminal_outcome,
)
from content.execution.queue.runtime import DISCARDED_ISSUE_CODES

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


def _terminal_partial_closure_ready(
    ctx: ExecutionContext,
    stage: ExecutionStage,
    queue_stage: QueueJobStage,
) -> bool:
    """Return whether resume can reuse a non-empty terminal object closure."""

    if _delivered_count(ctx, stage, queue_stage) <= 0:
        return False
    declared = _declared_jobs(ctx.execution_id, queue_stage)
    return bool(declared) and all(
        job.state is QueueJobState.SUCCEEDED
        or (
            job.state in _TERMINAL_JOB_STATES
            and job.last_issue is not None
            and job.last_issue.code in DISCARDED_ISSUE_CODES
        )
        for job in declared
    )


def _delivered_count(
    ctx: ExecutionContext,
    stage: ExecutionStage,
    queue_stage: QueueJobStage,
) -> int:
    """本阶段已交付的达标对象数。

    主页创作的交付真相是磁盘上的三件套与采纳门结论，队列作业状态只是调度账本：
    作业可能因超时或信封校验被判终态，而对象已由 finalize 正常落盘。两者一旦分叉
    必须以采纳门为准，否则批次会在实际已达标时被账本误判为供给不足。
    """
    if stage is ExecutionStage.BUILD_HOMEPAGE:
        from content.execution.controller.homepage_authoring import (
            homepage_quota_verdict,
        )

        return homepage_quota_verdict(ctx).qualified_count
    return _succeeded_count(ctx.execution_id, queue_stage)


def _quota_reached(
    ctx: ExecutionContext,
    stage: ExecutionStage,
    queue_stage: QueueJobStage,
) -> bool:
    from content.execution.spec_contract import approved_quota

    return _delivered_count(ctx, stage, queue_stage) >= approved_quota(ctx.execution_id)


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
                "ReliableTask fleet exhausted the job retry policy"
                f"{failure_detail}"
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


def _dispatch_fleet(
    ctx: ExecutionContext,
    stage: ExecutionStage,
    queue_stage: QueueJobStage,
) -> ReliableTaskDispatchResult:
    from core.runtime_policy import active_runtime_policy

    from content.execution.queue.reliabletask.fleet import run_reliabletask_fleet

    # The worker may finish between dispatch_reliabletask_checkpoint's first
    # quota check and this function. Re-read durable delivery before asking the
    # fleet for pending jobs, otherwise a successful final job is misreported
    # as infrastructure unavailable because the pending set is now empty.
    if _quota_reached(ctx, stage, queue_stage) or _terminal_partial_closure_ready(
        ctx,
        stage,
        queue_stage,
    ):
        return ReliableTaskDispatchResult(
            stage=stage,
            queue_stage=queue_stage,
            status=ReliableTaskDispatchStatus.COMPLETED,
            attempted_count=0,
            completed_count=_delivered_count(ctx, stage, queue_stage),
        )
    remaining_jobs = _remaining_jobs(ctx.execution_id, queue_stage)
    active_jobs = tuple(
        job for job in remaining_jobs if job.state not in _TERMINAL_JOB_STATES
    )
    if not active_jobs:
        if not remaining_jobs:
            return ReliableTaskDispatchResult(
                stage=stage,
                queue_stage=queue_stage,
                status=ReliableTaskDispatchStatus.COMPLETED,
                attempted_count=0,
                completed_count=_delivered_count(ctx, stage, queue_stage),
            )
        terminal_issues = tuple(
            job.last_issue
            or _contract_issue(
                stage,
                f"ReliableTask terminal job lacks typed failure evidence: {job.job_id}",
            )
            for job in remaining_jobs
        )
        discarded = tuple(
            issue
            for issue in terminal_issues
            if issue.code in DISCARDED_ISSUE_CODES
        )
        blocking = tuple(
            issue
            for issue in terminal_issues
            if issue.code not in DISCARDED_ISSUE_CODES
        )
        if not blocking:
            # With zero delivered objects, an object-level discard is also the
            # lane blocker. Preserve its typed code/recovery/message verbatim;
            # replacing it with a synthetic "candidate pool exhausted" error
            # destroys the repair route (for example QUALITY_FAILED ->
            # rewind_compose for a mismatched article figure).
            blocking = terminal_issues
        return ReliableTaskDispatchResult(
            stage=stage,
            queue_stage=queue_stage,
            status=ReliableTaskDispatchStatus.BLOCKED,
            attempted_count=0,
            completed_count=_delivered_count(ctx, stage, queue_stage),
            issues=blocking,
            discarded=discarded,
        )
    policy = active_runtime_policy()
    expected_job_ids = frozenset(
        job.job_id
        for job in active_jobs
    )
    try:
        report = run_reliabletask_fleet(
            ctx.execution_id,
            queue_stage,
            workers=ctx.max_workers,
            completion_grace_seconds=policy.managed_future_grace_seconds,
        )
    except ReliableTaskJobSetCollisionError as exc:
        return ReliableTaskDispatchResult(
            stage=stage,
            queue_stage=queue_stage,
            status=ReliableTaskDispatchStatus.BLOCKED,
            attempted_count=0,
            completed_count=0,
            issues=(_contract_issue(stage, str(exc)),),
        )
    except (OSError, RuntimeError, ValueError) as exc:
        # A fleet invocation may finish the final object and then observe an
        # empty pending set while preparing its durable receipt. Re-read the
        # local acceptance truth before classifying that terminal race as an
        # infrastructure outage.
        post_fleet_jobs = _remaining_jobs(ctx.execution_id, queue_stage)
        if (
            _quota_reached(ctx, stage, queue_stage)
            or _terminal_partial_closure_ready(ctx, stage, queue_stage)
            or not post_fleet_jobs
            or (
                post_fleet_jobs
                and all(
                    job.state in _TERMINAL_JOB_STATES
                    for job in post_fleet_jobs
                )
            )
        ):
            return _dispatch_fleet(ctx, stage, queue_stage)
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
        expected_job_ids=expected_job_ids,
        outcomes=report.outcomes,
    )
    # 对象级质量失败由过采候选池吸收；批次级问题（receipt 与声明作业不一致、
    # fleet 不可用）不属于任何对象，永远不可被配额吸收。未知问题码按批次级处理，
    # 宁可阻断也不静默放行。
    discarded = tuple(issue for issue in issues if issue.code in DISCARDED_ISSUE_CODES)
    blocking = tuple(issue for issue in issues if issue.code not in DISCARDED_ISSUE_CODES)
    delivered = _delivered_count(ctx, stage, queue_stage)
    if queue_stage is QueueJobStage.PUBLISH:
        # Publish delivery may be proven by canonical objects even when resume
        # jobs are dead (idempotent re-apply). Prefer the fleet's finalized count
        # and commercial pass over the local succeeded-job ledger alone.
        delivered = max(delivered, int(report.finalized_object_count or 0))
    publish_quota_met = queue_stage is QueueJobStage.PUBLISH and bool(report.passed)
    quota_met = _quota_reached(ctx, stage, queue_stage) or publish_quota_met
    if blocking and not publish_quota_met:
        status = ReliableTaskDispatchStatus.BLOCKED
    elif quota_met:
        # 配额已交付即收工：过采出来的剩余候选继续跑只是纯浪费额度。
        status = ReliableTaskDispatchStatus.COMPLETED
        blocking = ()
    elif _active_jobs(ctx.execution_id, queue_stage):
        status = ReliableTaskDispatchStatus.WAITING
    elif delivered > 0:
        # The candidate pool is terminal, but a non-empty reviewed closure
        # exists. Quota is a scale milestone; publish every qualified object
        # and retain the remainder as typed discards.
        status = ReliableTaskDispatchStatus.COMPLETED
        blocking = ()
    else:
        # Only an empty qualified closure blocks the lane.
        status = ReliableTaskDispatchStatus.BLOCKED
        blocking = blocking or discarded
        if not blocking:
            blocking = (
                _contract_issue(
                    stage,
                    "ReliableTask terminal closure has no typed object outcome",
                ),
            )
    return ReliableTaskDispatchResult(
        stage=stage,
        queue_stage=queue_stage,
        status=status,
        attempted_count=sum(int(getattr(outcome, "attempts", 0)) for outcome in report.outcomes),
        completed_count=delivered,
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
    # 配额已交付即视为本 checkpoint 完成：剩余作业要么是终态丢弃对象，
    # 要么是过采冗余，再次派发只是重复消耗额度。
    if _quota_reached(ctx, stage, queue_stage) or _terminal_partial_closure_ready(
        ctx,
        stage,
        queue_stage,
    ):
        return None
    return _dispatch_fleet(ctx, stage, queue_stage)


__all__ = [
    "ReliableTaskDispatchResult",
    "dispatch_reliabletask_checkpoint",
]
