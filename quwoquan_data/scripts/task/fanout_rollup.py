"""fan-out 归并、观测与治理：分区 reducer + 全局进度/SLO + dead/spillover 巡检。

`qwq-data task rollup --plan <id>`：聚合冻结计划各分区 object-queue 状态 + batch_reducer_gate，
算全局进度/通过率/dead 率，落 rollup.json。drift 抽检复用 `qwq-data verify sample-drift`（链接，不重写）。
"""
from __future__ import annotations

from typing import Any, Mapping

from _common import fanout_plan as fp
from _common import fanout_strategies as fs
from _common import content_object
from _common.io import read_json, write_json
from _common.paths import batch_root, fanout_rollup_path, fanout_run_matrix_path, fanout_summary_path
from task import object_queue as oq
from task.run import load_workflow_state
from task import store

ROLLUP_VERSION = "quwoquan_data.fanout_rollup/1"
SUMMARY_VERSION = "quwoquan_data.fanout_summary/1"


def _reducer_gate(task_id: str, batch_id: str) -> dict[str, Any] | None:
    path = batch_root(task_id, batch_id) / "_shared" / "batch_reducer_gate.json"
    if not path.is_file():
        return None
    data = read_json(path)
    return data if isinstance(data, dict) else None


def _run_matrix(plan_id: str) -> dict[str, Any]:
    path = fanout_run_matrix_path(plan_id)
    if not path.is_file():
        return {}
    data = read_json(path)
    return data if isinstance(data, dict) else {}


def _save_run_matrix(plan_id: str, matrix: Mapping[str, Any]) -> None:
    write_json(fanout_run_matrix_path(plan_id), dict(matrix))


def _safe_div(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _workflow_status(task_id: str, batch_id: str) -> dict[str, Any]:
    state = load_workflow_state(task_id, batch_id)
    waiting = str(state.get("waitingCheckpoint") or "")
    completed = [str(item) for item in (state.get("completed") or []) if str(item)]
    if "publish" in completed:
        status = "succeeded"
    elif waiting:
        status = "manual_required" if waiting == "produce_author" else "queued"
    elif state.get("lastFailedStage"):
        status = "failed"
    else:
        status = "queued"
    return {
        "status": status,
        "waitingCheckpoint": waiting or None,
        "completed": completed,
        "lastFailedStage": str(state.get("lastFailedStage") or "") or None,
    }


def _published_refs(task_id: str, batch_id: str) -> set[str]:
    published: set[str] = set()
    for ref in content_object.iter_content_refs(task_id, batch_id):
        try:
            obj_dir = content_object.content_object_dir(task_id, batch_id, ref)
        except KeyError:
            continue
        manifest_path = obj_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = read_json(manifest_path)
        except Exception:  # noqa: BLE001
            continue
        if str(manifest.get("reviewDecision") or "") == "approved":
            published.add(ref)
    return published


def _unit_ref_names(
    task_id: str,
    batch_id: str,
    queue: Mapping[str, Any],
    matrix_refs: Mapping[str, Any],
) -> list[str]:
    refs = {
        ref
        for state_refs in (queue.get("byState") or {}).values()
        for ref in state_refs
    }
    refs.update(content_object.iter_content_refs(task_id, batch_id))
    refs.update(
        ref
        for ref, rec in matrix_refs.items()
        if isinstance(rec, Mapping)
        and str(rec.get("taskId") or "") == task_id
        and str(rec.get("batchId") or "") == batch_id
    )
    return sorted(refs)


def _plan_ref_rows(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    plan_id = str(plan.get("planId") or "")
    matrix = _run_matrix(plan_id)
    matrix_refs = matrix.get("refs") if isinstance(matrix.get("refs"), Mapping) else {}
    rows: list[dict[str, Any]] = []
    for unit in fs.expand_units(plan):
        task_id = str(unit["taskId"])
        batch_id = str(unit["batchId"])
        queue = oq.queue_summary(task_id, batch_id)
        workflow = _workflow_status(task_id, batch_id)
        reducer = _reducer_gate(task_id, batch_id)
        published_refs = _published_refs(task_id, batch_id)
        jobs = {
            str(job.get("ref") or ""): job
            for job in oq._load_jobs(task_id, batch_id)  # noqa: SLF001 - 汇总阶段读取终态真相源
            if str(job.get("stage") or "") == "author"
        }
        ref_names = _unit_ref_names(task_id, batch_id, queue, matrix_refs if isinstance(matrix_refs, Mapping) else {})
        for ref in ref_names:
            job = jobs.get(ref) or {}
            state = str(job.get("state") or "")
            if ref in published_refs or workflow["status"] == "succeeded":
                final_status = "succeeded"
            elif state == oq.STATE_SUCCEEDED:
                final_status = "succeeded"
            elif state == oq.STATE_DEAD:
                final_status = "manual_required"
            elif state == oq.STATE_BLOCKED:
                final_status = "manual_required"
            elif state == oq.STATE_SPILLED:
                final_status = "failed"
            elif state == oq.STATE_FAILED:
                final_status = "queued" if bool(job.get("sameRunRetryable", True)) else "failed"
            elif state == oq.STATE_LEASED:
                final_status = "leased"
            elif state == oq.STATE_QUEUED:
                final_status = "queued"
            else:
                final_status = workflow["status"]
            record = matrix_refs.get(ref) if isinstance(matrix_refs, Mapping) else None
            rows.append(
                {
                    "ref": ref,
                    "taskId": task_id,
                    "batchId": batch_id,
                    "partitionPath": list(unit.get("partitionPath") or []),
                    "queueState": state or None,
                    "status": final_status,
                    "workflowStatus": workflow["status"],
                    "waitingCheckpoint": workflow["waitingCheckpoint"],
                    "lastFailedStage": workflow["lastFailedStage"],
                    "reducerPassed": (reducer or {}).get("passed") if reducer is not None else None,
                    "published": ref in published_refs,
                    "runRecord": dict(record) if isinstance(record, Mapping) else None,
                    "lastError": str(job.get("lastError") or "") or None,
                }
            )
    return rows


def _build_plan_summary(plan: Mapping[str, Any], rollup: Mapping[str, Any]) -> dict[str, Any]:
    plan_id = str(plan.get("planId") or "")
    rows = _plan_ref_rows(plan)
    by_status: dict[str, int] = {}
    startup_failures = 0
    retryable_failures = 0
    spillover_count = 0
    for row in rows:
        status = str(row.get("status") or "queued")
        by_status[status] = by_status.get(status, 0) + 1
        record = row.get("runRecord") if isinstance(row.get("runRecord"), Mapping) else {}
        if str(record.get("status") or "") == "startup_failed":
            startup_failures += 1
        if status == "queued" and str(row.get("queueState") or "") == oq.STATE_FAILED:
            retryable_failures += 1
        if str(row.get("queueState") or "") == oq.STATE_SPILLED:
            spillover_count += 1
    total_refs = len(rows)
    succeeded = by_status.get("succeeded", 0)
    failed = by_status.get("failed", 0)
    manual_required = by_status.get("manual_required", 0)
    queued = by_status.get("queued", 0)
    leased = by_status.get("leased", 0)
    publishable = succeeded if failed == 0 and manual_required == 0 and queued == 0 and leased == 0 else 0
    summary = {
        "schemaVersion": SUMMARY_VERSION,
        "planId": plan_id,
        "goal": plan.get("goal"),
        "status": "ready_for_next_stage" if publishable == total_refs and total_refs > 0 else "blocked",
        "counts": {
            "totalRefs": total_refs,
            "succeeded": succeeded,
            "failed": failed,
            "manualRequired": manual_required,
            "queued": queued,
            "leased": leased,
            "publishable": publishable,
        },
        "metrics": {
            "startupFailureRate": _safe_div(startup_failures, total_refs),
            "retryConvergence": _safe_div(succeeded, succeeded + retryable_failures + failed + manual_required),
            "spilloverRate": _safe_div(spillover_count, total_refs),
            "publishablePassRate": _safe_div(publishable, total_refs),
        },
        "blockingRefs": {
            "failed": sorted(row["ref"] for row in rows if row["status"] == "failed"),
            "manualRequired": sorted(row["ref"] for row in rows if row["status"] == "manual_required"),
            "queued": sorted(row["ref"] for row in rows if row["status"] == "queued"),
            "leased": sorted(row["ref"] for row in rows if row["status"] == "leased"),
        },
        "refs": rows,
        "rollupPath": str(fanout_rollup_path(plan_id)),
        "runMatrixPath": str(fanout_run_matrix_path(plan_id)),
        "updatedAt": store.now_iso(),
    }
    if isinstance(rollup.get("totals"), Mapping):
        summary["queueTotals"] = dict(rollup["totals"])
    return summary


def build_rollup(plan: Mapping[str, Any]) -> dict[str, Any]:
    expansion = fs.expand_units(plan)
    ref_rows = _plan_ref_rows(plan)
    rows_by_unit: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in ref_rows:
        key = (str(row.get("taskId") or ""), str(row.get("batchId") or ""))
        rows_by_unit.setdefault(key, []).append(row)
    partitions: list[dict[str, Any]] = []
    totals = {
        "leaves": 0,
        "succeeded": 0,
        "failed": 0,
        "manualRequired": 0,
        "queued": 0,
        "leased": 0,
        "dead": 0,
        "spilled": 0,
    }

    for unit in expansion:
        task_id = unit["taskId"]
        batch_id = unit["batchId"]
        unit_rows = rows_by_unit.get((str(task_id), str(batch_id)), [])
        summary = oq.queue_summary(task_id, batch_id)
        by_state = summary.get("byState") or {}
        queue_counts = {state: len(refs) for state, refs in by_state.items()}
        counts = {
            "succeeded": sum(1 for row in unit_rows if row["status"] == "succeeded"),
            "failed": sum(1 for row in unit_rows if row["status"] == "failed"),
            "manualRequired": sum(1 for row in unit_rows if row["status"] == "manual_required"),
            "queued": sum(1 for row in unit_rows if row["status"] == "queued"),
            "leased": sum(1 for row in unit_rows if row["status"] == "leased"),
        }
        leaves = len(unit_rows)
        succeeded = counts["succeeded"]
        dead = queue_counts.get(oq.STATE_DEAD, 0)
        reducer = _reducer_gate(task_id, batch_id)
        notifications = oq.list_notifications(task_id, batch_id)
        workflow = _workflow_status(task_id, batch_id)
        partitions.append(
            {
                "partitionPath": unit["partitionPath"],
                "taskId": task_id,
                "batchId": batch_id,
                "leaves": leaves,
                "counts": counts,
                "queueCounts": queue_counts,
                "deadRefs": [d["ref"] for d in oq.dead_jobs(task_id, batch_id)],
                "reducerGate": {"present": reducer is not None, "passed": (reducer or {}).get("passed")}
                if reducer is not None else {"present": False},
                "notifications": len(notifications),
                "workflow": workflow,
                "complete": leaves > 0 and counts["succeeded"] == leaves,
            }
        )
        totals["leaves"] += leaves
        totals["succeeded"] += counts["succeeded"]
        totals["failed"] += counts["failed"]
        totals["manualRequired"] += counts["manualRequired"]
        totals["queued"] += counts["queued"]
        totals["leased"] += counts["leased"]
        totals["dead"] += dead
        totals["spilled"] += queue_counts.get(oq.STATE_SPILLED, 0)

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
    matrix = _run_matrix(plan_id)
    rows = _plan_ref_rows(plan)
    matrix_refs = matrix.get("refs") if isinstance(matrix.get("refs"), Mapping) else {}
    patched_refs: dict[str, Any] = {}
    startup_failures = 0
    completed = 0
    failed = 0
    for row in rows:
        ref = str(row.get("ref") or "")
        record = dict(matrix_refs.get(ref) or {}) if isinstance(matrix_refs, Mapping) else {}
        status = str(row.get("status") or "")
        if status == "succeeded":
            completed += 1
        elif status == "failed":
            failed += 1
        if str(record.get("status") or "") == "startup_failed":
            startup_failures += 1
        if status == "succeeded":
            record["status"] = "succeeded"
            record["started"] = True
            record["finalStatus"] = "succeeded"
            record["published"] = bool(row.get("published"))
            record["workflowStatus"] = str(row.get("workflowStatus") or "")
            record["waitingCheckpoint"] = row.get("waitingCheckpoint")
        patched_refs[ref] = record
    matrix["refs"] = patched_refs
    matrix["summary"] = {
        "assignments": len(rows),
        "leased": sum(1 for row in rows if str(row.get("status") or "") == "leased"),
        "completed": completed,
        "failed": failed,
        "attemptFailures": 0,
        "startupFailures": startup_failures,
        "orchestrated": len(matrix.get("orchestrators") or []),
        "orchestrationFailed": sum(
            1 for row in (matrix.get("orchestrators") or []) if isinstance(row, Mapping) and str(row.get("started")) == "False"
        ),
        "startupFailureRate": _safe_div(startup_failures, max(1, completed + failed)),
        "retryConvergence": _safe_div(completed, max(1, completed + failed)),
        "spilloverRate": 0.0,
    }
    _save_run_matrix(plan_id, matrix)
    write_json(fanout_rollup_path(plan_id), report)
    write_json(fanout_summary_path(plan_id), _build_plan_summary(plan, report))
    return report
