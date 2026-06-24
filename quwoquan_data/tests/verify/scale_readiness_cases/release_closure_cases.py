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
    write_json(root / "_shared" / "token_ledger.json", {"summary": {"unitCost": 1}})
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
    write_json(root / "_shared" / "token_ledger.json", {"summary": {"unitCost": 1}})
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
    write_json(root / "_shared" / "token_ledger.json", {"summary": {"unitCost": 1}})
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

__all__ = [name for name in globals() if not name.startswith("__")]
