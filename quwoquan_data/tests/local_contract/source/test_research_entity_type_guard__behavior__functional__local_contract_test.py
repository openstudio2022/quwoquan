"""download research 类型守卫契约（WP5 类型漂移修复）。

产线 bug：`download research-plan` 旁路允许空/单值 --entity-type 应用到全部实体，
空串在 resolve_entity_object_dir 静默回退 DEFAULT_DOMAIN_ETYPE（地点/打卡地），
错值则整批套错类型，在契约外类型目录批量制造漂移产物（舟山岱山/嵊泗实测）。

契约：
1. coverageTargets canonical 类型覆盖调用方 hint（错类型被校正）。
2. canonical 与 hint 双缺失时 fail-fast 抛错，禁止默认打卡地目录落盘。
3. prepare_source_plan 只在 canonical/校正后的类型目录建 1.download 计划。

可直接运行：
    python3 quwoquan_data/tests/local_contract/source/test_research_entity_type_guard__behavior__functional__local_contract_test.py
"""
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

_TMP = Path(tempfile.mkdtemp(prefix="research_etype_guard_"))

from core.paths import execution_entity_object_dir, ensure_execution_command_layout  # noqa: E402
from content.source.prepare import (  # noqa: E402
    prepare_source_plan,
    resolve_research_entity_types,
)
from content.execution import store  # noqa: E402
from support.execution_manifest_fixture import ExecutionFixtureBuilder  # noqa: E402

EXECUTION_ID = "20260711--travel-homepage-research-type--test-region-a--pilot-001"


def _mixed_type_task() -> str:
    spec = ExecutionFixtureBuilder(
        EXECUTION_ID,
        targets=(
            {
                "entityType": "地点/古镇",
                "name": "东沙古镇",
                "aliases": ["东沙古渔镇"],
            },
            {"entityType": "地点/自然景观", "name": "秀山岛"},
        ),
    ).spec_payload()
    store.save_spec(spec)
    return spec["executionId"]


def test_canonical_type_overrides_wrong_single_value_hint():
    execution_id = _mixed_type_task()
    # 复现产线场景：agent 对混类型分区整批传了第一个实体的类型。
    resolved = resolve_research_entity_types(
        execution_id,
        ["东沙古镇", "秀山岛"],
        fallback_type="地点/古镇",
    )
    assert resolved == {"东沙古镇": "地点/古镇", "秀山岛": "地点/自然景观"}
    # 别名同样命中 canonical。
    assert resolve_research_entity_types(execution_id, ["东沙古渔镇"])["东沙古渔镇"] == "地点/古镇"


def test_missing_type_fails_fast_instead_of_default_spot_dir():
    execution_id = _mixed_type_task()
    try:
        resolve_research_entity_types(execution_id, ["花鸟岛"], fallback_type="")
    except ValueError as exc:
        assert "entityType missing" in str(exc)
    else:
        raise AssertionError("expected fail-fast for missing entityType")


def test_prepare_source_plan_corrects_dir_and_refuses_default_drift():
    execution_id = _mixed_type_task()
    ensure_execution_command_layout(execution_id, "source")
    # 空 hint：canonical 校正落正确目录，不落默认打卡地目录。
    prepare_source_plan(
        execution_id,
        [{"entityId": "秀山岛", "canonicalName": "秀山岛", "entityType": ""}],
    )
    canonical_plan = (
        execution_entity_object_dir(execution_id, "地点", "自然景观", "秀山岛")
        / "1.download"
        / "homepage_source_plan.json"
    )
    drift_dir = execution_entity_object_dir(execution_id, "地点", "打卡地", "秀山岛")
    assert canonical_plan.is_file(), canonical_plan
    assert not drift_dir.exists(), drift_dir
    # canonical 与 hint 双缺失：拒绝写盘。
    try:
        prepare_source_plan(
            execution_id,
            [{"entityId": "花鸟岛", "canonicalName": "花鸟岛", "entityType": ""}],
        )
    except ValueError as exc:
        assert "entityType missing" in str(exc)
    else:
        raise AssertionError("expected prepare_source_plan fail-fast")
    assert not execution_entity_object_dir(execution_id, "地点", "打卡地", "花鸟岛").exists()


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"research entity type guard tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
