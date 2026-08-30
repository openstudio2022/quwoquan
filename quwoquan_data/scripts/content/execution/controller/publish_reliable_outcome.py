"""Freeze ReliableTask publish success and typed per-object exclusions."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from core.control_types import ExecutionStage, QueueJobState, StageStatus

from content.execution.closure.publish_outcome import (
    PUBLISH_JOB_FAILED,
    PUBLISH_PREPARATION_FAILED,
    normalize_publish_discards,
    publish_discard,
)
from content.execution.queue.model import QueueJob
from content.execution.support import (
    AUTO,
    DataIssueCode,
    DataRecoveryAction,
    ExecutionContext,
    StageResult,
    stage_issues,
)


def close_reliable_publish(
    ctx: ExecutionContext,
    reliable_jobs: Sequence[QueueJob],
    *,
    homepage_only: bool,
    homepage_refs: set[str],
    qualified_post_refs: set[str] | None,
    initial_discards: Iterable[Mapping[str, object]],
) -> tuple[StageResult | None, list[dict[str, object]]]:
    """Return a stage result only while waiting or when zero objects succeeded."""

    terminal_failures = [
        job
        for job in reliable_jobs
        if job.state in {QueueJobState.DEAD, QueueJobState.BLOCKED}
    ]
    pending_jobs = [
        job
        for job in reliable_jobs
        if job.state
        not in {
            QueueJobState.SUCCEEDED,
            QueueJobState.DEAD,
            QueueJobState.BLOCKED,
        }
    ]
    if pending_jobs:
        return (
            StageResult(
                ExecutionStage.PUBLISH,
                AUTO,
                StageStatus.WAITING,
                f"等待 ReliableTask 完成 {len(pending_jobs)} 个 canonical object transaction",
                checkpoint_hint=(
                    "Mongo+Redis ReliableTask worker 正在执行对象事务；"
                    "全部 publish job 写入 applied evidence 后，以同一 executionId resume"
                ),
            ),
            [dict(row) for row in initial_discards],
        )
    successful_jobs = [
        job for job in reliable_jobs if job.state is QueueJobState.SUCCEEDED
    ]
    planned_refs = {str(job.ref) for job in reliable_jobs}
    expected_refs = (
        set(homepage_refs)
        if homepage_only
        else {
            str(ref).removeprefix("posts/")
            for ref in (qualified_post_refs or set())
        }
    )
    if not homepage_only:
        planned_refs = {
            str(job.content_object_dir or "").removeprefix("posts/")
            for job in reliable_jobs
        }
    discards = [dict(row) for row in initial_discards]
    discards.extend(
        publish_discard(object_ref, issue=PUBLISH_PREPARATION_FAILED)
        for object_ref in sorted(expected_refs - planned_refs)
    )
    for job in terminal_failures:
        object_ref = (
            str(job.ref)
            if homepage_only
            else str(job.content_object_dir or "").removeprefix("posts/")
        )
        discards.append(publish_discard(object_ref, issue=PUBLISH_JOB_FAILED))
    normalized = normalize_publish_discards(discards)
    if not successful_jobs:
        return (
            StageResult(
                ExecutionStage.PUBLISH,
                AUTO,
                StageStatus.FAILED,
                "ReliableTask publish finalized zero canonical objects",
                # RETRY_DELIVERY 的语义是重投同一批已评审对象。回退到 post_review
                # 会清掉已 approved 的评审证据、迫使 reviewer 重跑并耗尽它的
                # attempt 预算，最终把 publish 的真实失败伪装成 REVIEW_INVALID。
                fallback_stage=(
                    ExecutionStage.BUILD_VALIDATE
                    if homepage_only
                    else ExecutionStage.PUBLISH
                ),
                issue_records=stage_issues(
                    ExecutionStage.PUBLISH,
                    [issue for row in normalized for issue in row["issues"]],
                    code=DataIssueCode.QUALITY_FAILED,
                    recovery=DataRecoveryAction.RETRY_DELIVERY,
                ),
            ),
            normalized,
        )
    from content.execution.workspace import write_publish_ref

    if homepage_only:
        write_publish_ref(
            ctx.execution_id,
            entity_refs=[
                str(job.ref).removeprefix("/entity/") for job in successful_jobs
            ],
            publish_discards=normalized,
        )
    else:
        write_publish_ref(
            ctx.execution_id,
            post_refs=[
                str(job.content_object_dir or "").removeprefix("posts/")
                for job in successful_jobs
            ],
            publish_discards=normalized,
        )
    return None, normalized


__all__ = ["close_reliable_publish"]
