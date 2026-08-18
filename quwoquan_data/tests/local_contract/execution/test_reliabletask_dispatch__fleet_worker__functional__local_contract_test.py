"""The controller delegates every ReliableTask job to the service fleet."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path
from types import SimpleNamespace


DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
for path in (DATA_ROOT / "scripts", DATA_ROOT / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from content.execution.agent import reliabletask_dispatch  # noqa: E402
from content.execution.agent.agent_checkpoint import _managed_author_ref  # noqa: E402
from content.execution.agent.outcome import AgentRunOutcome  # noqa: E402
from content.execution.context import ExecutionContext  # noqa: E402
from content.execution.queue.core import _read_job, _write_job  # noqa: E402
from content.execution.queue.jobs import enqueue_ref_job  # noqa: E402
from content.execution.queue.model import QueueLease  # noqa: E402
from content.execution.queue.reliabletask.fleet import (  # noqa: E402
    _has_audited_remote_recovery,
    fleet_batch_timeout_seconds,
)
from content.execution.queue.reliabletask.report import (  # noqa: E402
    ReliableTaskFleetOutcome,
    ReliableTaskFleetReport,
)
from content.execution.queue.reliabletask.worker import (  # noqa: E402
    _recover_completed_author_outcome,
)
from content.execution.workspace import execution_root  # noqa: E402
from content.execution.planning.recipe.model import _runtime_preflight_argv  # noqa: E402
from content.templates.registry import TemplateRegistry  # noqa: E402
from core.control_types import (  # noqa: E402
    AgentFailureKind,
    AgentProvider,
    ContentType,
    ExecutionStage,
    QueueBackend,
    QueueJobStage,
    QueueJobState,
    QueueTimelineEvent,
    ReliableTaskDispatchStatus,
    RuntimeEnvironment,
)
from governance.creators.assignment import creator_assignment_from_profile  # noqa: E402
from support.execution_manifest_fixture import ExecutionFixtureBuilder  # noqa: E402


EXECUTION_ID = "20260722--travel-homepage-generate--test-region-a--pilot-901"
OBJECT_REF = "/entity/地点/景区/测试实体甲"


def test_reliabletask_video_prompt_resolves_localized_content_ref() -> None:
    prompt = "- 内容 ref: `杭州西湖_video`\n- 主实体: `杭州西湖`"

    assert _managed_author_ref(prompt) == "杭州西湖_video"


def test_reliabletask_recovery__maps_controller_stage_to_queue_stage__contract__local_contract(
    monkeypatch,
) -> None:
    from content.execution import support

    monkeypatch.setattr(
        support,
        "load_execution_state",
        lambda _execution_id: SimpleNamespace(
            recovery_actions=[
                {
                    "stage": ExecutionStage.BUILD_HOMEPAGE.value,
                    "recoveredAt": "2026-07-27T00:00:00Z",
                }
            ]
        ),
    )

    assert _has_audited_remote_recovery(EXECUTION_ID, QueueJobStage.AUTHOR)
    assert not _has_audited_remote_recovery(EXECUTION_ID, QueueJobStage.PUBLISH)


def test_local_controller_delegates_declared_job_to_service_fleet(monkeypatch) -> None:
    shutil.rmtree(execution_root(EXECUTION_ID), ignore_errors=True)

    fixture = ExecutionFixtureBuilder(EXECUTION_ID)
    fixture.build()
    ctx = ExecutionContext(
        execution_id=EXECUTION_ID,
        entity_ids=("测试实体甲",),
        spec=fixture.spec(),
        managed=True,
        runtime=RuntimeEnvironment.LOCAL,
    )
    job = enqueue_ref_job(
        EXECUTION_ID,
        OBJECT_REF,
        "author",
        mutex_key=OBJECT_REF,
        queue_backend=QueueBackend.RELIABLE_TASK,
        meta={
            "contentType": ContentType.HOMEPAGE.value,
            "carrier": ContentType.HOMEPAGE.value,
            "entityRef": OBJECT_REF,
            "sourceRevision": "sha256:" + ("a" * 64),
            "contentObjectDir": "entities/地点/景区/测试实体甲",
        },
    )
    observed: list[tuple[str, str, int, int]] = []
    # 准出判定读采纳门（磁盘三件套），本用例只验证委派链路，故直接声明交付事实。
    from content.execution.controller import homepage_authoring

    delivered = {"qualified": 0}
    monkeypatch.setattr(
        homepage_authoring,
        "homepage_quota_verdict",
        lambda _ctx: homepage_authoring.HomepageQuotaVerdict(
            approved_quota=1,
            qualified_refs=(("地点/景区/测试实体甲",) if delivered["qualified"] else ()),
            discarded={},
        ),
    )

    def run_fleet(execution_id, stage, *, workers, completion_grace_seconds):
        observed.append((execution_id, stage.value, workers, completion_grace_seconds))
        delivered["qualified"] = 1
        leased = _read_job(EXECUTION_ID, job.job_id)
        _write_job(
            leased.with_timing(
                QueueTimelineEvent.SUCCEEDED,
                at="2026-07-22T00:00:00Z",
                state=QueueJobState.SUCCEEDED,
                lease=QueueLease(),
            )
        )
        return ReliableTaskFleetReport(
            total=1,
            succeeded=1,
            outcomes=(
                ReliableTaskFleetOutcome(
                    job_id=job.job_id,
                    status="succeeded",
                    attempts=1,
                ),
            ),
        )

    from content.execution.queue.reliabletask import fleet as reliabletask_fleet

    monkeypatch.setattr(reliabletask_fleet, "run_reliabletask_fleet", run_fleet)

    result = reliabletask_dispatch.dispatch_reliabletask_checkpoint(
        ctx,
        ExecutionStage.BUILD_HOMEPAGE,
    )

    assert result is not None
    assert result.status is ReliableTaskDispatchStatus.COMPLETED
    assert result.attempted_count == 1
    assert result.completed_count == 1
    assert observed and observed[0][:3] == (EXECUTION_ID, "author", ctx.max_workers)
    assert _read_job(EXECUTION_ID, job.job_id).state is QueueJobState.SUCCEEDED
    assert not hasattr(reliabletask_dispatch, "_dispatch_embedded")
    assert (
        reliabletask_dispatch.dispatch_reliabletask_checkpoint(
            ctx,
            ExecutionStage.BUILD_HOMEPAGE,
        )
        is None
    )
    shutil.rmtree(execution_root(EXECUTION_ID), ignore_errors=True)


def test_fleet_empty_pending_race_rechecks_delivered_quota(monkeypatch) -> None:
    execution_id = "20260807--travel-homepage-m1--china--scale-091"
    shutil.rmtree(execution_root(execution_id), ignore_errors=True)
    fixture = ExecutionFixtureBuilder(execution_id)
    fixture.build()
    ctx = ExecutionContext(
        execution_id=execution_id,
        entity_ids=("测试实体甲",),
        spec=fixture.spec(),
        managed=True,
        runtime=RuntimeEnvironment.LOCAL,
    )
    enqueue_ref_job(
        execution_id,
        OBJECT_REF,
        "author",
        mutex_key=OBJECT_REF,
        queue_backend=QueueBackend.RELIABLE_TASK,
        meta={
            "contentType": ContentType.HOMEPAGE.value,
            "carrier": ContentType.HOMEPAGE.value,
            "entityRef": OBJECT_REF,
            "sourceRevision": "sha256:" + ("9" * 64),
            "contentObjectDir": "entities/地点/景区/测试实体甲",
        },
    )
    from content.execution.controller import homepage_authoring
    from content.execution.queue.reliabletask import fleet as reliabletask_fleet

    delivered = {"ready": False}
    monkeypatch.setattr(
        homepage_authoring,
        "homepage_quota_verdict",
        lambda _ctx: homepage_authoring.HomepageQuotaVerdict(
            approved_quota=1,
            qualified_refs=(("地点/景区/测试实体甲",) if delivered["ready"] else ()),
            discarded={},
        ),
    )

    def terminal_race(*_args, **_kwargs):
        delivered["ready"] = True
        raise ValueError(f"execution 无待执行 ReliableTask author jobs：{execution_id}")

    monkeypatch.setattr(
        reliabletask_fleet,
        "run_reliabletask_fleet",
        terminal_race,
    )
    result = reliabletask_dispatch.dispatch_reliabletask_checkpoint(
        ctx,
        ExecutionStage.BUILD_HOMEPAGE,
    )

    assert result is not None
    assert result.status is ReliableTaskDispatchStatus.COMPLETED
    assert result.completed_count == 1
    assert result.issues == ()
    shutil.rmtree(execution_root(execution_id), ignore_errors=True)


def test_fleet_empty_pending_race_continues_controller_after_author_completion(
    monkeypatch,
) -> None:
    execution_id = "20260807--travel-homepage-m1--china--scale-092"
    shutil.rmtree(execution_root(execution_id), ignore_errors=True)
    fixture = ExecutionFixtureBuilder(execution_id)
    fixture.build()
    ctx = ExecutionContext(
        execution_id=execution_id,
        entity_ids=("测试实体甲",),
        spec=fixture.spec(),
        managed=True,
        runtime=RuntimeEnvironment.LOCAL,
    )
    job = enqueue_ref_job(
        execution_id,
        OBJECT_REF,
        "author",
        mutex_key=OBJECT_REF,
        queue_backend=QueueBackend.RELIABLE_TASK,
        meta={
            "contentType": ContentType.HOMEPAGE.value,
            "carrier": ContentType.HOMEPAGE.value,
            "entityRef": OBJECT_REF,
            "sourceRevision": "sha256:" + ("8" * 64),
            "contentObjectDir": "entities/地点/景区/测试实体甲",
        },
    )
    from content.execution.queue.reliabletask import fleet as reliabletask_fleet

    def terminal_race(*_args, **_kwargs):
        stored = _read_job(execution_id, job.job_id)
        _write_job(
            stored.with_timing(
                QueueTimelineEvent.SUCCEEDED,
                at="2026-08-07T00:00:00Z",
                state=QueueJobState.SUCCEEDED,
                lease=QueueLease(),
            )
        )
        raise ValueError(f"execution 无待执行 ReliableTask author jobs：{execution_id}")

    monkeypatch.setattr(
        reliabletask_fleet,
        "run_reliabletask_fleet",
        terminal_race,
    )

    result = reliabletask_dispatch.dispatch_reliabletask_checkpoint(
        ctx,
        ExecutionStage.BUILD_HOMEPAGE,
    )

    assert result is not None
    assert result.status is ReliableTaskDispatchStatus.COMPLETED
    assert result.completed_count == 0
    assert result.issues == ()
    shutil.rmtree(execution_root(execution_id), ignore_errors=True)


def test_reliabletask_resume_accepts_receipt_for_only_remaining_jobs__reliability__local_contract(
    monkeypatch,
) -> None:
    execution_id = "20260803--travel-article-generate--test-region-a--pilot-902"
    names = ("测试实体甲", "测试实体乙")
    shutil.rmtree(execution_root(execution_id), ignore_errors=True)
    fixture = ExecutionFixtureBuilder(
        execution_id,
        targets=tuple(
            {"name": name, "entityType": "地点/景区"} for name in names
        ),
        approved_quota=2,
    )
    fixture.build()
    ctx = ExecutionContext(
        execution_id=execution_id,
        entity_ids=names,
        spec=fixture.spec(),
        managed=True,
        runtime=RuntimeEnvironment.LOCAL,
    )
    creator_assignment = creator_assignment_from_profile(
        TemplateRegistry.load().creators["qwq_creator_highland_travel_blogger_001"]
    )
    jobs = tuple(
        enqueue_ref_job(
            execution_id,
            f"/entity/地点/景区/{name}",
            "author",
            mutex_key=f"/entity/地点/景区/{name}",
            queue_backend=QueueBackend.RELIABLE_TASK,
            meta={
                "contentType": ContentType.ARTICLE.value,
                "carrier": ContentType.ARTICLE.value,
                "entityRef": f"/entity/地点/景区/{name}",
                "sourceRevision": "sha256:" + (str(index + 1) * 64),
                "contentObjectDir": f"posts/article/攻略/{name}/1",
                **creator_assignment,
            },
        )
        for index, name in enumerate(names)
    )
    _write_job(
        _read_job(execution_id, jobs[0].job_id).with_timing(
            QueueTimelineEvent.SUCCEEDED,
            at="2026-08-03T00:00:00Z",
            state=QueueJobState.SUCCEEDED,
            lease=QueueLease(),
        )
    )

    def run_fleet(_execution_id, _stage, *, workers, completion_grace_seconds):
        assert _execution_id == execution_id
        assert workers == ctx.max_workers
        assert completion_grace_seconds > 0
        _write_job(
            _read_job(execution_id, jobs[1].job_id).with_timing(
                QueueTimelineEvent.SUCCEEDED,
                at="2026-08-03T00:01:00Z",
                state=QueueJobState.SUCCEEDED,
                lease=QueueLease(),
            )
        )
        return ReliableTaskFleetReport(
            total=1,
            succeeded=1,
            outcomes=(
                ReliableTaskFleetOutcome(
                    job_id=jobs[1].job_id,
                    status="succeeded",
                    attempts=1,
                ),
            ),
        )

    from content.execution.queue.reliabletask import fleet as reliabletask_fleet

    monkeypatch.setattr(reliabletask_fleet, "run_reliabletask_fleet", run_fleet)
    result = reliabletask_dispatch.dispatch_reliabletask_checkpoint(
        ctx,
        ExecutionStage.POST_AUTHOR,
    )

    assert result is not None
    assert result.status is ReliableTaskDispatchStatus.COMPLETED
    assert result.completed_count == 2
    assert result.issues == ()
    shutil.rmtree(execution_root(execution_id), ignore_errors=True)


def test_execution_runtime_preflight__uses_single_canonical_fleet_gate__contract__local_contract() -> None:
    argv = _runtime_preflight_argv(EXECUTION_ID)

    assert argv[:3] == ["task", "preflight", "--semantic-agent-startup"]
    assert "--require-reliabletask-fleet" not in argv


def test_reliabletask_fleet__waits_for_nonterminal_remote_jobs__reliability__local_contract(
    monkeypatch,
) -> None:
    shutil.rmtree(execution_root(EXECUTION_ID), ignore_errors=True)
    fixture = ExecutionFixtureBuilder(EXECUTION_ID)
    fixture.build()
    ctx = ExecutionContext(
        execution_id=EXECUTION_ID,
        entity_ids=("测试实体甲",),
        spec=fixture.spec(),
        managed=True,
        runtime=RuntimeEnvironment.LOCAL,
    )
    job = enqueue_ref_job(
        EXECUTION_ID,
        OBJECT_REF,
        "author",
        mutex_key=OBJECT_REF,
        queue_backend=QueueBackend.RELIABLE_TASK,
        meta={
            "contentType": ContentType.HOMEPAGE.value,
            "carrier": ContentType.HOMEPAGE.value,
            "entityRef": OBJECT_REF,
            "sourceRevision": "sha256:" + ("b" * 64),
            "contentObjectDir": "entities/地点/景区/测试实体甲",
        },
    )

    def run_fleet(_execution_id, _stage, *, workers, completion_grace_seconds):
        assert workers == ctx.max_workers
        assert completion_grace_seconds > 0
        return ReliableTaskFleetReport(
            total=1,
            succeeded=0,
            outcomes=(
                ReliableTaskFleetOutcome(
                    job_id=job.job_id,
                    status="processing",
                    attempts=1,
                ),
            ),
        )

    from content.execution.queue.reliabletask import fleet as reliabletask_fleet

    monkeypatch.setattr(reliabletask_fleet, "run_reliabletask_fleet", run_fleet)
    result = reliabletask_dispatch.dispatch_reliabletask_checkpoint(
        ctx,
        ExecutionStage.BUILD_HOMEPAGE,
    )

    assert result is not None
    assert result.status is ReliableTaskDispatchStatus.WAITING
    assert result.issues == ()
    shutil.rmtree(execution_root(EXECUTION_ID), ignore_errors=True)


def test_reliabletask_fleet__projects_terminal_worker_failure__reliability__local_contract(
    monkeypatch,
) -> None:
    shutil.rmtree(execution_root(EXECUTION_ID), ignore_errors=True)
    fixture = ExecutionFixtureBuilder(EXECUTION_ID)
    fixture.build()
    ctx = ExecutionContext(
        execution_id=EXECUTION_ID,
        entity_ids=("测试实体甲",),
        spec=fixture.spec(),
        managed=True,
        runtime=RuntimeEnvironment.LOCAL,
    )
    job = enqueue_ref_job(
        EXECUTION_ID,
        OBJECT_REF,
        "author",
        mutex_key=OBJECT_REF,
        queue_backend=QueueBackend.RELIABLE_TASK,
        meta={
            "contentType": ContentType.HOMEPAGE.value,
            "carrier": ContentType.HOMEPAGE.value,
            "entityRef": OBJECT_REF,
            "sourceRevision": "sha256:" + ("c" * 64),
            "contentObjectDir": "entities/地点/景区/测试实体甲",
        },
    )

    def run_fleet(_execution_id, _stage, *, workers, completion_grace_seconds):
        assert workers == ctx.max_workers
        assert completion_grace_seconds > 0
        return ReliableTaskFleetReport(
            total=1,
            succeeded=0,
            outcomes=(
                ReliableTaskFleetOutcome(
                    job_id=job.job_id,
                    status="dead",
                    attempts=job.max_attempts,
                    failure_code="RELIABLETASK.WORKER.handler_failed",
                ),
            ),
        )

    from content.execution.queue.reliabletask import fleet as reliabletask_fleet

    monkeypatch.setattr(reliabletask_fleet, "run_reliabletask_fleet", run_fleet)
    result = reliabletask_dispatch.dispatch_reliabletask_checkpoint(
        ctx,
        ExecutionStage.BUILD_HOMEPAGE,
    )

    stored = _read_job(EXECUTION_ID, job.job_id)
    assert result is not None
    assert result.status is ReliableTaskDispatchStatus.BLOCKED
    assert stored.state is QueueJobState.DEAD
    assert stored.attempt == job.max_attempts
    assert stored.last_issue is not None
    assert "failureCode=RELIABLETASK.WORKER.handler_failed" in stored.last_issue.message
    monkeypatch.setattr(
        reliabletask_fleet,
        "run_reliabletask_fleet",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("terminal resume must not dispatch an empty fleet")
        ),
    )
    resumed = reliabletask_dispatch.dispatch_reliabletask_checkpoint(
        ctx,
        ExecutionStage.BUILD_HOMEPAGE,
    )
    assert resumed is not None
    assert resumed.status is ReliableTaskDispatchStatus.BLOCKED
    assert resumed.issues
    assert resumed.discarded
    shutil.rmtree(execution_root(EXECUTION_ID), ignore_errors=True)


def test_reliabletask_late_remote_dead_preserves_verified_local_success(
    monkeypatch,
) -> None:
    shutil.rmtree(execution_root(EXECUTION_ID), ignore_errors=True)
    fixture = ExecutionFixtureBuilder(EXECUTION_ID)
    fixture.build()
    ctx = ExecutionContext(
        execution_id=EXECUTION_ID,
        entity_ids=("测试实体甲",),
        spec=fixture.spec(),
        managed=True,
        runtime=RuntimeEnvironment.LOCAL,
    )
    job = enqueue_ref_job(
        EXECUTION_ID,
        OBJECT_REF,
        "author",
        mutex_key=OBJECT_REF,
        queue_backend=QueueBackend.RELIABLE_TASK,
        meta={
            "contentType": ContentType.HOMEPAGE.value,
            "carrier": ContentType.HOMEPAGE.value,
            "entityRef": OBJECT_REF,
            "sourceRevision": "sha256:" + ("e" * 64),
            "contentObjectDir": "entities/地点/景区/测试实体甲",
        },
    )

    def run_fleet(_execution_id, _stage, *, workers, completion_grace_seconds):
        assert workers == ctx.max_workers
        assert completion_grace_seconds > 0
        stored = _read_job(EXECUTION_ID, job.job_id)
        _write_job(
            stored.with_timing(
                QueueTimelineEvent.SUCCEEDED,
                at="2026-08-07T11:28:18Z",
                state=QueueJobState.SUCCEEDED,
                lease=QueueLease(),
            )
        )
        return ReliableTaskFleetReport(
            total=1,
            succeeded=0,
            outcomes=(
                ReliableTaskFleetOutcome(
                    job_id=job.job_id,
                    status="dead",
                    attempts=job.max_attempts,
                    failure_code="RELIABLETASK.WORKER.handler_failed",
                ),
            ),
        )

    from content.execution.queue.reliabletask import fleet as reliabletask_fleet

    monkeypatch.setattr(reliabletask_fleet, "run_reliabletask_fleet", run_fleet)
    result = reliabletask_dispatch.dispatch_reliabletask_checkpoint(
        ctx,
        ExecutionStage.POST_AUTHOR,
    )

    stored = _read_job(EXECUTION_ID, job.job_id)
    reconciliation = stored.timings[-1].to_document()
    assert result is not None
    assert result.status is ReliableTaskDispatchStatus.COMPLETED
    assert stored.state is QueueJobState.SUCCEEDED
    assert stored.last_issue is None
    assert reconciliation["event"] == QueueTimelineEvent.RECONCILED.value
    assert reconciliation["reason"] == "stale_remote_terminal_after_local_success"
    assert reconciliation["remoteStatus"] == "dead"
    assert reconciliation["remoteFailureCode"] == (
        "RELIABLETASK.WORKER.handler_failed"
    )
    shutil.rmtree(execution_root(EXECUTION_ID), ignore_errors=True)


def test_failed_commercial_batch_does_not_block_nonempty_publish_closure(
    monkeypatch,
) -> None:
    shutil.rmtree(execution_root(EXECUTION_ID), ignore_errors=True)
    fixture = ExecutionFixtureBuilder(EXECUTION_ID)
    fixture.build()
    ctx = ExecutionContext(
        execution_id=EXECUTION_ID,
        entity_ids=("测试实体甲",),
        spec=fixture.spec(),
        managed=True,
        runtime=RuntimeEnvironment.LOCAL,
    )
    job = enqueue_ref_job(
        EXECUTION_ID,
        OBJECT_REF,
        "publish",
        mutex_key=OBJECT_REF,
        queue_backend=QueueBackend.RELIABLE_TASK,
        meta={
            "contentType": ContentType.HOMEPAGE.value,
            "carrier": ContentType.HOMEPAGE.value,
            "entityRef": OBJECT_REF,
            "sourceRevision": "sha256:" + ("d" * 64),
            "contentObjectDir": "entities/地点/景区/测试实体甲",
        },
    )

    def run_fleet(_execution_id, _stage, *, workers, completion_grace_seconds):
        assert workers == ctx.max_workers
        assert completion_grace_seconds > 0
        stored = _read_job(EXECUTION_ID, job.job_id)
        _write_job(
            stored.with_timing(
                QueueTimelineEvent.SUCCEEDED,
                at="2026-07-28T00:00:00Z",
                state=QueueJobState.SUCCEEDED,
                lease=QueueLease(),
            )
        )
        return ReliableTaskFleetReport(
            total=1,
            succeeded=1,
            outcomes=(
                ReliableTaskFleetOutcome(
                    job_id=job.job_id,
                    status="succeeded",
                    attempts=1,
                ),
            ),
            passed=False,
            accepted_content_throughput_status=(
                "GATE_BLOCK_INCOMPLETE_COMMERCIAL_BATCH"
            ),
        )

    from content.execution.queue.reliabletask import fleet as reliabletask_fleet

    monkeypatch.setattr(reliabletask_fleet, "run_reliabletask_fleet", run_fleet)
    result = reliabletask_dispatch.dispatch_reliabletask_checkpoint(
        ctx,
        ExecutionStage.PUBLISH,
    )

    assert result is not None
    assert result.status is ReliableTaskDispatchStatus.COMPLETED
    assert result.completed_count == 1
    assert result.issues == ()
    shutil.rmtree(execution_root(EXECUTION_ID), ignore_errors=True)


def test_reliabletask_fleet__derives_batch_deadline_from_object_waves__contract__local_contract() -> None:
    jobs = 100
    workers = 3
    object_timeout_seconds = 1200
    completion_grace_seconds = 15
    expected_waves = (jobs + workers - 1) // workers

    assert fleet_batch_timeout_seconds(
        job_count=jobs,
        workers=workers,
        object_timeout_seconds=object_timeout_seconds,
        completion_grace_seconds=completion_grace_seconds,
    ) == expected_waves * object_timeout_seconds + completion_grace_seconds


def test_reliabletask_author__recovers_completed_provenance_bound_output_after_timeout__(
    monkeypatch,
) -> None:
    from content.execution.agent import agent_checkpoint
    from content.post.article import draft_io

    execution_id = "20260728--travel-article-golden--test-region-a--pilot-001"
    ref = "测试实体甲__article_source_1"
    ctx = SimpleNamespace(execution_id=execution_id, model="gpt-5.6-sol")
    job = SimpleNamespace(ref=ref)
    meta = {
        "executionId": execution_id,
        "objectRef": ref,
        "status": "completed",
        "provider": "cursor_sdk",
        "model": "gpt-5.6-sol",
        "agentRunId": "author_run_1",
        "agentId": "agent_1",
        "promptSha256": "sha256:" + "1" * 64,
        "writingPackSha256": "sha256:" + "2" * 64,
        "sourceBundleSha256": "sha256:" + "3" * 64,
        "draftSha256": "sha256:" + "4" * 64,
    }
    monkeypatch.setattr(
        agent_checkpoint,
        "_managed_checkpoint_job_issues",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(draft_io, "read_draft_meta", lambda *_args: meta)
    failed = AgentRunOutcome.failed(
        AgentFailureKind.FUTURE_TIMEOUT,
        provider=AgentProvider.CURSOR_SDK,
        message="result future timed out after durable files were written",
        started=True,
        attempts=2,
    )

    recovered = _recover_completed_author_outcome(
        ctx,
        job,
        checkpoint="post_author",
        prompt=(
            "<task>\n"
            "# 写作任务：测试文章\n"
            "- ref: `测试实体甲__article_source_1` ｜ 类型: `entity` ｜ 载体: `article`\n"
            "</task>"
        ),
        outcome=failed,
    )

    assert recovered is not None
    assert recovered.succeeded
    assert recovered.run_id == "author_run_1"
    assert recovered.completion_mode == "durable_output_recovery"
