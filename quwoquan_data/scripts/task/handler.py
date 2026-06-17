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
import subprocess
import sys

from _common.io import read_json
from task import lint as lint_mod
from task import ops
from task import queue
from task import run as run_mod
from task import store
from task.cleanup_generated import build_cleanup_manifest, execute_cleanup, write_manifest
from task.decompose import register_decompose_parser
from task.content_supply import register_content_supply_parsers
from task.run import register_run_parser
from verify.gate import gate_verify
from verify.audit_summary import write_batch_audit_summary


def _split(arg: str | None) -> list[str]:
    return [x.strip() for x in (arg or "").split(",") if x.strip()]


def _fanout_runner_python() -> str | None:
    module = sys.modules.get("agent_ops.runners.fanout_runner")
    if module is not None and not getattr(module, "__file__", None):
        return None
    from _common.python_runtime import resolve_data_agent_python

    runner_python = resolve_data_agent_python(include_current=True)
    if runner_python is None:
        return None
    if Path(runner_python) == Path(sys.executable):
        return None
    return str(runner_python)


def _scaled_e2e_plan_runtime_issues(plan: dict, roots_by_unit: dict[tuple[str, str], list[str]]) -> list[str]:
    """Plan-level hard gates for scaled E2E verification.

    `gate_verify` only checks existing artifacts. The scaled E2E gate must also
    prove the fanout controller actually ran and every partition batch reached
    a terminal workflow state with at least one auditable output root.
    """
    from _common import fanout_strategies as fs
    from _common.paths import batch_workflow_state_path, fanout_run_matrix_path
    from task.run import load_workflow_state

    issues: list[str] = []
    plan_id = str(plan.get("planId") or "")
    matrix_path = fanout_run_matrix_path(plan_id)
    if not matrix_path.is_file():
        issues.append(f"{plan_id}: missing run_matrix.json")
    else:
        matrix = read_json(matrix_path)
        summary = matrix.get("summary") or {}
        for key in ("failed", "attemptFailures", "startupFailures", "orchestrationFailed"):
            count = int(summary.get(key) or 0)
            if count:
                issues.append(f"{plan_id}: run_matrix summary {key}={count}")
        if int(summary.get("orchestrated") or 0) == 0 and int(summary.get("completed") or 0) == 0:
            issues.append(f"{plan_id}: run_matrix has no completed or orchestrated work")
        for idx, item in enumerate(matrix.get("orchestrators") or []):
            if not item.get("reached"):
                worker = str(item.get("worker") or item.get("partition") or f"orchestrator[{idx}]")
                missing = ",".join(str(x) for x in (item.get("missing") or []))
                error = str(item.get("error") or "")
                detail = f" missing={missing}" if missing else ""
                if error:
                    detail += f" error={error}"
                issues.append(f"{plan_id}: {worker} did not reach required checkpoints{detail}")

    for unit in fs.expand_units(plan):
        task_id = str(unit["taskId"])
        batch_id = str(unit["batchId"])
        key = (task_id, batch_id)
        state_path = batch_workflow_state_path(task_id, batch_id)
        if not state_path.is_file():
            issues.append(f"{task_id}/{batch_id}: missing task_workflow_state.json")
        else:
            state = load_workflow_state(task_id, batch_id)
            status = str(state.get("status") or "")
            waiting = str(state.get("waitingCheckpoint") or "")
            if waiting:
                issues.append(f"{task_id}/{batch_id}: stuck at checkpoint {waiting}")
            if status not in {"succeeded", "completed", "done"}:
                issues.append(f"{task_id}/{batch_id}: workflow status is {status or 'unknown'}")
            failed_objects = state.get("failedObjects") or []
            if failed_objects:
                issues.append(f"{task_id}/{batch_id}: failedObjects={len(failed_objects)}")
        if not roots_by_unit.get(key):
            issues.append(f"{task_id}/{batch_id}: no current artifacts found for verification")
    return issues


def _prepare_author_jobs_for_paused_targets(plan: dict, paused_targets: list[tuple[str, str]]) -> None:
    from _common import fanout_strategies as fs
    from task import fanout_dispatch as fd

    paused_keys = {(task_id, batch_id) for task_id, batch_id in paused_targets}
    for unit in fs.expand_units(plan):
        key = (str(unit["taskId"]), str(unit["batchId"]))
        if key not in paused_keys:
            continue
        fd.sync_content_author_jobs(plan, unit, partition_path=list(unit.get("partitionPath") or []))


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


def handle_trial_review(args: argparse.Namespace) -> None:
    from task.trial_review import build_trial_review, parse_run_ref, write_trial_review

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


def handle_retry_stage(args: argparse.Namespace) -> None:
    from task.run import reset_stage_retries

    try:
        report = reset_stage_retries(
            str(args.task),
            str(args.batch),
            stage=str(args.stage or ""),
            reason=str(args.reason or "operator confirmed infrastructure recovery"),
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(report, ensure_ascii=False, indent=2))


def handle_scaled_e2e(args: argparse.Namespace) -> None:
    command = getattr(args, "scaled_e2e_command", "")
    if command == "prepare":
        from explore.handler import handle_explore
        from data.baseline import handle_baseline

        spec = store.load_spec(args.task)
        scope = spec.get("scope") or {}
        regions = [str(x) for x in (scope.get("regions") or []) if str(x)]
        task_region = str(scope.get("region") or "").strip()
        if not regions and task_region:
            regions = [task_region]
        entity_types = [str(x) for x in (scope.get("entityTypes") or []) if str(x)]
        handle_explore(
            argparse.Namespace(
                task=args.task,
                regions=",".join(regions),
                entity_types=",".join(entity_types),
            )
        )
        handle_baseline(
            argparse.Namespace(
                task=args.task,
                catalog=getattr(args, "catalog", None),
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
        run_mod.handle_run(
            argparse.Namespace(
                mode="single",
                task=args.task,
                batch=args.batch,
                plan=None,
                strategy=None,
                concurrency=None,
                batch_size=None,
                resume=False,
                reset_state=bool(getattr(args, "reset_state", False)),
                baseline_packet=None,
                until="produce_compose",
                max_workers=int(getattr(args, "max_workers", 10) or 10),
            )
        )
        print(
            f"[task scaled-e2e prepare] 已到 produce_compose。"
            f"\n下一步：qwq-data task scaled-e2e fanout-author --plan {args.plan}"
        )
        return
    if command == "fanout-author":
        run_mod.handle_run(
            argparse.Namespace(
                mode="fanout",
                task=None,
                batch=args.batch,
                plan=args.plan,
                strategy=getattr(args, "strategy", None),
                concurrency=getattr(args, "concurrency", None),
                batch_size=getattr(args, "batch_size", None),
                resume=False,
                reset_state=False,
                baseline_packet=None,
                until=None,
            )
        )
        return
    if command == "author-runner":
        fr = sys.modules.get("agent_ops.runners.fanout_runner")
        if fr is None:
            from agent_ops.runners import fanout_runner as fr
        argv = ["--plan", args.plan]
        if getattr(args, "strategy", None):
            argv += ["--strategy", args.strategy]
        if getattr(args, "concurrency", None) is not None:
            argv += ["--concurrency", str(args.concurrency)]
        if getattr(args, "max_workers", None) is not None:
            argv += ["--max-workers", str(args.max_workers)]
        if getattr(args, "runtime", None):
            argv += ["--runtime", args.runtime]
        if getattr(args, "model", None):
            argv += ["--model", args.model]
        if getattr(args, "cwd", None):
            argv += ["--cwd", args.cwd]
        if getattr(args, "spend_limit", None) is not None:
            argv += ["--spend-limit-usd", str(args.spend_limit)]
        if getattr(args, "refs", None):
            argv += ["--refs", args.refs]
        if getattr(args, "force_refs", None):
            argv += ["--force-refs", args.force_refs]
        if getattr(args, "orchestrate", False):
            argv += ["--orchestrate"]
        if getattr(args, "no_orchestrate", False):
            argv += ["--no-orchestrate"]
        runner_python = _fanout_runner_python()
        if runner_python:
            result = subprocess.run(
                [runner_python, str(REPO_ROOT / "agent_ops" / "runners" / "fanout_runner.py"), *argv],
                check=False,
            )
            if result.returncode != 0:
                raise SystemExit(result.returncode)
            return
        code = fr.main(argv)
        if code != 0:
            raise SystemExit(code)
        return
    if command == "rollup":
        handle_rollup(argparse.Namespace(plan=args.plan))
        return
    if command == "finalize":
        from _common import fanout_plan as fp
        from _common import fanout_strategies as fs
        from task.run import load_workflow_state

        plan = fp.load_plan(args.plan)
        if plan is None:
            print(f"[task scaled-e2e finalize] plan not found: {args.plan}", file=sys.stderr)
            raise SystemExit(2)
        units = fs.expand_units(plan)
        failures: list[str] = []
        paused_for_author: list[tuple[str, str]] = []
        for unit in units:
            task_id = str(unit["taskId"])
            batch_id = str(unit["batchId"])
            try:
                run_mod.handle_run(
                    argparse.Namespace(
                        mode="single",
                        task=task_id,
                        batch=batch_id,
                        plan=None,
                        strategy=None,
                        concurrency=None,
                        batch_size=None,
                        resume=True,
                        reset_state=bool(getattr(args, "reset_state", False)),
                        baseline_packet=None,
                        until=None,
                    )
                )
            except SystemExit as exc:
                code = int(getattr(exc, "code", 1) or 0)
                if code == 10:
                    state = load_workflow_state(task_id, batch_id)
                    waiting = str(state.get("waitingCheckpoint") or "")
                    if waiting == "produce_author":
                        paused_for_author.append((task_id, batch_id))
                    else:
                        failures.append(f"{task_id}/{batch_id}: paused_at={waiting or 'unknown'}")
                    continue
                if code not in (0,):
                    failures.append(f"{task_id}/{batch_id}: exit={code}")
        if paused_for_author:
            _prepare_author_jobs_for_paused_targets(plan, paused_for_author)
            handle_scaled_e2e(
                argparse.Namespace(
                    scaled_e2e_command="author-runner",
                    plan=args.plan,
                    strategy=getattr(args, "strategy", None),
                    concurrency=getattr(args, "concurrency", None),
                    max_workers=getattr(args, "max_workers", None),
                    runtime=getattr(args, "runtime", None),
                    model=getattr(args, "model", None),
                    cwd=getattr(args, "cwd", None),
                    spend_limit=getattr(args, "spend_limit", None),
                    orchestrate=False,
                    no_orchestrate=True,
                )
            )
            for task_id, batch_id in paused_for_author:
                try:
                    run_mod.handle_run(
                        argparse.Namespace(
                            mode="single",
                            task=task_id,
                            batch=batch_id,
                            plan=None,
                            strategy=None,
                            concurrency=None,
                            batch_size=None,
                            resume=True,
                            reset_state=bool(getattr(args, "reset_state", False)),
                            baseline_packet=None,
                            until=None,
                        )
                    )
                except SystemExit as exc:
                    code = int(getattr(exc, "code", 1) or 0)
                    if code == 10:
                        state = load_workflow_state(task_id, batch_id)
                        waiting = str(state.get("waitingCheckpoint") or "")
                        failures.append(f"{task_id}/{batch_id}: paused_at={waiting or 'unknown'}")
                        continue
                    if code not in (0,):
                        failures.append(f"{task_id}/{batch_id}: exit={code}")
                        continue
        if failures:
            print(f"[task scaled-e2e finalize] FAILED ({len(failures)} partition(s))", file=sys.stderr)
            for item in failures[:100]:
                print(f"  - {item}", file=sys.stderr)
            raise SystemExit(1)
        print(f"[task scaled-e2e finalize] finalized {len(units)} partition batch(es)")
        return
    if command == "verify":
        if getattr(args, "plan", None):
            from _common import fanout_plan as fp
            from _common import fanout_strategies as fs
            from verify.handler import handle_sample_drift, handle_goldenset

            plan = fp.load_plan(args.plan)
            if plan is None:
                print(f"[task scaled-e2e verify] plan not found: {args.plan}", file=sys.stderr)
                raise SystemExit(2)
            roots: list[str] = []
            roots_by_unit: dict[tuple[str, str], list[str]] = {}
            issues: list[str] = []
            for unit in fs.expand_units(plan):
                task_id = str(unit["taskId"])
                batch_id = str(unit["batchId"])
                unit_roots, unit_issues = gate_verify(task=task_id, batch=batch_id, scope="current")
                roots_by_unit[(task_id, batch_id)] = [str(r) for r in unit_roots]
                roots.extend([str(r) for r in unit_roots])
                issues.extend(unit_issues)
                write_batch_audit_summary(task_id, batch_id, roots=unit_roots, issues=unit_issues)
                try:
                    handle_sample_drift(
                        argparse.Namespace(
                            task=task_id,
                            batch=batch_id,
                            fraction=1.0,
                            samples_file=None,
                            baseline=None,
                            report_out=None,
                        )
                    )
                except SystemExit as exc:
                    if int(getattr(exc, "code", 1) or 0) != 0:
                        issues.append(f"{task_id}/{batch_id}: sample-drift failed")
            try:
                handle_goldenset(argparse.Namespace(baseline=None, report_out=None))
            except SystemExit as exc:
                if int(getattr(exc, "code", 1) or 0) != 0:
                    issues.append("goldenset regression gate failed")
            issues.extend(_scaled_e2e_plan_runtime_issues(plan, roots_by_unit))
        else:
            roots, issues = gate_verify(task=args.task, batch=args.batch, scope="current")
        if roots:
            print(f"[task scaled-e2e verify] roots={len(roots)}")
        if issues:
            print(f"[task scaled-e2e verify] FAILED ({len(issues)} issue(s))", file=sys.stderr)
            for issue in issues[:200]:
                print(f"  - {issue}", file=sys.stderr)
            raise SystemExit(1)
        print("[task scaled-e2e verify] PASSED")
        return
    print("[task scaled-e2e] 需要子命令：prepare | fanout-author | rollup | verify", file=sys.stderr)
    raise SystemExit(2)


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
    pn.add_argument("--entity-articles", dest="entity_articles", type=int,
                    help="content.quotas.entityArticles（显式写入 task.yaml，允许 0）")
    pn.add_argument("--route-articles", dest="route_articles", type=int,
                    help="content.quotas.routeArticles（显式写入 task.yaml，允许 0）")
    pn.add_argument("--gallery-posts", dest="gallery_posts", type=int,
                    help="content.quotas.galleryPosts（显式写入 task.yaml，允许 0）")
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
    pstg.add_argument("--source-task", dest="source_task", default="旅行/地域/四川省/景区/景区精选")
    pstg.add_argument("--discovery", help="discovery JSON 路径；默认取 source task 的 discovery_sichuan_100e.json")
    pstg.add_argument("--limit", type=int, default=50)
    pstg.add_argument(
        "--reserve-ratio",
        type=float,
        default=0.2,
        help="额外选择备用 coverageTargets 比例；默认 0.2，用于 partial replacement",
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
    pserun.add_argument("--model", default="composer-2.5")
    pserun.add_argument("--cwd", default=os.getcwd())
    pserun.add_argument("--spend-limit-usd", dest="spend_limit", type=float)
    pserun.add_argument("--refs", help="仅运行逗号分隔的 ref 列表（content-mode 为内容对象 ref）")
    pserun.add_argument("--force-refs", dest="force_refs", help="强制重跑逗号分隔的已成稿 ref")
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
    psef2.add_argument("--model", default="composer-2.5")
    psef2.add_argument("--cwd", default=os.getcwd())
    psef2.add_argument("--spend-limit-usd", dest="spend_limit", type=float)
    psef2.add_argument("--reset-state", dest="reset_state", action="store_true")
    psef2.set_defaults(handler=handle_scaled_e2e)

    psev = sesub.add_parser("verify", help="显式校验某 runtime task/batch")
    psev.add_argument("--task")
    psev.add_argument("--batch")
    psev.add_argument("--plan", help="若提供，则聚合校验 plan 下全部分区 task/batch")
    psev.set_defaults(handler=handle_scaled_e2e)

    register_run_parser(sub)
    register_decompose_parser(sub)
    register_content_supply_parsers(sub)
    queue.register_queue_parser(sub)

    def _dispatch(args: argparse.Namespace) -> None:
        if not getattr(args, "task_command", None):
            p.print_help()
            raise SystemExit(1)

    p.set_defaults(handler=_dispatch)
