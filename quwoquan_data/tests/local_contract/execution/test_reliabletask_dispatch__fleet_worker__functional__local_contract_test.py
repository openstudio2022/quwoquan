"""The controller delegates every ReliableTask job to the service fleet."""
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
from content.execution.reliabletask_fleet import (  # noqa: E402
    ReliableTaskFleetOutcome,
    ReliableTaskFleetReport,
    fleet_batch_timeout_seconds,
)
from content.execution.workspace import execution_root  # noqa: E402
from content.execution.recipe import _runtime_preflight_argv  # noqa: E402
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


EXECUTION_ID = "20260722--travel-homepage-generate--test-region-a--pilot-901"
OBJECT_REF = "/entity/地点/景区/测试实体甲"


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

    def run_fleet(execution_id, stage, *, workers, completion_grace_seconds):
        observed.append((execution_id, stage.value, workers, completion_grace_seconds))
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

    from content.execution import reliabletask_fleet

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


def test_execution_runtime_preflight__requires_ops_fleet_before_authoring__contract__local_contract() -> None:
    argv = _runtime_preflight_argv(EXECUTION_ID)

    assert "--require-reliabletask-fleet" in argv


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

    from content.execution import reliabletask_fleet

    monkeypatch.setattr(reliabletask_fleet, "run_reliabletask_fleet", run_fleet)
    result = reliabletask_dispatch.dispatch_reliabletask_checkpoint(
        ctx,
        ExecutionStage.BUILD_HOMEPAGE,
    )

    assert result is not None
    assert result.status is ReliableTaskDispatchStatus.WAITING
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
