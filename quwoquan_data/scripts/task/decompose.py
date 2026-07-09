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


def _partitions_from_task_selection(task_id: str) -> list[dict]:
    """把 committed task 的 target_selection.json 投影为 discovery partitions（WP5）。

    批次冻结计划必须与 select-targets 圈选结果同源（ready 过滤 + dedup 账本排除后
    的精确成员），否则分区 task 会覆盖未圈选地点。分组键 = 目标 region（区县），
    主清单契约字段（geoTagRef 等）随目标透传。
    """
    from _common.io import read_json as _read_json
    from task import store as task_store

    selection_path = task_store.committed_task_root(task_id) / "_shared" / "target_selection.json"
    if not selection_path.is_file():
        raise FileNotFoundError(f"task selection 不存在: {selection_path}（先 task select-targets --write）")
    payload = _read_json(selection_path)
    targets = [row for row in (payload.get("targets") or []) if isinstance(row, dict)]
    grouped: dict[str, list[dict]] = {}
    for row in targets:
        region = str(row.get("region") or "").strip() or "未分区"
        leaf = {key: value for key, value in row.items() if key not in ("region", "sourceName")}
        grouped.setdefault(region, []).append(leaf)
    return [{"key": region, "leaves": leaves} for region, leaves in grouped.items()]


def handle_load(args: argparse.Namespace) -> None:
    """从 agent 发现产物批量合并。三种输入（互斥）：

    ① --discovery：discovery JSON：
    {"partitions": [
        {"key": "四川省", "path": ["四川省"]?, "category": "景区"?, "taskKey": "四川省"?,
         "leaves": [{"name": "九寨沟", "entityType": "地点/景区"}, ...],
         "partitions": [ ...递归... ]}
    ]}

    ② --master-list --provinces 四川省,浙江省：行政区枚举 SOP 产线——
       从主清单目录（verticals/travel/coverage/中国/{省}/{市州}.yaml）只读投影
       省→市州→区县三级分区树递归合并，叶子 name 取 canonicalName；
       同时在 plan.geoCoverage 声明省份，发现门叠加地理覆盖校验
       （市州文件齐全 + 区县全覆盖；叶子 geoTagRef/类型 scope 由
       `qwq-data verify coverage-master-list` C1-C9 承担）。

    ③ --from-task-selection <taskId>：批次圈选同源投影（WP5 fanout by-partition）——
       读 committed task 的 target_selection.json，按目标 region（区县）分组成分区，
       计划成员与 select-targets 结果精确一致（ready 过滤 + dedup 排除后）。
    """
    plan = _require_plan(args.plan)
    provinces = [p.strip() for p in (getattr(args, "provinces", "") or "").split(",") if p.strip()]
    from_task = str(getattr(args, "from_task_selection", "") or "").strip()
    if from_task:
        try:
            parts = _partitions_from_task_selection(from_task)
        except (FileNotFoundError, ValueError, OSError) as exc:
            print(f"[task decompose] ERROR: {exc}", file=sys.stderr)
            raise SystemExit(2)
        if not parts:
            print(f"[task decompose] ERROR: task {from_task} 的 target_selection 无目标", file=sys.stderr)
            raise SystemExit(2)
    elif getattr(args, "master_list", False):
        if not provinces:
            print("[task decompose] ERROR: --master-list 需要 --provinces 省份列表", file=sys.stderr)
            raise SystemExit(2)
        from _common.coverage_master_list import discovery_partitions_from_master_list

        parts = discovery_partitions_from_master_list(provinces)
        if not parts:
            print(f"[task decompose] ERROR: 主清单目录下未找到省份 {provinces} 的市州文件", file=sys.stderr)
            raise SystemExit(2)
        geo = plan.setdefault("geoCoverage", {"country": "中国", "provinces": []})
        geo["provinces"] = sorted({*geo.get("provinces", []), *provinces})
    else:
        if not args.discovery:
            print("[task decompose] ERROR: 需要 --discovery JSON、--master-list --provinces 或 --from-task-selection", file=sys.stderr)
            raise SystemExit(2)
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

    pld = dsub.add_parser("load", help="从发现产物 JSON 或主清单目录批量合并分区+叶子")
    pld.add_argument("--plan", required=True)
    pld.add_argument("--discovery", help="发现产物 JSON 路径（顶层 partitions[]）")
    pld.add_argument(
        "--master-list",
        dest="master_list",
        action="store_true",
        help="从主清单目录（coverage/中国/{省}/{市州}.yaml）投影省→市州→区县分区树，并声明地理覆盖门",
    )
    pld.add_argument("--provinces", help="--master-list 模式的省份列表（逗号分隔，如 四川省,浙江省）")
    pld.add_argument(
        "--from-task-selection",
        dest="from_task_selection",
        help="批次圈选同源投影（WP5）：读 committed task 的 target_selection.json，按目标 region 分组成分区",
    )
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
