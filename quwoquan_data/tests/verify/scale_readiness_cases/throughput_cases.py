"""Throughput projection, queue backend, and creator-load cases."""
from __future__ import annotations

from common import *  # noqa: F401,F403

def test_scale_readiness_passes_by_per_worker_throughput_projection():
    """商用日产由「实测单位速率 × 承诺并发」投影达成，wall-clock 串行吞吐仅作质量证据。"""
    _save_spec(queue_backend="reliabletask", max_concurrency=10)
    root = batch_root(TASK, "projection_go")
    _write_env_ready("projection_go")
    write_json(
        root / "_shared" / "task_workflow_state.json",
        {
            "status": "succeeded",
            "throughput": {
                "measurementMode": "wall_clock_current_batch",
                "objectsPerHour": 2.05,
                "maxWorkers": 1,
                "agentActive": {
                    "measurementMode": "agent_run_history",
                    "authorRunCount": 1,
                    "authorActiveSeconds": 3600.0,
                    "finishedAuthorJobs": 50,
                    "finishedAuthorJobsPerHour": 50.0,
                    "effectiveWorkerCount": 1,
                    "perWorkerObjectsPerHour": 50.0,
                },
            },
            "quality": {"firstPassRate": 0.82},
        },
    )
    write_json(root / "_shared" / "token_ledger.json", {"summary": {"unitCost": 1}})
    write_json(root / "_shared" / "gamma_import_report.json", {"status": "passed"})
    write_json(release_root("projection_go_release") / "release_manifest.json", {"releaseId": "projection_go_release"})

    import task.target_selection as target_selection
    import verify.scale_readiness as scale_readiness

    original = target_selection.audit_managed_batch
    original_integrity = scale_readiness.scan_runtime_batch_integrity
    try:
        target_selection.audit_managed_batch = lambda task_id, batch_id: {
            "targetCount": 1,
            "lanePassed": {"homepage": 1, "article": 1, "image": 1},
            "failedLaneCount": 0,
            "failedLanes": [],
            "abandonedCount": 0,
            "abandonedContentCount": 0,
        }
        scale_readiness.scan_runtime_batch_integrity = lambda task_id, batch_id: {
            "passed": True,
            "stats": {"postCount": 5, "articleCount": 4, "imageCount": 1, "assetCount": 5},
            "issues": [],
        }
        report = build_scale_readiness_report(
            TASK,
            "projection_go",
            daily_target=10_000,
            release_id="projection_go_release",
            require_import=True,
        )
    finally:
        target_selection.audit_managed_batch = original
        scale_readiness.scan_runtime_batch_integrity = original_integrity
    assert report["passed"], report["blockers"]
    assert report["decision"] == "go"
    projection = report["executionReadiness"]["throughputProjection"]
    assert projection["available"] is True
    assert projection["perWorkerObjectsPerHour"] == 50.0
    assert projection["committedConcurrency"] == 10
    assert projection["projectedObjectsPerHour"] == 500.0
    warn_text = "\n".join(report["warnings"])
    assert "per-worker projection" in warn_text
    assert "unproven assumption" in warn_text


def test_scale_readiness_projection_requires_reliabletask_backend():
    """承诺并发必须有 reliabletask 队列背书；否则不计入投影，回落 wall-clock 吞吐阻断。"""
    _save_spec(queue_backend="memory", max_concurrency=10)
    root = batch_root(TASK, "projection_no_queue")
    _write_env_ready("projection_no_queue")
    write_json(
        root / "_shared" / "task_workflow_state.json",
        {
            "status": "succeeded",
            "throughput": {
                "objectsPerHour": 2.05,
                "agentActive": {
                    "finishedAuthorJobs": 50,
                    "authorActiveSeconds": 3600.0,
                    "finishedAuthorJobsPerHour": 50.0,
                    "effectiveWorkerCount": 1,
                    "perWorkerObjectsPerHour": 50.0,
                },
            },
            "quality": {"firstPassRate": 0.82},
        },
    )
    write_json(root / "_shared" / "token_ledger.json", {"summary": {"unitCost": 1}})
    write_json(root / "_shared" / "gamma_import_report.json", {"status": "passed"})
    write_json(release_root("projection_nq_release") / "release_manifest.json", {"releaseId": "projection_nq_release"})

    import task.target_selection as target_selection
    import verify.scale_readiness as scale_readiness

    original = target_selection.audit_managed_batch
    original_integrity = scale_readiness.scan_runtime_batch_integrity
    try:
        target_selection.audit_managed_batch = lambda task_id, batch_id: {
            "targetCount": 1,
            "lanePassed": {"homepage": 1, "article": 1, "image": 1},
            "failedLaneCount": 0,
            "failedLanes": [],
            "abandonedCount": 0,
            "abandonedContentCount": 0,
        }
        scale_readiness.scan_runtime_batch_integrity = lambda task_id, batch_id: {
            "passed": True,
            "stats": {"postCount": 5, "articleCount": 4, "imageCount": 1, "assetCount": 5},
            "issues": [],
        }
        report = build_scale_readiness_report(
            TASK,
            "projection_no_queue",
            daily_target=10_000,
            release_id="projection_nq_release",
            require_import=True,
        )
    finally:
        target_selection.audit_managed_batch = original
        scale_readiness.scan_runtime_batch_integrity = original_integrity
    text = "\n".join(report["blockers"])
    assert not report["passed"]
    assert "daily target >=10000 requires queueBackend=reliabletask" in text
    assert "measured throughput 2.0500 objects/hour < required 416.6667 objects/hour" in text
    assert report["executionReadiness"]["throughputProjection"]["available"] is False


def test_scale_readiness_blocks_when_measured_throughput_is_below_target():
    _save_spec()
    root = batch_root(TASK, "slow")
    _write_env_ready("slow")
    write_json(
        root / "_shared" / "task_workflow_state.json",
        {
            "status": "succeeded",
            "throughput": {"objectsPerHour": 45.6},
            "quality": {"firstPassRate": 0.82},
        },
    )
    write_json(root / "_shared" / "token_ledger.json", {"summary": {"unitCost": 1}})
    write_json(root / "_shared" / "gamma_import_report.json", {"status": "passed"})
    write_json(release_root("slow_release") / "release_manifest.json", {"releaseId": "slow_release"})

    import task.target_selection as target_selection
    import verify.scale_readiness as scale_readiness

    original = target_selection.audit_managed_batch
    original_integrity = scale_readiness.scan_runtime_batch_integrity
    try:
        target_selection.audit_managed_batch = lambda task_id, batch_id: {
            "targetCount": 1,
            "lanePassed": {"homepage": 1, "article": 1, "image": 1},
            "failedLaneCount": 0,
            "failedLanes": [],
            "abandonedCount": 0,
            "abandonedContentCount": 0,
        }
        scale_readiness.scan_runtime_batch_integrity = lambda task_id, batch_id: {
            "passed": True,
            "stats": {"postCount": 5, "articleCount": 4, "imageCount": 1, "assetCount": 5},
            "issues": [],
        }
        report = build_scale_readiness_report(
            TASK,
            "slow",
            daily_target=10_000,
            release_id="slow_release",
            require_import=True,
        )
    finally:
        target_selection.audit_managed_batch = original
        scale_readiness.scan_runtime_batch_integrity = original_integrity
    text = "\n".join(report["blockers"])
    assert not report["passed"]
    assert "measured throughput 45.6000 objects/hour < required 416.6667 objects/hour" in text


def test_scale_readiness_reports_and_blocks_creator_overload_for_100_level():
    spec = _save_spec()
    spec["workflowPolicy"] = {"requireCreatorAssignment": True}
    store.save_spec(spec)
    root = batch_root(TASK, "creator_overload")
    write_json(
        root / "_shared" / "content_plan_packet.json",
        {
            "schemaVersion": "quwoquan_data.content_plan_packet",
            "items": [
                {
                    "ref": "九寨沟_planning_consultation",
                    "kind": "entity",
                    "carrier": "article",
                    "contentType": "article",
                    "entityRefs": ["/entity/地点/景区/九寨沟"],
                    "tagRefs": ["Topic/旅行"],
                    **_creator_assignment(),
                },
                {
                    "ref": "九寨沟_decision_experience",
                    "kind": "entity",
                    "carrier": "article",
                    "contentType": "article",
                    "entityRefs": ["/entity/地点/景区/九寨沟"],
                    "tagRefs": ["Topic/旅行"],
                    **_creator_assignment(),
                },
            ],
        },
    )
    report = build_scale_readiness_report(
        TASK,
        "creator_overload",
        daily_target=100,
        target_goal=100,
        min_pass_rate=0.9,
        require_import=False,
    )
    assert report["creatorLoad"]["creatorCount"] == 1
    assert report["creatorLoad"]["maxPlannedPerCreator"] == 2
    assert "qwq_creator_travel_blogger_chuanxi_001" in report["creatorLoad"]["overloadedCreatorProfileIds"]
    assert any("creator load exceeds publishCadence.maxDailyPosts=1" in item for item in report["blockers"])

__all__ = [name for name in globals() if not name.startswith("__")]
