"""Scaled E2E task orchestration helpers."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from _common.io import read_json
from task import run as run_mod
from task import store
from verify.audit_summary import write_batch_audit_summary
from verify.gate import gate_verify

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
REPO_ROOT = DATA_ROOT.parent


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


def _scaled_e2e_plan_runtime_issues(
    plan: dict,
    roots_by_unit: dict[tuple[str, str], list[str]],
) -> list[str]:
    """Plan-level hard gates for scaled E2E verification."""
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


def _prepare_author_jobs_for_paused_targets(
    plan: dict,
    paused_targets: list[tuple[str, str]],
) -> None:
    from _common import fanout_strategies as fs
    from task import fanout_dispatch as fd

    paused_keys = {(task_id, batch_id) for task_id, batch_id in paused_targets}
    for unit in fs.expand_units(plan):
        key = (str(unit["taskId"]), str(unit["batchId"]))
        if key not in paused_keys:
            continue
        fd.sync_content_author_jobs(plan, unit, partition_path=list(unit.get("partitionPath") or []))


def handle_scaled_e2e(args: argparse.Namespace) -> None:
    command = getattr(args, "scaled_e2e_command", "")
    if command == "prepare":
        from data.baseline import handle_baseline
        from explore.handler import handle_explore

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
        if getattr(args, "source_task", None):
            argv += ["--source-task", args.source_task]
        if getattr(args, "source_batch", None):
            argv += ["--source-batch", args.source_batch]
        if getattr(args, "skip_startup_probe", False):
            argv += ["--skip-startup-probe"]
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
        from task.handler import handle_rollup

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
            from verify.handler import handle_goldenset, handle_sample_drift

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
