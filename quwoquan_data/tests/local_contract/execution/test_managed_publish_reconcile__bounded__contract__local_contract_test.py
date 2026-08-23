# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/spec.md
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-004
"""Managed publish reconcile must not loop forever when promote keeps failing."""
from __future__ import annotations

import shutil

from content.execution import store
from content.execution.agent import agent_managed as subject
from content.execution.context import ExecutionContext
from content.execution.queue.backend import load_execution_queue_backend
from content.execution.queue.jobs import enqueue_ref_job
from content.execution.queue.reliabletask.projection import (
    record_reliabletask_completion,
)
from content.execution.queue.reliabletask.report import ReliableTaskFleetReport
from content.execution.workspace import execution_root
from core.control_types import (
    ContentType,
    ExecutionStateStatus,
    QueueBackend,
    RuntimeEnvironment,
)
from core.io import write_json
from support.execution_manifest_fixture import ExecutionFixtureBuilder


EXECUTION_ID = "20260731--travel-image-reconcile-bound--test-region-a--pilot-913"
PUBLISH_WAITING_EXECUTION_ID = (
    "20260822--travel-image-publish-waiting--test-region-a--pilot-914"
)
PUBLISH_COMPLETED_EXECUTION_ID = (
    "20260822--travel-image-publish-completed--test-region-a--pilot-915"
)
PUBLISH_BLOCKED_EXECUTION_ID = (
    "20260822--travel-image-publish-blocked--test-region-a--pilot-916"
)
PUBLISH_DISPATCH_MISSING_EXECUTION_ID = (
    "20260822--travel-image-publish-missing--test-region-a--pilot-917"
)


def test_managed_controller_stops_after_second_reconcile_failure(monkeypatch) -> None:
    fixture = ExecutionFixtureBuilder(
        EXECUTION_ID,
        targets=({"name": "实体甲", "entityType": "地点/景区"},),
        approved_quota=1,
    )
    fixture.build()
    from content.execution.support import load_execution_state, save_execution_state

    state = load_execution_state(EXECUTION_ID)
    state.status = ExecutionStateStatus.RUNNING
    state.completed = ["publish"]
    state.failed_objects = ["promote failed"]
    save_execution_state(state)

    calls = {"controller": 0}

    def fake_controller(_ctx):
        calls["controller"] += 1
        return 0

    def fake_reconcile(_ctx):
        return False

    import content.execution.controller.orchestrator as orchestrator

    monkeypatch.setattr(orchestrator, "run_controller", fake_controller)
    monkeypatch.setattr(subject, "_reconcile_completed_publish_state", fake_reconcile)

    ctx = ExecutionContext(
        execution_id=EXECUTION_ID,
        entity_ids=("实体甲",),
        spec=fixture.spec(),
        managed=True,
        runtime=RuntimeEnvironment.LOCAL,
    )
    code = subject.run_managed_controller(ctx)
    assert code == 1
    assert calls["controller"] == 2
    from content.execution.support import load_execution_state

    state = load_execution_state(EXECUTION_ID)
    assert state.status is ExecutionStateStatus.MANUAL_REQUIRED
    assert "reconcile failed" in str(state.next_action or "")


def _publish_context(execution_id: str, *, enqueue: bool = True):
    root = execution_root(execution_id)
    shutil.rmtree(root, ignore_errors=True)
    fixture = ExecutionFixtureBuilder(
        execution_id,
        targets=({"name": "实体甲", "entityType": "地点/景区"},),
        approved_quota=1,
        queue_backend=QueueBackend.LOCAL_FILE,
    )
    fixture.build()
    queue_envelope = load_execution_queue_backend(execution_id)
    assert queue_envelope["queueBackend"] == QueueBackend.LOCAL_FILE.value
    assert queue_envelope["poolDeliveryBackend"] == QueueBackend.RELIABLE_TASK.value
    ctx = ExecutionContext(
        execution_id=execution_id,
        entity_ids=("实体甲",),
        spec=store.load_spec(execution_id),
        managed=True,
        runtime=RuntimeEnvironment.LOCAL,
    )
    job = None
    if enqueue:
        ref = "/entity/地点/景区/实体甲"
        job = enqueue_ref_job(
            execution_id,
            ref,
            "publish",
            mutex_key=ref,
            queue_backend=QueueBackend.RELIABLE_TASK,
            meta={
                "contentType": ContentType.IMAGE.value,
                "carrier": ContentType.IMAGE.value,
                "entityRef": ref,
                "sourceRevision": "sha256:" + ("a" * 64),
                "contentObjectDir": "posts/image/实体甲",
            },
        )
    from content.execution.support import load_execution_state, save_execution_state

    state = load_execution_state(execution_id)
    state.status = ExecutionStateStatus.WAITING_AGENT
    state.waiting_checkpoint = "publish"
    save_execution_state(state)
    return root, ctx, job


def _decoded_publish_report(
    execution_id: str,
    job_id: str,
    *,
    status: str,
    attempts: int,
    succeeded: int,
    accepted_count: int,
    failure_code: str = "",
) -> ReliableTaskFleetReport:
    passed = accepted_count >= 1
    return ReliableTaskFleetReport.from_document(
        {
            "executionId": execution_id,
            "stage": "publish",
            "jobSetEnvelopeDigest": "sha256:" + ("b" * 64),
            "jobSetDigest": "sha256:" + ("c" * 64),
            "actualTaskDigest": "sha256:" + ("c" * 64),
            "total": 1,
            "succeeded": succeeded,
            "finalizedObjectCount": accepted_count,
            "requiredQuota": 1,
            "duplicatePublishCount": 0,
            "missingObjectCount": 0,
            "publishTaskCount": 1,
            "objectTransactionResultCount": accepted_count,
            "researchAcceptedCount": accepted_count,
            "commercialAcceptedCount": 0,
            "passed": passed,
            "acceptedContentThroughputStatus": (
                "MEASURED"
                if passed
                else "GATE_BLOCK_INCOMPLETE_COMMERCIAL_BATCH"
            ),
            "recoveryEligibleCount": 0,
            "automaticRecoveredCount": 0,
            "manualRecoveredCount": 0,
            "automaticRecoveryStatus": "NOT_EXERCISED",
            "automaticRecoveryRate": 0.0,
            "fleetPeakConcurrentWorkers": 1,
            "fleetWaveCount": 1,
            "fleetBatchDeadlineEpochSeconds": 1_787_318_400,
            "taskOutcomes": [
                {
                    "jobId": job_id,
                    "status": status,
                    "attempts": attempts,
                    "failureCode": failure_code,
                }
            ],
        }
    )


def _forbid_semantic_publish_repair(monkeypatch) -> None:
    monkeypatch.setattr(
        subject,
        "_run_managed_checkpoint",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("publish must not enter semantic Agent repair")
        ),
    )


def test_publish_reliabletask_wait_does_not_enter_semantic_agent_repair(
    monkeypatch,
) -> None:
    root, ctx, job = _publish_context(PUBLISH_WAITING_EXECUTION_ID)
    assert job is not None
    try:
        from content.execution.controller import orchestrator
        from content.execution.queue.reliabletask import fleet as reliabletask_fleet
        from content.execution.support import load_execution_state

        monkeypatch.setattr(orchestrator, "run_controller", lambda _ctx: 10)
        monkeypatch.setattr(
            reliabletask_fleet,
            "run_reliabletask_fleet",
            lambda _execution_id, _stage: _decoded_publish_report(
                PUBLISH_WAITING_EXECUTION_ID,
                job.job_id,
                status="processing",
                attempts=1,
                succeeded=0,
                accepted_count=0,
            ),
        )
        _forbid_semantic_publish_repair(monkeypatch)

        assert subject.run_managed_controller(ctx) == 10
        state = load_execution_state(PUBLISH_WAITING_EXECUTION_ID)
        assert state.status is ExecutionStateStatus.WAITING_AGENT
        assert state.retry_counts.get("publish", 0) == 0
        assert state.failed_issue_records == []
        assert state.failed_objects == []
        assert "ReliableTask publish" in str(state.next_action or "")
        assert "status=waiting" in str(state.next_action or "")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_publish_reliabletask_completion_resumes_controller_without_agent_repair(
    monkeypatch,
) -> None:
    root, ctx, job = _publish_context(PUBLISH_COMPLETED_EXECUTION_ID)
    assert job is not None
    try:
        from content.execution.controller import orchestrator
        from content.execution.queue.reliabletask import fleet as reliabletask_fleet
        from content.execution.support import load_execution_state

        calls = {"controller": 0}

        def run_controller(_ctx) -> int:
            calls["controller"] += 1
            return 10 if calls["controller"] == 1 else 0

        def run_fleet(_execution_id, _stage) -> ReliableTaskFleetReport:
            apply_report = root / "evidence/test/publish-apply.json"
            write_json(
                apply_report,
                {
                    "schema": "quwoquan_data.object_transaction_apply",
                    "status": "applied",
                    "executionId": PUBLISH_COMPLETED_EXECUTION_ID,
                },
            )
            record_reliabletask_completion(
                PUBLISH_COMPLETED_EXECUTION_ID,
                job.job_id,
                evidence_path=apply_report,
                evidence_root=root,
            )
            return _decoded_publish_report(
                PUBLISH_COMPLETED_EXECUTION_ID,
                job.job_id,
                status="succeeded",
                attempts=1,
                succeeded=1,
                accepted_count=1,
            )

        monkeypatch.setattr(orchestrator, "run_controller", run_controller)
        monkeypatch.setattr(reliabletask_fleet, "run_reliabletask_fleet", run_fleet)
        _forbid_semantic_publish_repair(monkeypatch)

        assert subject.run_managed_controller(ctx) == 0
        state = load_execution_state(PUBLISH_COMPLETED_EXECUTION_ID)
        assert calls["controller"] == 2
        assert state.status is ExecutionStateStatus.RUNNING
        assert state.retry_counts.get("publish", 0) == 0
        assert state.failed_issue_records == []
        assert state.failed_objects == []
        assert "status=completed" in str(state.next_action or "")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_publish_reliabletask_block_preserves_typed_issue_without_agent_repair(
    monkeypatch,
) -> None:
    root, ctx, job = _publish_context(PUBLISH_BLOCKED_EXECUTION_ID)
    assert job is not None
    try:
        from content.execution.controller import orchestrator
        from content.execution.queue.reliabletask import fleet as reliabletask_fleet
        from content.execution.support import load_execution_state

        monkeypatch.setattr(orchestrator, "run_controller", lambda _ctx: 10)
        monkeypatch.setattr(
            reliabletask_fleet,
            "run_reliabletask_fleet",
            lambda _execution_id, _stage: _decoded_publish_report(
                PUBLISH_BLOCKED_EXECUTION_ID,
                job.job_id,
                status="dead",
                attempts=job.max_attempts,
                succeeded=0,
                accepted_count=0,
                failure_code="RELIABLETASK.WORKER.handler_failed",
            ),
        )
        _forbid_semantic_publish_repair(monkeypatch)

        assert subject.run_managed_controller(ctx) == 1
        from content.execution.queue.core import _read_job

        state = load_execution_state(PUBLISH_BLOCKED_EXECUTION_ID)
        assert state.status is ExecutionStateStatus.MANUAL_REQUIRED
        assert state.retry_counts.get("publish", 0) == 0
        assert len(state.failed_issue_records) == 1
        issue = state.failed_issue_records[0]
        assert issue["code"] == "DATA.CONTRACT.INVALID"
        assert issue["stage"] == "publish"
        assert issue["recovery"] == "stop"
        object_issue = _read_job(
            PUBLISH_BLOCKED_EXECUTION_ID,
            job.job_id,
        ).last_issue
        assert object_issue is not None
        assert object_issue.code.value == "DATA.QUEUE.EXECUTION_FAILED"
        assert object_issue.stage.value == "publish"
        assert object_issue.recovery.value == "stop"
        assert "status=blocked" in str(state.next_action or "")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_publish_dispatch_contract_gap_fails_closed_with_typed_issue(
    monkeypatch,
) -> None:
    root, ctx, job = _publish_context(
        PUBLISH_DISPATCH_MISSING_EXECUTION_ID,
        enqueue=False,
    )
    assert job is None
    try:
        from content.execution.controller import orchestrator
        from content.execution.queue.reliabletask import fleet as reliabletask_fleet
        from content.execution.support import load_execution_state

        monkeypatch.setattr(orchestrator, "run_controller", lambda _ctx: 10)
        monkeypatch.setattr(
            reliabletask_fleet,
            "run_reliabletask_fleet",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("missing publish declaration must not dispatch fleet")
            ),
        )
        _forbid_semantic_publish_repair(monkeypatch)

        assert subject.run_managed_controller(ctx) == 1
        state = load_execution_state(PUBLISH_DISPATCH_MISSING_EXECUTION_ID)
        assert state.status is ExecutionStateStatus.MANUAL_REQUIRED
        assert state.waiting_checkpoint is None
        assert state.retry_counts.get("publish", 0) == 0
        assert len(state.failed_issue_records) == 1
        issue = state.failed_issue_records[0]
        assert issue["code"] == "DATA.CONTRACT.INVALID"
        assert issue["stage"] == "publish"
        assert issue["recovery"] == "stop"
        assert "repair publish queue declaration" in str(state.next_action or "")
    finally:
        shutil.rmtree(root, ignore_errors=True)
