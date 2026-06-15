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

from _common.io import write_json  # noqa: E402
from _common.paths import batch_root  # noqa: E402
from task.target_selection import (  # noqa: E402
    DEFAULT_MANDATORY,
    _workflow_failure_items,
    build_multimodal_spec,
    ineligible_targets_from_batch,
    select_targets,
)


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


def test_build_multimodal_spec_uses_separated_research_image_contract():
    spec = build_multimodal_spec(
        name="多模态重跑",
        title="多模态重跑",
        region="四川省",
        category="景区",
        targets=[{"name": "四姑娘山", "entityType": "地点/景区", "region": "川西"}],
        created_by="test",
    )
    content = spec["content"]
    assert content["modalityContract"] == "separated_research"
    assert content["carriers"] == ["article", "image"]
    assert content["quotas"]["entityArticlesPerTarget"] == 4
    assert content["quotas"]["imageWorksPerTarget"] == 1
    assert spec["acceptance"]["minPostsPerEntity"] == 5
    assert "galleryPostsPerTarget" not in content["quotas"]


def _run_all() -> None:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")


if __name__ == "__main__":
    _run_all()
