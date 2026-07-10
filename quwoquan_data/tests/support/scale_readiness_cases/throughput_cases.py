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
    _write_token_ledger("projection_go")
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
    _write_token_ledger("projection_no_queue")
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
    _write_token_ledger("slow")
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


def test_scale_readiness_blocks_estimated_token_ledger():
    _save_spec()
    root = batch_root(TASK, "estimated_ledger")
    _write_env_ready("estimated_ledger")
    write_json(
        root / "_shared" / "task_workflow_state.json",
        {
            "status": "succeeded",
            "throughput": {"objectsPerHour": 500.0},
            "quality": {"firstPassRate": 0.82},
        },
    )
    _write_token_ledger("estimated_ledger", measurement_mode="estimated_from_artifacts")
    write_json(root / "_shared" / "gamma_import_report.json", {"status": "passed"})
    write_json(
        release_root("estimated_ledger_release") / "release_manifest.json",
        {"releaseId": "estimated_ledger_release"},
    )

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
            "estimated_ledger",
            daily_target=100,
            release_id="estimated_ledger_release",
            require_import=True,
        )
    finally:
        target_selection.audit_managed_batch = original
        scale_readiness.scan_runtime_batch_integrity = original_integrity

    text = "\n".join(report["blockers"])
    assert not report["passed"]
    assert "TokenLedger measurementMode must not be estimated_from_artifacts" in text
    assert report["executionReadiness"]["authoritativeTokenLedgerMeasurementMode"] == "estimated_from_artifacts"
    assert report["executionReadiness"]["authoritativeTokenLedgerReady"] is False


def test_scale_readiness_accepts_estimated_token_ledger_with_explicit_flag():
    """H100 口径（2026-07-06 裁定）：estimated 账本仅在显式传参时可准出，默认仍阻断。"""
    _save_spec()
    root = batch_root(TASK, "estimated_ledger_accepted")
    _write_env_ready("estimated_ledger_accepted")
    write_json(
        root / "_shared" / "task_workflow_state.json",
        {
            "status": "succeeded",
            "throughput": {"objectsPerHour": 500.0},
            "quality": {"firstPassRate": 0.95},
        },
    )
    _write_token_ledger("estimated_ledger_accepted", measurement_mode="estimated_from_artifacts")
    write_json(root / "_shared" / "gamma_import_report.json", {"status": "passed"})
    write_json(
        release_root("estimated_ledger_accepted_release") / "release_manifest.json",
        {"releaseId": "estimated_ledger_accepted_release"},
    )

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
            "estimated_ledger_accepted",
            daily_target=100,
            release_id="estimated_ledger_accepted_release",
            require_import=True,
            accept_estimated_token_ledger=True,
        )
    finally:
        target_selection.audit_managed_batch = original
        scale_readiness.scan_runtime_batch_integrity = original_integrity

    blockers = "\n".join(report["blockers"])
    assert "TokenLedger measurementMode must not be estimated_from_artifacts" not in blockers
    warn_text = "\n".join(report["warnings"])
    assert "estimated_from_artifacts explicitly accepted" in warn_text
    assert report["executionReadiness"]["estimatedTokenLedgerAccepted"] is True
    # 诚实性：显式接受不等于 authoritative 就绪。
    assert report["executionReadiness"]["authoritativeTokenLedgerReady"] is False
    assert report["passed"], report["blockers"]


def test_scale_readiness_derives_first_pass_from_review_repair_report():
    """最终修复成功不能抹掉首轮 review 失败证据。"""
    _save_spec()
    root = batch_root(TASK, "first_pass_repaired")
    _write_env_ready("first_pass_repaired")
    write_json(
        root / "_shared" / "task_workflow_state.json",
        {
            "status": "succeeded",
            "throughput": {"objectsPerHour": 500},
            "quality": {"firstPassRate": 1.0, "reviewedRefs": 5, "repairedRefs": 0},
        },
    )
    write_json(
        root / "task_workflow" / "results" / "repair_report" / "produce_review.json",
        {
            "payload": {
                "failedStage": "produce_review",
                "issues": [
                    "release missing planned post ref(s): 九寨沟__article_a, 九寨沟__article_b",
                    "九寨沟__article_a: review_gate failed: entityCoverage",
                    "九寨沟__article_b: review_gate failed: baseDraftFidelity",
                ],
            }
        },
    )
    _write_token_ledger("first_pass_repaired")
    write_json(root / "_shared" / "gamma_import_report.json", {"status": "passed"})
    write_json(release_root("first_pass_repaired_release") / "release_manifest.json", {"releaseId": "first_pass_repaired_release"})

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
            "first_pass_repaired",
            daily_target=10_000,
            release_id="first_pass_repaired_release",
            require_import=True,
        )
    finally:
        target_selection.audit_managed_batch = original
        scale_readiness.scan_runtime_batch_integrity = original_integrity
    assert report["executionReadiness"]["firstPassRate"] == 0.6
    assert report["executionReadiness"]["firstPassEvidence"]["source"] == "produce_review_repair_report"
    assert not report["passed"]
    assert any("firstPassRate 60.00% < 70%" in item for item in report["blockers"])


def test_scale_readiness_reports_and_blocks_creator_overload_for_100_level_commercial():
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
        mode="commercial",
    )
    assert report["creatorLoad"]["creatorCount"] == 1
    assert report["creatorLoad"]["maxPlannedPerCreator"] == 2
    assert report["creatorLoad"]["maxPlannedPerCreatorDay"] == 2
    assert "qwq_creator_travel_blogger_chuanxi_001" in report["creatorLoad"]["overloadedCreatorProfileIds"]
    assert any("creator load exceeds publishCadence.maxDailyPosts=1" in item for item in report["blockers"])


def test_scale_readiness_allows_creator_cadence_spread_across_days_for_commercial():
    spec = _save_spec()
    spec["workflowPolicy"] = {"requireCreatorAssignment": True}
    store.save_spec(spec)
    root = batch_root(TASK, "creator_spread_days")
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
                    "publishSchedule": {"dayOffset": 0},
                    "entityRefs": ["/entity/地点/景区/九寨沟"],
                    "tagRefs": ["Topic/旅行"],
                    **_creator_assignment(),
                },
                {
                    "ref": "九寨沟_decision_experience",
                    "kind": "entity",
                    "carrier": "article",
                    "contentType": "article",
                    "publishSchedule": {"dayOffset": 1},
                    "entityRefs": ["/entity/地点/景区/九寨沟"],
                    "tagRefs": ["Topic/旅行"],
                    **_creator_assignment(),
                },
            ],
        },
    )
    report = build_scale_readiness_report(
        TASK,
        "creator_spread_days",
        daily_target=100,
        target_goal=100,
        min_pass_rate=0.9,
        require_import=False,
        mode="commercial",
    )
    assert report["creatorLoad"]["maxPlannedPerCreator"] == 2
    assert report["creatorLoad"]["maxPlannedPerCreatorDay"] == 1
    assert not report["creatorLoad"]["overloadedCreatorProfileIds"]
    assert not any("creator load exceeds publishCadence.maxDailyPosts=1" in item for item in report["blockers"])


def test_scale_readiness_warns_creator_overload_for_100_level_trial():
    spec = _save_spec()
    spec["workflowPolicy"] = {"requireCreatorAssignment": True}
    store.save_spec(spec)
    root = batch_root(TASK, "creator_overload_trial")
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
        "creator_overload_trial",
        daily_target=100,
        target_goal=100,
        min_pass_rate=0.7,
        require_import=False,
        mode="trial",
    )
    assert "qwq_creator_travel_blogger_chuanxi_001" in report["creatorLoad"]["overloadedCreatorProfileIds"]
    assert not any("creator load exceeds publishCadence.maxDailyPosts=1" in item for item in report["blockers"])
    assert any("trial creator load exceeds publishCadence.maxDailyPosts=1" in item for item in report["warnings"])

__all__ = [name for name in globals() if not name.startswith("__")]
