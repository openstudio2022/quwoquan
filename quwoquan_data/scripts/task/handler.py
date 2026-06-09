"""qwq-data task — 任务工程子命令（薄编排壳，复用现有 explore/build/produce/promote/publish）。

子命令：
  new        从层级参数脚手架 committed task.yaml + progress.json + notes.md
  run        无人值守 workflow 编排：按 DAG 跑 download→build→produce→publish（Agent checkpoint 暂停/resume）
  list       扫描全部 committed 任务总览（--tree 树状，--vertical 过滤）
  show       打印单任务 spec+progress+lock
  lint       校验任务规格（路径↔id、archetype scope、实体类型真相源、重复）
  lock/unlock 并发锁（runtime/.lock，pid+ts+owner，陈旧锁检测）
  resume     读 progress 算缺口，输出下一步
  status     打印覆盖率
  record-run 追加 runs/run_*.json + 刷新 progress
  trace      溯源反查（publish 产物来自哪个任务）
  hydrate    按 sourceTaskId 把 publish 产物拉回 runtime 工作区
"""
from __future__ import annotations


import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import argparse
import json
import sys

from task import lint as lint_mod
from task import ops
from task import queue
from task import store
from task.decompose import register_decompose_parser
from task.run import register_run_parser


def _split(arg: str | None) -> list[str]:
    return [x.strip() for x in (arg or "").split(",") if x.strip()]


def handle_new(args: argparse.Namespace) -> None:
    scope: dict = {}
    if args.region:
        scope["region"] = args.region
    if args.entity_types:
        scope["entityTypes"] = _split(args.entity_types)
    if args.route:
        scope["route"] = args.route
    if args.anchor_entities:
        scope["anchorEntities"] = _split(args.anchor_entities)
    if args.theme:
        scope["theme"] = args.theme
    if args.regions:
        scope["regions"] = _split(args.regions)

    targets: list[dict] = []
    remaining: list[str] = []
    for raw in _split(args.coverage):
        # 格式 领域/类型/名称 或 领域/类型|名称
        if "|" in raw:
            etype, name = raw.split("|", 1)
        else:
            bits = raw.rsplit("/", 1)
            etype, name = (bits[0], bits[1]) if len(bits) == 2 else (raw, raw)
        targets.append({"entityType": etype, "name": name})
        remaining.append(f"{etype}/{name}")
    if targets:
        scope["coverageTargets"] = targets

    # 只写特化 override；未给的字段沿 _defaults.yaml 继承（carriers/audiences/conditionAxes 默认不写）。
    content: dict = {}
    if _split(args.angles):
        content["angles"] = _split(args.angles)
    if _split(args.audiences):
        content["audiences"] = _split(args.audiences)
    if _split(args.carriers):
        content["carriers"] = _split(args.carriers)
    if _split(args.emphasis):
        content["emphasis"] = _split(args.emphasis)
    cond: dict = {}
    if _split(args.cond_regions):
        cond["regions"] = _split(args.cond_regions)
    if _split(args.cond_seasons):
        cond["seasons"] = _split(args.cond_seasons)
    if cond:
        content["conditionAxes"] = cond

    spec = store.scaffold_spec(
        vertical=args.vertical,
        organize_by=args.organize_by,
        key=args.key,
        name=args.name,
        category=args.category,
        archetype=args.archetype,
        title=args.title,
        parent_task_id=args.parent,
        scope=scope,
        content=content,
        created_by=args.owner or "task new",
    )
    if store.spec_exists(spec["taskId"]) and not args.force:
        print(f"[task new] 已存在: {spec['taskId']}（--force 覆盖）", file=sys.stderr)
        raise SystemExit(1)
    spec_path = store.save_spec(spec)
    store.save_progress(store.init_progress(spec["taskId"], remaining=remaining))
    store.write_notes_if_absent(
        spec["taskId"],
        f"# {spec['title']}\n\n- taskId: `{spec['taskId']}`\n- archetype: {spec['taskArchetype']}\n\n"
        f"## 覆盖种子实体\n\n" + "".join(f"- {t['entityType']}/{t['name']}\n" for t in targets) +
        "\n## 经验沉淀\n\n(在此记录踩坑/取舍/数据源)\n",
    )
    print(f"[task new] {spec['taskId']}\n  spec: {spec_path}\n  runtime: {store.runtime_task_root(spec['taskId'])}")


def handle_list(args: argparse.Namespace) -> None:
    if args.tree:
        ops.print_tree(args.vertical)
    else:
        ops.print_list(args.vertical)


def handle_show(args: argparse.Namespace) -> None:
    ops.show(args.task_id)


def handle_lint(args: argparse.Namespace) -> None:
    total, results, warnings = lint_mod.lint_all(args.task_id)
    for tid, warns in warnings.items():
        print(f"WARN {tid}")
        for w in warns:
            print(f"  ~ {w}")
    if not results:
        print("[task lint] OK — 全部任务规格合法")
        return
    for tid, errs in results.items():
        print(f"FAIL {tid}")
        for e in errs:
            print(f"  - {e}")
    print(f"\n[task lint] {total} 处问题")
    raise SystemExit(1)


def handle_lock(args: argparse.Namespace) -> None:
    ok, msg = store.acquire_lock(args.task_id, args.owner or "cli", force=args.force)
    print(f"[task lock] {args.task_id}: {msg}")
    if not ok:
        raise SystemExit(1)


def handle_unlock(args: argparse.Namespace) -> None:
    released = store.release_lock(args.task_id)
    print(f"[task unlock] {args.task_id}: {'released' if released else 'no lock'}")


def handle_resume(args: argparse.Namespace) -> None:
    ops.resume(args.task_id)


def handle_status(args: argparse.Namespace) -> None:
    ops.status(args.task_id)


def handle_record_run(args: argparse.Namespace) -> None:
    reflections: list[dict] = []
    if any([args.reflect_query, args.reflect_attribution, args.reflect_decision]):
        reflections.append({
            "query": args.reflect_query or "",
            "attribution": args.reflect_attribution or "",
            "decision": args.reflect_decision or "",
        })
    ops.record_run(
        args.task_id,
        owner=args.owner or "cli",
        summary=args.summary or "",
        entities_added=args.entities_added,
        posts_added=args.posts_added,
        mark_done=_split(args.mark_done),
        next_suggested=_split(args.next),
        batches=_split(args.batches),
        reflections=reflections,
        open_gaps=_split(args.open_gap),
    )


def handle_trace(args: argparse.Namespace) -> None:
    ops.trace(ref=args.ref, task_id=args.task_id)


def handle_hydrate(args: argparse.Namespace) -> None:
    ops.hydrate(args.task_id)


def handle_adopt(args: argparse.Namespace) -> None:
    prefixes = _split(args.entity_types)
    if not prefixes:
        print("[task adopt] 需要 --entity-types（如 机构/学校）", file=sys.stderr)
        raise SystemExit(2)
    result = ops.adopt_publish(args.task_id, prefixes, batch_id=args.batch_id or "adopted_history", force=args.force)
    if args.sync_progress:
        prog = store.load_progress(args.task_id)
        adopted = result["adoptedEntities"]
        prog["coverage"]["entities"]["done"] = adopted
        prog["coverage"]["entities"]["remaining"] = [
            r for r in prog["coverage"]["entities"].get("remaining", []) if r not in set(adopted)
        ]
        prog["counts"]["entities"] = len(adopted)
        prog["counts"]["posts"] = prog["counts"].get("posts", 0) + result["posts"]
        store.save_progress(prog)
        print(f"[task adopt] progress synced: entities={len(adopted)} posts+={result['posts']}")
    if args.reindex:
        from publish_ops.build_publish_lookup_indexes import build_publish_lookup_indexes
        counts = build_publish_lookup_indexes()
        print(f"[task adopt] reindex: entities={counts['entities']} posts={counts['posts']}")


def handle_prune_publish(args: argparse.Namespace) -> None:
    if not args.orphans:
        print("[task prune-publish] 需要 --orphans（仅清除无 sourceTaskId 归属的孤儿内容）", file=sys.stderr)
        raise SystemExit(2)
    result = ops.prune_publish(orphans_only=True)
    if args.reindex:
        from publish_ops.build_publish_lookup_indexes import build_publish_lookup_indexes
        counts = build_publish_lookup_indexes()
        print(f"[task prune-publish] reindex: entities={counts['entities']} posts={counts['posts']}")


def handle_cleanup_runtime(args: argparse.Namespace) -> None:
    ops.cleanup_runtime(args.task_id)


def handle_rollup(args: argparse.Namespace) -> None:
    from task import fanout_rollup

    try:
        report = fanout_rollup.rollup(args.plan)
    except ValueError as exc:
        print(f"[task rollup] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("task", help="任务工程：规格/账本/锁/溯源（薄编排壳）")
    sub = p.add_subparsers(dest="task_command")

    pn = sub.add_parser("new", help="脚手架新任务")
    pn.add_argument("--vertical", required=True, choices=["travel", "campus", "photography", "tech", "car"])
    pn.add_argument("--organize-by", dest="organize_by", required=True, choices=["地域", "环线", "主题"])
    pn.add_argument("--key", required=True, help="组织键：四川省/川西环线/风物美食")
    pn.add_argument("--name", required=True, help="任务名：景区全覆盖/川西大环线自驾")
    pn.add_argument("--category", help="实体类别（地域轴）：景区/古镇/美食/高校")
    pn.add_argument("--archetype", help="覆盖默认 archetype")
    pn.add_argument("--title", help="人读标题")
    pn.add_argument("--parent", help="父任务 id（_省域总览）")
    pn.add_argument("--region", help="scope.region")
    pn.add_argument("--regions", help="scope.regions 逗号分隔")
    pn.add_argument("--entity-types", dest="entity_types", help="scope.entityTypes 逗号分隔，如 地点/景区")
    pn.add_argument("--route", help="loop_route 环线名")
    pn.add_argument("--anchor-entities", dest="anchor_entities", help="loop_route 锚点逗号分隔")
    pn.add_argument("--theme", help="theme_collection 主题键")
    pn.add_argument("--coverage", help="覆盖实体清单：领域/类型/名称 逗号分隔，如 地点/景区/九寨沟,地点/景区/黄龙")
    pn.add_argument("--angles", help="content.angles 逗号分隔（仅与垂类默认不同时写，否则继承）")
    pn.add_argument("--audiences", help="content.audiences 逗号分隔（默认继承垂类）")
    pn.add_argument("--carriers", help="content.carriers 逗号分隔（默认继承全局 [article]）")
    pn.add_argument("--emphasis", help="content.emphasis 逗号分隔：实体类别选题侧重，如 人文叙事,古建筑")
    pn.add_argument("--cond-regions", dest="cond_regions", help="conditionAxes.regions（默认不写，继承地域全谱）")
    pn.add_argument("--cond-seasons", dest="cond_seasons", help="conditionAxes.seasons（默认不写，继承四季/旱雨季）")
    pn.add_argument("--owner", help="createdBy")
    pn.add_argument("--force", action="store_true")
    pn.set_defaults(handler=handle_new)

    pl = sub.add_parser("list", help="任务总览")
    pl.add_argument("--vertical")
    pl.add_argument("--tree", action="store_true")
    pl.set_defaults(handler=handle_list)

    ps = sub.add_parser("show", help="单任务详情")
    ps.add_argument("task_id")
    ps.set_defaults(handler=handle_show)

    pli = sub.add_parser("lint", help="校验任务规格")
    pli.add_argument("task_id", nargs="?", help="只校验单任务（缺省校验全部）")
    pli.set_defaults(handler=handle_lint)

    plk = sub.add_parser("lock", help="持锁")
    plk.add_argument("task_id")
    plk.add_argument("--owner")
    plk.add_argument("--force", action="store_true", help="强制夺锁（陈旧锁）")
    plk.set_defaults(handler=handle_lock)

    pu = sub.add_parser("unlock", help="释放锁")
    pu.add_argument("task_id")
    pu.set_defaults(handler=handle_unlock)

    pr = sub.add_parser("resume", help="算缺口给下一步")
    pr.add_argument("task_id")
    pr.set_defaults(handler=handle_resume)

    pst = sub.add_parser("status", help="覆盖率")
    pst.add_argument("task_id")
    pst.set_defaults(handler=handle_status)

    prr = sub.add_parser("record-run", help="记录运行+刷新进度")
    prr.add_argument("task_id")
    prr.add_argument("--owner")
    prr.add_argument("--summary", required=True)
    prr.add_argument("--entities-added", dest="entities_added", type=int, default=0)
    prr.add_argument("--posts-added", dest="posts_added", type=int, default=0)
    prr.add_argument("--mark-done", dest="mark_done", help="标记完成实体 entityType/name 逗号分隔")
    prr.add_argument("--next", help="nextSuggested 逗号分隔")
    prr.add_argument("--batches", help="涉及 batch 逗号分隔")
    prr.add_argument("--reflect-query", dest="reflect_query", help="ReAct 反思：本轮检索/问题")
    prr.add_argument("--reflect-attribution", dest="reflect_attribution",
                     help="质量归因：证据不足/模板失配/执行问题")
    prr.add_argument("--reflect-decision", dest="reflect_decision", help="回退/调整决策")
    prr.add_argument("--open-gap", dest="open_gap", help="未解决缺口逗号分隔，写入 progress.openGaps")
    prr.set_defaults(handler=handle_record_run)

    pt = sub.add_parser("trace", help="溯源反查")
    pt.add_argument("--ref", help="publish 路径片段")
    pt.add_argument("--task-id", dest="task_id", help="列某任务在 publish 的产物")
    pt.set_defaults(handler=handle_trace)

    ph = sub.add_parser("hydrate", help="按 sourceTaskId 拉回 publish 产物到 runtime")
    ph.add_argument("task_id")
    ph.set_defaults(handler=handle_hydrate)

    pa = sub.add_parser("adopt", help="把 publish 现有内容纳入任务并回填 sourceTaskId")
    pa.add_argument("task_id")
    pa.add_argument("--entity-types", dest="entity_types", required=True, help="匹配实体类型前缀逗号分隔，如 机构/学校")
    pa.add_argument("--batch-id", dest="batch_id", help="sourceBatchId（默认 adopted_history）")
    pa.add_argument("--force", action="store_true", help="覆盖已有 sourceTaskId")
    pa.add_argument("--sync-progress", dest="sync_progress", action="store_true", help="同步任务进度 done=已采纳实体")
    pa.add_argument("--reindex", action="store_true", help="重建 publish lookup 索引")
    pa.set_defaults(handler=handle_adopt)

    pp = sub.add_parser("prune-publish", help="清除 publish 中无任务归属(孤儿)的 posts/entities")
    pp.add_argument("--orphans", action="store_true", help="清除 sourceTaskId 为空的孤儿内容（必填确认）")
    pp.add_argument("--reindex", action="store_true", help="清除后重建 publish lookup 索引")
    pp.set_defaults(handler=handle_prune_publish)

    pcr = sub.add_parser(
        "cleanup-runtime",
        help="迁移 task/_shared 账本并清理 task 根历史镜像位",
    )
    pcr.add_argument("task_id")
    pcr.set_defaults(handler=handle_cleanup_runtime)

    prl = sub.add_parser("rollup", help="fanout 归并治理：分区 reducer + 全局进度/SLO + dead/spillover 巡检")
    prl.add_argument("--plan", required=True, help="冻结计划 planId")
    prl.set_defaults(handler=handle_rollup)

    register_run_parser(sub)
    register_decompose_parser(sub)
    queue.register_queue_parser(sub)

    def _dispatch(args: argparse.Namespace) -> None:
        if not getattr(args, "task_command", None):
            p.print_help()
            raise SystemExit(1)

    p.set_defaults(handler=_dispatch)
