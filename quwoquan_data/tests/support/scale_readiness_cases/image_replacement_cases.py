"""Image strategy and replacement closure cases."""
from __future__ import annotations

from common import *  # noqa: F401,F403

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
    _write_token_ledger("open_license_shortage")
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
    _write_token_ledger("reference_only")
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
    _write_token_ledger("trial_replaced")
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
    _write_token_ledger("trial_replacement_history")
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
    _write_token_ledger("commercial_replaced")
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


def test_scale_readiness_source_admission_uses_active_replacement_targets():
    _save_spec()
    spec = store.load_spec(TASK)
    spec["scope"]["reserveCoverageTargets"] = [{"entityType": "地点/景区", "name": "都江堰"}]
    store.save_spec(spec)
    batch_id = "source_admission_active_replacement"
    root = batch_root(TASK, batch_id)
    _write_env_ready(batch_id)
    write_json(
        root / "_shared" / "task_workflow_state.json",
        {
            "status": "succeeded",
            "throughput": {"objectsPerHour": 500},
            "quality": {"firstPassRate": 0.82},
            "abandonedObjects": [{"entityId": "九寨沟", "status": "abandoned"}],
            "replacementObjects": [{"entityId": "都江堰", "entityType": "地点/景区", "status": "active"}],
        },
    )
    _write_token_ledger(batch_id)
    write_json(root / "_shared" / "gamma_import_report.json", {"status": "passed"})
    write_json(
        release_root("source_admission_active_replacement_release") / "release_manifest.json",
        {"releaseId": "source_admission_active_replacement_release"},
    )

    entity_dir = root / "entities" / "地点" / "景区" / "都江堰"
    sources: list[dict[str, str]] = []
    long_text = "都江堰水利工程以鱼嘴、飞沙堰、宝瓶口组织岷江水势，体现四川古代工程智慧。" * 40
    for index, lane in enumerate(["homepage", "article", "article", "article", "article", "image"], start=1):
        unit = root / "sources" / f"{index:02d}_{lane}"
        unit.mkdir(parents=True, exist_ok=True)
        (unit / "source.md").write_text(long_text if lane != "image" else "都江堰图库底稿", encoding="utf-8")
        write_json(unit / "meta.json", {"researchLane": lane, "sourceId": f"unit_{index}_{lane}"})
        if lane == "image":
            write_json(unit / "assets" / "index.json", {"assets": [{"sourceAssetId": "asset_001"}]})
        sources.append({"sourceRef": f"sources/{unit.name}/source.md"})
    write_json(entity_dir / "1.download" / "source_refs.json", {"sources": sources})

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
            batch_id,
            daily_target=10_000,
            source_ready_goal=6,
            release_id="source_admission_active_replacement_release",
            require_import=True,
            mode="trial",
        )
    finally:
        target_selection.audit_managed_batch = original
        scale_readiness.scan_runtime_batch_integrity = original_integrity
    assert report["passed"], report["blockers"]
    assert report["sourceAdmission"]["targetEntityCount"] == 1
    assert report["sourceAdmission"]["sourceReadyObjectCapacity"] == 6
    assert [item["entity"] for item in report["sourceAdmission"]["perEntity"]] == ["都江堰"]


def test_scale_readiness_source_admission_reports_source_mix_breakdown():
    """H100/H1000 准出证据：homepage 主源的源站组合分布必须进 sourceAdmission 报告。"""
    _save_spec()
    batch_id = "source_admission_source_mix"
    root = batch_root(TASK, batch_id)
    _write_env_ready(batch_id)
    write_json(
        root / "_shared" / "task_workflow_state.json",
        {
            "status": "succeeded",
            "throughput": {"objectsPerHour": 500},
            "quality": {"firstPassRate": 0.82},
        },
    )
    _write_token_ledger(batch_id)
    write_json(root / "_shared" / "gamma_import_report.json", {"status": "passed"})
    write_json(
        release_root("source_admission_source_mix_release") / "release_manifest.json",
        {"releaseId": "source_admission_source_mix_release"},
    )

    entity_dir = root / "entities" / "地点" / "景区" / "九寨沟"
    long_text = "九寨沟以钙华彩池、瀑布群与藏族村寨闻名，是四川代表性的世界自然遗产地。" * 40
    homepage_metas = [
        {"researchLane": "homepage", "url": "https://zh.wikipedia.org/wiki/九寨沟"},
        {"researchLane": "homepage", "platform": "百度百科", "url": "https://baike.baidu.com/item/九寨沟"},
        {"researchLane": "homepage", "sourceKind": "sogou_baike"},
        # focus 被判弱相关的 homepage 源不得进入 sourceMixBreakdown。
        {
            "researchLane": "homepage",
            "platform": "头条百科",
            "entityFocusVerdict": "off_entity",
        },
    ]
    sources: list[dict[str, str]] = []
    for index, meta in enumerate(homepage_metas, start=1):
        unit = root / "sources" / f"mix_{index:02d}_homepage"
        unit.mkdir(parents=True, exist_ok=True)
        (unit / "source.md").write_text(long_text, encoding="utf-8")
        write_json(unit / "meta.json", {"sourceId": f"mix_{index}", **meta})
        sources.append({"sourceRef": f"sources/{unit.name}/source.md"})
    write_json(entity_dir / "1.download" / "source_refs.json", {"sources": sources})

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
            batch_id,
            daily_target=10_000,
            release_id="source_admission_source_mix_release",
            require_import=True,
            mode="trial",
        )
    finally:
        target_selection.audit_managed_batch = original
        scale_readiness.scan_runtime_batch_integrity = original_integrity
    admission = report["sourceAdmission"]
    assert admission["sourceMixBreakdown"] == {
        "wikipedia": 1,
        "baidu_baike": 1,
        "sogou_baike": 1,
    }
    assert "toutiao_baike" not in admission["sourceMixBreakdown"]
    per_entity = {item["entity"]: item for item in admission["perEntity"]}
    assert per_entity["九寨沟"]["focusBlockedSourceUnits"] == 1

__all__ = [name for name in globals() if not name.startswith("__")]
