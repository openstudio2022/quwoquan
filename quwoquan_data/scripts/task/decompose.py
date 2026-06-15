"""qwq-data task decompose — 阶段 A：agent 发现式逐层分片写回计划 + 发现门 + 人工冻结。

CLI-first 三段式（[CLI prepare] -> [Agent semantic] -> [CLI validate + gate]）：
- CLI 准备：init 落计划骨架；add-partition / add-leaves / load 提供结构化写回入口。
- Agent 语义：planner agent 联网发现逐层枚举分区与叶子（不绑定固定行政区划，按用户指令分维）。
- CLI 校验+门：show 跑发现门；freeze 在发现门全过 + 人工确认后冻结，成阶段 B 唯一真相源。

子命令：
  init           落计划骨架（goal/vertical/分片维度/defaults/coverageTargets）
  add-partition  新增分区（支持递归 --parent）
  add-leaves     向分区追加叶子对象（幂等去重）
  load           从 agent 发现产物（JSON）批量合并分区+叶子
  show           打印计划摘要 + 发现门未过项
  freeze         发现门全过 + --confirm 后冻结
"""
from __future__ import annotations

import argparse
import json
import sys

from _common import fanout_plan as fp
from _common.io import read_json


def _emit(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _require_plan(plan_id: str) -> dict:
    plan = fp.load_plan(plan_id)
    if plan is None:
        print(f"[task decompose] ERROR: 计划不存在: {plan_id}（先 init）", file=sys.stderr)
        raise SystemExit(2)
    return plan


def _path(arg: str | None) -> list[str]:
    return [p.strip() for p in (arg or "").split("/") if p.strip()]


def handle_init(args: argparse.Namespace) -> None:
    defaults: dict = {}
    if args.organize_by:
        defaults["organizeBy"] = args.organize_by
    if args.category:
        defaults["category"] = args.category
    if args.entity_type:
        defaults["entityType"] = args.entity_type
    if args.strategy:
        defaults["strategy"] = args.strategy
    if args.concurrency is not None:
        defaults["concurrency"] = int(args.concurrency)
    if args.batch_size is not None:
        defaults["batchSize"] = int(args.batch_size)
    if args.task_name:
        defaults["taskName"] = args.task_name

    if fp.load_plan(args.plan) is not None and not args.force:
        print(f"[task decompose] 计划已存在: {args.plan}（--force 重置）", file=sys.stderr)
        raise SystemExit(1)
    plan = fp.new_plan(
        args.plan,
        args.goal,
        args.vertical,
        partition_dimension=args.partition_dimension or "",
        defaults=defaults,
        source_task_id=str(getattr(args, "source_task_id", "") or ""),
    )
    cov: dict = {}
    if args.coverage_partitions is not None:
        cov["partitions"] = int(args.coverage_partitions)
    if args.coverage_leaves is not None:
        cov["leaves"] = int(args.coverage_leaves)
    if cov:
        plan["coverageTargets"] = cov
    path = fp.save_plan(plan)
    print(f"[task decompose] init {args.plan} -> {path}")
    _emit(fp.plan_summary(plan))


def handle_add_partition(args: argparse.Namespace) -> None:
    plan = _require_plan(args.plan)
    partition = fp.add_partition(
        plan,
        args.key,
        parent_path=_path(args.parent) or None,
        task_key=args.task_key,
        category=args.category,
    )
    fp.save_plan(plan)
    print(f"[task decompose] +partition {'/'.join(partition['path'])}")


def handle_add_leaves(args: argparse.Namespace) -> None:
    plan = _require_plan(args.plan)
    names = [n.strip() for n in (args.leaves or "").split(",") if n.strip()]
    leaves = [{"name": n, "entityType": args.entity_type} for n in names] if args.entity_type else [{"name": n} for n in names]
    added = fp.add_leaves(plan, _path(args.partition), leaves)
    fp.save_plan(plan)
    print(f"[task decompose] +{len(added)} leaves -> {args.partition} (skipped dup: {len(names) - len(added)})")


def handle_load(args: argparse.Namespace) -> None:
    """从 agent 发现产物批量合并。discovery JSON：

    {"partitions": [
        {"key": "四川省", "path": ["四川省"]?, "category": "景区"?, "taskKey": "四川省"?,
         "leaves": [{"name": "九寨沟", "entityType": "地点/景区"}, ...],
         "partitions": [ ...递归... ]}
    ]}
    """
    plan = _require_plan(args.plan)
    data = read_json(args.discovery)
    parts = data.get("partitions") if isinstance(data, dict) else None
    if not isinstance(parts, list):
        print("[task decompose] ERROR: discovery JSON 需要顶层 partitions[]", file=sys.stderr)
        raise SystemExit(2)

    added_parts = 0
    added_leaves = 0

    def _merge(nodes: list, parent_path: list[str]) -> None:
        nonlocal added_parts, added_leaves
        for node in nodes:
            if not isinstance(node, dict):
                continue
            key = str(node.get("key") or "").strip()
            if not key:
                continue
            fp.add_partition(
                plan,
                key,
                parent_path=parent_path or None,
                task_key=node.get("taskKey"),
                category=node.get("category"),
            )
            added_parts += 1
            here = [*parent_path, key]
            leaves = node.get("leaves") or []
            if leaves:
                added = fp.add_leaves(plan, here, [l for l in leaves if isinstance(l, dict)])
                added_leaves += len(added)
            sub = node.get("partitions") or []
            if sub:
                _merge(sub, here)

    _merge(parts, [])
    fp.save_plan(plan)
    print(f"[task decompose] loaded discovery: +{added_parts} partitions, +{added_leaves} leaves")
    _emit(fp.plan_summary(plan))


def handle_show(args: argparse.Namespace) -> None:
    plan = _require_plan(args.plan)
    issues = fp.discovery_gate_issues(plan)
    _emit(
        {
            "summary": fp.plan_summary(plan),
            "partitionDimension": plan.get("partitionDimension"),
            "discoveryGate": {"passed": not issues, "issues": issues},
            "frozen": plan.get("status") == "frozen",
        }
    )


def handle_freeze(args: argparse.Namespace) -> None:
    plan = _require_plan(args.plan)
    try:
        fp.freeze_plan(plan, confirmed=bool(args.confirm))
    except ValueError as exc:
        print(f"[task decompose] FREEZE BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(1)
    fp.save_plan(plan)
    print(f"[task decompose] FROZEN {args.plan} @ {plan['frozenAt']}")
    _emit(fp.plan_summary(plan))
    print(
        f"[task decompose] 阶段 B：qwq-data task run --mode fanout --plan {args.plan} "
        f"--strategy {(plan.get('defaults') or {}).get('strategy')} --concurrency {(plan.get('defaults') or {}).get('concurrency')}"
    )


def register_decompose_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("decompose", help="阶段 A：agent 发现式分片写回计划 + 发现门 + 冻结")
    dsub = p.add_subparsers(dest="decompose_command")

    pi = dsub.add_parser("init", help="落计划骨架")
    pi.add_argument("--plan", required=True, help="planId（计划唯一标识）")
    pi.add_argument("--goal", required=True, help="顶层目标，如『全国景点主页』")
    pi.add_argument("--vertical", required=True, choices=["travel", "campus", "photography", "tech", "car"])
    pi.add_argument("--partition-dimension", dest="partition_dimension", help="分片维度人读标签（省/区县/类别/批）")
    pi.add_argument("--source-task-id", dest="source_task_id", help="源任务 taskId（派生分区 task 继承 baseline/spec 用）")
    pi.add_argument("--organize-by", dest="organize_by", choices=["地域", "环线", "主题"], help="task new organizeBy（默认地域）")
    pi.add_argument("--category", help="叶子分区默认 category（如 景区/学校）")
    pi.add_argument("--entity-type", dest="entity_type", help="叶子默认 entityType（如 地点/景区）")
    pi.add_argument("--task-name", dest="task_name", help="分区 task 名（默认取 goal）")
    pi.add_argument("--strategy", choices=["by-partition", "flat-pool", "by-leaf", "by-batch"], help="默认拉起策略")
    pi.add_argument("--concurrency", type=int, help="默认并发度")
    pi.add_argument("--batch-size", dest="batch_size", type=int, help="by-batch 默认每块叶子数")
    pi.add_argument("--coverage-partitions", dest="coverage_partitions", type=int, help="声明分区覆盖目标数（冻结门校验）")
    pi.add_argument("--coverage-leaves", dest="coverage_leaves", type=int, help="声明叶子覆盖目标数（冻结门校验）")
    pi.add_argument("--force", action="store_true", help="计划已存在时重置")
    pi.set_defaults(handler=handle_init)

    pp = dsub.add_parser("add-partition", help="新增分区（递归 --parent）")
    pp.add_argument("--plan", required=True)
    pp.add_argument("--key", required=True, help="分区键，如 四川省")
    pp.add_argument("--parent", help="父分区路径（/ 分隔，如 四川省/阿坝州）；空=根")
    pp.add_argument("--task-key", dest="task_key", help="task new --key（默认取 key）")
    pp.add_argument("--category", help="分区 category")
    pp.set_defaults(handler=handle_add_partition)

    pa = dsub.add_parser("add-leaves", help="向分区追加叶子对象（幂等去重）")
    pa.add_argument("--plan", required=True)
    pa.add_argument("--partition", required=True, help="分区路径（/ 分隔）")
    pa.add_argument("--leaves", required=True, help="叶子名逗号分隔，如 九寨沟,稻城亚丁")
    pa.add_argument("--entity-type", dest="entity_type", help="叶子 entityType（默认取计划 defaults.entityType）")
    pa.set_defaults(handler=handle_add_leaves)

    pld = dsub.add_parser("load", help="从 agent 发现产物 JSON 批量合并分区+叶子")
    pld.add_argument("--plan", required=True)
    pld.add_argument("--discovery", required=True, help="发现产物 JSON 路径（顶层 partitions[]）")
    pld.set_defaults(handler=handle_load)

    psh = dsub.add_parser("show", help="计划摘要 + 发现门")
    psh.add_argument("--plan", required=True)
    psh.set_defaults(handler=handle_show)

    pf = dsub.add_parser("freeze", help="发现门全过 + --confirm 后冻结")
    pf.add_argument("--plan", required=True)
    pf.add_argument("--confirm", action="store_true", help="人工确认冻结（必填）")
    pf.set_defaults(handler=handle_freeze)

    def _dispatch(args: argparse.Namespace) -> None:
        if not getattr(args, "decompose_command", None):
            p.print_help()
            raise SystemExit(1)

    p.set_defaults(handler=_dispatch)
