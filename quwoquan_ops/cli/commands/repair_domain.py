"""stackctl `repair` 子命令域主入口。

从 stackctl.py 逐字迁出 `command_repair`: 白名单 fix 分发（rebuild-packages /
restart-stack / reclaim-ports / orphan-compose / build-cache / output-layout /
content-outbox / media-dead-letter 等）与报告聚合。

测试经 ``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号，
因此函数体内一律经函数内延迟导入 `_stackctl` 属性访问（含本模块符号互调），
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time

from typing import Any
from typing import Mapping


def command_repair(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    if args.fix == "reconcile-output-layout":
        report_dir = _stackctl.resolve_report_dir(args, "repo", "repo")
        if args.target != "repo":
            details = [
                "reconcile-output-layout is repository-scoped and requires --target repo"
            ]
            return _stackctl._finish_output_layout_reconciliation(
                report_dir=report_dir,
                status="gate_block",
                summary="output layout reconciliation is GATE_BLOCK",
                details=details,
                report={
                    "command": "repair",
                    "target": args.target,
                    "fix": args.fix,
                    "status": "gate_block",
                    "destructiveRepairPerformed": False,
                    "destructiveActions": [],
                    "resourceReleaseIssues": details,
                },
                exit_code=2,
            )
        return _stackctl._repair_output_layout(args, report_dir=report_dir)
    if args.target == "repo":
        report_dir = _stackctl.resolve_report_dir(args, "repo", "repo")
        summary = f"{args.fix} is not available for repository target"
        _stackctl._write_summary_bundle(
            report_dir,
            command="repair",
            target="repo",
            status="failed",
            summary=summary,
            details=[summary],
        )
        return {
            "exitCode": 2,
            "summary": summary,
            "details": [summary],
            "reportDir": _stackctl.relpath(report_dir),
        }
    topology = _stackctl.load_environment_topology()
    target = _stackctl.get_target(topology, args.target)
    env_name = str(target["env"])
    report_dir = _stackctl.resolve_report_dir(args, env_name, args.target)
    steps: list[dict[str, Any]] = []
    if args.fix == "service-core-cutover":
        try:
            with _stackctl._local_stack_operation_lock(args.target):
                workspace = _stackctl._mutable_workspace_snapshot()
                rendered = _stackctl._dev_session_render_runtime_inputs(
                    environment=env_name,
                    target=args.target,
                    report_dir=report_dir,
                    workspace_snapshot=workspace,
                )
                previous_attempt = _stackctl.load_test_live_startup_attempt(args.target)

                def commit_runtime(
                    runtime_plan: Mapping[str, Any],
                ) -> Mapping[str, Any]:
                    if not isinstance(previous_attempt, Mapping):
                        raise ValueError(
                            "service-core cutover requires the current test-live receipt"
                        )
                    _stackctl.transition_test_live_startup_attempt(
                        environment=env_name,
                        target=args.target,
                        attempt_id=str(previous_attempt["attemptId"]),
                        status="stopped",
                        failure="superseded by successful service-core cutover",
                    )
                    attempt_id = (
                        f"{env_name}-service-core-cutover-"
                        + hashlib.sha256(
                            f"{report_dir}\0{time.time_ns()}".encode("utf-8")
                        ).hexdigest()[:24]
                    )
                    _stackctl.transition_test_live_startup_attempt(
                        environment=env_name,
                        target=args.target,
                        attempt_id=attempt_id,
                        status="prepared",
                        runtime_plan=runtime_plan,
                        run_root=report_dir,
                    )
                    _stackctl.transition_test_live_startup_attempt(
                        environment=env_name,
                        target=args.target,
                        attempt_id=attempt_id,
                        status="partial",
                        runtime_plan=runtime_plan,
                        run_root=report_dir,
                    )
                    return _stackctl.transition_test_live_startup_attempt(
                        environment=env_name,
                        target=args.target,
                        attempt_id=attempt_id,
                        status="running",
                        runtime_plan=runtime_plan,
                        run_root=report_dir,
                    )

                result = _stackctl.service_core_cutover.execute(
                    target=args.target,
                    compose_project=str(
                        getattr(args, "compose_project", "") or ""
                    ),
                    preserve_volumes=bool(
                        getattr(args, "preserve_volumes", False)
                    ),
                    report_dir=report_dir,
                    rendered=rendered,
                    workspace_before=workspace,
                    workspace_after_build=_stackctl._mutable_workspace_snapshot,
                    leases=_stackctl.active_consumer_leases(args.target),
                    runner=_stackctl.run,
                    commit_runtime=commit_runtime,
                )
        except (
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            result = {
                "exitCode": 2,
                "status": "gate_block",
                "blockerKind": "service_core_cutover_preflight_failed",
                "details": [str(exc)],
                "rollbackTriggered": False,
            }
            report_dir.mkdir(parents=True, exist_ok=True)
            _stackctl.write_json(report_dir / "report.json", result)
        summary = (
            "Alpha service-core cutover completed"
            if int(result.get("exitCode", 2)) == 0
            else "Alpha service-core cutover is GATE_BLOCK"
        )
        return {
            **result,
            "summary": summary,
            "reportDir": _stackctl.relpath(report_dir),
        }
    if args.fix == "repair-active-content-release-outbox":
        return _stackctl._repair_active_content_release_outbox(
            args,
            environment=env_name,
            target_name=args.target,
            report_dir=report_dir,
        )
    if args.fix == "repair-media-processing-dead-letter-indexes":
        return _stackctl._repair_media_processing_dead_letter_indexes(
            args,
            environment=env_name,
            target_name=args.target,
            report_dir=report_dir,
        )
    if args.fix == "reclaim-orphaned-compose":
        return _stackctl._repair_orphaned_compose(
            args,
            environment=env_name,
            report_dir=report_dir,
        )
    if args.fix == "reclaim-stale-test-live-receipt":
        return _stackctl._repair_stale_test_live_receipt(
            args,
            environment=env_name,
            report_dir=report_dir,
        )
    if args.fix == "reclaim-undownable-startup-receipt":
        return _stackctl._repair_undownable_startup_receipt(
            args,
            environment=env_name,
            report_dir=report_dir,
        )
    if args.fix == "reclaim-orphaned-processes":
        if args.target != "alpha-local":
            summary = "reclaim-orphaned-processes is only available for alpha-local"
            _stackctl._write_summary_bundle(
                report_dir,
                command="repair",
                target=args.target,
                status="failed",
                summary=summary,
                details=[summary],
            )
            return {
                "exitCode": 2,
                "summary": summary,
                "details": [summary],
                "reportDir": _stackctl.relpath(report_dir),
            }
        try:
            reclaimed = _stackctl.alpha_content_release_runtime.reclaim_orphaned_managed_processes(
                confirm=bool(
                    getattr(args, "confirm_orphaned_process_reclaim", False)
                )
            )
            occupied = [
                item
                for item in _stackctl._network_report(args.target)["ports"]
                if item["open"]
            ]
            if occupied:
                raise RuntimeError(
                    "canonical Alpha ports remain occupied after orphan repair: "
                    + ", ".join(
                        f"{item['name']}:{item['port']}" for item in occupied
                    )
                )
            preserved_observability: list[str] = []
            observability_root = _stackctl.output_root() / "env/alpha/observability"
            if observability_root.is_dir():
                incomplete_runs = [
                    entry
                    for entry in sorted(observability_root.iterdir())
                    if entry.is_dir() and not (entry / "manifest.json").is_file()
                ]
                if incomplete_runs:
                    preservation_root = (
                        report_dir / "attachments/incomplete-observability"
                    )
                    preservation_root.mkdir(parents=True, exist_ok=True)
                    for incomplete_run in incomplete_runs:
                        destination = preservation_root / incomplete_run.name
                        if destination.exists():
                            raise RuntimeError(
                                "incomplete observability preservation target already exists: "
                                + str(destination)
                            )
                        shutil.move(str(incomplete_run), str(destination))
                        preserved_observability.append(_stackctl.relpath(destination))
        except RuntimeError as exc:
            summary = f"stackctl repair orphan reclaim is GATE_BLOCK for {args.target}"
            details = [str(exc)]
            _stackctl.write_json(
                report_dir / "report.json",
                {
                    "command": "repair",
                    "target": args.target,
                    "fix": args.fix,
                    "status": "gate_block",
                    "destructiveRepairPerformed": False,
                    "details": details,
                },
            )
            _stackctl._write_summary_bundle(
                report_dir,
                command="repair",
                target=args.target,
                status="failed",
                summary=summary,
                details=details,
            )
            return {
                "exitCode": 2,
                "summary": summary,
                "details": details,
                "reportDir": _stackctl.relpath(report_dir),
            }
        details = [
            f"reclaimed managed role={name} pid={record['pid']} pgid={record['pgid']}"
            for name, record in sorted(reclaimed.items())
        ] or ["no orphaned Alpha managed process matched"]
        details.extend(
            f"preserved incomplete observability as repair attachment: {path}"
            for path in preserved_observability
        )
        summary = f"stackctl repair reclaimed orphaned Alpha processes for {args.target}"
        _stackctl.write_json(
            report_dir / "report.json",
            {
                "command": "repair",
                "target": args.target,
                "fix": args.fix,
                "status": "passed",
                "destructiveRepairPerformed": bool(reclaimed),
                "destructiveActions": details if reclaimed else [],
                "preservedIncompleteObservability": preserved_observability,
            },
        )
        _stackctl.write_json(
            report_dir / "repair_plan.json",
            {
                "target": args.target,
                "fix": args.fix,
                "actions": [
                    "terminate only ledger-less Alpha wrappers matching the repository path and canonical port signatures"
                ],
            },
        )
        _stackctl._write_summary_bundle(
            report_dir,
            command="repair",
            target=args.target,
            status="ok",
            summary=summary,
            details=details,
        )
        return {
            "exitCode": 0,
            "summary": summary,
            "details": details,
            "reportDir": _stackctl.relpath(report_dir),
        }
    if args.fix == "reclaim-build-cache":
        if args.target not in _stackctl.LOCAL_BUILD_CACHE_TARGETS:
            summary = (
                "reclaim-build-cache is only available for "
                "alpha-local, beta-local, or gamma-local"
            )
            _stackctl._write_summary_bundle(
                report_dir,
                command="repair",
                target=args.target,
                status="failed",
                summary=summary,
                details=[summary],
            )
            return {
                "exitCode": 2,
                "summary": summary,
                "details": [summary],
                "reportDir": _stackctl.relpath(report_dir),
            }
        return _stackctl._repair_reclaim_build_cache(
            args,
            report_dir=report_dir,
        )
    if args.fix == "rebuild-packages":
        package_args = argparse.Namespace(
            command="package",
            env=env_name,
            service="",
            include_services=True,
            target=args.target,
            output_format="json",
            report_dir=str(report_dir / "rebuild-packages"),
        )
        payload = _stackctl.command_package(package_args)
        _stackctl.write_json(report_dir / "report.json", {"command": "repair", "nested": payload})
        _stackctl.write_json(
            report_dir / "repair_plan.json",
            {"target": args.target, "fix": args.fix, "actions": ["rebuild environment packages"]},
        )
        return payload
    if args.fix == "restart-stack":
        # Restart is destructive for local state. Validate every external
        # deployment prerequisite before stopping a currently running stack;
        # otherwise a failed `up` would turn a partial outage into a full one.
        if args.target in {"alpha-local", "beta-local", "gamma-local"}:
            try:
                _stackctl._load_active_product_telemetry_log_sink(env_name, args.target)
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                summary = (
                    "stackctl repair restart-stack blocked before stop: "
                    f"deployment prerequisite failed: {exc}"
                )
                _stackctl.write_json(
                    report_dir / "report.json",
                    {
                        "command": "repair",
                        "target": args.target,
                        "fix": args.fix,
                        "steps": [],
                        "blockedBeforeStop": True,
                        "reason": str(exc),
                    },
                )
                _stackctl.write_json(
                    report_dir / "repair_plan.json",
                    {
                        "target": args.target,
                        "fix": args.fix,
                        "actions": [
                            "ensure the declared local Provider topology is available and QWQ_DEPLOY_WORK_ROOT is writable when materialization is required",
                            "rerun stackctl doctor before restart-stack",
                        ],
                    },
                )
                _stackctl._write_summary_bundle(
                    report_dir,
                    command="repair",
                    target=args.target,
                    status="failed",
                    summary=summary,
                    details=[str(exc)],
                )
                return {
                    "exitCode": 2,
                    "summary": summary,
                    "details": [str(exc)],
                    "reportDir": _stackctl.relpath(report_dir),
                }
        down_args = argparse.Namespace(command="down", target=args.target, output_format="json", report_dir=str(report_dir / "down"))
        up_args = argparse.Namespace(
            command="up",
            env="",
            target=args.target,
            device_id="",
            skip_app=True,
            skip_build=False,
            workload="full",
            rollout_mode="",
            output_format="json",
            # Startup receipts require runRoot to be one direct canonical run
            # directory. Nesting `up` below the repair report violates that
            # contract before any workload can start.
            report_dir="",
        )
        down_payload = _stackctl.command_down(down_args)
        if int(down_payload.get("exitCode") or 0) != 0:
            steps = [down_payload]
            summary = (
                f"stackctl repair restart-stack stopped after down failure for "
                f"{args.target}"
            )
            _stackctl.write_json(
                report_dir / "report.json",
                {
                    "command": "repair",
                    "target": args.target,
                    "fix": args.fix,
                    "status": "failed",
                    "steps": steps,
                },
            )
            _stackctl.write_json(
                report_dir / "repair_plan.json",
                {
                    "target": args.target,
                    "fix": args.fix,
                    "actions": [
                        "resolve the recorded down failure",
                        "rerun restart-stack only after resources are stopped",
                    ],
                },
            )
            _stackctl._write_summary_bundle(
                report_dir,
                command="repair",
                target=args.target,
                status="failed",
                summary=summary,
                details=[str(down_payload.get("summary") or "down failed")],
            )
            return {
                "exitCode": int(down_payload.get("exitCode") or 1),
                "summary": summary,
                "details": [str(down_payload.get("summary") or "down failed")],
                "reportDir": _stackctl.relpath(report_dir),
            }
        up_payload = _stackctl.command_up(up_args)
        steps = [down_payload, up_payload]
        _stackctl.write_json(report_dir / "report.json", {"command": "repair", "steps": steps})
        _stackctl.write_json(
            report_dir / "repair_plan.json",
            {"target": args.target, "fix": args.fix, "actions": ["stop stack", "start stack"]},
        )
        _stackctl._write_summary_bundle(
            report_dir,
            command="repair",
            target=args.target,
            status="ok" if up_payload["exitCode"] == 0 else "failed",
            summary=f"stackctl repair restart-stack completed for {args.target}",
            details=[down_payload["summary"], up_payload["summary"]],
        )
        return {
            "exitCode": 0 if up_payload["exitCode"] == 0 else up_payload["exitCode"],
            "summary": f"stackctl repair restart-stack completed for {args.target}",
            "details": [down_payload["summary"], up_payload["summary"]],
            "reportDir": _stackctl.relpath(report_dir),
        }
    if args.fix == "reclaim-ports":
        # Port reclaim is deliberately diagnostic-only.  It must remain usable
        # when the active candidate is stale or invalid, because that is the
        # exact state in which operators need an inventory before a supported
        # teardown.  Health inspection continues to use _network_report and
        # therefore still requires a current candidate/startup identity.
        ports = _stackctl._canonical_port_occupancy_report(args.target)["ports"]
        occupied = [item for item in ports if item["open"]]
        _stackctl.write_json(report_dir / "report.json", {"command": "repair", "target": args.target, "occupied": occupied})
        _stackctl.write_json(
            report_dir / "repair_plan.json",
            {
                "target": args.target,
                "fix": args.fix,
                "actions": [f"inspect listener on {item['name']}:{item['port']}" for item in occupied],
            },
        )
        _stackctl._write_summary_bundle(
            report_dir,
            command="repair",
            target=args.target,
            status="ok",
            summary=f"stackctl repair reclaim-ports inspected {args.target}",
            details=[f"{item['name']} listens on {item['port']}" for item in occupied] or ["no occupied canonical ports"],
        )
        return {
            "exitCode": 0,
            "summary": f"stackctl repair reclaim-ports inspected {args.target}",
            "details": [f"{item['name']} listens on {item['port']}" for item in occupied] or ["no occupied canonical ports"],
            "reportDir": _stackctl.relpath(report_dir),
        }
    return {
        "exitCode": 2,
        "summary": f"unsupported repair fix: {args.fix}",
        "details": [],
    }


def register_parser(subparsers: "argparse._SubParsersAction") -> None:
    """向 stackctl build_parser 注册本域子命令（从 build_parser 逐字迁出）。"""
    import quwoquan_ops.cli.stackctl as _stackctl

    repair_parser = subparsers.add_parser("repair")
    repair_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    repair_parser.add_argument("--target", choices=(*_stackctl.TARGETS, "repo"), required=True)
    repair_parser.add_argument(
        "--fix",
        choices=[
            "rebuild-packages",
            "reclaim-build-cache",
            "reclaim-orphaned-processes",
            "reclaim-orphaned-compose",
            "reclaim-stale-test-live-receipt",
            "reclaim-undownable-startup-receipt",
            "service-core-cutover",
            "restart-stack",
            "reclaim-ports",
            "reconcile-output-layout",
            "repair-active-content-release-outbox",
            "repair-media-processing-dead-letter-indexes",
        ],
        required=True,
    )
    repair_parser.add_argument(
        "--compose-project",
        default="",
        help="Exact local Compose project required by service-core-cutover.",
    )
    repair_parser.add_argument(
        "--preserve-volumes",
        action="store_true",
        help="Explicitly preserve every named volume during service-core-cutover.",
    )
    repair_parser.add_argument(
        "--confirm-global-build-cache-reclaim",
        action="store_true",
        help=(
            "Confirm daemon-global removal of all unused local Docker builder "
            "cache while containers, images, volumes, and runtime data remain preserved."
        ),
    )
    repair_parser.add_argument(
        "--confirm-active-content-release-outbox-repair",
        action="store_true",
        help=(
            "Confirm candidate-bound replay repair of the exact active Content "
            "release while only Mongo and the packaged importer are running."
        ),
    )
    repair_parser.add_argument(
        "--confirm-media-processing-dead-letter-index-migration",
        action="store_true",
        help=(
            "Confirm candidate-bound removal of the two retired MediaAsset "
            "dead-letter indexes while only Mongo and the packaged migration "
            "command are running."
        ),
    )
    repair_parser.add_argument(
        "--expected-retired-index-drop-count",
        type=int,
        default=-1,
        help=(
            "Exact retired MediaAsset index count expected to be removed: "
            "2 for the first migration or 0 for authoritative replay."
        ),
    )
    repair_parser.add_argument(
        "--content-import-report",
        default="",
        help="Exact existing active Content import receipt used as repair identity.",
    )
    repair_parser.add_argument(
        "--expected-outbox-repair-count",
        type=int,
        default=-1,
        help="Exact release-scoped payload count expected in this replay transaction.",
    )
    repair_parser.add_argument(
        "--confirm-orphaned-process-reclaim",
        action="store_true",
        help=(
            "Confirm termination of ledger-less Alpha process groups only after "
            "their target-scoped wrapper and canonical port signatures match."
        ),
    )
    repair_parser.add_argument(
        "--orphaned-compose-attestation",
        default="",
        help=(
            "Canonical create-once attestation path below the target environment "
            "runs root. Planning creates it without removing resources; consuming "
            "it also requires --confirm-orphaned-compose-teardown."
        ),
    )
    repair_parser.add_argument(
        "--confirm-orphaned-compose-teardown",
        action="store_true",
        help=(
            "Confirm exact-ID removal of the containers and networks sealed in a "
            "fresh orphan Compose attestation; named volumes remain preserved."
        ),
    )
    repair_parser.add_argument(
        "--confirm-stale-test-live-receipt-reclaim",
        action="store_true",
        help=(
            "Confirm removal of one test-live startup receipt the current contract "
            "cannot admit, after a live probe proves the project owns no container, "
            "network or canonical port. The receipt is archived first and named "
            "volumes remain preserved."
        ),
    )
    repair_parser.add_argument(
        "--confirm-undownable-startup-receipt-reclaim",
        action="store_true",
        help=(
            "Confirm retirement of one non-stopped startup receipt whose own "
            "candidate topology cannot produce a valid Compose project, after a "
            "live probe proves the project owns no container, network or canonical "
            "port. The receipt is archived first and named volumes remain preserved."
        ),
    )
    repair_parser.add_argument(
        "--output-layout-action",
        choices=("plan", "apply"),
        default="plan",
        help=(
            "Create an immutable output/root-layout reconciliation plan, or apply "
            "one exact ready plan. This repair is available only with --target repo."
        ),
    )
    repair_parser.add_argument(
        "--output-layout-plan-ref",
        default="",
        help=(
            "Exact immutable plan below the canonical repo runs root; required for "
            "--output-layout-action apply."
        ),
    )
    repair_parser.add_argument(
        "--confirm-output-layout-reconciliation",
        action="store_true",
        help=(
            "Confirm reversible move-only application of one exact ready output "
            "layout plan. Named volumes, environment runtime, Data, and source are excluded."
        ),
    )

