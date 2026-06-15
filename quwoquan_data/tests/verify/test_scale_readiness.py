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

    original = target_selection.audit_managed_batch
    try:
        target_selection.audit_managed_batch = lambda task_id, batch_id: {
            "targetCount": 1,
            "lanePassed": {"homepage": 1, "article": 1, "image": 1},
            "failedLaneCount": 0,
            "failedLanes": [],
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
    assert report["passed"], report["blockers"]
    assert report["decision"] == "go"


def _run_all() -> None:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")


if __name__ == "__main__":
    _run_all()
