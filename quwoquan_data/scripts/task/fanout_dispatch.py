"""阶段 B 确定性分层调度：把冻结计划落成 task/batch + object-queue 叶子 job（幂等可重放）。

`qwq-data task run --mode fanout` 的核心：
  冻结计划 → 每叶子分区建 committed task（task new 等价）→ 各叶子 enqueue 为 author job
  → 按 strategy 展开 assignment（供 cursor-sdk 外部 runner 消费）。

幂等性：
- task new：spec 已存在则跳过（不 --force 不覆盖）。
- object-queue enqueue：jobId = sha1(task|batch|ref|stage) 稳定，重复 enqueue 不重置 attempt。
- dispatch_state.json：记录已建 task / 已 enqueue 分区，重放安全。

与单模式的关系：fanout --strategy flat-pool --concurrency 1 的终态 job 集与
单模式顺序处理同一分区等价（见 tests/orchestrate/test_mode_single_fanout_equivalence.py）。
不重复造队列/门：复用 object_queue + handoff + Ralph 出口门。
"""
from __future__ import annotations

from typing import Any, Mapping

from _common import fanout_strategies as fs
from _common.io import read_json, write_json
from _common.paths import fanout_dispatch_state_path
from task import object_queue as oq
from task import store

DISPATCH_STATE_VERSION = "quwoquan_data.fanout_dispatch_state/1"


def ensure_partition_task(plan: Mapping[str, Any], unit: Mapping[str, Any]) -> dict[str, Any]:
    """为一个叶子分区建 committed task（幂等：已存在则不覆盖）。返回 {taskId, created}。"""
    defaults = plan.get("defaults") or {}
    scope: dict[str, Any] = {
        "coverageTargets": [
            {"entityType": l.get("entityType"), "name": l.get("name")} for l in unit.get("leaves") or []
        ],
    }
    if unit.get("entityTypes"):
        scope["entityTypes"] = list(unit["entityTypes"])

    spec = store.scaffold_spec(
        vertical=str(plan.get("vertical") or "travel"),
        organize_by=str(defaults.get("organizeBy") or "地域"),
        key=str(unit.get("taskKey")),
        name=str(unit.get("taskName")),
        category=(str(unit.get("category")) if unit.get("category") else None),
        scope=scope,
        created_by="task run --mode fanout",
    )
    task_id = spec["taskId"]
    if task_id != unit.get("taskId"):
        # 不一致说明寻址漂移（strategies 与 scaffold 不同源），直接暴露而非静默。
        raise RuntimeError(f"task id drift: scaffold={task_id} != strategy={unit.get('taskId')}")
    if store.spec_exists(task_id):
        return {"taskId": task_id, "created": False}
    store.save_spec(spec)
    remaining = [f"{l.get('entityType')}/{l.get('name')}" for l in unit.get("leaves") or []]
    store.save_progress(store.init_progress(task_id, remaining=remaining))
    return {"taskId": task_id, "created": True}


def enqueue_partition_leaves(plan: Mapping[str, Any], unit: Mapping[str, Any]) -> list[dict[str, Any]]:
    """把分区叶子 enqueue 为 object-queue author job（幂等）。"""
    defaults = plan.get("defaults") or {}
    stage = str(defaults.get("stage") or "author")
    budget = defaults.get("budget") or {}
    jobs: list[dict[str, Any]] = []
    for leaf in unit.get("leaves") or []:
        ref = str(leaf.get("ref") or "").strip()
        if not ref:
            continue
        jobs.append(
            oq.enqueue_ref_job(
                str(unit["taskId"]),
                str(unit["batchId"]),
                ref,
                stage,
                mutex_key=str(leaf.get("mutexKey") or ref),
                max_attempts=int(budget.get("maxAttempts") or oq.DEFAULT_MAX_ATTEMPTS),
                max_wall_clock_seconds=int(budget.get("maxWallClockSeconds") or oq.DEFAULT_MAX_WALL_CLOCK_SECONDS),
                stuck_threshold=int(budget.get("stuckThreshold") or oq.DEFAULT_STUCK_THRESHOLD),
                token_budget=int(budget.get("tokenBudget") or 0),
                cost_budget_usd=float(budget.get("costBudgetUsd") or 0.0),
                meta={
                    "planId": plan.get("planId"),
                    "partitionPath": list(unit.get("partitionPath") or []),
                    "entityType": leaf.get("entityType"),
                    "name": leaf.get("name"),
                },
            )
        )
    return jobs


def dispatch(
    plan: Mapping[str, Any],
    *,
    strategy: str | None = None,
    concurrency: int | None = None,
    batch_size: int | None = None,
) -> dict[str, Any]:
    """执行调度：建 task + enqueue 叶子 + 展开 assignment。要求 plan 已冻结。

    返回 dispatch 报告（含 expansion 与 perPartition 统计），并落 dispatch_state.json。
    """
    if str(plan.get("status")) != "frozen":
        raise ValueError(f"plan must be frozen before dispatch (status={plan.get('status')})")

    expansion = fs.expand(plan, strategy=strategy, concurrency=concurrency, batch_size=batch_size)
    per_partition: list[dict[str, Any]] = []
    created_tasks: list[str] = []
    for unit in expansion["units"]:
        task_info = ensure_partition_task(plan, unit)
        if task_info["created"]:
            created_tasks.append(task_info["taskId"])
        jobs = enqueue_partition_leaves(plan, unit)
        per_partition.append(
            {
                "partitionPath": unit["partitionPath"],
                "taskId": unit["taskId"],
                "batchId": unit["batchId"],
                "taskCreated": task_info["created"],
                "enqueued": len(jobs),
                "queueSummary": oq.queue_summary(unit["taskId"], unit["batchId"]),
            }
        )

    report = {
        "schemaVersion": DISPATCH_STATE_VERSION,
        "planId": plan.get("planId"),
        "strategy": expansion["strategy"],
        "concurrency": expansion["concurrency"],
        "batchSize": expansion["batchSize"],
        "createdTasks": created_tasks,
        "assignments": expansion["assignments"],
        "perPartition": per_partition,
        "totals": {
            "partitions": len(per_partition),
            "tasksCreated": len(created_tasks),
            "leavesEnqueued": sum(p["enqueued"] for p in per_partition),
            "assignments": len(expansion["assignments"]),
        },
        "updatedAt": store.now_iso(),
    }
    write_json(fanout_dispatch_state_path(str(plan["planId"])), report)
    return report


def load_dispatch_state(plan_id: str) -> dict[str, Any] | None:
    path = fanout_dispatch_state_path(plan_id)
    if not path.is_file():
        return None
    data = read_json(path)
    return data if isinstance(data, dict) else None
