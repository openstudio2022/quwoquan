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

from _common.command_packet import build_packet, write_packet
from _common import fanout_strategies as fs
from _common import ops_governance as og
from _common.io import read_json, write_json, write_ndjson
from _common.paths import fanout_dispatch_state_path, task_baseline_freeze_packet_path, task_catalog, task_shared_dir
from task import object_queue as oq
from task import store

DISPATCH_STATE_VERSION = "quwoquan_data.fanout_dispatch_state/1"


def _plan_controller_run_id(plan: Mapping[str, Any]) -> str:
    explicit = str(plan.get("controllerRunId") or "").strip()
    return explicit or f"plan:{plan.get('planId')}"


def _job_assignment(
    plan: Mapping[str, Any],
    unit: Mapping[str, Any],
    *,
    ref: str,
    role: str,
    scope: Mapping[str, Any],
    allowed_write_roots: list[str],
    budget: Mapping[str, Any],
) -> dict[str, Any]:
    controller_run_id = _plan_controller_run_id(plan)
    partition_path = [str(item) for item in (unit.get("partitionPath") or []) if str(item).strip()]
    batch_assignment = og.build_assignment(
        task_id=str(unit["taskId"]),
        batch_id=str(unit["batchId"]),
        controller_run_id=controller_run_id,
        assignment_path=["batch"],
        role="batch_controller",
        scope={
            "sliceType": "batch",
            "planId": str(plan.get("planId") or ""),
            "taskId": str(unit["taskId"]),
            "batchId": str(unit["batchId"]),
        },
        allowed_read_roots=["_shared"],
        allowed_write_roots=["_shared"],
        budget={"maxAttempts": 1},
    )
    batch_assignment = og.append_assignment(str(unit["taskId"]), str(unit["batchId"]), batch_assignment)
    slice_path = partition_path or ["sourceTask"]
    partition_assignment = og.build_assignment(
        task_id=str(unit["taskId"]),
        batch_id=str(unit["batchId"]),
        controller_run_id=controller_run_id,
        assignment_path=[*slice_path],
        role="partition_agent",
        parent_assignment_id=str(batch_assignment["assignmentId"]),
        scope={
            "sliceType": "partition",
            "partitionPath": slice_path,
            "planId": str(plan.get("planId") or ""),
        },
        allowed_read_roots=["_shared"],
        allowed_write_roots=["_shared"],
        budget={"maxAttempts": 1},
    )
    partition_assignment = og.append_assignment(str(unit["taskId"]), str(unit["batchId"]), partition_assignment)
    assignment_path = [*slice_path, ref]
    assignment = og.build_assignment(
        task_id=str(unit["taskId"]),
        batch_id=str(unit["batchId"]),
        controller_run_id=controller_run_id,
        assignment_path=assignment_path,
        role=role,
        parent_assignment_id=str(partition_assignment["assignmentId"]),
        scope=scope,
        allowed_read_roots=["_shared", *allowed_write_roots],
        allowed_write_roots=allowed_write_roots,
        budget=budget,
    )
    og.append_assignment(str(unit["taskId"]), str(unit["batchId"]), assignment)
    return assignment


def content_ref_author_mode(plan: Mapping[str, Any]) -> bool:
    """sourceTask 派生型 fanout：author 队列以 compose 后内容对象 ref 为真相源。"""
    return bool(str(plan.get("sourceTaskId") or "").strip())


def _source_task_spec(plan: Mapping[str, Any]) -> dict[str, Any] | None:
    source_task_id = str(plan.get("sourceTaskId") or "").strip()
    if not source_task_id or not store.spec_exists(source_task_id):
        return None
    return store.load_spec(source_task_id)


def _partition_region(unit: Mapping[str, Any], source_spec: Mapping[str, Any] | None) -> str:
    key = str(unit.get("taskKey") or "").strip()
    if key:
        return key
    if source_spec:
        return str((source_spec.get("scope") or {}).get("region") or "")
    return ""


def _inherit_content(plan: Mapping[str, Any], source_spec: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if source_spec and isinstance(source_spec.get("content"), Mapping):
        return dict(source_spec.get("content") or {})
    defaults = plan.get("defaults") or {}
    content: dict[str, Any] = {}
    if defaults.get("angles"):
        content["angles"] = list(defaults.get("angles") or [])
    return content or None


def _distribute_quota(total: int, weights: list[int]) -> list[int]:
    """按叶子数比例守恒分摊配额；余数用最大余数法补齐。"""
    total = max(0, int(total or 0))
    if total <= 0 or not weights:
        return [0 for _ in weights]
    safe_weights = [max(0, int(w or 0)) for w in weights]
    weight_sum = sum(safe_weights)
    if weight_sum <= 0:
        # 极端兜底：均匀分摊，保持总量守恒。
        base, rem = divmod(total, len(safe_weights))
        return [base + (1 if i < rem else 0) for i in range(len(safe_weights))]
    floors: list[int] = []
    remainders: list[tuple[int, int]] = []
    allocated = 0
    for idx, weight in enumerate(safe_weights):
        product = total * weight
        floor = product // weight_sum
        remainder = product % weight_sum
        floors.append(floor)
        remainders.append((remainder, idx))
        allocated += floor
    remaining = total - allocated
    for _remainder, idx in sorted(remainders, key=lambda item: (-item[0], item[1]))[:remaining]:
        floors[idx] += 1
    return floors


def _plan_unit_leaf_weights(plan: Mapping[str, Any]) -> dict[tuple[str, ...], int]:
    return {
        tuple(unit.get("partitionPath") or []): len(unit.get("leaves") or [])
        for unit in fs.expand_units(plan)
    }


def _partition_quotas(
    plan: Mapping[str, Any],
    source_spec: Mapping[str, Any] | None,
) -> dict[tuple[str, ...], dict[str, int]]:
    """把 source task 总配额按分区叶子数守恒分摊到派生分区 task。"""
    if not source_spec or not isinstance(source_spec.get("content"), Mapping):
        return {}
    quotas = (source_spec.get("content") or {}).get("quotas") or {}
    if not isinstance(quotas, Mapping):
        return {}
    unit_weights = _plan_unit_leaf_weights(plan)
    paths = list(unit_weights.keys())
    weights = [unit_weights[path] for path in paths]
    quota_keys = ("entityArticles", "routeArticles", "galleryPosts")
    distributed: dict[str, list[int]] = {
        key: _distribute_quota(int(quotas.get(key) or 0), weights)
        for key in quota_keys
    }
    out: dict[tuple[str, ...], dict[str, int]] = {}
    for idx, path in enumerate(paths):
        values = {
            key: distributed[key][idx]
            for key in quota_keys
            if distributed[key][idx] > 0
        }
        if values:
            out[path] = values
    return out


def _ensure_partition_baseline(task_id: str, unit: Mapping[str, Any]) -> None:
    rows = []
    region = str(unit.get("region") or "")
    for leaf in unit.get("leaves") or []:
        entity_type = str(leaf.get("entityType") or "").strip()
        name = str(leaf.get("name") or "").strip()
        if not entity_type or not name:
            continue
        rows.append(
            {
                "topic_id": f"{entity_type}/{name}",
                "domain": entity_type.split("/", 1)[0] if "/" in entity_type else "",
                "entity_type": entity_type,
                "canonical_name": name,
                "region": region,
                "source_count": 1,
                "geo_tag_ref": f"/tag/地域/{region}" if region else "",
                "source_kind": "coverageTarget",
                "status": "candidate",
                "taskId": task_id,
            }
        )
    write_ndjson(task_catalog(task_id), rows)
    packet = build_packet(
        task_id=task_id,
        command="data baseline",
        object_kind="task",
        object_ref=task_id,
        stage="baseline",
        read_policy=["task.yaml", "progress.json", "catalog.ndjson"],
        stop_if=["taskId mismatch", "catalog does not cover all explore targets"],
        output_policy=["write task/_shared/baseline_freeze_packet.json", "write task/_shared/baseline_report.json"],
        inputs={
            "taskSpecPath": str(store.committed_task_spec(task_id) if hasattr(store, "committed_task_spec") else ""),
            "progressPath": str(store.committed_task_progress(task_id) if hasattr(store, "committed_task_progress") else ""),
            "catalogPath": str(task_catalog(task_id)),
        },
        outputs={
            "packetPath": str(task_baseline_freeze_packet_path(task_id)),
            "reportPath": str(task_shared_dir(task_id) / "baseline_report.json"),
        },
        handoff_to="data workflow run",
        evidence={"required": ["baseline_freeze_packet.json", "baseline_report.json"]},
        summary={"catalogRowCount": len(rows), "coverageTargetCount": len(rows), "taskRegion": region},
    )
    write_packet(task_baseline_freeze_packet_path(task_id), packet)
    write_json(
        task_shared_dir(task_id) / "baseline_report.json",
        {
            "schemaVersion": "quwoquan.data.baseline_report/1",
            "taskId": task_id,
            "status": "passed",
            "issues": [],
            "packetPath": str(task_baseline_freeze_packet_path(task_id)),
            "inputs": {"catalogPath": str(task_catalog(task_id))},
            "summary": packet.get("summary") or {},
        },
    )


def ensure_partition_task(plan: Mapping[str, Any], unit: Mapping[str, Any]) -> dict[str, Any]:
    """为一个叶子分区建 committed task（幂等：已存在则不覆盖）。返回 {taskId, created}。"""
    defaults = plan.get("defaults") or {}
    source_spec = _source_task_spec(plan)
    region = _partition_region(unit, source_spec)
    partition_path = tuple(unit.get("partitionPath") or [])
    scope: dict[str, Any] = {
        "coverageTargets": [
            {"entityType": l.get("entityType"), "name": l.get("name")} for l in unit.get("leaves") or []
        ],
    }
    if unit.get("entityTypes"):
        scope["entityTypes"] = list(unit["entityTypes"])
    if region:
        scope["region"] = region

    content = _inherit_content(plan, source_spec)
    quotas_by_partition = _partition_quotas(plan, source_spec)
    if content and partition_path in quotas_by_partition:
        content = dict(content)
        content["quotas"] = quotas_by_partition[partition_path]

    spec = store.scaffold_spec(
        vertical=str(plan.get("vertical") or "travel"),
        organize_by=str(defaults.get("organizeBy") or "地域"),
        key=str(unit.get("taskKey")),
        name=str(unit.get("taskName")),
        category=(str(unit.get("category")) if unit.get("category") else None),
        scope=scope,
        content=content,
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
    unit = {**dict(unit), "region": region}
    _ensure_partition_baseline(task_id, unit)
    return {"taskId": task_id, "created": True}


def enqueue_partition_leaves(plan: Mapping[str, Any], unit: Mapping[str, Any]) -> list[dict[str, Any]]:
    """把分区叶子 enqueue 为 object-queue author job（幂等）。"""
    if content_ref_author_mode(plan):
        return []
    defaults = plan.get("defaults") or {}
    stage = str(defaults.get("stage") or "author")
    budget = defaults.get("budget") or {}
    queue_backend = defaults.get("queueBackend")
    jobs: list[dict[str, Any]] = []
    for leaf in unit.get("leaves") or []:
        ref = str(leaf.get("ref") or "").strip()
        if not ref:
            continue
        assignment = _job_assignment(
            plan,
            unit,
            ref=ref,
            role="object_subagent",
            scope={
                "sliceType": "coverage_leaf",
                "entityType": leaf.get("entityType"),
                "name": leaf.get("name"),
                "ref": ref,
            },
            allowed_write_roots=["_shared/object_queue"],
            budget=budget,
        )
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
                queue_backend=str(queue_backend) if queue_backend else None,
                meta={
                    "planId": plan.get("planId"),
                    "partitionPath": list(unit.get("partitionPath") or []),
                    "entityType": leaf.get("entityType"),
                    "name": leaf.get("name"),
                    "requireGovernance": True,
                    "controllerRunId": assignment["controllerRunId"],
                    "assignmentId": assignment["assignmentId"],
                    "assignmentPath": assignment["assignmentPath"],
                    "owner": assignment["role"],
                    "allowedReadRoots": assignment["allowedReadRoots"],
                    "allowedWriteRoots": assignment["allowedWriteRoots"],
                    "assignment": assignment,
                },
            )
        )
    return jobs


def sync_content_author_jobs(
    plan: Mapping[str, Any],
    target: Mapping[str, Any],
    *,
    partition_path: list[str] | None = None,
    refs: list[str] | None = None,
    force_refs: list[str] | None = None,
) -> dict[str, Any]:
    """在 produce_compose 之后按内容对象 ref 准备 author packet 并入队。"""
    from _common import content_object
    from _common.creator_assignment import CREATOR_ASSIGNMENT_FIELDS, creator_from_payload
    from _common.draft_io import draft_article_path, draft_package_dir, is_placeholder, read_writing_pack, write_writing_pack
    from _common.handoff import build_author_job_packet

    task_id = str(target["taskId"])
    batch_id = str(target["batchId"])
    defaults = plan.get("defaults") or {}
    budget = defaults.get("budget") or {}
    default_creator = creator_from_payload(defaults.get("creatorAssignment") or defaults)
    queue_backend = defaults.get("queueBackend")
    stage_name = str(defaults.get("stage") or "author")
    prepared_refs: list[str] = []
    skipped_authored_refs: list[str] = []
    jobs: list[dict[str, Any]] = []
    ref_filter = {str(item) for item in (refs or []) if str(item).strip()} if refs else None
    force_ref_filter = {str(item) for item in (force_refs or []) if str(item).strip()} if force_refs else set()
    for ref in content_object.iter_content_refs(task_id, batch_id):
        if ref_filter is not None and ref not in ref_filter:
            continue
        try:
            article_path = draft_article_path(task_id, batch_id, ref)
        except KeyError:
            continue
        brief = content_object.read_brief_object(task_id, batch_id, ref) or {}
        pack = read_writing_pack(task_id, batch_id, ref) or {}
        if not brief or not pack:
            continue
        effective_pack = dict(pack)
        creator_assignment = creator_from_payload(effective_pack) or default_creator
        for field in CREATOR_ASSIGNMENT_FIELDS:
            if field in creator_assignment and effective_pack.get(field) in (None, "", {}):
                effective_pack[field] = creator_assignment[field]
        if effective_pack != pack:
            write_writing_pack(task_id, batch_id, ref, effective_pack)
        authored = article_path.is_file() and not is_placeholder(article_path.read_text(encoding="utf-8"))
        packet = build_author_job_packet(
            ref=ref,
            brief=brief,
            writing_pack=effective_pack,
            prompt_rel="4.draft/prompt.md",
            content_object_rel=content_object.content_object_rel(task_id, batch_id, ref),
        )
        write_json(draft_package_dir(task_id, batch_id, ref) / "author_job_packet.json", packet)
        object_dir = content_object.content_object_rel(task_id, batch_id, ref)
        job_meta = {
            "planId": plan.get("planId"),
            "partitionPath": list(partition_path or []),
            "contentRef": ref,
            "contentObjectDir": object_dir,
            "title": effective_pack.get("title"),
            "writingIntent": effective_pack.get("writingIntent"),
            "baseSourceRef": effective_pack.get("baseSourceRef"),
            "sourcePaths": list(effective_pack.get("sourcePaths") or []),
            "carrier": effective_pack.get("carrier"),
            "promptRef": "4.draft/prompt.md",
            "writingPackRef": "3.compose/writing_pack.json",
        }
        job_meta.update(creator_assignment)
        assignment_unit = {**dict(target), "partitionPath": list(partition_path or [])}
        assignment = _job_assignment(
            plan,
            assignment_unit,
            ref=ref,
            role="author_subagent",
            scope={
                "sliceType": "content_ref",
                "ref": ref,
                "contentObjectDir": object_dir,
                "baseSourceRef": effective_pack.get("baseSourceRef"),
            },
            allowed_write_roots=[str(object_dir)],
            budget=budget,
        )
        job_meta.update(
            {
                "requireGovernance": True,
                "controllerRunId": assignment["controllerRunId"],
                "assignmentId": assignment["assignmentId"],
                "assignmentPath": assignment["assignmentPath"],
                "owner": assignment["role"],
                "allowedReadRoots": assignment["allowedReadRoots"],
                "allowedWriteRoots": assignment["allowedWriteRoots"],
                "sourceUnitId": og.source_unit_id(source_ref=str(effective_pack.get("baseSourceRef") or "")),
                "sourceUnitIdRequired": bool(effective_pack.get("baseSourceRef")),
                "assignment": assignment,
            }
        )
        refreshed = oq.refresh_job_definition(
            task_id,
            batch_id,
            ref,
            stage_name,
            mutex_key=str(effective_pack.get("baseSourceRef") or ref),
            max_attempts=int(budget.get("maxAttempts") or oq.DEFAULT_MAX_ATTEMPTS),
            max_startup_failures=int(budget.get("maxStartupFailures") or oq.DEFAULT_MAX_STARTUP_FAILURES),
            max_wall_clock_seconds=int(budget.get("maxWallClockSeconds") or oq.DEFAULT_MAX_WALL_CLOCK_SECONDS),
            stuck_threshold=int(budget.get("stuckThreshold") or oq.DEFAULT_STUCK_THRESHOLD),
            token_budget=int(budget.get("tokenBudget") or 0),
            cost_budget_usd=float(budget.get("costBudgetUsd") or 0.0),
            queue_backend=str(queue_backend) if queue_backend else None,
            meta=job_meta,
        )
        if authored and ref not in force_ref_filter:
            skipped_authored_refs.append(ref)
            continue
        prepared_refs.append(ref)
        if authored and ref in force_ref_filter and refreshed is not None:
            oq.requeue_refs(task_id, batch_id, [ref], stage_name, reason="force_reauthor")
            jobs.append(oq.refresh_job_definition(
                task_id,
                batch_id,
                ref,
                stage_name,
                mutex_key=str(effective_pack.get("baseSourceRef") or ref),
                max_attempts=int(budget.get("maxAttempts") or oq.DEFAULT_MAX_ATTEMPTS),
                max_startup_failures=int(budget.get("maxStartupFailures") or oq.DEFAULT_MAX_STARTUP_FAILURES),
                max_wall_clock_seconds=int(budget.get("maxWallClockSeconds") or oq.DEFAULT_MAX_WALL_CLOCK_SECONDS),
                stuck_threshold=int(budget.get("stuckThreshold") or oq.DEFAULT_STUCK_THRESHOLD),
                token_budget=int(budget.get("tokenBudget") or 0),
                cost_budget_usd=float(budget.get("costBudgetUsd") or 0.0),
                queue_backend=str(queue_backend) if queue_backend else None,
                meta=job_meta,
            ) or {})
            continue
        jobs.append(
            oq.enqueue_ref_job(
                task_id,
                batch_id,
                ref,
                stage_name,
                mutex_key=str(effective_pack.get("baseSourceRef") or ref),
                max_attempts=int(budget.get("maxAttempts") or oq.DEFAULT_MAX_ATTEMPTS),
                max_startup_failures=int(budget.get("maxStartupFailures") or oq.DEFAULT_MAX_STARTUP_FAILURES),
                max_wall_clock_seconds=int(budget.get("maxWallClockSeconds") or oq.DEFAULT_MAX_WALL_CLOCK_SECONDS),
                stuck_threshold=int(budget.get("stuckThreshold") or oq.DEFAULT_STUCK_THRESHOLD),
                token_budget=int(budget.get("tokenBudget") or 0),
                cost_budget_usd=float(budget.get("costBudgetUsd") or 0.0),
                queue_backend=str(queue_backend) if queue_backend else None,
                meta=job_meta,
            )
        )
    if skipped_authored_refs:
        oq.purge_jobs(
            task_id,
            batch_id,
            stage=stage_name,
            refs=skipped_authored_refs,
        )
    if prepared_refs:
        oq.revive_dead_startup_jobs(
            task_id,
            batch_id,
            refs=prepared_refs,
            stage=stage_name,
        )
    return {"preparedRefs": prepared_refs, "skippedAuthoredRefs": skipped_authored_refs, "jobs": jobs}


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
    if content_ref_author_mode(plan) and strategy in {fs.STRATEGY_BY_LEAF, fs.STRATEGY_BY_BATCH}:
        raise ValueError(
            "sourceTask-derived content fanout only supports by-partition/flat-pool; "
            "by-leaf/by-batch still bind coverage leaf refs and would drift from content_object refs"
        )

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
        "contentRefAuthorMode": content_ref_author_mode(plan),
        "strategy": expansion["strategy"],
        "concurrency": expansion["concurrency"],
        "batchSize": expansion["batchSize"],
        "createdTasks": created_tasks,
        "assignments": expansion["assignments"],
        "perPartition": per_partition,
        "totals": {
            "partitions": len(per_partition),
            "tasksCreated": len(created_tasks),
            "leafRefsPlanned": sum(len(u["refs"]) for u in expansion["units"]),
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
