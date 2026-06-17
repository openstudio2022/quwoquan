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
                "九寨沟: download_repair required: only 0 article source unit(s) with images",
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


def test_scale_readiness_commercial_blocks_replaced_abandoned_entity():
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
    assert not report["passed"]
    assert "zero abandoned entities" in "\n".join(report["blockers"])


def _run_all() -> None:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")


if __name__ == "__main__":
    _run_all()
