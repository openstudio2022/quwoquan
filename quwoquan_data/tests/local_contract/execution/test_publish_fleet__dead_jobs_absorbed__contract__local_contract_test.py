# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/geo-content-trinity/spec.md
"""Publish must absorb DEAD jobs when fleet.passed already meets quota."""
from __future__ import annotations

import shutil
from pathlib import Path
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


def test_homepage_object_publish_reads_incremental_inventory_before_apply(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from content.execution import workspace as workspace_module
    from content.release.canonical import (
        application,
        canonical_inventory,
        object_transaction,
        object_transaction_audit,
        object_transaction_contract,
    )
    from core import paths as paths_module
    from core import tree_integrity

    output_root = tmp_path / "output"
    publish_root = tmp_path / "publish"
    execution_dir = output_root / "data/tasks" / EXECUTION_ID
    inventory_calls: list[Path] = []
    tree_scans: list[Path] = []
    before_merkle = "sha256:" + "1" * 64
    object_merkle = "sha256:" + "2" * 64

    monkeypatch.setattr(paths_module, "OUTPUT_ROOT", output_root)
    monkeypatch.setattr(paths_module, "PUBLISH_ROOT", publish_root)
    monkeypatch.setattr(
        workspace_module,
        "execution_root",
        lambda _execution_id: execution_dir,
    )
    monkeypatch.setattr(
        canonical_inventory,
        "load_or_bootstrap_inventory",
        lambda root: (
            inventory_calls.append(root)
            or {"stats": {"merkleRoot": before_merkle}}
        ),
    )

    def tree_stats(path: Path) -> dict[str, str]:
        tree_scans.append(path)
        if path == publish_root:
            raise AssertionError("object publish hot path scanned the whole tree")
        return {"merkleRoot": object_merkle}

    monkeypatch.setattr(tree_integrity, "tree_integrity_stats", tree_stats)
    monkeypatch.setattr(
        object_transaction,
        "build_entity_object_transaction_package",
        lambda **_kwargs: None,
    )

    def audit(**kwargs):
        assert kwargs["expected_canonical_merkle"] == before_merkle
        return {"dryRunAttestationSha256": "sha256:" + "3" * 64}

    monkeypatch.setattr(object_transaction_audit, "audit_object_transaction", audit)
    monkeypatch.setattr(
        object_transaction_audit,
        "validate_publish_invariants",
        lambda _root: {"status": "passed", "issues": []},
    )
    monkeypatch.setattr(
        application,
        "apply_object_transaction",
        lambda **_kwargs: {"objectClosureDigest": "sha256:" + "4" * 64},
    )
    monkeypatch.setattr(
        object_transaction_contract,
        "refresh_canonical_tag_snapshots",
        lambda _root: None,
    )

    result = publish_module.publish_homepage_object(
        EXECUTION_ID,
        "/entity/地点/景区/测试实体甲",
    )

    assert inventory_calls == [publish_root]
    assert publish_root not in tree_scans
    assert result["canonicalObjectSha256"] == object_merkle


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
    report_path = root / "evidence/reliabletask/publish_fleet_report.json"
    write_json(
        report_path,
        {
            "schema": "quwoquan.reliabletask_fleet_report",
            "executionId": EXECUTION_ID,
            "stage": "publish",
            "jobSetEnvelopeDigest": "sha256:" + "a" * 64,
            "jobSetDigest": "sha256:" + "b" * 64,
            "actualTaskDigest": "sha256:" + "b" * 64,
            "passed": True,
            "backend": "mongodb+redis",
            "total": 3,
            "succeeded": 3,
            "stageCompletedCount": 0,
            "publishTaskCount": 3,
            "objectTransactionResultCount": 3,
            "researchAcceptedCount": 3,
            "commercialAcceptedCount": 0,
            "fleetControlPlaneThroughputPerHour": 1.0,
            "fleetAcceptedThroughputPerHour": 1.0,
            "endToEndAcceptedThroughputPerHour": 1.0,
            "acceptedContentThroughputStatus": "MEASURED",
            "recoveryEligibleCount": 0,
            "automaticRecoveredCount": 0,
            "manualRecoveredCount": 0,
            "automaticRecoveryStatus": "NOT_EXERCISED",
            "automaticRecoveryRate": 0.0,
            "firstAttemptSuccessRate": 1.0,
            "finalizedWithinStageBudgetRate": 1.0,
            "duplicatePublishCount": 0,
            "missingObjectCount": 0,
            "requiredQuota": 3,
            "finalizedObjectCount": 0,
            "idempotencyKey": "test",
            "taskOutcomes": [
                {"jobId": f"job-{index}", "status": "succeeded", "attempts": 1}
                for index in range(3)
            ],
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
        "latest_attempt_report_path",
        lambda _execution_id, _stage: report_path,
    )
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
        "content.execution.planning.qualification.finalize_execution_qualification",
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
        "content.execution.queue.reliabletask.jobs.prepare_reliable_publish_jobs",
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
