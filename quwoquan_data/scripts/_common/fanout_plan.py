"""fan-out 编排分片计划树：构建 / 加载 / 校验 / 去重 / 互斥 / 覆盖 / 冻结门。

阶段 A（agent 发现式分解）写回此计划；冻结后是阶段 B（确定性分层调度）唯一真相源。
计划落 runtime/_shared/orchestrate/{planId}/fanout_plan.json（不进 publish）。

设计原则（与 13-coding-discipline R24 抽象克制一致）：
- 纯逻辑、确定性（时间戳走 store.now_iso()，便于测试）。
- 分片维度不绑定固定行政区划；由 planner agent 按用户指令决定（省/区县/类别/批）。
- 叶子去重 + 分区互斥：同一 ref 全局唯一，不得跨分区重复（避免重复生产）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from _common.io import read_json, write_json
from _common.paths import fanout_plan_path
from task import store

PLAN_SCHEMA = "quwoquan_data.fanout_plan/1"
VALID_VERTICALS = ("travel", "campus", "photography", "tech", "car")
VALID_STATUS = ("draft", "frozen", "running", "done")
VALID_STRATEGIES = ("by-partition", "flat-pool", "by-leaf", "by-batch")

DEFAULT_DEFAULTS: dict[str, Any] = {
    "stage": "author",
    "organizeBy": "地域",
    "strategy": "by-partition",
    "concurrency": 4,
    "batchSize": 5,
    "budget": {
        "maxWallClockSeconds": 1200,
        "maxAttempts": 2,
        "stuckThreshold": 3,
        "tokenBudget": 0,
        "costBudgetUsd": 0.0,
    },
}


def leaf_ref(entity_type: str, name: str) -> str:
    """稳定叶子 ref = entityType__name（/ 替换为 _），与 task run produce_plan 约定一致。"""
    etype = str(entity_type or "").strip() or "地点/景区"
    return f"{etype}__{str(name).strip()}".replace("/", "_")


# ─── 构建 ──────────────────────────────────────────────────────────────
def new_plan(
    plan_id: str,
    goal: str,
    vertical: str,
    *,
    partition_dimension: str = "",
    defaults: Mapping[str, Any] | None = None,
    source_task_id: str = "",
) -> dict[str, Any]:
    merged = {**DEFAULT_DEFAULTS, **(dict(defaults) if defaults else {})}
    if defaults and isinstance(defaults.get("budget"), Mapping):
        merged["budget"] = {**DEFAULT_DEFAULTS["budget"], **dict(defaults["budget"])}
    return {
        "schemaVersion": PLAN_SCHEMA,
        "planId": plan_id,
        "goal": goal,
        "vertical": vertical,
        "sourceTaskId": source_task_id or "",
        "partitionDimension": partition_dimension,
        "status": "draft",
        "createdAt": store.now_iso(),
        "updatedAt": store.now_iso(),
        "frozenAt": None,
        "defaults": merged,
        "coverageTargets": {},
        "partitions": [],
    }


def _find_partition(partitions: list[dict[str, Any]], path: list[str]) -> dict[str, Any] | None:
    """按 path 在分区树中定位分区（递归）。"""
    if not path:
        return None
    head, *rest = path
    for part in partitions:
        if str(part.get("key")) == head:
            if not rest:
                return part
            return _find_partition(part.get("partitions") or [], rest)
    return None


def add_partition(
    plan: dict[str, Any],
    key: str,
    *,
    parent_path: list[str] | None = None,
    task_key: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """新增分区（支持递归：parent_path 指定挂载点；空=根）。幂等：已存在则返回现有。"""
    parent_path = parent_path or []
    container = plan["partitions"]
    if parent_path:
        parent = _find_partition(plan["partitions"], parent_path)
        if parent is None:
            raise ValueError(f"parent partition not found: {parent_path}")
        container = parent.setdefault("partitions", [])
    path = [*parent_path, key]
    existing = next((p for p in container if str(p.get("key")) == key), None)
    if existing is not None:
        return existing
    partition = {
        "key": key,
        "path": path,
        "taskKey": task_key or key,
        "leaves": [],
        "partitions": [],
    }
    if category:
        partition["category"] = category
    container.append(partition)
    plan["updatedAt"] = store.now_iso()
    return partition


# 主清单 leaf → 计划叶子契约字段透传集（与 task_spec coverageTargets 同口径，WP5）：
# geoTagRef 是 homepage 物化必填（build/homepage._REQUIRED_ENTITY_FIELDS），
# 丢失会让 fanout 分区 task 在 build_validate 硬阻断。
LEAF_CONTRACT_SCALAR_FIELDS = ("geoTagRef",)
LEAF_CONTRACT_LIST_FIELDS = ("geoTagRefs", "typeTagRefs", "aliases")


def apply_leaf_contract_fields(row: dict[str, Any], leaf: Mapping[str, Any]) -> dict[str, Any]:
    """把主清单契约字段（存在才写）从 leaf 透传到目标 row（计划叶子 / coverageTarget）。"""
    for field in LEAF_CONTRACT_SCALAR_FIELDS:
        value = str(leaf.get(field) or "").strip()
        if value:
            row[field] = value
    for field in LEAF_CONTRACT_LIST_FIELDS:
        values = [str(v).strip() for v in (leaf.get(field) or []) if str(v).strip()]
        if values:
            row[field] = values
    return row


def add_leaves(
    plan: dict[str, Any],
    partition_path: list[str],
    leaves: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """向分区追加叶子对象（幂等去重：同 ref 不重复加入本分区）。

    leaves 每条 {name, entityType?, ref?, mutexKey?}；缺省 ref 由 leaf_ref 派生。
    主清单契约字段（geoTagRef/geoTagRefs/typeTagRefs/aliases）存在即透传，
    供 fanout 分区 task 的 coverageTargets/baseline 消费（打标 + 物化必填）。
    """
    partition = _find_partition(plan["partitions"], partition_path)
    if partition is None:
        raise ValueError(f"partition not found: {partition_path}")
    existing_refs = {str(l.get("ref")) for l in partition.get("leaves") or []}
    added: list[dict[str, Any]] = []
    for raw in leaves:
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        etype = str(raw.get("entityType") or plan.get("defaults", {}).get("entityType") or "地点/景区")
        ref = str(raw.get("ref") or "").strip() or leaf_ref(etype, name)
        if ref in existing_refs:
            continue
        leaf = apply_leaf_contract_fields(
            {
                "name": name,
                "entityType": etype,
                "ref": ref,
                "mutexKey": str(raw.get("mutexKey") or "") or ref,
            },
            raw,
        )
        partition.setdefault("leaves", []).append(leaf)
        existing_refs.add(ref)
        added.append(leaf)
    plan["updatedAt"] = store.now_iso()
    return added


# ─── 遍历 ──────────────────────────────────────────────────────────────
def iter_partitions(plan: Mapping[str, Any]) -> Iterator[dict[str, Any]]:
    """深度优先遍历所有分区（含递归子分区）。"""

    def _walk(parts: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        for part in parts:
            yield part
            yield from _walk(part.get("partitions") or [])

    yield from _walk(list(plan.get("partitions") or []))


def iter_leaves(plan: Mapping[str, Any]) -> Iterator[tuple[list[str], dict[str, Any]]]:
    """遍历所有叶子，返回 (partitionPath, leaf)。"""
    for part in iter_partitions(plan):
        path = list(part.get("path") or [part.get("key")])
        for leaf in part.get("leaves") or []:
            yield path, leaf


def leaf_partitions(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    """返回直接挂载叶子的分区（叶子分区 = 调度的最小 task 单元）。"""
    return [p for p in iter_partitions(plan) if p.get("leaves")]


# ─── 校验门 ────────────────────────────────────────────────────────────
def leaf_dedup_issues(plan: Mapping[str, Any]) -> list[str]:
    """叶子去重门：同一 ref 不得在计划中出现多次（跨分区也算重复）。"""
    seen: dict[str, list[str]] = {}
    for path, leaf in iter_leaves(plan):
        ref = str(leaf.get("ref") or "")
        if not ref:
            continue
        seen.setdefault(ref, []).append("/".join(path))
    return [
        f"duplicate leaf ref {ref!r} appears in partitions {parts}"
        for ref, parts in sorted(seen.items())
        if len(parts) > 1
    ]


def partition_mutex_issues(plan: Mapping[str, Any]) -> list[str]:
    """分区互斥门：同一 mutexKey 不得跨不同叶子分区（避免同源并行派生雷同）。"""
    by_mutex: dict[str, set[str]] = {}
    for path, leaf in iter_leaves(plan):
        mutex = str(leaf.get("mutexKey") or leaf.get("ref") or "")
        if not mutex:
            continue
        by_mutex.setdefault(mutex, set()).add("/".join(path))
    return [
        f"mutexKey {mutex!r} spans multiple partitions {sorted(parts)} (同源不得跨分区并行)"
        for mutex, parts in sorted(by_mutex.items())
        if len(parts) > 1
    ]


def coverage_issues(plan: Mapping[str, Any]) -> list[str]:
    """覆盖门：声明的 coverageTargets 与实际分区/叶子规模一致（声明才校验）。"""
    issues: list[str] = []
    targets = plan.get("coverageTargets") or {}
    want_parts = int(targets.get("partitions") or 0)
    want_leaves = int(targets.get("leaves") or 0)
    if want_parts:
        actual = len(leaf_partitions(plan))
        if actual != want_parts:
            issues.append(f"coverage: declared {want_parts} partitions but plan has {actual}")
    if want_leaves:
        actual_leaves = sum(1 for _ in iter_leaves(plan))
        if actual_leaves != want_leaves:
            issues.append(f"coverage: declared {want_leaves} leaves but plan has {actual_leaves}")
    return issues


def discovery_gate_issues(plan: Mapping[str, Any]) -> list[str]:
    """发现门（阶段 A 出口 / 冻结前置）：结构完整 + 无空分区 + 去重 + 互斥 + 覆盖。"""
    issues: list[str] = []
    if str(plan.get("schemaVersion")) != PLAN_SCHEMA:
        issues.append(f"schemaVersion must be {PLAN_SCHEMA}")
    if str(plan.get("vertical")) not in VALID_VERTICALS:
        issues.append(f"vertical must be one of {VALID_VERTICALS}")
    if not str(plan.get("goal") or "").strip():
        issues.append("goal required")
    partitions = plan.get("partitions") or []
    if not partitions:
        issues.append("plan has no partitions (planner agent must discover at least one)")
    strategy = str((plan.get("defaults") or {}).get("strategy") or "")
    if strategy and strategy not in VALID_STRATEGIES:
        issues.append(f"defaults.strategy must be one of {VALID_STRATEGIES}")

    # 无空分区：每个分区必须有叶子或子分区。
    for part in iter_partitions(plan):
        has_leaves = bool(part.get("leaves"))
        has_sub = bool(part.get("partitions"))
        if not has_leaves and not has_sub:
            issues.append(f"empty partition {'/'.join(part.get('path') or [part.get('key', '?')])} (no leaves / sub-partitions)")
        if not str(part.get("key") or "").strip():
            issues.append("partition missing key")

    # 叶子字段完整。
    for path, leaf in iter_leaves(plan):
        where = "/".join(path)
        if not str(leaf.get("name") or "").strip():
            issues.append(f"leaf in {where} missing name")
        if not str(leaf.get("ref") or "").strip():
            issues.append(f"leaf {leaf.get('name')!r} in {where} missing ref")

    issues += leaf_dedup_issues(plan)
    issues += partition_mutex_issues(plan)
    issues += coverage_issues(plan)
    issues += geo_coverage_gate_issues(plan)
    return issues


def geo_coverage_gate_issues(plan: Mapping[str, Any]) -> list[str]:
    """地理覆盖发现门（枚举产线 SOP）：plan 声明 geoCoverage 时才校验。

    `decompose load --master-list` 写入 geoCoverage = {country, provinces[]}，
    冻结前要求声明省份的主清单市州文件齐全、每文件覆盖行政区树全部区县
    （唯一实现在 _common.coverage_master_list.geo_coverage_issues；此处仅接线，
    延迟 import 保持本模块对未声明 geoCoverage 的计划零文件系统依赖）。
    """
    geo = plan.get("geoCoverage") or {}
    provinces = [str(p) for p in (geo.get("provinces") or []) if str(p).strip()]
    if not provinces:
        return []
    from _common.coverage_master_list import geo_coverage_issues

    return geo_coverage_issues(provinces, country=str(geo.get("country") or "中国"))


def freeze_plan(plan: dict[str, Any], *, confirmed: bool) -> dict[str, Any]:
    """冻结计划：必须发现门全过 + 人工确认（confirmed=True）。返回冻结后的 plan。

    冻结后 status=frozen，是阶段 B 唯一真相源（幂等可重放）。
    """
    issues = discovery_gate_issues(plan)
    if issues:
        raise ValueError("cannot freeze: discovery gate failed:\n  - " + "\n  - ".join(issues))
    if not confirmed:
        raise ValueError("cannot freeze: human confirmation required (--confirm)")
    plan["status"] = "frozen"
    plan["frozenAt"] = store.now_iso()
    plan["updatedAt"] = store.now_iso()
    return plan


def plan_summary(plan: Mapping[str, Any]) -> dict[str, Any]:
    parts = leaf_partitions(plan)
    return {
        "planId": plan.get("planId"),
        "goal": plan.get("goal"),
        "status": plan.get("status"),
        "strategy": (plan.get("defaults") or {}).get("strategy"),
        "concurrency": (plan.get("defaults") or {}).get("concurrency"),
        "leafPartitions": len(parts),
        "totalPartitions": sum(1 for _ in iter_partitions(plan)),
        "leaves": sum(1 for _ in iter_leaves(plan)),
    }


# ─── IO ────────────────────────────────────────────────────────────────
def save_plan(plan: dict[str, Any]) -> Path:
    plan["updatedAt"] = store.now_iso()
    path = fanout_plan_path(plan["planId"])
    write_json(path, plan)
    return path


def load_plan(plan_id: str) -> dict[str, Any] | None:
    path = fanout_plan_path(plan_id)
    if not path.is_file():
        return None
    data = read_json(path)
    return data if isinstance(data, dict) else None
