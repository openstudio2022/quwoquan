"""配额门在 fleet dispatch 层的判定：达标数满足配额即推进，丢弃对象不阻断批次。

批次准出的唯一下界是 ``executionPolicy.approvedQuota``。候选池按 oversampleFactor
过采，质量不达标对象直接丢弃、不重试。dispatch 层若仍按「任一作业终态失败即阻断」
判定，整批会停在 ``manual_required``，后续 build_validate / publish 永远到不了。
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path


DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
for path in (DATA_ROOT / "scripts", DATA_ROOT / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from content.execution.agent import reliabletask_dispatch  # noqa: E402
from content.execution.context import ExecutionContext  # noqa: E402
from content.execution.queue.core import _read_job, _write_job  # noqa: E402
from content.execution.queue.jobs import enqueue_ref_job  # noqa: E402
from content.execution.queue.model import QueueLease  # noqa: E402
from content.execution.queue.reliabletask.report import (  # noqa: E402
    ReliableTaskFleetOutcome,
    ReliableTaskFleetReport,
)
from content.execution.workspace import execution_root  # noqa: E402
from core.control_types import (  # noqa: E402
    ContentType,
    ExecutionStage,
    QueueBackend,
    QueueJobState,
    QueueTimelineEvent,
    ReliableTaskDispatchStatus,
    RuntimeEnvironment,
)
from support.execution_manifest_fixture import ExecutionFixtureBuilder  # noqa: E402


EXECUTION_ID = "20260727--travel-homepage-generate--test-region-q--pilot-902"
_NAMES = ("配额实体甲", "配额实体乙", "配额实体丙", "配额实体丁")


def _build(quota: int):
    shutil.rmtree(execution_root(EXECUTION_ID), ignore_errors=True)
    fixture = ExecutionFixtureBuilder(
        EXECUTION_ID,
        targets=tuple({"name": name, "entityType": "地点/景区"} for name in _NAMES),
        approved_quota=quota,
    )
    fixture.build()
    ctx = ExecutionContext(
        execution_id=EXECUTION_ID,
        entity_ids=_NAMES,
        spec=fixture.spec(),
        managed=True,
        runtime=RuntimeEnvironment.LOCAL,
    )
    jobs = []
    for index, name in enumerate(_NAMES):
        ref = f"/entity/地点/景区/{name}"
        jobs.append(
            enqueue_ref_job(
                EXECUTION_ID,
                ref,
                "author",
                mutex_key=ref,
                queue_backend=QueueBackend.RELIABLE_TASK,
                meta={
                    "contentType": ContentType.HOMEPAGE.value,
                    "carrier": ContentType.HOMEPAGE.value,
                    "entityRef": ref,
                    "sourceRevision": "sha256:" + (str(index) * 64),
                    "contentObjectDir": f"entities/地点/景区/{name}",
                },
            )
        )
    return ctx, jobs


def _deliver(monkeypatch, quota: int) -> dict[str, int]:
    """接管采纳门：磁盘上的达标对象数是本阶段准出的唯一真相源。

    返回可变计数器，创作跑批前为 0，fleet 跑过之后由用例设定真实落盘数。
    """
    from content.execution.controller import homepage_authoring

    delivered = {"qualified": 0}

    def verdict(_ctx):
        qualified = delivered["qualified"]
        return homepage_authoring.HomepageQuotaVerdict(
            approved_quota=quota,
            qualified_refs=tuple(f"地点/景区/{name}" for name in _NAMES[:qualified]),
            discarded={
                f"地点/景区/{name}": ("质量不达标",) for name in _NAMES[qualified:]
            },
        )

    monkeypatch.setattr(homepage_authoring, "homepage_quota_verdict", verdict)
    return delivered


def _settle(jobs, succeeded: int, delivered: dict[str, int] | None = None, finalized: int = 0):
    """前 ``succeeded`` 个作业成功，其余由 fleet 判死（质量不达标）。

    ``finalized`` 是本轮真正落盘的达标对象数，可以与账本成功数不同。
    """

    def run_fleet(_execution_id, _stage):
        if delivered is not None:
            delivered["qualified"] = finalized
        outcomes = []
        for index, job in enumerate(jobs):
            if index < succeeded:
                _write_job(
                    _read_job(EXECUTION_ID, job.job_id).with_timing(
                        QueueTimelineEvent.SUCCEEDED,
                        at="2026-07-27T00:00:00Z",
                        state=QueueJobState.SUCCEEDED,
                        lease=QueueLease(),
                    )
                )
                outcomes.append(
                    ReliableTaskFleetOutcome(
                        job_id=job.job_id, status="succeeded", attempts=1
                    )
                )
                continue
            outcomes.append(
                ReliableTaskFleetOutcome(
                    job_id=job.job_id,
                    status="dead",
                    attempts=job.max_attempts,
                    failure_code="RELIABLETASK.WORKER.handler_failed",
                )
            )
        return ReliableTaskFleetReport(
            total=len(jobs), succeeded=succeeded, outcomes=tuple(outcomes)
        )

    return run_fleet


def test_quota_met_with_discards__batch_advances__functional__local_contract(
    monkeypatch,
) -> None:
    """4 个候选中 3 个达标、1 个被丢弃，配额 3 → 批次必须继续推进。"""
    ctx, jobs = _build(quota=3)
    from content.execution.queue.reliabletask import fleet as reliabletask_fleet

    delivered = _deliver(monkeypatch, quota=3)
    monkeypatch.setattr(
        reliabletask_fleet,
        "run_reliabletask_fleet",
        _settle(jobs, succeeded=3, delivered=delivered, finalized=3),
    )
    result = reliabletask_dispatch.dispatch_reliabletask_checkpoint(
        ctx, ExecutionStage.BUILD_HOMEPAGE
    )

    assert result is not None
    assert result.status is ReliableTaskDispatchStatus.COMPLETED
    assert result.completed_count == 3
    # 被丢弃的对象独立记账，不得混入阻断问题
    assert len(result.discarded) == 1
    assert result.issues == ()
    assert _read_job(EXECUTION_ID, jobs[3].job_id).state is QueueJobState.DEAD
    shutil.rmtree(execution_root(EXECUTION_ID), ignore_errors=True)


def test_quota_met__resume_does_not_redispatch_discards__functional__local_contract(
    monkeypatch,
) -> None:
    """恢复时不得因残留丢弃对象重新派发，否则批次会反复撞上同一批不达标对象。"""
    ctx, jobs = _build(quota=3)
    from content.execution.queue.reliabletask import fleet as reliabletask_fleet

    delivered = _deliver(monkeypatch, quota=3)
    monkeypatch.setattr(
        reliabletask_fleet,
        "run_reliabletask_fleet",
        _settle(jobs, succeeded=3, delivered=delivered, finalized=3),
    )
    reliabletask_dispatch.dispatch_reliabletask_checkpoint(
        ctx, ExecutionStage.BUILD_HOMEPAGE
    )

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("已达配额后不应再次派发 fleet")

    monkeypatch.setattr(reliabletask_fleet, "run_reliabletask_fleet", fail_if_called)

    assert (
        reliabletask_dispatch.dispatch_reliabletask_checkpoint(
            ctx, ExecutionStage.BUILD_HOMEPAGE
        )
        is None
    )
    shutil.rmtree(execution_root(EXECUTION_ID), ignore_errors=True)


def test_final_job_completion_race_is_not_reported_as_fleet_unavailable(
    monkeypatch,
) -> None:
    """The last job can become durable after the outer quota check."""
    ctx, _jobs = _build(quota=1)
    from content.execution.queue.reliabletask import fleet as reliabletask_fleet

    checks = iter((False, True))
    monkeypatch.setattr(
        reliabletask_dispatch,
        "_quota_reached",
        lambda *_args: next(checks),
    )
    monkeypatch.setattr(
        reliabletask_dispatch,
        "_delivered_count",
        lambda *_args: 1,
    )
    monkeypatch.setattr(
        reliabletask_fleet,
        "run_reliabletask_fleet",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("durable quota must be re-read before fleet dispatch")
        ),
    )

    result = reliabletask_dispatch.dispatch_reliabletask_checkpoint(
        ctx,
        ExecutionStage.BUILD_HOMEPAGE,
    )

    assert result is not None
    assert result.status is ReliableTaskDispatchStatus.COMPLETED
    assert result.attempted_count == 0
    assert result.completed_count == 1
    shutil.rmtree(execution_root(EXECUTION_ID), ignore_errors=True)


def test_quota_short__candidate_pool_exhausted__publishes_partial__functional__local_contract(
    monkeypatch,
) -> None:
    """候选池耗尽但已有合格对象时必须 partial 准出，不能用配额误杀整 lane。"""
    ctx, jobs = _build(quota=3)
    from content.execution.queue.reliabletask import fleet as reliabletask_fleet

    delivered = _deliver(monkeypatch, quota=3)
    monkeypatch.setattr(
        reliabletask_fleet,
        "run_reliabletask_fleet",
        _settle(jobs, succeeded=2, delivered=delivered, finalized=2),
    )
    result = reliabletask_dispatch.dispatch_reliabletask_checkpoint(
        ctx, ExecutionStage.BUILD_HOMEPAGE
    )

    assert result is not None
    assert result.status is ReliableTaskDispatchStatus.COMPLETED
    assert result.completed_count == 2
    assert len(result.discarded) == 2
    assert result.issues == ()

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("partial closure resume must not redispatch terminal jobs")

    monkeypatch.setattr(reliabletask_fleet, "run_reliabletask_fleet", fail_if_called)
    assert (
        reliabletask_dispatch.dispatch_reliabletask_checkpoint(
            ctx, ExecutionStage.BUILD_HOMEPAGE
        )
        is None
    )
    shutil.rmtree(execution_root(EXECUTION_ID), ignore_errors=True)


def test_candidate_pool_exhausted__zero_qualified__blocks__functional__local_contract(
    monkeypatch,
) -> None:
    ctx, jobs = _build(quota=3)
    from content.execution.queue.reliabletask import fleet as reliabletask_fleet

    delivered = _deliver(monkeypatch, quota=3)
    monkeypatch.setattr(
        reliabletask_fleet,
        "run_reliabletask_fleet",
        _settle(jobs, succeeded=0, delivered=delivered, finalized=0),
    )

    result = reliabletask_dispatch.dispatch_reliabletask_checkpoint(
        ctx, ExecutionStage.BUILD_HOMEPAGE
    )

    assert result is not None
    assert result.status is ReliableTaskDispatchStatus.BLOCKED
    assert result.completed_count == 0
    assert any("无合格对象" in str(issue) for issue in result.issues)
    shutil.rmtree(execution_root(EXECUTION_ID), ignore_errors=True)


def test_acceptance_gate_outranks_queue_ledger__functional__local_contract(
    monkeypatch,
) -> None:
    """作业账本与磁盘产物分叉时以采纳门为准。

    作业可能因租约超时或信封校验被判终态，而 finalize 已把三件套正常落盘。
    若 dispatch 仍按账本的 SUCCEEDED 计数判配额，实际已达标的批次会被误判为
    供给不足而停在 manual_required——这正是 pilot-013 的真实停摆原因。
    """
    ctx, jobs = _build(quota=3)
    from content.execution.queue.reliabletask import fleet as reliabletask_fleet

    # 账本只认 1 个成功，磁盘上却有 4 个达标对象。
    delivered = _deliver(monkeypatch, quota=3)
    monkeypatch.setattr(
        reliabletask_fleet,
        "run_reliabletask_fleet",
        _settle(jobs, succeeded=1, delivered=delivered, finalized=4),
    )
    result = reliabletask_dispatch.dispatch_reliabletask_checkpoint(
        ctx, ExecutionStage.BUILD_HOMEPAGE
    )

    assert result is not None
    assert result.status is ReliableTaskDispatchStatus.COMPLETED
    assert result.completed_count == 4
    assert result.issues == ()
    shutil.rmtree(execution_root(EXECUTION_ID), ignore_errors=True)


def _build_publish(quota: int):
    shutil.rmtree(execution_root(EXECUTION_ID), ignore_errors=True)
    fixture = ExecutionFixtureBuilder(
        EXECUTION_ID,
        targets=tuple({"name": name, "entityType": "地点/景区"} for name in _NAMES),
        approved_quota=quota,
    )
    fixture.build()
    ctx = ExecutionContext(
        execution_id=EXECUTION_ID,
        entity_ids=_NAMES,
        spec=fixture.spec(),
        managed=True,
        runtime=RuntimeEnvironment.LOCAL,
    )
    jobs = []
    for index, name in enumerate(_NAMES):
        ref = f"/entity/地点/景区/{name}"
        jobs.append(
            enqueue_ref_job(
                EXECUTION_ID,
                ref,
                "publish",
                mutex_key=ref,
                queue_backend=QueueBackend.RELIABLE_TASK,
                meta={
                    "contentType": ContentType.HOMEPAGE.value,
                    "carrier": ContentType.HOMEPAGE.value,
                    "entityRef": ref,
                    "sourceRevision": "sha256:" + (str(index) * 64),
                    "contentObjectDir": f"entities/地点/景区/{name}",
                },
            )
        )
    return ctx, jobs


def _settle_publish(
    jobs,
    *,
    succeeded: int,
    passed: bool,
    finalized_object_count: int,
):
    def run_fleet(_execution_id, _stage):
        outcomes = []
        for index, job in enumerate(jobs):
            if index < succeeded:
                _write_job(
                    _read_job(EXECUTION_ID, job.job_id).with_timing(
                        QueueTimelineEvent.SUCCEEDED,
                        at="2026-07-27T00:00:00Z",
                        state=QueueJobState.SUCCEEDED,
                        lease=QueueLease(),
                    )
                )
                outcomes.append(
                    ReliableTaskFleetOutcome(
                        job_id=job.job_id, status="succeeded", attempts=1
                    )
                )
                continue
            outcomes.append(
                ReliableTaskFleetOutcome(
                    job_id=job.job_id,
                    status="dead",
                    attempts=job.max_attempts,
                    failure_code="RELIABLETASK.WORKER.handler_failed",
                )
            )
        return ReliableTaskFleetReport(
            total=len(jobs),
            succeeded=succeeded,
            outcomes=tuple(outcomes),
            passed=passed,
            finalized_object_count=finalized_object_count,
        )

    return run_fleet


def test_publish_finalized_quota_outranks_dead_jobs__functional__local_contract(
    monkeypatch,
) -> None:
    """Publish 幂等重放：作业全死但 finalizedObjectCount≥配额且 fleet.passed 时必须收工。"""
    ctx, jobs = _build_publish(quota=3)
    from content.execution.queue.reliabletask import fleet as reliabletask_fleet

    monkeypatch.setattr(
        reliabletask_fleet,
        "run_reliabletask_fleet",
        _settle_publish(
            jobs,
            succeeded=0,
            passed=True,
            finalized_object_count=5,
        ),
    )
    result = reliabletask_dispatch.dispatch_reliabletask_checkpoint(
        ctx, ExecutionStage.PUBLISH
    )

    assert result is not None
    assert result.status is ReliableTaskDispatchStatus.COMPLETED
    assert result.completed_count == 5
    assert result.issues == ()
    shutil.rmtree(execution_root(EXECUTION_ID), ignore_errors=True)
