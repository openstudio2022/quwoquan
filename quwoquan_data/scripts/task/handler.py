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
REPO_ROOT = DATA_ROOT.parent
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT, REPO_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import argparse
import json
import os
import sys

from _common.io import read_json
from _common.python_runtime import DEFAULT_CURSOR_STARTUP_TIMEOUT_SECONDS
from task import lint as lint_mod
from task import ops
from task import queue
from task import run as run_mod
from task import store
from task.cleanup_generated import build_cleanup_manifest, execute_cleanup, write_manifest
from task.decompose import register_decompose_parser
from task.content_supply import register_content_supply_parsers
from task.recipe import register_recipe_parser
from task.image_scale_proof import handle_open_license_proof
from task.run import register_run_parser
from task import scaled_e2e as scaled_e2e_mod
from task.trial_review import build_trial_review, parse_run_ref, write_trial_review
from verify.gate import gate_verify
from verify.audit_summary import write_batch_audit_summary


def handle_scaled_e2e(args: argparse.Namespace) -> None:
    # Keep scaled_e2e helpers aligned with handler-level test injection points.
    scaled_e2e_mod.gate_verify = gate_verify
    scaled_e2e_mod.write_batch_audit_summary = write_batch_audit_summary
    scaled_e2e_mod.handle_scaled_e2e(args)


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

    # 只写特化 override；未给的字段由 presetRef 指向的家族 preset 补齐（carriers/audiences 默认不写）。
    content: dict = {}
    if _split(args.angles):
        content["angles"] = _split(args.angles)
    if _split(args.audiences):
        content["audiences"] = _split(args.audiences)
    if _split(args.carriers):
        content["carriers"] = _split(args.carriers)
    if _split(args.emphasis):
        content["emphasis"] = _split(args.emphasis)
    quotas: dict[str, int] = {}
    for key, value in (
        ("entityArticles", getattr(args, "entity_articles", None)),
        ("routeArticles", getattr(args, "route_articles", None)),
        ("galleryPosts", getattr(args, "gallery_posts", None)),
    ):
        if value is None:
            continue
        if value < 0:
            print(f"[task new] 配额不能为负数: {key}={value}", file=sys.stderr)
            raise SystemExit(2)
        quotas[key] = int(value)
    if quotas:
        content["quotas"] = quotas

    spec = store.scaffold_spec(
        vertical=args.vertical,
        organize_by=args.organize_by,
        key=args.key,
        name=args.name,
        category=args.category,
        archetype=args.archetype,
        title=args.title,
        intent_label=getattr(args, "intent_label", None),
        parent_task_id=args.parent,
        preset_ref=getattr(args, "preset", None),
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


def handle_trial_review(args: argparse.Namespace) -> None:
    compares = [
        parse_run_ref(value, default_task_id=args.task)
        for value in (getattr(args, "compare", None) or [])
    ]
    report = build_trial_review(args.task, args.batch, compare_runs=compares)
    if args.write:
        path = write_trial_review(report)
        print(f"[task trial-review] wrote {path}")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        gate = report.get("qualityAndScaleGate") or {}
        convergence = report.get("convergence") or {}
        efficiency = report.get("efficiency") or {}
        decision = report.get("decision") or {}
        print(f"[task trial-review] {args.task} / {args.batch}")
        print(
            "  convergence="
            f"{convergence.get('trend')} score={convergence.get('score')} "
            f"status={convergence.get('status')}"
        )
        print(
            "  gate="
            f"{'PASS' if gate.get('passed') else 'BLOCK'} "
            f"blockers={len(gate.get('blockers') or [])} warnings={len(gate.get('warnings') or [])}"
        )
        print(
            "  efficiency="
            f"authorJobs={efficiency.get('estimatedAuthorJobs')} "
            f"localWaves={efficiency.get('estimatedLocalWaves')}"
        )
        print(f"  decision={decision.get('nextGate')} canScale={decision.get('canScale')}")
        for item in (gate.get("blockers") or [])[:8]:
            print(f"  - {item}")
        for item in (gate.get("warnings") or [])[:5]:
            print(f"  ~ {item}")
    if args.strict and not ((report.get("qualityAndScaleGate") or {}).get("passed")):
        raise SystemExit(1)


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


def handle_cleanup_generated(args: argparse.Namespace) -> None:
    manifest = build_cleanup_manifest(
        task_id=getattr(args, "task", None),
        batch_id=getattr(args, "batch", None),
        release_id=getattr(args, "release", None),
        all_runtime=bool(getattr(args, "all_runtime", False)),
        all_releases=bool(getattr(args, "all_releases", False)),
    )
    if getattr(args, "manifest_out", None):
        write_manifest(Path(args.manifest_out), manifest)
        print(f"[task cleanup-generated] wrote manifest: {args.manifest_out}")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    if manifest.get("issues"):
        raise SystemExit(1)
    if not getattr(args, "confirm", False):
        print("[task cleanup-generated] dry-run only; pass --confirm to delete")
        return
    result = execute_cleanup(manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if getattr(args, "prepare_task", None):
        _prepare_generated_run_inputs(
            str(args.prepare_task),
            regions=getattr(args, "prepare_regions", None),
            entity_types=getattr(args, "prepare_entity_types", None),
        )


def _prepare_generated_run_inputs(
    task_id: str,
    *,
    regions: str | None = None,
    entity_types: str | None = None,
) -> None:
    """Rebuild task catalog and baseline after a generated-runtime cleanup."""
    from data.baseline import handle_baseline
    from explore.handler import handle_explore

    spec = store.load_spec(task_id)
    scope = spec.get("scope") or {}
    region_value = str(regions or scope.get("region") or "").strip()
    entity_type_value = str(
        entity_types
        or ",".join(str(item) for item in (scope.get("entityTypes") or []) if str(item))
    ).strip()
    print(f"[task cleanup-generated] prepare task inputs: {task_id}")
    handle_explore(
        argparse.Namespace(
            task=task_id,
            regions=region_value,
            entity_types=entity_type_value,
        )
    )
    handle_baseline(
        argparse.Namespace(
            task=task_id,
            catalog=None,
            spec_doc=None,
            design_doc=None,
            acceptance_doc=None,
            workflow_doc=None,
            command_matrix_doc=None,
            catalog_config=None,
            naming_rules=None,
            geo_band_rules=None,
            schema_files=[],
            config_files=[],
            output=None,
        )
    )


def handle_rollup(args: argparse.Namespace) -> None:
    from task import fanout_rollup
    from _common.paths import fanout_summary_path

    try:
        report = fanout_rollup.rollup(args.plan)
    except ValueError as exc:
        print(f"[task rollup] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
    summary_path = fanout_summary_path(args.plan)
    summary = read_json(summary_path) if summary_path.is_file() else None
    if summary is None:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    print(json.dumps({"rollup": report, "summary": summary}, ensure_ascii=False, indent=2))


def handle_select_targets(args: argparse.Namespace) -> None:
    from task.target_selection import handle_select_targets as _handle

    _handle(args)


def handle_audit_batch(args: argparse.Namespace) -> None:
    from task.target_selection import handle_audit_batch as _handle

    _handle(args)


def handle_abandon_targets(args: argparse.Namespace) -> None:
    from task.run import mark_abandoned_content_refs, mark_abandoned_entities

    entities = [item.strip() for item in str(args.entities or "").split(",") if item.strip()]
    refs = [item.strip() for item in str(getattr(args, "content_refs", "") or "").split(",") if item.strip()]
    if not entities and not refs:
        raise SystemExit("--entities or --content-refs must not be empty")
    report: dict[str, object] = {}
    if entities:
        report["entities"] = mark_abandoned_entities(
            str(args.task),
            str(args.batch),
            entities,
            stage=str(args.stage or ""),
            reason=str(args.reason or "fast_fail"),
        )
    if refs:
        report["contentRefs"] = mark_abandoned_content_refs(
            str(args.task),
            str(args.batch),
            refs,
            stage=str(args.stage or ""),
            reason=str(args.reason or "fast_fail"),
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))


def handle_throughput_plan(args: argparse.Namespace) -> None:
    from _common.throughput_plan import ThroughputConfig, compute_throughput_plan

    config = ThroughputConfig(
        daily_target=int(args.daily_target),
        channels=int(args.channels),
        runtime=str(args.runtime),
        local_bridge_cap_per_machine=int(args.local_bridge_cap),
        warm_seconds_per_article=float(args.warm_seconds),
        cold_seconds_per_article=float(args.cold_seconds),
        active_hours_per_day=float(args.active_hours),
        first_pass_rate=float(args.first_pass_rate),
        utilization=float(args.utilization),
    )
    plan = compute_throughput_plan(config)
    report = plan.to_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if getattr(args, "require_feasible", False) and not plan.meets_target:
        raise SystemExit(1)


def handle_retry_stage(args: argparse.Namespace) -> None:
    from task.run import reset_stage_retries

    try:
        report = reset_stage_retries(
            str(args.task),
            str(args.batch),
            stage=str(args.stage or ""),
            reason=str(args.reason or "operator confirmed infrastructure recovery"),
            reset_react_rewinds=bool(getattr(args, "reset_react_rewinds", False)),
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
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
    pn.add_argument("--intent-label", dest="intent_label",
                    help="≤16字人类可读任务意图标签（顶层批次目录前缀 runtime/batches/<标签>__<批次>/；缺省取任务名清洗截断）")
    pn.add_argument("--preset",
                    help="presetRef（families/ 相对路径去 .preset.yaml 后缀）；缺省按垂类解析 content/<vertical>/article/base")
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
    pn.add_argument("--entity-articles", dest="entity_articles", type=int,
                    help="content.quotas.entityArticles（显式写入 task.yaml，允许 0）")
    pn.add_argument("--route-articles", dest="route_articles", type=int,
                    help="content.quotas.routeArticles（显式写入 task.yaml，允许 0）")
    pn.add_argument("--gallery-posts", dest="gallery_posts", type=int,
                    help="content.quotas.galleryPosts（显式写入 task.yaml，允许 0）")
    pn.add_argument("--emphasis", help="content.emphasis 逗号分隔：实体类别选题侧重，如 人文叙事,古建筑")
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

    ptr = sub.add_parser("trial-review", help="复盘 managed 试跑证据、收敛趋势与 Cursor SDK 效率瓶颈")
    ptr.add_argument("--task", required=True)
    ptr.add_argument("--batch", default="run_1")
    ptr.add_argument(
        "--compare",
        action="append",
        help="追加历史试跑用于趋势比较，格式 TASK::BATCH；同任务可只写 batchId",
    )
    ptr.add_argument("--json", action="store_true")
    ptr.add_argument("--write", action="store_true", help="写入 batch/_shared/trial_review.json")
    ptr.add_argument("--strict", action="store_true", help="质量/规模门未通过时返回非零退出码")
    ptr.set_defaults(handler=handle_trial_review)

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

    pcg = sub.add_parser(
        "cleanup-generated",
        help="清理生成型 runtime/release 产物；默认 dry-run，保留 committed task、publish、tag/entity 真源",
    )
    pcg.add_argument("--task", help="runtime taskId")
    pcg.add_argument("--batch", help="runtime batchId；与 --task 搭配只清指定 batch")
    pcg.add_argument("--release", help="releaseId；只清指定 isolated release")
    pcg.add_argument("--all-runtime", action="store_true", help="清空 runtime/ 下全部生成产物")
    pcg.add_argument("--all-releases", action="store_true", help="清空 release/ 下全部 isolated release")
    pcg.add_argument("--manifest-out", help="写出清理清单 JSON")
    pcg.add_argument("--confirm", action="store_true", help="确认执行删除；缺省只 dry-run")
    pcg.add_argument(
        "--prepare-task",
        help="删除确认后重建该 task 的 catalog.ndjson 与 baseline_freeze_packet.json",
    )
    pcg.add_argument("--prepare-regions", help="prepare-task 的 explore regions；默认取 task scope.region")
    pcg.add_argument(
        "--prepare-entity-types",
        help="prepare-task 的 explore entity types；默认取 task scope.entityTypes",
    )
    pcg.set_defaults(handler=handle_cleanup_generated)

    prl = sub.add_parser("rollup", help="fanout 归并治理：分区 reducer + 全局进度/SLO + dead/spillover 巡检")
    prl.add_argument("--plan", required=True, help="冻结计划 planId")
    prl.set_defaults(handler=handle_rollup)

    pstg = sub.add_parser(
        "select-targets",
        help="从 discovery 分区确定性选择多模态 coverageTargets，支持按历史不可行对象排除",
    )
    # 缺省 None → target_selection.DEFAULT_SOURCE_TASK_ID（全国维度常量，单一真相源）。
    pstg.add_argument("--source-task", dest="source_task", help="跨批去重账本维度 taskId；默认全国常量")
    pstg.add_argument("--discovery", help="discovery 输入：主清单目录或 JSON 文件；默认全国主清单 verticals/travel/coverage/中国/")
    pstg.add_argument("--limit", type=int, default=50)
    pstg.add_argument(
        "--reserve-ratio",
        type=float,
        default=0.2,
        help="额外选择备用 coverageTargets 比例；默认 0.2，用于 partial replacement",
    )
    pstg.add_argument(
        "--elastic-overfetch",
        action="store_true",
        help="启用弹性超采：--limit 保留为目标实体数，实际按 overfetch multiplier 选择更多候选",
    )
    pstg.add_argument(
        "--overfetch-multiplier",
        type=float,
        default=2.0,
        help="弹性超采倍率；默认 2.0（目标 20 → 候选 40）",
    )
    pstg.add_argument(
        "--allow-quota-shortfall",
        action="store_true",
        help="允许内容配额短缺以 reasoned reject 隔离，不阻断已达标对象",
    )
    pstg.add_argument(
        "--allow-over-production",
        action="store_true",
        help="允许达标候选超过目标口径时继续产出，并在报告中区分目标/实际口径",
    )
    pstg.add_argument(
        "--min-batch-completion-mode",
        default="",
        help="批次完成口径；弹性超采默认 best_effort_with_reasoned_rejects",
    )
    pstg.add_argument(
        "--source-readiness",
        dest="source_readiness",
        help="按主清单 leaf.sourceReadiness 过滤候选（逗号分隔，如 ready）；缺省不过滤",
    )
    pstg.add_argument("--mandatory", help="必须保留实体，逗号分隔；默认川西五景")
    pstg.add_argument("--exclude", help="显式排除实体，逗号分隔")
    pstg.add_argument("--exclude-from-task", dest="exclude_from_task", help="从历史 managed batch failedObjects 读取不可行实体")
    pstg.add_argument("--exclude-from-batch", dest="exclude_from_batch", help="与 --exclude-from-task 配套的 batchId")
    pstg.add_argument(
        "--exclude-from-run",
        dest="exclude_from_run",
        action="append",
        help="追加排除历史批次不可行实体，格式 TASK_ID::BATCH_ID；可重复",
    )
    pstg.add_argument("--region", default="四川省")
    pstg.add_argument("--category", default="景区")
    pstg.add_argument("--name", required=True, help="新任务名")
    pstg.add_argument("--title", help="新任务标题；默认同 name")
    pstg.add_argument("--intent-label", dest="intent_label",
                      help="≤16字人类可读任务意图标签（顶层批次目录前缀；缺省取任务名清洗截断）")
    pstg.add_argument("--preset",
                      help="presetRef；缺省 homepage-only 形态绑定 content/travel/homepage/base，否则按垂类默认")
    pstg.add_argument(
        "--entity-articles-per-target",
        type=int,
        default=4,
        help="每个实体的文章配额；默认 4",
    )
    pstg.add_argument(
        "--entity-homepages-per-target",
        type=int,
        default=1,
        help="每个实体的主页配额；默认 1，图片作品-only 批次可设为 0",
    )
    pstg.add_argument(
        "--image-works-per-target",
        type=int,
        default=1,
        help="每个实体的图片作品配额；默认 1（100 实体验收即 100 图库）",
    )
    pstg.add_argument("--owner", help="createdBy")
    pstg.add_argument("--write", action="store_true", help="写入 committed task；默认只打印 selection report")
    pstg.add_argument("--force", action="store_true", help="覆盖同名任务")
    pstg.set_defaults(handler=handle_select_targets)

    pab = sub.add_parser("audit-batch", help="审计 managed separated_research 批次 lane 通过率和图片容量")
    pab.add_argument("--task", required=True)
    pab.add_argument("--batch", required=True)
    pab.add_argument("--json", action="store_true")
    pab.add_argument("--write", action="store_true", help="写入 batch/_shared/managed_batch_audit.json")
    pab.add_argument("--strict", action="store_true", help="failedLaneCount > 0 时返回非零退出码")
    pab.set_defaults(handler=handle_audit_batch)

    pop = sub.add_parser(
        "open-license-proof",
        help="从 batch 图片 source plan 生成百级开放许可图片预筛证明",
    )
    pop.add_argument("--task", required=True)
    pop.add_argument("--batch", required=True)
    pop.add_argument("--write", action="store_true", help="写入 batch/_shared/open_license_scale_proof.json")
    pop.add_argument(
        "--apply-task",
        action="store_true",
        help="仅在 proof 通过时写回 task.yaml 的 content.research.openLicenseScaleProof",
    )
    pop.add_argument("--strict", action="store_true", help="proof 未通过时返回非零退出码")
    pop.set_defaults(handler=handle_open_license_proof)

    pabn = sub.add_parser("abandon-targets", help="快速失败：标记实体 abandoned，后续 workflow/audit 跳过")
    pabn.add_argument("--task", required=True)
    pabn.add_argument("--batch", required=True)
    pabn.add_argument("--entities", default="", help="逗号分隔实体名")
    pabn.add_argument("--content-refs", default="", help="逗号分隔内容 ref（文章/图片对象）")
    pabn.add_argument("--stage", default="unknown")
    pabn.add_argument("--reason", default="fast_fail")
    pabn.set_defaults(handler=handle_abandon_targets)

    prst = sub.add_parser("retry-stage", help="恢复已确认的基础设施故障：清理指定 stage retry 计数后重试")
    prst.add_argument("--task", required=True)
    prst.add_argument("--batch", required=True)
    prst.add_argument("--stage", required=True)
    prst.add_argument("--reason", default="operator confirmed infrastructure recovery")
    prst.add_argument(
        "--reset-react-rewinds",
        action="store_true",
        help="质量合同/门禁代码已修复后，显式重置指定 stage 及后续 Ralph 回退计数",
    )
    prst.set_defaults(handler=handle_retry_stage)

    pse = sub.add_parser("scaled-e2e", help="放大规模 E2E 薄壳：只编排现有 CLI/fanout 主线，不产正文")
    sesub = pse.add_subparsers(dest="scaled_e2e_command")

    psep = sesub.add_parser("prepare", help="baseline + single workflow 到 produce_compose（不写正文）")
    psep.add_argument("--task", required=True)
    psep.add_argument("--batch", required=True)
    psep.add_argument("--plan", required=True, help="后续 fanout 使用的冻结计划 planId")
    psep.add_argument("--catalog", help="可选 baseline catalog path")
    psep.add_argument("--reset-state", dest="reset_state", action="store_true")
    psep.add_argument("--max-workers", dest="max_workers", type=int, default=10)
    psep.add_argument("--runtime", choices=["local", "cloud"], default="local")
    psep.add_argument("--model", default="composer")
    psep.add_argument("--cwd", default=os.getcwd())
    psep.add_argument(
        "--startup-timeout-seconds",
        dest="startup_timeout_seconds",
        type=float,
        default=DEFAULT_CURSOR_STARTUP_TIMEOUT_SECONDS,
    )
    psep.add_argument("--force-clean-workspace-agent-state", action="store_true")
    psep.set_defaults(handler=handle_scaled_e2e)

    psef = sesub.add_parser("fanout-author", help="复用 task run --mode fanout 调度 author 子任务")
    psef.add_argument("--plan", required=True)
    psef.add_argument("--batch", default="run_1")
    psef.add_argument("--strategy", choices=["by-partition", "flat-pool", "by-leaf", "by-batch"])
    psef.add_argument("--concurrency", type=int)
    psef.add_argument("--batch-size", dest="batch_size", type=int)
    psef.set_defaults(handler=handle_scaled_e2e)

    pserun = sesub.add_parser("author-runner", help="复用 fanout_runner 真正并行拉起 author subagent")
    pserun.add_argument("--plan", required=True)
    pserun.add_argument("--strategy", choices=["by-partition", "flat-pool", "by-leaf", "by-batch"])
    pserun.add_argument("--concurrency", type=int)
    pserun.add_argument("--max-workers", dest="max_workers", type=int)
    pserun.add_argument("--runtime", choices=["local", "cloud"], default="cloud")
    pserun.add_argument("--model", default="composer")
    pserun.add_argument("--cwd", default=os.getcwd())
    pserun.add_argument("--spend-limit-usd", dest="spend_limit", type=float)
    pserun.add_argument("--refs", help="仅运行逗号分隔的 ref 列表（content-mode 为内容对象 ref）")
    pserun.add_argument("--force-refs", dest="force_refs", help="强制重跑逗号分隔的已成稿 ref")
    pserun.add_argument("--source-task", dest="source_task", help="sourceTask content author 直接消费的 taskId")
    pserun.add_argument("--source-batch", dest="source_batch", help="sourceTask content author 直接消费的 batchId")
    pserun.add_argument("--skip-startup-probe", action="store_true", help="跳过 author-runner 前置 Cursor startup probe（仅限已有外部门禁证据的测试）")
    pserun.add_argument("--orchestrate", action="store_true")
    pserun.add_argument("--no-orchestrate", dest="no_orchestrate", action="store_true")
    pserun.set_defaults(handler=handle_scaled_e2e)

    pser = sesub.add_parser("rollup", help="复用 task rollup 汇总 fanout 执行状态")
    pser.add_argument("--plan", required=True)
    pser.set_defaults(handler=handle_scaled_e2e)

    psef2 = sesub.add_parser("finalize", help="在 fanout author 后恢复各分区 workflow，跑 review/materialize/publish")
    psef2.add_argument("--plan", required=True)
    psef2.add_argument("--strategy", choices=["by-partition", "flat-pool", "by-leaf", "by-batch"])
    psef2.add_argument("--concurrency", type=int)
    psef2.add_argument("--max-workers", dest="max_workers", type=int)
    psef2.add_argument("--runtime", choices=["local", "cloud"], default="cloud")
    psef2.add_argument("--model", default="composer")
    psef2.add_argument("--cwd", default=os.getcwd())
    psef2.add_argument("--spend-limit-usd", dest="spend_limit", type=float)
    psef2.add_argument("--reset-state", dest="reset_state", action="store_true")
    psef2.add_argument(
        "--startup-timeout-seconds",
        dest="startup_timeout_seconds",
        type=float,
        default=DEFAULT_CURSOR_STARTUP_TIMEOUT_SECONDS,
    )
    psef2.add_argument("--force-clean-workspace-agent-state", action="store_true")
    psef2.add_argument("--source-task", dest="source_task", help="sourceTask content author 直接消费的 taskId")
    psef2.add_argument("--source-batch", dest="source_batch", help="sourceTask content author 直接消费的 batchId")
    psef2.set_defaults(handler=handle_scaled_e2e)

    psev = sesub.add_parser("verify", help="显式校验某 runtime task/batch")
    psev.add_argument("--task")
    psev.add_argument("--batch")
    psev.add_argument("--plan", help="若提供，则聚合校验 plan 下全部分区 task/batch")
    psev.add_argument("--source-task", dest="source_task", help="sourceTask content author 直接消费的 taskId")
    psev.add_argument("--source-batch", dest="source_batch", help="sourceTask content author 直接消费的 batchId")
    psev.set_defaults(handler=handle_scaled_e2e)

    pseq = sesub.add_parser("run", help="无人托管一键执行 prepare→author→finalize→verify")
    pseq.add_argument("--task", required=True)
    pseq.add_argument("--batch", required=True)
    pseq.add_argument("--plan", required=True, help="冻结 fanout planId")
    pseq.add_argument("--catalog", help="可选 baseline catalog path")
    pseq.add_argument("--strategy", choices=["by-partition", "flat-pool", "by-leaf", "by-batch"])
    pseq.add_argument("--concurrency", type=int, default=2)
    pseq.add_argument("--max-workers", dest="max_workers", type=int, default=2)
    pseq.add_argument("--runtime", choices=["local", "cloud"], default="local")
    pseq.add_argument("--model", default="composer")
    pseq.add_argument("--cwd", default=os.getcwd())
    pseq.add_argument("--spend-limit-usd", dest="spend_limit", type=float)
    pseq.add_argument("--cycles", type=int, default=3, help="author/finalize/verify 最大闭环轮数")
    pseq.add_argument(
        "--download-prefetch",
        dest="download_prefetch",
        type=int,
        default=0,
        help="两段流水线：author cycle 前对已物化分区并发预跑 download 段的并发度（0=关闭）",
    )
    pseq.add_argument("--reset-state", dest="reset_state", action="store_true")
    pseq.add_argument("--skip-prepare", action="store_true", help="已有 prepare 证据时跳过 prepare 阶段")
    pseq.add_argument("--skip-startup-probe", action="store_true", help="跳过 author-runner 前置 Cursor startup probe")
    pseq.add_argument(
        "--startup-timeout-seconds",
        dest="startup_timeout_seconds",
        type=float,
        default=DEFAULT_CURSOR_STARTUP_TIMEOUT_SECONDS,
    )
    pseq.add_argument("--force-clean-workspace-agent-state", action="store_true")
    pseq.add_argument("--source-task", dest="source_task", help="sourceTask content author 直接消费的 taskId")
    pseq.add_argument("--source-batch", dest="source_batch", help="sourceTask content author 直接消费的 batchId")
    pseq.set_defaults(handler=handle_scaled_e2e)

    ptp = sub.add_parser(
        "throughput-plan",
        help="确定性容量推算：单篇耗时 × 可行并行通道 → 可达日产 + 目标所需通道/机器 + 代码可解 vs 外部约束分层",
    )
    ptp.add_argument("--daily-target", dest="daily_target", type=int, default=100_000,
                     help="目标日产成稿数（默认十万）")
    ptp.add_argument("--channels", type=int, default=1, help="当前可用并行创作通道数")
    ptp.add_argument("--runtime", choices=["local", "cloud"], default="cloud",
                     help="local=单机共享 bridge（受冷启上限）；cloud=独立 agent（受平台配额）")
    ptp.add_argument("--local-bridge-cap", dest="local_bridge_cap", type=int, default=3,
                     help="单机本地 bridge 冷启安全并发上限（P6 cold-start cap，默认 3）")
    ptp.add_argument("--warm-seconds", dest="warm_seconds", type=float, default=32.0,
                     help="暖 bridge 单篇耗时（实测默认 32s）")
    ptp.add_argument("--cold-seconds", dest="cold_seconds", type=float, default=62.0,
                     help="冷启 bridge 单篇耗时（实测默认 62s）")
    ptp.add_argument("--active-hours", dest="active_hours", type=float, default=24.0,
                     help="每日有效生产小时数（无人值守默认 24）")
    ptp.add_argument("--first-pass-rate", dest="first_pass_rate", type=float, default=0.85,
                     help="首轮通过率（0-1，折算重试损耗）")
    ptp.add_argument("--utilization", type=float, default=0.80,
                     help="墙钟利用率（0-1，折算编排/审核/空窗）")
    ptp.add_argument("--require-feasible", dest="require_feasible", action="store_true",
                     help="当前配置达不到目标日产时返回非零退出码")
    ptp.set_defaults(handler=handle_throughput_plan)

    register_run_parser(sub)
    register_recipe_parser(sub)
    register_decompose_parser(sub)
    register_content_supply_parsers(sub)
    queue.register_queue_parser(sub)

    def _dispatch(args: argparse.Namespace) -> None:
        if not getattr(args, "task_command", None):
            p.print_help()
            raise SystemExit(1)

    p.set_defaults(handler=_dispatch)
