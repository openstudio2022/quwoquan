"""fanout_plan contract tests：构建 / 去重 / 互斥 / 覆盖 / 发现门 / 冻结门 / IO。

可直接运行：python3 quwoquan_data/tests/local_contract/orchestrate/test_fanout_plan__local_contract_test.py
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

_TMP = tempfile.mkdtemp(prefix="qwq_fanout_plan_test_")
os.environ["QWQ_RUNTIME_ROOT"] = _TMP

from _common import fanout_plan as fp  # noqa: E402


def _good_plan() -> dict:
    plan = fp.new_plan("plan_test", "全国景点主页", "travel", partition_dimension="省")
    fp.add_partition(plan, "四川省")
    fp.add_partition(plan, "云南省")
    fp.add_leaves(plan, ["四川省"], [{"name": "九寨沟"}, {"name": "稻城亚丁"}])
    fp.add_leaves(plan, ["云南省"], [{"name": "玉龙雪山"}])
    return plan


def test_new_plan_defaults_merged():
    plan = fp.new_plan("p1", "全国高校主页", "campus")
    assert plan["status"] == "draft"
    assert plan["defaults"]["strategy"] == "by-partition"
    assert plan["defaults"]["budget"]["maxWallClockSeconds"] == 1200


def test_add_partition_idempotent():
    plan = fp.new_plan("p2", "g", "travel")
    a = fp.add_partition(plan, "四川省")
    b = fp.add_partition(plan, "四川省")
    assert a is b
    assert len(plan["partitions"]) == 1


def test_leaf_ref_derivation_and_add():
    plan = _good_plan()
    refs = [leaf["ref"] for _, leaf in fp.iter_leaves(plan)]
    assert "地点_景区__九寨沟" in refs
    assert len(refs) == 3


def test_add_leaves_dedup_within_partition():
    plan = fp.new_plan("p3", "g", "travel")
    fp.add_partition(plan, "四川省")
    fp.add_leaves(plan, ["四川省"], [{"name": "九寨沟"}])
    added = fp.add_leaves(plan, ["四川省"], [{"name": "九寨沟"}])
    assert added == []  # 同 ref 不重复


def test_recursive_subpartitions():
    plan = fp.new_plan("p4", "g", "travel")
    fp.add_partition(plan, "四川省")
    fp.add_partition(plan, "阿坝州", parent_path=["四川省"])
    fp.add_leaves(plan, ["四川省", "阿坝州"], [{"name": "九寨沟"}])
    parts = fp.leaf_partitions(plan)
    assert len(parts) == 1 and parts[0]["key"] == "阿坝州"
    leaves = list(fp.iter_leaves(plan))
    assert leaves[0][0] == ["四川省", "阿坝州"]


def test_leaf_dedup_issue_across_partitions():
    plan = _good_plan()
    # 手动制造跨分区重复 ref
    fp.add_leaves(plan, ["云南省"], [{"name": "九寨沟"}])
    issues = fp.leaf_dedup_issues(plan)
    assert any("九寨沟" in i for i in issues)


def test_partition_mutex_issue():
    plan = fp.new_plan("p5", "g", "travel")
    fp.add_partition(plan, "A")
    fp.add_partition(plan, "B")
    fp.add_leaves(plan, ["A"], [{"name": "x", "ref": "rx", "mutexKey": "shared"}])
    fp.add_leaves(plan, ["B"], [{"name": "y", "ref": "ry", "mutexKey": "shared"}])
    issues = fp.partition_mutex_issues(plan)
    assert any("shared" in i for i in issues)


def test_coverage_issue():
    plan = _good_plan()
    plan["coverageTargets"] = {"partitions": 31, "leaves": 3}
    issues = fp.coverage_issues(plan)
    assert any("31 partitions" in i for i in issues)
    assert not any("leaves" in i for i in issues)  # 3 leaves matches


def test_discovery_gate_blocks_empty_partition():
    plan = fp.new_plan("p6", "g", "travel")
    fp.add_partition(plan, "空分区")
    issues = fp.discovery_gate_issues(plan)
    assert any("empty partition" in i for i in issues)


def test_freeze_requires_gate_and_confirm():
    plan = _good_plan()
    try:
        fp.freeze_plan(plan, confirmed=False)
    except ValueError as exc:
        assert "confirmation" in str(exc)
    else:
        raise AssertionError("freeze without confirm must fail")
    frozen = fp.freeze_plan(plan, confirmed=True)
    assert frozen["status"] == "frozen" and frozen["frozenAt"]


def test_freeze_blocked_by_discovery_issue():
    plan = fp.new_plan("p7", "g", "travel")
    fp.add_partition(plan, "空")
    try:
        fp.freeze_plan(plan, confirmed=True)
    except ValueError as exc:
        assert "discovery gate failed" in str(exc)
    else:
        raise AssertionError("freeze with empty partition must fail")


def test_save_load_roundtrip():
    plan = _good_plan()
    fp.save_plan(plan)
    loaded = fp.load_plan("plan_test")
    assert loaded is not None
    assert fp.plan_summary(loaded)["leaves"] == 3


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"fanout_plan tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
