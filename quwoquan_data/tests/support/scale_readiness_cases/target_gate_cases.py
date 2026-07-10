"""Quality target and source admission funnel cases."""
from __future__ import annotations

import sys
from pathlib import Path

_CASES_DIR = Path(__file__).resolve().parent
if str(_CASES_DIR) not in sys.path:
    sys.path.insert(0, str(_CASES_DIR))

from common import *  # noqa: F401,F403

def test_scale_readiness_target_gate_reports_funnel_and_blocks_low_capacity():
    spec = _save_spec()
    spec["scope"]["coverageTargets"] = [
        {"entityType": "地点/景区", "name": f"四川景区{i:02d}"}
        for i in range(25)
    ]
    store.save_spec(spec)
    batch = "target_gate_low_capacity"
    root = batch_root(TASK, batch)
    write_json(
        root / "_shared" / "env_ready_report.json",
        {
            "schemaVersion": "quwoquan_data.env_ready_report",
            "ready": True,
            "preflight": {"ready": True, "issues": []},
            "cursorStartup": {
                "checked": True,
                "ready": False,
                "probeType": "agent_prompt_smoke",
                "error": "internal error",
            },
        },
    )
    write_json(
        root / "_shared" / "task_workflow_state.json",
        {
            "status": "succeeded",
            "throughput": {"objectsPerHour": 500},
            "quality": {"firstPassRate": 0.82},
        },
    )
    _write_token_ledger(batch)
    write_json(root / "_shared" / "gamma_import_report.json", {"status": "passed"})
    write_json(root / "_shared" / "quality_target_report.json", {"qualityPassedObjectCount": 14})
    write_json(release_root("target_gate_low_capacity_release") / "release_manifest.json", {"releaseId": "target_gate_low_capacity_release"})
    write_json(
        root / "_shared" / "content_plan_packet.json",
        {
            "schemaVersion": "quwoquan_data.content_plan_packet/1",
            "items": [
                {"ref": f"article_{i}", "carrier": "article"}
                for i in range(25)
            ]
            + [
                {"ref": f"image_{i}", "carrier": "image"}
                for i in range(10)
            ],
        },
    )

    import task.target_selection as target_selection
    import verify.scale_readiness as scale_readiness

    original = target_selection.audit_managed_batch
    original_integrity = scale_readiness.scan_runtime_batch_integrity
    try:
        target_selection.audit_managed_batch = lambda task_id, batch_id: {
            "targetCount": 25,
            "lanePassed": {"homepage": 14, "article": 35, "image": 10},
            "failedLaneCount": 11,
            "failedLanes": [{"entity": "四川景区01", "lane": "homepage", "issues": ["homepage sources=0"]}],
            "abandonedCount": 11,
            "abandonedContentCount": 0,
            "replacementCount": 0,
        }
        scale_readiness.scan_runtime_batch_integrity = lambda task_id, batch_id: {
            "passed": True,
            "stats": {"postCount": 14, "articleCount": 10, "imageCount": 4, "assetCount": 4},
            "issues": [],
        }
        report = build_scale_readiness_report(
            TASK,
            batch,
            daily_target=10_000,
            release_id="target_gate_low_capacity_release",
            require_import=True,
            target_goal=100,
            min_pass_rate=0.9,
            mode="trial",
        )
    finally:
        target_selection.audit_managed_batch = original
        scale_readiness.scan_runtime_batch_integrity = original_integrity

    assert not report["passed"]
    text = "\n".join(report["blockers"])
    assert "Cursor SDK startup probe failed in batch env_ready_report" in text
    assert "quality target satisfaction 14.00% < 90%" in text
    assert "firstPassRate 82.00% < 90%" in text
    assert "source-ready object capacity 0 < required 120" in text
    assert report["qualityTarget"]["qualityPassedObjectCount"] == 14
    assert report["qualityTarget"]["targetSatisfactionRate"] == 0.14
    assert report["funnel"]["targeted"] == 100
    assert report["funnel"]["contentPlanned"] == 35
    assert report["funnel"]["reviewPassed"] == 14
    assert report["sourceAdmission"]["sourceReadyObjectCapacity"] == 0


def test_scale_readiness_dynamic_site_supply_image_reports_true_capacity():
    import verify.scale_readiness as scale_readiness

    spec = _save_spec()
    spec["scope"]["coverageTargets"] = [{"entityType": "主题/风光", "name": "风光摄影"}]
    spec["content"]["quotas"] = {
        "entityHomepagesPerTarget": 0,
        "entityArticlesPerTarget": 0,
        "imageWorksPerTarget": 100,
        "routeArticles": 0,
    }
    spec.setdefault("content", {}).setdefault("research", {})["lanes"] = ["image"]
    spec.setdefault("workflowPolicy", {})["siteSupplyDynamicContentPlan"] = True
    store.save_spec(spec)
    batch = "target_gate_dynamic_site_supply_capacity"
    root = batch_root(TASK, batch)
    _write_env_ready(batch)
    _write_token_ledger(batch)
    write_json(
        root / "_shared" / "task_workflow_state.json",
        {
            "status": "succeeded",
            "throughput": {"objectsPerHour": 5_000},
            "quality": {"firstPassRate": 1.0, "reviewedRefs": 100, "repairedRefs": 0},
        },
    )
    write_json(root / "_shared" / "gamma_import_report.json", {"status": "passed"})
    write_json(root / "_shared" / "quality_target_report.json", {"qualityPassedObjectCount": 100})
    write_json(
        root / "_shared" / "content_plan_packet.json",
        {
            "schemaVersion": "quwoquan_data.content_plan_packet/1",
            "items": [{"ref": f"image_{i}", "carrier": "image"} for i in range(100)],
        },
    )
    write_json(
        root / "_shared" / "site_supply_content_plan_report.json",
        {
            "schemaVersion": "quwoquan.site_supply.content_plan_report/1",
            "vertical": "photography",
            "siteId": "pinterest",
            "batchId": "h100_real_pin_4",
            "selectedCount": 100,
            "requestedCount": 100,
            "itemCount": 100,
            "eligibleAvailableCount": 100,
        },
    )
    write_json(
        Path(scale_readiness.RUNTIME_ROOT)
        / "site_supply"
        / "photography"
        / "pinterest"
        / "h100_real_pin_4"
        / "_shared"
        / "attributed_asset_ingest_report.json",
        {
            "schemaVersion": "quwoquan.site_supply.attributed_asset_ingest_report/1",
            "funnel": {"qualifiedImageWorks": 116},
        },
    )
    write_json(
        release_root("target_gate_dynamic_site_supply_capacity_release") / "release_manifest.json",
        {"releaseId": "target_gate_dynamic_site_supply_capacity_release"},
    )

    import task.target_selection as target_selection

    original = target_selection.audit_managed_batch
    original_integrity = scale_readiness.scan_runtime_batch_integrity
    try:
        target_selection.audit_managed_batch = lambda task_id, batch_id: {
            "targetCount": 1,
            "lanePassed": {"homepage": 0, "article": 0, "image": 1},
            "failedLaneCount": 0,
            "failedLanes": [],
            "abandonedCount": 0,
            "abandonedContentCount": 0,
            "replacementCount": 0,
        }
        scale_readiness.scan_runtime_batch_integrity = lambda task_id, batch_id: {
            "passed": True,
            "stats": {"postCount": 100, "articleCount": 0, "imageCount": 100, "assetCount": 100},
            "issues": [],
        }
        report = build_scale_readiness_report(
            TASK,
            batch,
            daily_target=10_000,
            release_id="target_gate_dynamic_site_supply_capacity_release",
            require_import=True,
            source_ready_goal=120,
            target_goal=100,
            min_pass_rate=0.9,
            mode="trial",
        )
    finally:
        target_selection.audit_managed_batch = original
        scale_readiness.scan_runtime_batch_integrity = original_integrity

    assert not report["passed"]
    assert report["sourceAdmission"]["sourceReadyObjectCapacity"] == 116
    assert "source-ready object capacity 116 < required 120" in "\n".join(report["blockers"])

__all__ = [name for name in globals() if not name.startswith("__")]
