"""景区/打卡地类型冲突判定的读路径契约（WP5 假阳性修复）。

产线 bug（舟山嵊泗/普陀实测）：多类型分区 execution 级 etype 为空，audit/precheck 等
读路径以空 hint 调 resolve_entity_object_dir → 默认「地点/打卡地」；此时
_raise_if_scenic_location_type_conflict 只检查 sibling（canonical 景区目录，真实
产物）是否存在，current（打卡地）并不在磁盘上也抛「same execution contains both」，
把 completion gate 炸成 manual_required——canonical 产物越完整越必炸。

契约：
1. current 未物化（或无 marker）+ sibling 已物化 → 读路径解析不抛（假阳性禁止）。
2. current 与 sibling 双双物化（真漂移共存）→ 必须抛（gate 语义不放宽）。
3. audit_managed_execution 对多类型分区（execution etype 空）在 canonical 目录物化后可用，
   不得因空 hint 默认类型触发假冲突。

可直接运行：
    python3 quwoquan_data/tests/local_contract/task/test_entity_type_conflict_read_path__local_contract_test.py
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

_TMP = Path(tempfile.mkdtemp(prefix="etype_conflict_read_"))

from core.paths import execution_entity_object_dir, ensure_execution_command_layout  # noqa: E402
from content.source.source_unit import resolve_entity_object_dir  # noqa: E402
from content.execution import store  # noqa: E402
from content.execution.selection import build_execution_spec  # noqa: E402

_EXECUTIONS = {
    "未物化": "20260711--travel-homepage-entity-type--test-region-a--pilot-001",
    "双物化": "20260711--travel-homepage-entity-type--test-region-a--pilot-002",
    "审计": "20260711--travel-homepage-entity-type--test-region-a--pilot-003",
}


def _mixed_type_task(name: str = "类型冲突读路径批") -> str:
    execution_id = next(value for marker, value in _EXECUTIONS.items() if marker in name)
    spec = build_execution_spec(
        execution_id=execution_id,
        name=name,
        title=name,
        region="中国/test-region-a/舟山市/嵊泗县",
        category="景区",
        targets=[
            {"entityType": "地点/景区", "name": "嵊泗列岛", "aliases": ["嵊泗列岛风景名胜区"]},
            {"entityType": "地点/自然景观", "name": "花鸟岛"},
        ],
        created_by="test",
        entity_articles_per_target=0,
        entity_homepages_per_target=1,
        image_works_per_target=0,
        video_works_per_target=0,
        target_entity_count=2,
    )
    store.save_spec(spec)
    return spec["executionId"]


def _materialize(execution_id: str, domain: str, etype: str, name: str) -> Path:
    obj = execution_entity_object_dir(execution_id, domain, etype, name)
    obj.mkdir(parents=True, exist_ok=True)
    (obj / "page.md").write_text(f"# {name}\n", encoding="utf-8")
    return obj


def test_unmaterialized_default_hint_does_not_raise_against_canonical():
    execution_id = _mixed_type_task("类型冲突读路径批_未物化")
    ensure_execution_command_layout(execution_id, "source")
    _materialize(execution_id, "地点", "景区", "嵊泗列岛")
    # 空 hint → 默认打卡地路径；打卡地目录不存在，不得判为漂移共存。
    obj = resolve_entity_object_dir(execution_id, "嵊泗列岛", etype_hint="")
    assert obj.name == "嵊泗列岛" and obj.parent.name == "打卡地", obj
    # 显式错误 hint 同理：只要错类型目录未物化，读解析不抛。
    obj2 = resolve_entity_object_dir(execution_id, "嵊泗列岛", etype_hint="地点/打卡地")
    assert obj2 == obj


def test_dual_materialized_trees_still_raise():
    execution_id = _mixed_type_task("类型冲突读路径批_双物化")
    ensure_execution_command_layout(execution_id, "source")
    _materialize(execution_id, "地点", "景区", "嵊泗列岛")
    _materialize(execution_id, "地点", "打卡地", "嵊泗列岛")
    for hint in ("", "地点/打卡地", "地点/景区"):
        try:
            resolve_entity_object_dir(execution_id, "嵊泗列岛", etype_hint=hint)
        except ValueError as exc:
            assert "entity type drift detected" in str(exc)
        else:
            raise AssertionError(f"expected drift error for hint={hint!r}")


def test_audit_managed_execution_usable_on_mixed_type_partition():
    execution_id = _mixed_type_task("类型冲突读路径批_审计")
    ensure_execution_command_layout(execution_id, "source")
    _materialize(execution_id, "地点", "景区", "嵊泗列岛")
    _materialize(execution_id, "地点", "自然景观", "花鸟岛")
    from content.execution.readiness_audit import audit_execution_readiness
    from core.control_types import ExecutionStateStatus
    from support.execution_manifest_fixture import ExecutionFixtureBuilder

    audit = audit_execution_readiness(
        execution_id,
        execution_state_override=ExecutionFixtureBuilder(execution_id).state(
            status=ExecutionStateStatus.SUCCEEDED,
        ),
    )
    assert int(audit.get("targetCount") or 0) == 2, audit.get("targetCount")


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"entity type conflict read-path tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
