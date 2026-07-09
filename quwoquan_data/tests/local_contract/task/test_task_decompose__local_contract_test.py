"""task decompose 契约（WP5）：--from-task-selection 批次圈选同源投影。

冻结计划成员必须与 select-targets 圈选结果精确一致（ready 过滤 + dedup 排除后），
按目标 region 分组成分区，主清单契约字段（geoTagRef 等）随叶子透传。

可直接运行：
    python3 quwoquan_data/tests/local_contract/task/test_task_decompose__local_contract_test.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# 直跑隔离（pytest 下 conftest 已注入 QWQ_DATA_ROOT 隔离根，此处幂等兜底）。
if "QWQ_DATA_ROOT" not in os.environ and "QWQ_RUNTIME_ROOT" not in os.environ:
    _TMP = tempfile.mkdtemp(prefix="qwq_decompose_test_")
    os.environ["QWQ_DATA_ROOT"] = _TMP

from _common import fanout_plan as fp  # noqa: E402
from task import decompose as decompose_mod  # noqa: E402
from task import store  # noqa: E402

_TASK_ID = "旅行/地域/中国/浙江省/舟山市/景区/舟山主页测试"


def _write_selection(targets: list[dict]) -> None:
    selection_path = store.committed_task_root(_TASK_ID) / "_shared" / "target_selection.json"
    selection_path.parent.mkdir(parents=True, exist_ok=True)
    selection_path.write_text(
        json.dumps({"targets": targets, "selectedCount": len(targets)}, ensure_ascii=False),
        encoding="utf-8",
    )


def _init_plan(plan_id: str) -> None:
    decompose_mod.handle_init(
        argparse.Namespace(
            plan=plan_id,
            goal="WP5 测试",
            vertical="travel",
            partition_dimension="行政区划",
            organize_by="region",
            category="景区",
            entity_type="地点/景区",
            strategy="by-partition",
            concurrency=2,
            batch_size=None,
            task_name=None,
            coverage_partitions=None,
            coverage_leaves=None,
            force=True,
            source_task_id=_TASK_ID,
        )
    )


def test_load_from_task_selection_groups_by_region_and_keeps_contract_fields():
    """圈选投影契约：按 region 分组；geoTagRef/typeTagRefs/aliases 透传进叶子；
    region/sourceName 不进叶子字段。"""
    _write_selection(
        [
            {"name": "普陀山", "entityType": "地点/景区", "region": "普陀区", "sourceName": "普陀山风景名胜区",
             "geoTagRef": "geo/中国/浙江省/舟山市/普陀区", "typeTagRefs": ["type/景区"], "aliases": ["普陀山风景区"]},
            {"name": "朱家尖", "entityType": "地点/景区", "region": "普陀区", "sourceName": "朱家尖",
             "geoTagRef": "geo/中国/浙江省/舟山市/普陀区"},
            {"name": "舟山鸦片战争遗址公园", "entityType": "地点/景区", "region": "定海区", "sourceName": "舟山鸦片战争遗址公园",
             "geoTagRef": "geo/中国/浙江省/舟山市/定海区"},
        ]
    )
    plan_id = "wp5_decompose_selection_test"
    _init_plan(plan_id)
    decompose_mod.handle_load(
        argparse.Namespace(
            plan=plan_id,
            discovery=None,
            master_list=False,
            provinces="",
            from_task_selection=_TASK_ID,
        )
    )
    plan = fp.load_plan(plan_id)
    parts = {str(p.get("key")): p for p in (plan.get("partitions") or [])}
    assert set(parts) == {"普陀区", "定海区"}, sorted(parts)
    putuo_leaves = {str(l.get("name")): l for l in parts["普陀区"].get("leaves") or []}
    assert set(putuo_leaves) == {"普陀山", "朱家尖"}
    leaf = putuo_leaves["普陀山"]
    assert leaf.get("geoTagRef") == "geo/中国/浙江省/舟山市/普陀区"
    assert leaf.get("typeTagRefs") == ["type/景区"]
    assert leaf.get("aliases") == ["普陀山风景区"]
    assert "region" not in leaf and "sourceName" not in leaf
    assert len(parts["定海区"].get("leaves") or []) == 1


def test_load_from_task_selection_missing_selection_blocks():
    """selection 不存在 → 必须 BLOCK（exit 2），不得静默空计划。"""
    plan_id = "wp5_decompose_missing_selection_test"
    _init_plan(plan_id)
    try:
        decompose_mod.handle_load(
            argparse.Namespace(
                plan=plan_id,
                discovery=None,
                master_list=False,
                provinces="",
                from_task_selection="旅行/地域/中国/不存在/景区/无此任务",
            )
        )
        raise AssertionError("selection 缺失必须 SystemExit")
    except SystemExit as exc:
        assert int(exc.code or 0) == 2


if __name__ == "__main__":
    failures = 0
    for fn_name, fn in sorted(
        (k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)
    ):
        try:
            fn()
            print(f"PASS {fn_name}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {fn_name}: {exc}")
    raise SystemExit(1 if failures else 0)
