"""Release inference and abandoned-content closure cases."""
from __future__ import annotations

from common import *  # noqa: F401,F403

def test_scale_readiness_infers_release_id_from_workflow_state():
    _save_spec()
    root = batch_root(TASK, "state_release")
    _write_env_ready("state_release")
    release_id = "state_release_id"
    write_json(
        root / "_shared" / "task_workflow_state.json",
        {
            "status": "succeeded",
            "releaseId": release_id,
            "throughput": {"objectsPerHour": 500},
            "quality": {"firstPassRate": 0.82},
        },
    )
    _write_token_ledger("state_release")
    write_json(root / "_shared" / "gamma_import_report.json", {"status": "passed"})
    write_json(release_root(release_id) / "release_manifest.json", {"releaseId": release_id})

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
            "state_release",
            daily_target=10_000,
            require_import=True,
        )
    finally:
        target_selection.audit_managed_batch = original
        scale_readiness.scan_runtime_batch_integrity = original_integrity

    assert report["passed"], report["blockers"]
    assert report["executionReadiness"]["releaseId"] == release_id


def test_scale_readiness_blocks_abandoned_content_even_after_workflow_success():
    _save_spec()
    spec = store.load_spec(TASK)
    spec["workflowPolicy"] = {"allowPartialContent": False}
    store.save_spec(spec)
    root = batch_root(TASK, "abandoned_green")
    _write_env_ready("abandoned_green")
    write_json(
        root / "_shared" / "task_workflow_state.json",
        {
            "status": "succeeded",
            "throughput": {"objectsPerHour": 500},
            "quality": {"firstPassRate": 0.82},
        },
    )
    _write_token_ledger("abandoned_green")
    write_json(root / "_shared" / "gamma_import_report.json", {"status": "passed"})
    write_json(release_root("abandoned_release") / "release_manifest.json", {"releaseId": "abandoned_release"})

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
            "abandonedContentCount": 1,
        }
        scale_readiness.scan_runtime_batch_integrity = lambda task_id, batch_id: {
            "passed": True,
            "stats": {"postCount": 4, "articleCount": 4, "imageCount": 0, "assetCount": 4},
            "issues": [],
        }
        report = build_scale_readiness_report(
            TASK,
            "abandoned_green",
            daily_target=10_000,
            release_id="abandoned_release",
            require_import=True,
        )
    finally:
        target_selection.audit_managed_batch = original
        scale_readiness.scan_runtime_batch_integrity = original_integrity
    text = "\n".join(report["blockers"])
    assert not report["passed"]
    assert "zero abandoned content objects" in text
    assert "materialized image count 0 < expected 1" in text


def test_scale_readiness_trial_allows_low_abandoned_content_ratio():
    _save_spec()
    spec = store.load_spec(TASK)
    spec["scope"]["coverageTargets"] = [
        {"entityType": "地点/景区", "name": f"景区{i}"}
        for i in range(20)
    ]
    store.save_spec(spec)
    root = batch_root(TASK, "trial_abandoned_content")
    _write_env_ready("trial_abandoned_content")
    write_json(
        root / "_shared" / "task_workflow_state.json",
        {
            "status": "succeeded",
            "throughput": {"objectsPerHour": 500},
            "quality": {"firstPassRate": 0.82},
        },
    )
    _write_token_ledger("trial_abandoned_content")
    write_json(root / "_shared" / "gamma_import_report.json", {"status": "passed"})
    write_json(
        release_root("trial_abandoned_content_release") / "release_manifest.json",
        {"releaseId": "trial_abandoned_content_release"},
    )

    import task.target_selection as target_selection
    import verify.scale_readiness as scale_readiness

    original = target_selection.audit_managed_batch
    original_integrity = scale_readiness.scan_runtime_batch_integrity
    try:
        target_selection.audit_managed_batch = lambda task_id, batch_id: {
            "targetCount": 20,
            "lanePassed": {"homepage": 20, "article": 20, "image": 20},
            "failedLaneCount": 0,
            "failedLanes": [],
            "abandonedCount": 0,
            "abandonedContentCount": 1,
            "abandonedContentObjects": [
                {
                    "ref": "景区7_decision_experience",
                    "reason": "quality_gate_react_exhausted",
                    "status": "abandoned",
                }
            ],
        }
        scale_readiness.scan_runtime_batch_integrity = lambda task_id, batch_id: {
            "passed": True,
            "stats": {"postCount": 119, "articleCount": 79, "imageCount": 20, "assetCount": 119},
            "issues": [],
        }
        report = build_scale_readiness_report(
            TASK,
            "trial_abandoned_content",
            daily_target=10_000,
            release_id="trial_abandoned_content_release",
            require_import=True,
            mode="trial",
        )
    finally:
        target_selection.audit_managed_batch = original
        scale_readiness.scan_runtime_batch_integrity = original_integrity
    assert report["passed"], report["blockers"]
    assert report["partialDelivery"]["abandonedContentByType"] == {"article": 1}
    assert report["partialDelivery"]["fulfillment"]["article"] == 0.9875
    assert any("partial article delivery accepted" in item for item in report["warnings"])


def test_scale_readiness_classifies_image_shortfall_refs_as_image():
    _save_spec()
    root = batch_root(TASK, "trial_image_shortfall")
    _write_env_ready("trial_image_shortfall")
    write_json(
        root / "_shared" / "task_workflow_state.json",
        {
            "status": "succeeded",
            "throughput": {"objectsPerHour": 500},
            "quality": {"firstPassRate": 0.82},
        },
    )
    _write_token_ledger("trial_image_shortfall")
    write_json(root / "_shared" / "gamma_import_report.json", {"status": "passed"})
    write_json(
        release_root("trial_image_shortfall_release") / "release_manifest.json",
        {"releaseId": "trial_image_shortfall_release"},
    )

    import task.target_selection as target_selection
    import verify.scale_readiness as scale_readiness

    original = target_selection.audit_managed_batch
    original_integrity = scale_readiness.scan_runtime_batch_integrity
    try:
        target_selection.audit_managed_batch = lambda task_id, batch_id: {
            "targetCount": 20,
            "lanePassed": {"homepage": 20, "article": 20, "image": 19},
            "failedLaneCount": 0,
            "failedLanes": [],
            "abandonedCount": 0,
            "abandonedContentCount": 1,
            "abandonedContentObjects": [
                {
                    "ref": "景区7_image_shortfall_1",
                    "reason": "sources directory missing",
                    "status": "abandoned",
                }
            ],
        }
        scale_readiness.scan_runtime_batch_integrity = lambda task_id, batch_id: {
            "passed": True,
            "stats": {"postCount": 119, "articleCount": 80, "imageCount": 19, "assetCount": 119},
            "issues": [],
        }
        report = build_scale_readiness_report(
            TASK,
            "trial_image_shortfall",
            daily_target=10_000,
            release_id="trial_image_shortfall_release",
            require_import=True,
            mode="trial",
        )
    finally:
        target_selection.audit_managed_batch = original
        scale_readiness.scan_runtime_batch_integrity = original_integrity
    assert report["partialDelivery"]["abandonedContentByType"] == {"image": 1}
    assert report["partialDelivery"]["fulfillment"]["image"] == 0.95


def test_scale_readiness_trial_accepts_reasoned_reject_completion_when_target_met():
    _save_spec()
    root = batch_root(TASK, "trial_reasoned_reject_complete")
    write_json(
        root / "_shared" / "env_ready_report.json",
        {
            "schemaVersion": "quwoquan_data.env_ready_report",
            "ready": True,
            "cursorStartup": {"checked": True, "ready": True},
        },
    )
    release_id = "trial_reasoned_reject_complete_release"
    write_json(
        root / "_shared" / "task_workflow_state.json",
        {
            "status": "completed_with_reasoned_rejects",
            "releaseId": release_id,
            "throughput": {"objectsPerHour": 500},
            "quality": {"firstPassRate": 0.82},
        },
    )
    _write_token_ledger("trial_reasoned_reject_complete")
    write_json(root / "_shared" / "gamma_import_report.json", {"status": "passed"})
    write_json(release_root(release_id) / "release_manifest.json", {"releaseId": release_id})

    import task.target_selection as target_selection
    import verify.scale_readiness as scale_readiness

    original = target_selection.audit_managed_batch
    original_integrity = scale_readiness.scan_runtime_batch_integrity
    try:
        target_selection.audit_managed_batch = lambda task_id, batch_id: {
            "targetCount": 1,
            "lanePassed": {"homepage": 1, "article": 1, "image": 1},
            "failedLaneCount": 1,
            "failedLanes": [{"entity": "九寨沟", "lane": "article", "issues": ["reasoned reject"]}],
            "abandonedCount": 0,
            "abandonedContentCount": 1,
            "abandonedContentObjects": [
                {"ref": "九寨沟_article_reject", "reason": "reasoned_reject", "status": "abandoned"}
            ],
        }
        scale_readiness.scan_runtime_batch_integrity = lambda task_id, batch_id: {
            "passed": True,
            "stats": {"postCount": 5, "articleCount": 4, "imageCount": 1, "assetCount": 5},
            "issues": [],
        }
        report = build_scale_readiness_report(
            TASK,
            "trial_reasoned_reject_complete",
            daily_target=100,
            target_goal=5,
            min_pass_rate=0.7,
            source_ready_goal=0,
            release_id=release_id,
            require_import=True,
            mode="trial",
        )
    finally:
        target_selection.audit_managed_batch = original
        scale_readiness.scan_runtime_batch_integrity = original_integrity

    assert report["passed"], report["blockers"]
    assert report["workflowState"]["status"] == "completed_with_reasoned_rejects"
    assert any("completed_with_reasoned_rejects accepted for trial" in item for item in report["warnings"])


def test_scale_readiness_commercial_closure_blocks_failed_lane_even_with_partial_flag():
    spec = _save_spec()
    spec["workflowPolicy"] = {
        "allowPartialContent": True,
        "articleCommercialClosure": True,
        "targetObjectCount": 100,
    }
    store.save_spec(spec)
    batch = "commercial_failed_lane_block"
    root = batch_root(TASK, batch)
    _write_env_ready(batch)
    write_json(
        root / "_shared" / "task_workflow_state.json",
        {
            "status": "succeeded",
            "throughput": {"objectsPerHour": 500},
            "quality": {"firstPassRate": 0.95},
        },
    )
    _write_token_ledger(batch)
    write_json(root / "_shared" / "gamma_import_report.json", {"status": "passed"})
    release_id = "commercial_failed_lane_release"
    write_json(
        release_root(release_id) / "release_manifest.json",
        {"releaseId": release_id, "sourceTaskId": TASK, "sourceBatchId": batch},
    )

    import task.target_selection as target_selection
    import verify.scale_readiness as scale_readiness

    original = target_selection.audit_managed_batch
    original_runtime = scale_readiness.scan_runtime_batch_integrity
    original_release = scale_readiness.scan_release_integrity
    try:
        target_selection.audit_managed_batch = lambda task_id, batch_id: {
            "targetCount": 1,
            "lanePassed": {"homepage": 0, "article": 1, "image": 1},
            "failedLaneCount": 1,
            "failedLanes": [{"entity": "九寨沟", "lane": "homepage", "issues": ["homepage missing"]}],
            "abandonedCount": 0,
            "abandonedContentCount": 0,
            "replacementCount": 0,
        }
        scale_readiness.scan_runtime_batch_integrity = lambda task_id, batch_id: {
            "passed": True,
            "stats": {"postCount": 100, "articleCount": 80, "imageCount": 20, "assetCount": 100},
            "issues": [],
        }
        scale_readiness.scan_release_integrity = lambda release_id: {
            "passed": True,
            "issues": [],
            "stats": {"postCount": 100, "articleCount": 80, "imageCount": 20, "assetCount": 100},
        }
        report = build_scale_readiness_report(
            TASK,
            batch,
            daily_target=100,
            target_goal=100,
            min_pass_rate=0.9,
            release_id=release_id,
            require_import=True,
        )
    finally:
        target_selection.audit_managed_batch = original
        scale_readiness.scan_runtime_batch_integrity = original_runtime
        scale_readiness.scan_release_integrity = original_release

    assert not report["passed"]
    assert report["funnel"]["targeted"] == 100
    assert "managed batch audit has failedLaneCount=1" in "\n".join(report["blockers"])


def test_scale_readiness_commercial_closure_blocks_release_integrity_issue():
    spec = _save_spec()
    spec["workflowPolicy"] = {
        "allowPartialContent": True,
        "articleCommercialClosure": True,
        "targetObjectCount": 100,
    }
    store.save_spec(spec)
    batch = "commercial_release_integrity_block"
    root = batch_root(TASK, batch)
    _write_env_ready(batch)
    write_json(
        root / "_shared" / "task_workflow_state.json",
        {
            "status": "succeeded",
            "throughput": {"objectsPerHour": 500},
            "quality": {"firstPassRate": 0.95},
        },
    )
    _write_token_ledger(batch)
    write_json(root / "_shared" / "gamma_import_report.json", {"status": "passed"})
    release_id = "commercial_release_integrity_block_release"
    write_json(
        release_root(release_id) / "release_manifest.json",
        {"releaseId": release_id, "sourceTaskId": TASK, "sourceBatchId": batch},
    )

    import task.target_selection as target_selection
    import verify.scale_readiness as scale_readiness

    original = target_selection.audit_managed_batch
    original_runtime = scale_readiness.scan_runtime_batch_integrity
    original_release = scale_readiness.scan_release_integrity
    try:
        target_selection.audit_managed_batch = lambda task_id, batch_id: {
            "targetCount": 1,
            "lanePassed": {"homepage": 1, "article": 1, "image": 1},
            "failedLaneCount": 0,
            "failedLanes": [],
            "abandonedCount": 0,
            "abandonedContentCount": 0,
            "replacementCount": 0,
        }
        scale_readiness.scan_runtime_batch_integrity = lambda task_id, batch_id: {
            "passed": True,
            "stats": {"postCount": 100, "articleCount": 80, "imageCount": 20, "assetCount": 100},
            "issues": [],
        }
        scale_readiness.scan_release_integrity = lambda release_id: {
            "passed": False,
            "issues": ["release missing primary entity homepage(s): 九寨沟"],
            "stats": {"postCount": 100, "articleCount": 80, "imageCount": 20, "assetCount": 100},
        }
        report = build_scale_readiness_report(
            TASK,
            batch,
            daily_target=100,
            target_goal=100,
            min_pass_rate=0.9,
            release_id=release_id,
            require_import=True,
        )
    finally:
        target_selection.audit_managed_batch = original
        scale_readiness.scan_runtime_batch_integrity = original_runtime
        scale_readiness.scan_release_integrity = original_release

    assert not report["passed"]
    assert "release integrity failed: release missing primary entity homepage(s): 九寨沟" in "\n".join(
        report["blockers"]
    )


def test_scale_readiness_commercial_closure_blocks_text_only_release():
    spec = _save_spec()
    spec["workflowPolicy"] = {
        "allowPartialContent": True,
        "articleCommercialClosure": True,
        "targetObjectCount": 1,
    }
    spec["content"]["quotas"] = {
        "entityHomepagesPerTarget": 0,
        "entityArticlesPerTarget": 1,
        "imageWorksPerTarget": 0,
        "routeArticles": 0,
    }
    store.save_spec(spec)
    batch = "commercial_text_only_block"
    root = batch_root(TASK, batch)
    _write_env_ready(batch)
    write_json(
        root / "_shared" / "task_workflow_state.json",
        {
            "status": "succeeded",
            "throughput": {"objectsPerHour": 500},
            "quality": {"firstPassRate": 1.0},
        },
    )
    _write_token_ledger(batch)
    write_json(root / "_shared" / "gamma_import_report.json", {"status": "passed"})
    release_id = "commercial_text_only_release"
    release_dir = release_root(release_id)
    write_json(
        release_dir / "release_manifest.json",
        {"releaseId": release_id, "sourceTaskId": TASK, "sourceBatchId": batch},
    )
    write_json(
        release_dir / "posts" / "article" / "攻略" / "text_only_topic" / "manifest.json",
        {
            "carrier": "article",
            "contentType": "article",
            "publishMediaMode": "text_only",
            "topicId": "text_only_topic",
        },
    )

    import task.target_selection as target_selection
    import verify.scale_readiness as scale_readiness

    original = target_selection.audit_managed_batch
    original_runtime = scale_readiness.scan_runtime_batch_integrity
    original_release = scale_readiness.scan_release_integrity
    try:
        target_selection.audit_managed_batch = lambda task_id, batch_id: {
            "targetCount": 1,
            "lanePassed": {"homepage": 0, "article": 1, "image": 0},
            "failedLaneCount": 0,
            "failedLanes": [],
            "abandonedCount": 0,
            "abandonedContentCount": 0,
            "replacementCount": 0,
        }
        scale_readiness.scan_runtime_batch_integrity = lambda task_id, batch_id: {
            "passed": True,
            "stats": {"postCount": 1, "articleCount": 1, "imageCount": 0, "assetCount": 0},
            "issues": [],
        }
        scale_readiness.scan_release_integrity = lambda release_id: {
            "passed": True,
            "issues": [],
            "stats": {"postCount": 1, "articleCount": 1, "imageCount": 0, "assetCount": 0},
        }
        report = build_scale_readiness_report(
            TASK,
            batch,
            daily_target=100,
            target_goal=1,
            min_pass_rate=0.9,
            release_id=release_id,
            require_import=True,
        )
    finally:
        target_selection.audit_managed_batch = original
        scale_readiness.scan_runtime_batch_integrity = original_runtime
        scale_readiness.scan_release_integrity = original_release

    assert not report["passed"]
    assert report["releaseIntegrity"]["textOnlyArticles"] == ["text_only_topic"]
    assert "commercial mixed-layout gate failed" in "\n".join(report["blockers"])


def test_scale_readiness_accepts_text_only_release_with_explicit_flag():
    """R-CS10 收口口径（2026-07-06 裁定）：text_only 文章仅在显式传参时可准出，默认仍阻断。"""
    spec = _save_spec()
    spec["workflowPolicy"] = {
        "allowPartialContent": True,
        "articleCommercialClosure": True,
        "targetObjectCount": 1,
    }
    spec["content"]["quotas"] = {
        "entityHomepagesPerTarget": 0,
        "entityArticlesPerTarget": 1,
        "imageWorksPerTarget": 0,
        "routeArticles": 0,
    }
    store.save_spec(spec)
    batch = "commercial_text_only_accept"
    root = batch_root(TASK, batch)
    _write_env_ready(batch)
    write_json(
        root / "_shared" / "task_workflow_state.json",
        {
            "status": "succeeded",
            "throughput": {"objectsPerHour": 500},
            "quality": {"firstPassRate": 1.0},
        },
    )
    _write_token_ledger(batch)
    write_json(root / "_shared" / "gamma_import_report.json", {"status": "passed"})
    release_id = "commercial_text_only_accept_release"
    release_dir = release_root(release_id)
    write_json(
        release_dir / "release_manifest.json",
        {"releaseId": release_id, "sourceTaskId": TASK, "sourceBatchId": batch},
    )
    write_json(
        release_dir / "posts" / "article" / "攻略" / "text_only_topic" / "manifest.json",
        {
            "carrier": "article",
            "contentType": "article",
            "publishMediaMode": "text_only",
            "topicId": "text_only_topic",
        },
    )

    import task.target_selection as target_selection
    import verify.scale_readiness as scale_readiness

    original = target_selection.audit_managed_batch
    original_runtime = scale_readiness.scan_runtime_batch_integrity
    original_release = scale_readiness.scan_release_integrity
    try:
        target_selection.audit_managed_batch = lambda task_id, batch_id: {
            "targetCount": 1,
            "lanePassed": {"homepage": 0, "article": 1, "image": 0},
            "failedLaneCount": 0,
            "failedLanes": [],
            "abandonedCount": 0,
            "abandonedContentCount": 0,
            "replacementCount": 0,
        }
        scale_readiness.scan_runtime_batch_integrity = lambda task_id, batch_id: {
            "passed": True,
            "stats": {"postCount": 1, "articleCount": 1, "imageCount": 0, "assetCount": 0},
            "issues": [],
        }
        scale_readiness.scan_release_integrity = lambda release_id: {
            "passed": True,
            "issues": [],
            "stats": {"postCount": 1, "articleCount": 1, "imageCount": 0, "assetCount": 0},
        }
        report = build_scale_readiness_report(
            TASK,
            batch,
            daily_target=100,
            target_goal=1,
            min_pass_rate=0.9,
            release_id=release_id,
            require_import=True,
            accept_text_only_articles=True,
        )
    finally:
        target_selection.audit_managed_batch = original
        scale_readiness.scan_runtime_batch_integrity = original_runtime
        scale_readiness.scan_release_integrity = original_release

    blockers = "\n".join(report["blockers"])
    assert "commercial mixed-layout gate failed" not in blockers
    warn_text = "\n".join(report["warnings"])
    assert "text_only articles explicitly accepted" in warn_text
    assert report["releaseIntegrity"]["textOnlyArticles"] == ["text_only_topic"]
    assert report["releaseIntegrity"]["textOnlyArticlesAccepted"] is True
    # source-ready 门等其他 blocker 不受本口径影响；这里只断言 text_only 门被显式接受。

__all__ = [name for name in globals() if not name.startswith("__")]
