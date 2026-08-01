# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/spec.md
"""Publish must absorb DEAD jobs when fleet.passed already meets quota."""
from __future__ import annotations

import shutil
from types import SimpleNamespace

from content.execution.controller import publish as publish_module
from content.execution.context import ExecutionContext
from content.execution.support import StageStatus
from core.control_types import (
    ExecutionStage,
    QueueJobState,
    RuntimeEnvironment,
)
from core.io import write_json
from core.paths import execution_root
from support.execution_manifest_fixture import ExecutionFixtureBuilder


EXECUTION_ID = "20260731--travel-homepage-publish--test-region-a--pilot-911"
_NAMES = ("测试实体甲", "测试实体乙", "测试实体丙")


def test_publish_absorbs_dead_jobs_when_fleet_passed_quota(monkeypatch) -> None:
    shutil.rmtree(execution_root(EXECUTION_ID), ignore_errors=True)
    fixture = ExecutionFixtureBuilder(
        EXECUTION_ID,
        targets=tuple({"name": name, "entityType": "地点/景区"} for name in _NAMES),
        approved_quota=3,
    )
    fixture.build()
    ctx = ExecutionContext(
        execution_id=EXECUTION_ID,
        entity_ids=_NAMES,
        spec=fixture.spec(),
        managed=False,
        runtime=RuntimeEnvironment.LOCAL,
    )
    root = execution_root(EXECUTION_ID)
    write_json(
        root / "evidence/reliabletask/publish_fleet_report.json",
        {
            "schema": "quwoquan.reliabletask_fleet_report",
            "passed": True,
            "backend": "mongodb+redis",
            "total": 3,
            "succeeded": 2,
            "stageCompletedCount": 0,
            "publishTaskCount": 3,
            "objectTransactionResultCount": 2,
            "commercialAcceptedCount": 3,
            "fleetControlPlaneThroughputPerHour": 1.0,
            "fleetAcceptedThroughputPerHour": 1.0,
            "endToEndAcceptedThroughputPerHour": 1.0,
            "acceptedContentThroughputStatus": "MEASURED",
            "automaticRecoveryRate": 1.0,
            "finalizedWithinStageBudgetRate": 1.0,
            "duplicatePublishCount": 0,
            "missingObjectCount": 0,
            "requiredQuota": 3,
            "finalizedObjectCount": 0,
            "idempotencyKey": "test",
            "taskOutcomes": [],
            "executionCreatedAt": "2026-07-31T00:00:00Z",
            "fleetStartedAt": "2026-07-31T00:00:00Z",
            "canonicalFinalizedAt": "2026-07-31T00:00:00Z",
            "fleetWallClockMilliseconds": 1,
            "endToEndWallClockMilliseconds": 1,
            "completedAt": "2026-07-31T00:00:00Z",
        },
    )

    dead = SimpleNamespace(
        state=QueueJobState.DEAD,
        ref="/entity/地点/景区/测试实体甲",
        content_object_dir="entities/地点/景区/测试实体甲",
    )
    ok_jobs = [
        SimpleNamespace(
            state=QueueJobState.SUCCEEDED,
            ref=f"/entity/地点/景区/{name}",
            content_object_dir=f"entities/地点/景区/{name}",
        )
        for name in _NAMES[1:]
    ]
    monkeypatch.setattr(
        publish_module,
        "_is_homepage_only_execution",
        lambda _ctx: True,
    )
    monkeypatch.setattr(
        publish_module,
        "_publishable_homepage_names",
        lambda _ctx: set(_NAMES),
    )
    monkeypatch.setattr(
        "content.execution.controller.homepage_authoring.homepage_quota_verdict",
        lambda _ctx: SimpleNamespace(
            qualified_refs=tuple(f"地点/景区/{name}" for name in _NAMES),
            discarded={},
            qualified_count=3,
            approved_quota=3,
        ),
    )
    monkeypatch.setattr(
        "content.execution.qualification.finalize_execution_qualification",
        lambda *_a, **_k: SimpleNamespace(passed=True, issues=()),
    )
    monkeypatch.setattr(
        "core.publish_materialization.materialize_task_publish_inputs",
        lambda *_a, **_k: {
            "entityCount": 3,
            "postCount": 0,
            "tagCount": 0,
            "relationCount": 0,
        },
    )
    monkeypatch.setattr(
        "content.execution.reliabletask_jobs.prepare_reliable_publish_jobs",
        lambda _ctx, homepage_refs=None: (dead, *ok_jobs),
    )
    written: dict[str, object] = {}
    monkeypatch.setattr(
        "content.execution.workspace.write_publish_ref",
        lambda execution_id, **kwargs: written.update(
            {"execution_id": execution_id, **kwargs}
        ),
    )
    monkeypatch.setattr(
        "content.post.object_index.iter_content_refs",
        lambda _execution_id: (),
    )
    monkeypatch.setattr(
        "content.execution.queue.runtime.reconcile_completed_refs",
        lambda *_a, **_k: (),
    )
    monkeypatch.setattr(
        "content.execution.recovery.post_recovery._purge_stale_author_queue",
        lambda *_a, **_k: None,
    )

    result = publish_module._run_publish(ctx)

    assert result.status is StageStatus.DONE, result.message
    assert result.stage is ExecutionStage.PUBLISH
    assert "object transaction failed" not in result.message
    assert written["execution_id"] == EXECUTION_ID
    assert set(written["entity_refs"]) == {f"地点/景区/{name}" for name in _NAMES}
    shutil.rmtree(execution_root(EXECUTION_ID), ignore_errors=True)
