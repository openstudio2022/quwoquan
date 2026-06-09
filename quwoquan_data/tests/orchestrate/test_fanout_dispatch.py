"""fanout_dispatch contract tests：建 task + enqueue 叶子 + 幂等可重放。

可直接运行：python3 quwoquan_data/tests/orchestrate/test_fanout_dispatch.py
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

# 隔离 runtime + committed 根（避免污染仓库 quwoquan_data/tasks）
_TMP = tempfile.mkdtemp(prefix="qwq_fanout_dispatch_test_")
os.environ["QWQ_RUNTIME_ROOT"] = str(Path(_TMP) / "runtime")
os.environ["QWQ_COMMITTED_TASKS_ROOT"] = str(Path(_TMP) / "tasks")

from _common import fanout_plan as fp  # noqa: E402
from task import fanout_dispatch as fd  # noqa: E402
from task import object_queue as oq  # noqa: E402
from task import store  # noqa: E402


def _frozen_plan(plan_id: str) -> dict:
    plan = fp.new_plan(plan_id, "全国景点主页", "travel", defaults={"strategy": "by-partition", "concurrency": 3, "entityType": "地点/景区"})
    fp.add_partition(plan, "四川省")
    fp.add_partition(plan, "云南省")
    fp.add_leaves(plan, ["四川省"], [{"name": "九寨沟"}, {"name": "稻城亚丁"}])
    fp.add_leaves(plan, ["云南省"], [{"name": "玉龙雪山"}])
    fp.freeze_plan(plan, confirmed=True)
    fp.save_plan(plan)
    return plan


def test_dispatch_requires_frozen():
    plan = fp.new_plan("p_unfrozen", "g", "travel")
    fp.add_partition(plan, "A")
    fp.add_leaves(plan, ["A"], [{"name": "x"}])
    try:
        fd.dispatch(plan)
    except ValueError as exc:
        assert "frozen" in str(exc)
    else:
        raise AssertionError("dispatch must require frozen plan")


def test_dispatch_creates_tasks_and_enqueues_leaves():
    plan = _frozen_plan("p_dispatch1")
    report = fd.dispatch(plan)
    assert report["totals"]["partitions"] == 2
    assert report["totals"]["tasksCreated"] == 2
    assert report["totals"]["leavesEnqueued"] == 3
    # committed task spec 真的落盘
    sc_task = "旅行/地域/四川省/全国景点主页"
    assert store.spec_exists(sc_task)
    summary = oq.queue_summary(sc_task, "fanout_p_dispatch1")
    assert summary["total"] == 2


def test_dispatch_is_idempotent():
    plan = _frozen_plan("p_dispatch2")
    r1 = fd.dispatch(plan)
    r2 = fd.dispatch(plan)
    assert r1["totals"]["leavesEnqueued"] == r2["totals"]["leavesEnqueued"]
    # 第二次不再新建 task
    assert r2["totals"]["tasksCreated"] == 0
    # 队列总数不翻倍
    assert r1["perPartition"][0]["queueSummary"]["total"] == r2["perPartition"][0]["queueSummary"]["total"]


def test_dispatch_state_persisted():
    plan = _frozen_plan("p_dispatch3")
    fd.dispatch(plan)
    state = fd.load_dispatch_state("p_dispatch3")
    assert state is not None
    assert state["planId"] == "p_dispatch3"
    assert state["strategy"] == "by-partition"


def test_strategy_invariant_job_set():
    """终态 job 集与策略/并发无关：by-leaf 与 flat-pool 入队同一组 jobId。"""
    plan_a = _frozen_plan("p_inv_a")
    plan_b = _frozen_plan("p_inv_b")
    fd.dispatch(plan_a, strategy="by-leaf", concurrency=5)
    fd.dispatch(plan_b, strategy="flat-pool", concurrency=1)
    sc = "旅行/地域/四川省/全国景点主页"
    jobs_a = sorted(oq.queue_summary(sc.replace("p_inv", "p_inv"), "fanout_p_inv_a")["byState"].get("queued", []))
    jobs_b = sorted(oq.queue_summary(sc, "fanout_p_inv_b")["byState"].get("queued", []))
    assert jobs_a == jobs_b == ["地点_景区__九寨沟", "地点_景区__稻城亚丁"]


def test_rollup_aggregates_partitions():
    from task import fanout_rollup
    from task import object_queue as _oq

    plan = _frozen_plan("p_rollup")
    fd.dispatch(plan)
    # 让四川一个叶子成功
    sc = "旅行/地域/四川省/全国景点主页"
    job = _oq.acquire_lease(sc, "fanout_p_rollup", worker="w", stage="author")
    _oq.complete_job(sc, "fanout_p_rollup", job["jobId"], job["lease"])

    report = fanout_rollup.rollup("p_rollup")
    assert report["totals"]["leaves"] == 3
    assert report["totals"]["succeeded"] == 1
    assert report["slo"]["partitionsTotal"] == 2
    assert 0.0 < report["slo"]["progress"] < 1.0


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"fanout_dispatch tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
