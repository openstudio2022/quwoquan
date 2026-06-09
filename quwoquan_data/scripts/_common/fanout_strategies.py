"""fan-out 四策略展开：把冻结计划树确定性映射为「task/batch 单元 + agent 分配」。

「多种方式一批拉起多个 agents」一键切换（与计划 defaults.strategy / --strategy 对齐）：

- by-partition：每个叶子分区一个 orchestrator agent（如省 agent），消费本分区队列、拉叶子 subagent。
- flat-pool   ：M 个 worker（M=concurrency）跨全部分区 lease 叶子（最省 agent 数）。
- by-leaf     ：每个叶子一个 cloud agent（最大并行 / 最高成本）。
- by-batch    ：叶子按 batchSize 在分区内切块，每块一个 agent。

展开是纯函数、确定性的（同计划同策略 → 同 assignment 集），供 dispatch 与 runner 共用，
也供退化等价测试（fanout concurrency=1 ≈ single）断言。

task/batch 寻址真相源：
- taskId = build_task_id(vertical, organizeBy, partition.taskKey, category, name)
- batchId = "fanout_{planId}"（同计划稳定，幂等可重放）
"""
from __future__ import annotations

import math
from typing import Any, Mapping

from _common.fanout_plan import iter_leaves, leaf_partitions
from task.store import build_task_id

STRATEGY_BY_PARTITION = "by-partition"
STRATEGY_FLAT_POOL = "flat-pool"
STRATEGY_BY_LEAF = "by-leaf"
STRATEGY_BY_BATCH = "by-batch"
VALID_STRATEGIES = (STRATEGY_BY_PARTITION, STRATEGY_FLAT_POOL, STRATEGY_BY_LEAF, STRATEGY_BY_BATCH)


def partition_batch_id(plan: Mapping[str, Any]) -> str:
    return f"fanout_{plan.get('planId')}"


def _partition_name(plan: Mapping[str, Any], partition: Mapping[str, Any]) -> str:
    defaults = plan.get("defaults") or {}
    return str(defaults.get("taskName") or plan.get("goal") or partition.get("key") or "fanout")


def partition_task_id(plan: Mapping[str, Any], partition: Mapping[str, Any]) -> str:
    defaults = plan.get("defaults") or {}
    organize_by = str(defaults.get("organizeBy") or "地域")
    category = str(partition.get("category") or defaults.get("category") or "") or None
    return build_task_id(
        str(plan.get("vertical") or "travel"),
        organize_by,
        str(partition.get("taskKey") or partition.get("key")),
        category,
        _partition_name(plan, partition),
    )


def partition_refs(partition: Mapping[str, Any]) -> list[str]:
    return [str(l.get("ref")) for l in partition.get("leaves") or [] if l.get("ref")]


def expand_units(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    """确定性 task/batch 单元（与策略无关）：每个叶子分区 → 一个 (taskId, batchId, refs)。"""
    batch_id = partition_batch_id(plan)
    units: list[dict[str, Any]] = []
    for partition in leaf_partitions(plan):
        leaves = partition.get("leaves") or []
        entity_types = sorted({str(l.get("entityType")) for l in leaves if l.get("entityType")})
        units.append(
            {
                "partitionPath": list(partition.get("path") or [partition.get("key")]),
                "taskKey": str(partition.get("taskKey") or partition.get("key")),
                "taskName": _partition_name(plan, partition),
                "taskId": partition_task_id(plan, partition),
                "batchId": batch_id,
                "category": partition.get("category") or (plan.get("defaults") or {}).get("category"),
                "entityTypes": entity_types,
                "refs": partition_refs(partition),
                "leaves": [
                    {"ref": str(l.get("ref")), "name": l.get("name"), "entityType": l.get("entityType"),
                     "mutexKey": l.get("mutexKey") or l.get("ref")}
                    for l in leaves
                ],
            }
        )
    return units


def _chunk(items: list[str], size: int) -> list[list[str]]:
    size = max(1, int(size))
    return [items[i : i + size] for i in range(0, len(items), size)] or [[]]


def expand(
    plan: Mapping[str, Any],
    *,
    strategy: str | None = None,
    concurrency: int | None = None,
    batch_size: int | None = None,
) -> dict[str, Any]:
    """把计划展开为 {strategy, concurrency, units, assignments}。

    assignment 是「一次 agent 拉起」的工作单元：
      {assignmentId, kind, targets:[{taskId,batchId}], refs:[...], partitionPath?}
    runner 据 targets lease-next，据 refs 限定范围（pool-worker refs 为空=跨全单元 lease）。
    """
    defaults = plan.get("defaults") or {}
    strat = str(strategy or defaults.get("strategy") or STRATEGY_BY_PARTITION)
    if strat not in VALID_STRATEGIES:
        raise ValueError(f"unknown strategy {strat!r}; valid={VALID_STRATEGIES}")
    conc = int(concurrency if concurrency is not None else defaults.get("concurrency") or 1)
    conc = max(1, conc)
    bsize = int(batch_size if batch_size is not None else defaults.get("batchSize") or 5)

    units = expand_units(plan)
    assignments: list[dict[str, Any]] = []

    if strat == STRATEGY_BY_PARTITION:
        for unit in units:
            assignments.append(
                {
                    "assignmentId": f"part::{'/'.join(unit['partitionPath'])}",
                    "kind": "partition",
                    "targets": [{"taskId": unit["taskId"], "batchId": unit["batchId"]}],
                    "refs": list(unit["refs"]),
                    "partitionPath": unit["partitionPath"],
                }
            )

    elif strat == STRATEGY_FLAT_POOL:
        targets = [{"taskId": u["taskId"], "batchId": u["batchId"]} for u in units]
        # 池 worker 数不超过总叶子数（无活可干的 worker 无意义）。
        total_leaves = sum(len(u["refs"]) for u in units)
        workers = max(1, min(conc, total_leaves or 1))
        for i in range(workers):
            assignments.append(
                {
                    "assignmentId": f"pool::w{i}",
                    "kind": "pool-worker",
                    "workerIndex": i,
                    "targets": targets,
                    "refs": [],  # 跨全单元 lease（不预分配）
                }
            )

    elif strat == STRATEGY_BY_LEAF:
        for path, leaf in iter_leaves(plan):
            unit = next((u for u in units if u["partitionPath"] == path), None)
            if unit is None:
                continue
            ref = str(leaf.get("ref"))
            assignments.append(
                {
                    "assignmentId": f"leaf::{ref}",
                    "kind": "leaf",
                    "targets": [{"taskId": unit["taskId"], "batchId": unit["batchId"]}],
                    "refs": [ref],
                    "partitionPath": path,
                }
            )

    elif strat == STRATEGY_BY_BATCH:
        for unit in units:
            for ci, chunk in enumerate(_chunk(list(unit["refs"]), bsize)):
                if not chunk:
                    continue
                assignments.append(
                    {
                        "assignmentId": f"batch::{'/'.join(unit['partitionPath'])}#{ci}",
                        "kind": "batch",
                        "targets": [{"taskId": unit["taskId"], "batchId": unit["batchId"]}],
                        "refs": chunk,
                        "partitionPath": unit["partitionPath"],
                    }
                )

    return {
        "planId": plan.get("planId"),
        "strategy": strat,
        "concurrency": conc,
        "batchSize": bsize,
        "units": units,
        "assignments": assignments,
    }
