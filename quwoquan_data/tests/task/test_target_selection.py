"""Target selection and managed batch audit contract tests."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

_TMP = Path(tempfile.mkdtemp(prefix="qwq_target_selection_"))
os.environ["QWQ_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["QWQ_COMMITTED_TASKS_ROOT"] = str(_TMP / "tasks")

from _common.io import read_ndjson, write_json  # noqa: E402
from _common.paths import batch_root, task_catalog  # noqa: E402
from task.target_selection import (  # noqa: E402
    DEFAULT_MANDATORY,
    _workflow_failure_items,
    audit_managed_batch,
    build_multimodal_spec,
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
            "九寨沟: download_repair required: only 0 article source unit(s) with images",
        ],
    }
    items = _workflow_failure_items(state)
    assert items == [
        {
            "entity": "九寨沟",
            "lane": "article",
            "issues": ["九寨沟: download_repair required: only 0 article source unit(s) with images"],
        }
    ]


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
    assert content["quotas"]["imageWorksPerTarget"] == 2
    assert spec["acceptance"]["minPostsPerEntity"] == 6
    assert spec["workflowPolicy"]["allowPartialContent"] is True
    assert spec["workflowPolicy"]["deliveryMode"] == "partial_with_replacement_report"
    assert spec["scope"]["reserveCoverageTargets"][0]["name"] == "都江堰"
    assert "galleryPostsPerTarget" not in content["quotas"]


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
