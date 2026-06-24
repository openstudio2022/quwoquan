"""Core scale readiness evidence and partial-delivery cases."""
from __future__ import annotations

from common import *  # noqa: F401,F403

def test_homepage_passed_count_accepts_hash_finalization_report():
    root = batch_root(TASK, "homepage_hash_finalization")
    entity = root / "entities" / "地点" / "景区" / "都江堰"
    write_json(entity / "_entity.json", {"label": "都江堰", "domain": "地点", "type": "景区"})
    (entity / "page.md").parent.mkdir(parents=True, exist_ok=True)
    (entity / "page.md").write_text("# 都江堰\n\n正文", encoding="utf-8")
    write_json(entity / "manifest.json", {"assets": []})
    write_json(
        entity / "5.review" / "review.json",
        {"decision": "approved", "checks": {"sourceReadiness": {"passed": True}}},
    )
    write_json(
        entity / "5.review" / "provenance.json",
        {"final": {"generator": "agent"}, "originalSources": ["source.md"]},
    )
    write_json(
        entity / "5.review" / "finalization_report.json",
        {
            "schemaVersion": "quwoquan_data.finalization_report",
            "draftArticleRef": "4.draft/page.md",
            "finalArticleRef": "page.md",
            "draftSha256": "sha256:draft",
            "finalSha256": "sha256:final",
        },
    )

    assert _homepage_passed_count(root) == 1


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

__all__ = [name for name in globals() if not name.startswith("__")]
