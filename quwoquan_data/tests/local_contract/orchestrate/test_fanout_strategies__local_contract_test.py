"""fanout_strategies contract tests：四策略确定性展开 + task/batch 寻址。

可直接运行：python3 quwoquan_data/tests/local_contract/orchestrate/test_fanout_strategies__local_contract_test.py
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

_TMP = tempfile.mkdtemp(prefix="qwq_fanout_strat_test_")
os.environ["QWQ_RUNTIME_ROOT"] = _TMP

from _common import fanout_plan as fp  # noqa: E402
from _common import fanout_strategies as fs  # noqa: E402


def _plan() -> dict:
    plan = fp.new_plan("planX", "全国景点主页", "travel", partition_dimension="省")
    fp.add_partition(plan, "四川省")
    fp.add_partition(plan, "云南省")
    fp.add_leaves(plan, ["四川省"], [{"name": "九寨沟"}, {"name": "稻城亚丁"}, {"name": "峨眉山"}])
    fp.add_leaves(plan, ["云南省"], [{"name": "玉龙雪山"}])
    return plan


def test_task_id_addressing():
    plan = _plan()
    units = fs.expand_units(plan)
    sc = next(u for u in units if u["partitionPath"] == ["四川省"])
    assert sc["taskId"] == "旅行/地域/四川省/全国景点主页"
    assert sc["batchId"] == "fanout_planX"
    assert len(sc["refs"]) == 3


def test_by_partition_one_assignment_per_partition():
    plan = _plan()
    exp = fs.expand(plan, strategy="by-partition")
    assert len(exp["assignments"]) == 2
    assert all(a["kind"] == "partition" for a in exp["assignments"])


def test_by_leaf_one_assignment_per_leaf():
    plan = _plan()
    exp = fs.expand(plan, strategy="by-leaf")
    assert len(exp["assignments"]) == 4  # 3 + 1 leaves
    assert all(len(a["refs"]) == 1 for a in exp["assignments"])


def test_flat_pool_concurrency_capped_by_leaves():
    plan = _plan()
    exp = fs.expand(plan, strategy="flat-pool", concurrency=10)
    # 4 leaves total → at most 4 pool workers
    assert len(exp["assignments"]) == 4
    assert all(a["kind"] == "pool-worker" and a["refs"] == [] for a in exp["assignments"])
    # 每个 pool worker 都能 lease 全部分区单元
    assert all(len(a["targets"]) == 2 for a in exp["assignments"])


def test_by_batch_chunks_within_partition():
    plan = _plan()
    exp = fs.expand(plan, strategy="by-batch", batch_size=2)
    # 四川 3 refs → 2 chunks (2+1)；云南 1 ref → 1 chunk = 3 assignments
    assert len(exp["assignments"]) == 3
    sc_chunks = [a for a in exp["assignments"] if a["partitionPath"] == ["四川省"]]
    assert sorted(len(a["refs"]) for a in sc_chunks) == [1, 2]


def test_flat_pool_concurrency_one_single_worker():
    plan = _plan()
    exp = fs.expand(plan, strategy="flat-pool", concurrency=1)
    assert len(exp["assignments"]) == 1
    assert exp["assignments"][0]["kind"] == "pool-worker"


def test_unknown_strategy_rejected():
    plan = _plan()
    try:
        fs.expand(plan, strategy="bogus")
    except ValueError as exc:
        assert "unknown strategy" in str(exc)
    else:
        raise AssertionError("unknown strategy must raise")


def test_deterministic_expansion():
    plan = _plan()
    a = fs.expand(plan, strategy="by-partition")
    b = fs.expand(plan, strategy="by-partition")
    assert a == b


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"fanout_strategies tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
