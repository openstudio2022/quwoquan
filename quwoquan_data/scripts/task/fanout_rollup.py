"""fan-out 归并、观测与治理：分区 reducer + 全局进度/SLO + dead/spillover 巡检。

`qwq-data task rollup --plan <id>`：聚合冻结计划各分区 object-queue 状态 + batch_reducer_gate，
算全局进度/通过率/dead 率，落 rollup.json。drift 抽检复用 `qwq-data verify sample-drift`（链接，不重写）。
"""
from __future__ import annotations

from typing import Any, Mapping

from _common import fanout_plan as fp
from _common import fanout_strategies as fs
from _common.io import read_json, write_json
from _common.paths import batch_root, fanout_rollup_path
from task import object_queue as oq
from task import store

ROLLUP_VERSION = "quwoquan_data.fanout_rollup/1"


def _reducer_gate(task_id: str, batch_id: str) -> dict[str, Any] | None:
    path = batch_root(task_id, batch_id) / "_shared" / "batch_reducer_gate.json"
    if not path.is_file():
        return None
    data = read_json(path)
    return data if isinstance(data, dict) else None


def build_rollup(plan: Mapping[str, Any]) -> dict[str, Any]:
    expansion = fs.expand_units(plan)
    partitions: list[dict[str, Any]] = []
    totals = {"leaves": 0, "succeeded": 0, "failed": 0, "dead": 0, "queued": 0, "leased": 0, "spilled": 0}

    for unit in expansion:
        task_id = unit["taskId"]
        batch_id = unit["batchId"]
        summary = oq.queue_summary(task_id, batch_id)
        by_state = summary.get("byState") or {}
        counts = {state: len(refs) for state, refs in by_state.items()}
        leaves = summary.get("total", 0)
        succeeded = counts.get(oq.STATE_SUCCEEDED, 0)
        dead = counts.get(oq.STATE_DEAD, 0)
        reducer = _reducer_gate(task_id, batch_id)
        notifications = oq.list_notifications(task_id, batch_id)
        partitions.append(
            {
                "partitionPath": unit["partitionPath"],
                "taskId": task_id,
                "batchId": batch_id,
                "leaves": leaves,
                "counts": counts,
                "deadRefs": [d["ref"] for d in oq.dead_jobs(task_id, batch_id)],
                "reducerGate": {"present": reducer is not None, "passed": (reducer or {}).get("passed")}
                if reducer is not None else {"present": False},
                "notifications": len(notifications),
                "complete": leaves > 0 and succeeded == leaves,
            }
        )
        totals["leaves"] += leaves
        totals["succeeded"] += succeeded
        totals["failed"] += counts.get(oq.STATE_FAILED, 0)
        totals["dead"] += dead
        totals["queued"] += counts.get(oq.STATE_QUEUED, 0)
        totals["leased"] += counts.get(oq.STATE_LEASED, 0)
        totals["spilled"] += counts.get(oq.STATE_SPILLED, 0)

    leaves_total = totals["leaves"] or 1
    slo = {
        "progress": round(totals["succeeded"] / leaves_total, 4),
        "passRate": round(totals["succeeded"] / leaves_total, 4),
        "deadRate": round(totals["dead"] / leaves_total, 4),
        "partitionsComplete": sum(1 for p in partitions if p["complete"]),
        "partitionsTotal": len(partitions),
    }
    return {
        "schemaVersion": ROLLUP_VERSION,
        "planId": plan.get("planId"),
        "goal": plan.get("goal"),
        "status": plan.get("status"),
        "totals": totals,
        "slo": slo,
        "partitions": partitions,
        "driftCheck": "qwq-data verify sample-drift（抽检产线漂移；不在 rollup 内重复实现）",
        "deadRepair": "qwq-data object-queue spillover --task <t> --batch <b> --target-batch <repair>（dead 溢出独立修复批）",
        "updatedAt": store.now_iso(),
    }


def rollup(plan_id: str) -> dict[str, Any]:
    plan = fp.load_plan(plan_id)
    if plan is None:
        raise ValueError(f"plan not found: {plan_id}")
    report = build_rollup(plan)
    write_json(fanout_rollup_path(plan_id), report)
    return report
