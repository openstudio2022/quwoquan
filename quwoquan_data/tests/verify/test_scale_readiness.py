"""Scale readiness gate contract tests."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
_TMP = Path(tempfile.mkdtemp(prefix="scale_readiness_"))
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_RELEASE_ROOT"] = str(_TMP / "release")
os.environ["QWQ_COMMITTED_TASKS_ROOT"] = str(_TMP / "tasks")
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from _common.io import write_json  # noqa: E402
from _common.paths import batch_root, release_root  # noqa: E402
from task import store  # noqa: E402
from verify.scale_readiness import build_scale_readiness_report  # noqa: E402


TASK = "旅行/地域/四川省/景区/规模门"
BATCH = "b1"


def _save_spec() -> dict:
    spec = store.scaffold_spec(
        vertical="travel",
        organize_by="地域",
        key="四川省",
        category="景区",
        name="规模门",
        scope={
            "region": "四川省",
            "entityTypes": ["地点/景区"],
            "coverageTargets": [{"entityType": "地点/景区", "name": "九寨沟"}],
        },
        content={
            "modalityContract": "separated_research",
            "queueBackend": "reliabletask",
            "research": {"maxConcurrency": 10},
            "quotas": {
                "entityHomepagesPerTarget": 1,
                "entityArticlesPerTarget": 4,
                "imageWorksPerTarget": 1,
                "routeArticles": 0,
            },
        },
    )
    spec["status"] = "active"
    store.save_spec(spec)
    return spec


def _write_env_ready(batch_id: str) -> None:
    write_json(
        batch_root(TASK, batch_id) / "_shared" / "env_ready_report.json",
        {
            "schemaVersion": "quwoquan_data.env_ready_report",
            "ready": True,
            "preflight": {"ready": True, "issues": []},
        },
    )


def test_scale_readiness_blocks_manual_required_batch():
    _save_spec()
    write_json(
        batch_root(TASK, BATCH) / "task_download" / "results" / "image_fetch_gate" / "九寨沟.json",
        {
            "payload": {
                "evidenceSummary": {
                    "plannedImages": 2,
                    "downloadedImages": 0,
                    "rejectedForQuality": [
                        "sourceImage:jzg: imagePixels: 九寨沟#1 尺寸过小 600x600（要求 ≥640x426）",
                        "sourceImage:jzg: 九寨沟#2: imageFetch failed/non-image/too small",
                    ],
                }
            }
        },
    )
    write_json(
        batch_root(TASK, BATCH) / "_shared" / "task_workflow_state.json",
        {
            "status": "manual_required",
            "waitingCheckpoint": "download_plan",
            "failedObjects": [
                "九寨沟: download_repair required: article research needs >= 4 text-qualified base sources",
            ],
        },
    )
    report = build_scale_readiness_report(TASK, BATCH, daily_target=10_000, require_import=True)
    text = "\n".join(report["blockers"])
    assert not report["passed"]
    assert report["decision"] == "no_go"
    assert "workflow status must be succeeded" in text
    assert "TokenLedger evidence missing" in text
    assert "release verify cannot be proven" in text
    assert report["downloadDiagnostics"]["rejectedByCategory"]["pixel_too_small"] == 1
    assert report["downloadDiagnostics"]["rejectedByCategory"]["fetch_or_non_image"] == 1


def test_scale_readiness_passes_when_scale_evidence_is_complete(monkeypatch=None):
    _save_spec()
    root = batch_root(TASK, "green")
    _write_env_ready("green")
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
    write_json(release_root("green_release") / "release_manifest.json", {"releaseId": "green_release"})

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
            "green",
            daily_target=10_000,
            release_id="green_release",
            require_import=True,
        )
    finally:
        target_selection.audit_managed_batch = original
        scale_readiness.scan_runtime_batch_integrity = original_integrity
    assert report["passed"], report["blockers"]
    assert report["decision"] == "go"


def test_scale_readiness_allows_partial_lane_and_object_shortfall():
    _save_spec()
    root = batch_root(TASK, "partial_shortfall")
    _write_env_ready("partial_shortfall")
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
    write_json(release_root("partial_shortfall_release") / "release_manifest.json", {"releaseId": "partial_shortfall_release"})

    import task.target_selection as target_selection
    import verify.scale_readiness as scale_readiness

    original = target_selection.audit_managed_batch
    original_integrity = scale_readiness.scan_runtime_batch_integrity
    try:
        target_selection.audit_managed_batch = lambda task_id, batch_id: {
            "targetCount": 1,
            "lanePassed": {"homepage": 0, "article": 1, "image": 0},
            "failedLaneCount": 2,
            "failedLanes": [
                {"entity": "九寨沟", "lane": "homepage", "issues": ["homepage sources=0"]},
                {"entity": "九寨沟", "lane": "image", "issues": ["image rights unclear"]},
            ],
            "abandonedCount": 1,
            "abandonedContentCount": 3,
        }
        scale_readiness.scan_runtime_batch_integrity = lambda task_id, batch_id: {
            "passed": True,
            "stats": {"postCount": 2, "articleCount": 2, "imageCount": 0, "assetCount": 2},
            "issues": [],
        }
        report = build_scale_readiness_report(
            TASK,
            "partial_shortfall",
            daily_target=10_000,
            release_id="partial_shortfall_release",
            require_import=True,
        )
    finally:
        target_selection.audit_managed_batch = original
        scale_readiness.scan_runtime_batch_integrity = original_integrity
    assert report["passed"], report["blockers"]
    assert report["partialDelivery"]["allowPartialContent"] is True
    assert report["partialDelivery"]["delivered"]["posts"] == 2
    assert report["partialDelivery"]["fulfillment"]["article"] == 0.5
    assert report["partialDelivery"]["fulfillment"]["image"] == 0.0
    assert any("failedLaneCount=2" in item for item in report["warnings"])
    assert any("partial image delivery accepted" in item for item in report["warnings"])


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


def test_scale_readiness_reports_structural_open_license_image_shortage():
    _save_spec()
    root = batch_root(TASK, "open_license_shortage")
    _write_env_ready("open_license_shortage")
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
        release_root("open_license_shortage_release") / "release_manifest.json",
        {"releaseId": "open_license_shortage_release"},
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
            "abandonedCount": 10,
            "abandonedContentCount": 0,
            "replacementCount": 10,
            "abandonedObjects": [
                {
                    "entityId": f"缺图景区{i}",
                    "reason": "source_unavailable_after_auto_research: no rights-compatible open-license images discovered",
                }
                for i in range(6)
            ],
        }
        scale_readiness.scan_runtime_batch_integrity = lambda task_id, batch_id: {
            "passed": True,
            "stats": {"postCount": 5, "articleCount": 4, "imageCount": 1, "assetCount": 5},
            "issues": [],
        }
        report = build_scale_readiness_report(
            TASK,
            "open_license_shortage",
            daily_target=10_000,
            release_id="open_license_shortage_release",
            require_import=True,
        )
    finally:
        target_selection.audit_managed_batch = original
        scale_readiness.scan_runtime_batch_integrity = original_integrity
    text = "\n".join(report["blockers"])
    warning_text = "\n".join(report["warnings"])
    assert report["passed"], text
    assert "open_license_publish is under-supplied" in warning_text
    assert report["imageAssetStrategy"]["structuralOpenLicenseShortage"] is True
    assert report["abandonmentDiagnostics"]["categories"]["imageOpenLicenseShortage"] == 6


def test_scale_readiness_warns_reference_only_strategy_for_publishable_image_quota():
    _save_spec()
    spec = store.load_spec(TASK)
    spec["content"]["research"]["imageAssetStrategy"] = "reference_only_no_image_release"
    store.save_spec(spec)
    root = batch_root(TASK, "reference_only")
    _write_env_ready("reference_only")
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
        release_root("reference_only_release") / "release_manifest.json",
        {"releaseId": "reference_only_release"},
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
            "reference_only",
            daily_target=10_000,
            release_id="reference_only_release",
            require_import=True,
        )
    finally:
        target_selection.audit_managed_batch = original
        scale_readiness.scan_runtime_batch_integrity = original_integrity
    text = "\n".join(report["blockers"])
    warning_text = "\n".join(report["warnings"])
    assert report["passed"], text
    assert "reference_only_no_image_release" in warning_text
    assert report["imageAssetStrategy"]["releaseAllowed"] is False


def test_scale_readiness_trial_allows_replaced_abandoned_entity():
    _save_spec()
    spec = store.load_spec(TASK)
    spec["scope"]["reserveCoverageTargets"] = [{"entityType": "地点/景区", "name": "都江堰"}]
    store.save_spec(spec)
    root = batch_root(TASK, "trial_replaced")
    _write_env_ready("trial_replaced")
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
    write_json(release_root("trial_replaced_release") / "release_manifest.json", {"releaseId": "trial_replaced_release"})

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
            "abandonedCount": 1,
            "abandonedContentCount": 0,
            "replacementCount": 1,
            "replacementObjects": [{"entityId": "都江堰", "status": "active"}],
        }
        scale_readiness.scan_runtime_batch_integrity = lambda task_id, batch_id: {
            "passed": True,
            "stats": {"postCount": 5, "articleCount": 4, "imageCount": 1, "assetCount": 5},
            "issues": [],
        }
        report = build_scale_readiness_report(
            TASK,
            "trial_replaced",
            daily_target=10_000,
            release_id="trial_replaced_release",
            require_import=True,
            mode="trial",
        )
    finally:
        target_selection.audit_managed_batch = original
        scale_readiness.scan_runtime_batch_integrity = original_integrity
    assert report["passed"], report["blockers"]
    assert report["replacementClosure"]["closed"] is True


def test_scale_readiness_trial_closes_by_active_targets_not_replacement_history_count():
    _save_spec()
    spec = store.load_spec(TASK)
    spec["scope"]["reserveCoverageTargets"] = [
        {"entityType": "地点/景区", "name": "都江堰"},
        {"entityType": "地点/景区", "name": "青城山"},
    ]
    store.save_spec(spec)
    root = batch_root(TASK, "trial_replacement_history")
    _write_env_ready("trial_replacement_history")
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
        release_root("trial_replacement_history_release") / "release_manifest.json",
        {"releaseId": "trial_replacement_history_release"},
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
            "abandonedCount": 2,
            "abandonedContentCount": 0,
            "replacementCount": 1,
            "replacementObjects": [{"entityId": "青城山", "status": "active"}],
        }
        scale_readiness.scan_runtime_batch_integrity = lambda task_id, batch_id: {
            "passed": True,
            "stats": {"postCount": 5, "articleCount": 4, "imageCount": 1, "assetCount": 5},
            "issues": [],
        }
        report = build_scale_readiness_report(
            TASK,
            "trial_replacement_history",
            daily_target=10_000,
            release_id="trial_replacement_history_release",
            require_import=True,
            mode="trial",
        )
    finally:
        target_selection.audit_managed_batch = original
        scale_readiness.scan_runtime_batch_integrity = original_integrity
    assert report["passed"], report["blockers"]
    assert report["replacementClosure"]["activeTargetCount"] == 1
    assert report["replacementClosure"]["requiredActiveTargets"] == 1
    assert report["replacementClosure"]["closed"] is True


def test_scale_readiness_commercial_allows_replaced_abandoned_entity_with_warning():
    _save_spec()
    root = batch_root(TASK, "commercial_replaced")
    _write_env_ready("commercial_replaced")
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
    write_json(release_root("commercial_replaced_release") / "release_manifest.json", {"releaseId": "commercial_replaced_release"})

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
            "abandonedCount": 1,
            "abandonedContentCount": 0,
            "replacementCount": 1,
        }
        scale_readiness.scan_runtime_batch_integrity = lambda task_id, batch_id: {
            "passed": True,
            "stats": {"postCount": 5, "articleCount": 4, "imageCount": 1, "assetCount": 5},
            "issues": [],
        }
        report = build_scale_readiness_report(
            TASK,
            "commercial_replaced",
            daily_target=10_000,
            release_id="commercial_replaced_release",
            require_import=True,
            mode="commercial",
        )
    finally:
        target_selection.audit_managed_batch = original
        scale_readiness.scan_runtime_batch_integrity = original_integrity
    assert report["passed"], report["blockers"]
    assert not any("zero abandoned entities" in item for item in report["blockers"])
    assert any("excluded from published entity/tag refs" in item for item in report["warnings"])


def _run_all() -> None:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")


if __name__ == "__main__":
    _run_all()
