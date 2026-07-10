"""退化等价契约：fanout --concurrency 1 与 single 同终态。

核心断言（与 13-coding-discipline R24 防两套实现一致）：
- fanout flat-pool concurrency=1 展开恰好 1 个 worker（顺序消费 = 单会话）。
- 顺序 drain 该 worker 的目标队列后，所有叶子 ref 终态 succeeded，
  与单模式逐 ref 处理同一分区得到的成品集合一致。

可直接运行：python3 quwoquan_data/tests/local_contract/orchestrate/test_mode_single_fanout_equivalence__local_contract_test.py
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

_TMP = tempfile.mkdtemp(prefix="qwq_mode_equiv_test_")
os.environ["QWQ_RUNTIME_ROOT"] = str(Path(_TMP) / "runtime")
os.environ["QWQ_COMMITTED_TASKS_ROOT"] = str(Path(_TMP) / "tasks")

from _common import fanout_plan as fp  # noqa: E402
from _common import fanout_strategies as fs  # noqa: E402
from task import fanout_dispatch as fd  # noqa: E402
from task import object_queue as oq  # noqa: E402


def _single_partition_plan(plan_id: str) -> dict:
    plan = fp.new_plan(plan_id, "四川景点主页", "travel", defaults={"entityType": "地点/景区"})
    fp.add_partition(plan, "四川省")
    fp.add_leaves(plan, ["四川省"], [{"name": "九寨沟"}, {"name": "稻城亚丁"}, {"name": "峨眉山"}])
    fp.freeze_plan(plan, confirmed=True)
    fp.save_plan(plan)
    return plan


def _drain_sequentially(targets: list[dict], worker: str) -> list[str]:
    """单 worker 顺序 lease→complete 直到无活，返回成功的 ref（模拟会话内顺序创作）。"""
    succeeded: list[str] = []
    guard = 0
    while guard < 100:
        guard += 1
        leased = None
        for t in targets:
            job = oq.acquire_lease(t["taskId"], t["batchId"], worker=worker, stage="author")
            if job is not None:
                oq.complete_job(t["taskId"], t["batchId"], job["jobId"], job["lease"])
                succeeded.append(str(job["ref"]))
                leased = job
                break
        if leased is None:
            break
    return sorted(succeeded)


def test_flat_pool_concurrency_one_single_worker():
    plan = _single_partition_plan("p_eq_expand")
    exp = fs.expand(plan, strategy="flat-pool", concurrency=1)
    assert len(exp["assignments"]) == 1
    assert exp["assignments"][0]["kind"] == "pool-worker"


def test_fanout_conc1_terminal_equals_all_refs():
    plan = _single_partition_plan("p_eq_drain")
    report = fd.dispatch(plan, strategy="flat-pool", concurrency=1)
    assignment = report["assignments"][0]
    drained = _drain_sequentially(assignment["targets"], worker="solo")
    expected = sorted(["地点_景区__九寨沟", "地点_景区__稻城亚丁", "地点_景区__峨眉山"])
    assert drained == expected, f"{drained} != {expected}"
    # 终态全部 succeeded（与单模式逐 ref 走完一致）
    sc = "旅行/地域/四川省/四川景点主页"
    summary = oq.queue_summary(sc, "fanout_p_eq_drain")
    assert summary["byState"].get("succeeded") == expected
    assert "queued" not in summary["byState"]


def test_conc1_and_concN_same_enqueued_set():
    """并发度只影响拉起 worker 数，不影响入队 job 集（幂等真相源单一）。"""
    plan1 = _single_partition_plan("p_eq_c1")
    planN = _single_partition_plan("p_eq_cN")
    r1 = fd.dispatch(plan1, strategy="flat-pool", concurrency=1)
    rN = fd.dispatch(planN, strategy="by-leaf", concurrency=9)
    assert r1["totals"]["leavesEnqueued"] == rN["totals"]["leavesEnqueued"] == 3


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"mode equivalence tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
