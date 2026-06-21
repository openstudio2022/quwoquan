"""Target selection and managed batch audit contract tests."""
from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

_TMP = Path(tempfile.mkdtemp(prefix="qwq_target_selection_"))
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_COMMITTED_TASKS_ROOT"] = str(_TMP / "tasks")

from _common.io import read_ndjson, write_json  # noqa: E402
from _common.entity_artifacts import prune_inactive_entity_artifacts  # noqa: E402
from _common.paths import batch_root, task_catalog  # noqa: E402
from _common.source_unit import resolve_entity_object_dir  # noqa: E402
from task.target_selection import (  # noqa: E402
    DEFAULT_MANDATORY,
    _workflow_failure_items,
    audit_managed_batch,
    build_multimodal_spec,
    handle_audit_batch,
    ineligible_targets_from_batch,
    select_targets,
    write_selected_task,
)
from task import store  # noqa: E402


def _discovery(path: Path) -> None:
    partitions = []
    for region in ("川西", "川北", "川南"):
        leaves = [
            {"name": f"{region}候选{index}", "entityType": "地点/景区"}
            for index in range(1, 30)
        ]
        partitions.append({"key": region, "leaves": leaves})
    partitions[0]["leaves"][:5] = [
        {"name": name, "entityType": "地点/景区"} for name in DEFAULT_MANDATORY
    ]
    write_json(path, {"partitions": partitions})


def test_ineligible_targets_from_managed_state():
    task = "旅行/地域/测试省/景区/多模态"
    batch = "b1"
    state = batch_root(task, batch) / "_shared" / "task_workflow_state.json"
    write_json(
        state,
        {
            "failedObjects": [
                "巴山大峡谷: image research needs enough rights-cleared collection assets",
                "大千园：image research needs enough rights-cleared collection assets",
                "agent status=error",
            ]
        },
    )
    assert ineligible_targets_from_batch(task, batch) == {"巴山大峡谷", "大千园"}


def test_ineligible_targets_include_abandoned_entities_and_content_refs():
    task = "旅行/地域/测试省/景区/多模态"
    batch = "b_abandoned_source"
    state = batch_root(task, batch) / "_shared" / "task_workflow_state.json"
    write_json(
        state,
        {
            "abandonedObjects": [
                {"entityId": "光雾山", "stage": "download_fetch", "reason": "source_unavailable"},
            ],
            "abandonedContentObjects": [
                {"ref": "毕棚沟_image", "stage": "content_plan", "reason": "source_unavailable"},
                {"ref": "青城山_seasonal_timing", "stage": "content_plan", "reason": "source_unavailable"},
            ],
        },
    )
    assert ineligible_targets_from_batch(task, batch) == {"光雾山", "毕棚沟", "青城山"}


def test_ineligible_targets_merge_audit_failed_lanes():
    task = "旅行/地域/测试省/景区/多模态"
    batch = "b_audit"
    shared = batch_root(task, batch) / "_shared"
    write_json(
        shared / "managed_batch_audit.json",
        {
            "failedLanes": [
                {"entity": "真佛山", "lane": "image", "issues": ["image supply"]},
                {"entity": "宝箴塞", "lane": "image", "issues": ["image supply"]},
            ]
        },
    )
    write_json(
        shared / "task_workflow_state.json",
        {"failedObjects": ["黄荆老林: image research needs enough rights-cleared collection assets"]},
    )
    assert ineligible_targets_from_batch(task, batch) == {"真佛山", "宝箴塞", "黄荆老林"}


def test_ineligible_targets_read_source_unavailable_report():
    task = "旅行/地域/测试省/景区/多模态"
    batch = "b_source_unavailable"
    shared = batch_root(task, batch) / "_shared"
    write_json(
        shared / "source_unavailable_targets.json",
        {
            "ineligibleTargets": [
                {
                    "entityId": "墨石公园",
                    "lanes": ["homepage", "article", "image"],
                    "issues": ["no rights-compatible image"],
                }
            ]
        },
    )
    assert ineligible_targets_from_batch(task, batch) == {"墨石公园"}


def test_workflow_failure_items_turn_manual_required_into_audit_failure():
    state = {
        "status": "manual_required",
        "failedObjects": [
            "九寨沟: download_repair required: article research needs >= 4 text-qualified base sources",
        ],
    }
    items = _workflow_failure_items(state)
    assert items == [
        {
            "entity": "九寨沟",
            "lane": "article",
            "issues": ["九寨沟: download_repair required: article research needs >= 4 text-qualified base sources"],
        }
    ]


def test_workflow_failure_items_allow_until_stop_state():
    assert _workflow_failure_items({"status": "stopped_at_until", "failedObjects": []}) == []


def test_audit_batch_skips_abandoned_targets():
    spec = build_multimodal_spec(
        name="abandoned审计",
        title="abandoned审计",
        region="测试省",
        category="景区",
        targets=[
            {"name": "可继续景区", "entityType": "地点/景区"},
            {"name": "快速失败景区", "entityType": "地点/景区"},
        ],
        created_by="test",
    )
    task = spec["taskId"]
    batch = "b_abandoned"
    store.save_spec(spec)
    write_json(
        batch_root(task, batch) / "_shared" / "task_workflow_state.json",
        {
            "status": "running",
            "abandonedObjects": [
                {
                    "entityId": "快速失败景区",
                    "stage": "download_plan",
                    "reason": "no authorized source after screening",
                    "status": "abandoned",
                }
            ],
        },
    )

    report = audit_managed_batch(task, batch)
    assert report["targetCount"] == 1
    assert report["abandonedCount"] == 1
    assert report["abandonedObjects"][0]["entityId"] == "快速失败景区"
    entity_failures = {
        item["entity"] for item in report["failedLanes"]
        if item.get("entity") != "__batch__"
    }
    assert entity_failures == {"可继续景区"}


def test_audit_batch_ignores_partial_auto_research_scope():
    spec = build_multimodal_spec(
        name="partial自动检索审计",
        title="partial自动检索审计",
        region="测试省",
        category="景区",
        targets=[
            {"name": "景区甲", "entityType": "地点/景区"},
            {"name": "景区乙", "entityType": "地点/景区"},
            {"name": "景区丙", "entityType": "地点/景区"},
        ],
        created_by="test",
    )
    task = spec["taskId"]
    batch = "b_partial_auto_report"
    store.save_spec(spec)
    write_json(
        batch_root(task, batch) / "_shared" / "auto_research_plan.json",
        {
            "sourceAvailability": {
                "readyTargets": ["景区乙"],
                "ineligibleTargets": [],
            }
        },
    )

    report = audit_managed_batch(task, batch)

    assert report["targetCount"] == 3
    assert report["targetScope"] == "task_coverage"


def test_audit_batch_json_strict_exits_nonzero_when_failed():
    spec = build_multimodal_spec(
        name="json严格审计",
        title="json严格审计",
        region="测试省",
        category="景区",
        targets=[{"name": "缺源景区", "entityType": "地点/景区"}],
        created_by="test",
    )
    task = spec["taskId"]
    batch = "b_json_strict_failed"
    store.save_spec(spec)

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            handle_audit_batch(
                SimpleNamespace(
                    task=task,
                    batch=batch,
                    write=False,
                    json=True,
                    strict=True,
                )
            )
            assert False, "strict JSON audit should exit non-zero when failed lanes exist"
        except SystemExit as exc:
            assert exc.code == 1
    assert '"failedLaneCount"' in out.getvalue()


def test_audit_batch_reports_homepage_input_issue_after_build_prepare():
    spec = build_multimodal_spec(
        name="主页输入审计",
        title="主页输入审计",
        region="测试省",
        category="景区",
        targets=[{"name": "空底稿景区", "entityType": "地点/景区"}],
        created_by="test",
    )
    task = spec["taskId"]
    batch = "b_homepage_input_issue"
    store.save_spec(spec)
    entity = batch_root(task, batch) / "entities" / "地点" / "景区" / "空底稿景区"
    write_json(
        entity / "1.download" / "homepage_source_plan.json",
        {
            "payload": {
                "sources": [
                    {
                        "source_id": "home_wikipedia",
                        "platform": "维基百科",
                        "category": "encyclopedia",
                        "url": "https://zh.wikipedia.org/wiki/test",
                        "sourceUseMode": "factual_reference_only",
                    },
                    {
                        "source_id": "home_baidu",
                        "platform": "百度百科",
                        "category": "encyclopedia",
                        "url": "https://baike.baidu.com/item/test",
                        "sourceUseMode": "factual_reference_only",
                    },
                ]
            }
        },
    )
    write_json(
        entity / "3.compose" / "entity_page_input.json",
        {"payload": {"name": "空底稿景区", "domain": "地点", "etype": "景区", "baseDraft": {}}},
    )

    report = audit_managed_batch(task, batch)

    homepage_failures = [
        item for item in report["failedLanes"]
        if item.get("entity") == "空底稿景区" and item.get("lane") == "homepage"
    ]
    assert homepage_failures
    assert any(
        "baseDraft.sourceRef is empty" in issue
        for issue in homepage_failures[0]["issues"]
    ), homepage_failures


def test_audit_batch_blocks_inactive_entity_homepage_artifacts():
    spec = build_multimodal_spec(
        name="失活主页产物审计",
        title="失活主页产物审计",
        region="测试省",
        category="景区",
        targets=[{"name": "有效景区", "entityType": "地点/景区"}],
        created_by="test",
    )
    task = spec["taskId"]
    batch = "b_inactive_homepage_artifacts"
    store.save_spec(spec)
    shared = batch_root(task, batch) / "_shared"
    write_json(
        shared / "auto_research_plan.json",
        {"sourceAvailability": {"readyTargets": ["有效景区"], "ineligibleTargets": []}},
    )
    inactive = resolve_entity_object_dir(task, batch, "失活景区", etype_hint="地点/景区")
    write_json(inactive / "manifest.json", {"entityRef": "/entity/地点/景区/失活景区"})
    (inactive / "page.md").parent.mkdir(parents=True, exist_ok=True)
    (inactive / "page.md").write_text("失活主页", encoding="utf-8")
    (inactive / "assets").mkdir(parents=True, exist_ok=True)

    report = audit_managed_batch(task, batch)

    assert report["inactiveEntityArtifactCount"] == 1
    inactive_failures = [
        item for item in report["failedLanes"]
        if item.get("entity") == "失活景区" and item.get("lane") == "homepage"
    ]
    assert inactive_failures
    assert "outside active target set" in inactive_failures[0]["issues"][0]


def test_prune_inactive_entity_artifacts_keeps_download_evidence():
    task = "旅行/地域/测试省/景区/失活产物清理"
    batch = "b_prune_inactive"
    inactive = resolve_entity_object_dir(task, batch, "失活景区", etype_hint="地点/景区")
    write_json(inactive / "manifest.json", {"entityRef": "/entity/地点/景区/失活景区"})
    write_json(inactive / "_entity.json", {"name": "失活景区"})
    write_json(inactive / "1.download" / "source.md", {"source": "kept"})
    (inactive / "assets").mkdir(parents=True, exist_ok=True)

    rows = prune_inactive_entity_artifacts(
        task,
        batch,
        active_entity_names=["有效景区"],
    )

    assert [row["entity"] for row in rows] == ["失活景区"]
    assert not (inactive / "manifest.json").exists()
    assert not (inactive / "_entity.json").exists()
    assert not (inactive / "assets").exists()
    assert (inactive / "1.download" / "source.md").exists()


def test_audit_batch_dedupes_workflow_failure_for_same_entity_lane():
    spec = build_multimodal_spec(
        name="重复失败审计",
        title="重复失败审计",
        region="测试省",
        category="景区",
        targets=[{"name": "缺源景区", "entityType": "地点/景区"}],
        created_by="test",
    )
    task = spec["taskId"]
    batch = "b_duplicate_workflow_failure"
    store.save_spec(spec)

    report = audit_managed_batch(
        task,
        batch,
        workflow_state_override={
            "status": "waiting_agent",
            "failedObjects": ["缺源景区: article sources=0 need>=4"],
        },
    )

    assert report["failedLaneCount"] == 3
    article_failures = [
        item for item in report["failedLanes"]
        if item.get("entity") == "缺源景区" and item.get("lane") == "article"
    ]
    assert len(article_failures) == 1
    assert "缺源景区: article sources=0 need>=4" in article_failures[0]["issues"]


def test_audit_batch_ignores_stale_workflow_failure_when_current_lane_passes():
    spec = build_multimodal_spec(
        name="旧失败容错审计",
        title="旧失败容错审计",
        region="测试省",
        category="景区",
        targets=[{"name": "已修好景区", "entityType": "地点/景区"}],
        created_by="test",
    )
    task = spec["taskId"]
    batch = "b_stale_workflow_failure"
    store.save_spec(spec)
    dl = resolve_entity_object_dir(task, batch, "已修好景区", etype_hint="地点/景区") / "1.download"
    sources = [
        {
            "source_id": f"article_base_{idx}",
            "platform": "去哪儿攻略",
            "url": f"https://example.invalid/youji/{idx}",
            "category": "travelogue",
            "sourceRole": "base",
            "sourceUseMode": "factual_reference_only",
            "entityMatch": "strong",
            "candidateGate": {"passed": True, "issues": []},
        }
        for idx in range(1, 5)
    ]
    write_json(
        dl / "article_source_plan.json",
        {
            "schemaVersion": "quwoquan.download.source_plan",
            "payload": {
                "entityId": "已修好景区",
                "researchLane": "article",
                "sources": sources,
            },
        },
    )

    report = audit_managed_batch(
        task,
        batch,
        workflow_state_override={
            "status": "waiting_agent",
            "waitingCheckpoint": "download_plan",
            "failedObjects": ["已修好景区: article sources=2 need>=4"],
        },
    )

    assert not any(
        item.get("entity") == "已修好景区" and item.get("lane") == "article"
        for item in report["failedLanes"]
    )


def test_select_targets_excludes_failed_and_keeps_mandatory():
    discovery = _TMP / "discovery.json"
    _discovery(discovery)
    targets, report = select_targets(
        discovery_path=discovery,
        limit=12,
        mandatory=list(DEFAULT_MANDATORY),
        excluded={"川北候选1", "川南候选1"},
    )
    names = [target["name"] for target in targets]
    assert names[:5] == DEFAULT_MANDATORY
    assert "川北候选1" not in names
    assert "川南候选1" not in names
    assert len(names) == 12
    assert report["excluded"] == ["川北候选1", "川南候选1"]


def test_select_targets_adds_deterministic_reserve_pool():
    discovery = _TMP / "discovery_reserve.json"
    _discovery(discovery)
    targets, report = select_targets(
        discovery_path=discovery,
        limit=10,
        mandatory=list(DEFAULT_MANDATORY[:2]),
        excluded=set(),
        reserve_ratio=0.2,
    )
    selected = {target["name"] for target in targets}
    reserve = report["reserveTargets"]
    assert len(targets) == 10
    assert len(reserve) == 2
    assert not selected & {target["name"] for target in reserve}


def test_select_targets_prefers_discovery_canonical_name_and_keeps_source_name():
    discovery = _TMP / "discovery_canonical.json"
    write_json(
        discovery,
        {
            "partitions": [
                {
                    "key": "全国5A",
                    "leaves": [
                        {
                            "name": "承德市承德避暑山庄及周围寺庙景区",
                            "canonicalName": "承德避暑山庄及周围寺庙景区",
                            "entityType": "地点/景区",
                        }
                    ],
                }
            ]
        },
    )

    targets, report = select_targets(
        discovery_path=discovery,
        limit=1,
        mandatory=[],
        excluded=set(),
    )

    assert targets == [
        {
            "name": "承德避暑山庄及周围寺庙景区",
            "entityType": "地点/景区",
            "region": "全国5A",
            "sourceName": "承德市承德避暑山庄及周围寺庙景区",
        }
    ]
    assert report["targets"][0]["sourceName"] == "承德市承德避暑山庄及周围寺庙景区"


def test_select_targets_uses_selection_priority_within_partition():
    discovery = _TMP / "discovery_priority.json"
    write_json(
        discovery,
        {
            "partitions": [
                {
                    "key": "全国5A",
                    "leaves": [
                        {"name": "新晋景区", "entityType": "地点/景区", "selectionPriority": 2024},
                        {"name": "老牌景区", "entityType": "地点/景区", "selectionPriority": 2007},
                    ],
                }
            ]
        },
    )

    targets, report = select_targets(
        discovery_path=discovery,
        limit=1,
        mandatory=[],
        excluded=set(),
    )

    assert [target["name"] for target in targets] == ["老牌景区"]
    assert [target["name"] for target in report["reserveTargets"]] == []


def test_build_multimodal_spec_uses_separated_research_image_contract():
    spec = build_multimodal_spec(
        name="多模态重跑",
        title="多模态重跑",
        region="四川省",
        category="景区",
        targets=[{"name": "四姑娘山", "entityType": "地点/景区", "region": "川西"}],
        reserve_targets=[{"name": "都江堰", "entityType": "地点/景区", "region": "成都"}],
        created_by="test",
    )
    content = spec["content"]
    assert content["modalityContract"] == "separated_research"
    assert content["carriers"] == ["article", "image"]
    assert content["quotas"]["entityArticlesPerTarget"] == 4
    assert content["quotas"]["imageWorksPerTarget"] == 1
    assert spec["acceptance"]["minPostsPerEntity"] == 5
    assert spec["workflowPolicy"]["allowPartialContent"] is True
    assert spec["workflowPolicy"]["deliveryMode"] == "partial_with_replacement_report"
    assert spec["workflowPolicy"]["maxReplacementCandidatesPerWave"] >= 8
    assert spec["workflowPolicy"]["maxReplacementScreenedPerRun"] >= 8
    assert spec["scope"]["reserveCoverageTargets"][0]["name"] == "都江堰"
    assert "galleryPostsPerTarget" not in content["quotas"]


def test_build_multimodal_spec_allows_explicit_image_work_quota():
    spec = build_multimodal_spec(
        name="双图库重跑",
        title="双图库重跑",
        region="四川省",
        category="景区",
        targets=[{"name": "四姑娘山", "entityType": "地点/景区", "region": "川西"}],
        created_by="test",
        image_works_per_target=2,
    )

    assert spec["content"]["quotas"]["imageWorksPerTarget"] == 2
    assert spec["acceptance"]["minPostsPerEntity"] == 6


def test_write_selected_task_writes_catalog_for_baseline_gate():
    spec = build_multimodal_spec(
        name="可baseline试跑",
        title="可baseline试跑",
        region="四川省",
        category="景区",
        targets=[
            {"name": "四姑娘山", "entityType": "地点/景区", "region": "川西"},
            {"name": "都江堰", "entityType": "地点/景区", "region": "成都"},
        ],
        reserve_targets=[],
        created_by="test",
    )
    write_selected_task(spec, {"targets": []}, force=True)

    rows = read_ndjson(task_catalog(spec["taskId"]))
    assert [row["canonical_name"] for row in rows] == ["四姑娘山", "都江堰"]
    assert {row["topic_id"] for row in rows} == {"地点/景区/四姑娘山", "地点/景区/都江堰"}


def _run_all() -> None:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")


if __name__ == "__main__":
    _run_all()
