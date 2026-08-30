"""stackctl `up` 子命令域。

从 stackctl.py 逐字迁出:

- `register_parser`:`up` 子命令的 argparse 表面(帮助文案与参数集合
  逐字节保持不变);
- `command_up`:target 归一、operation lock 与 orphan-compose 收敛后的
  up 入口;
- `_reuse_running_full_for_bounded_workload`:bounded workload 对运行中
  full 栈的无损复用决策;
- `_fixed_candidate_runtime_identity` / `_runtime_identity_mismatches`:
  immutable candidate 的 startup receipt 身份派生与漂移比对
  (product-telemetry-log-sink 域经 stackctl 命名空间共用)。

`_command_up_impl` 锁内全量启动编排主干在 `commands/up_runtime.py`
(本模块顶层 re-export,供 stackctl 命名空间装配保持零漂移);
prod-sim / prod-hosted 的 App 启动分支与 `tail_*_background_logs`
家族在 `commands/up_app_launch.py`。
`_bind_formal_local_release_provider_environment` / `_gamma_start_command` /
`_run_with_live_output` / `_tail_file_for_startup` / `_write_summary_bundle` /
`_orphan_compose_runtime_gate` / `_optional_product_telemetry_environment`
等协作符号仍由 stackctl 命名空间拥有或位于兄弟域模块。测试经
``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号,因此
函数体内一律经函数内延迟导入 `_stackctl` 属性访问(含本模块符号互调),
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import contextlib
import json
from pathlib import Path
from typing import Any, Mapping

from quwoquan_ops.cli.commands.up_runtime import _command_up_impl as _runtime_command_up_impl


def _app_launch_projection(*, skip_app: bool, steps: list[dict[str, Any]]) -> dict[str, Any]:
    """Report App execution independently from service startup success."""

    if skip_app:
        return {
            "status": "not_executed",
            "reason": "--skip-app explicitly disabled App launch",
        }
    app_steps = [
        step
        for step in steps
        if isinstance(step, Mapping)
        and (
            str(step.get("name") or "") == "app-launch"
            or "app-launch" in " ".join(str(item) for item in step.get("argv") or [])
        )
    ]
    if not app_steps:
        return {
            "status": "not_executed",
            "reason": "no App launch attempt was created",
        }
    return {
        "status": "executed",
        "attempts": len(app_steps),
        "passed": all(int(step.get("exitCode") or 0) == 0 for step in app_steps),
    }


def _up_evidence_projection(
    args: argparse.Namespace,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Independently read back runtime identity and attach one evidence envelope."""

    import quwoquan_ops.cli.stackctl as _stackctl
    from quwoquan_ops.cli.lib.evidence_generation import (
        build_evidence_generation_envelope,
        sha256_file,
    )
    from quwoquan_ops.cli.lib.runtime_container_liveness import (
        ComposeProjectAbsent,
        verify_running_receipt_liveness,
    )

    requested_target = str(getattr(args, "target", "") or "").strip()
    requested_env = str(getattr(args, "env", "") or "").strip()
    selectors_resolved = bool(requested_target) != bool(requested_env)
    if selectors_resolved and not requested_target:
        requested_target = str(_stackctl.DEV_UP_STACK_TARGETS.get(requested_env) or "")
        if not requested_target:
            requested_target = _stackctl.app_target_for_env(requested_env)
    if not requested_target:
        return payload

    # Missing evidence allocation is a typed in-memory result, never an alias
    # for the current working directory.  Selector validation also completes
    # before candidate/startup readback so an invalid command cannot inherit
    # stale runtime evidence from an earlier attempt.
    report_ref = str(payload.get("reportDir") or "").strip()
    if not report_ref or not selectors_resolved:
        return payload
    resolved_env = (
        requested_env
        or str(payload.get("environment") or "").strip()
        or _stackctl.env_for_target(requested_target)
    )
    try:
        report_dir = _stackctl.validate_up_report_dir(
            report_ref,
            env_name=resolved_env,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return {
            **payload,
            "exitCode": 2,
            "summary": f"stackctl up is GATE_BLOCK for {requested_env or requested_target}",
            "details": [f"unsafe up report directory: {exc}"],
        }
    report_path = report_dir / "report.json"
    report: dict[str, Any] = {}
    report_was_loaded = False
    if report_path.is_file() and not report_path.is_symlink():
        try:
            loaded = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            loaded = {}
        if isinstance(loaded, dict) and loaded:
            report = loaded
            report_was_loaded = True
    if not report:
        # Early failures may not own a persisted report.  Preserve their typed
        # result instead of manufacturing an empty successful document.
        report = {
            "command": "up",
            "target": requested_env or requested_target,
            "resolvedTarget": requested_target,
            "status": (
                "ok"
                if int(payload.get("exitCode") or 0) == 0
                else "gate_block"
                if int(payload.get("exitCode") or 0) == 2
                else "failed"
            ),
            "details": list(payload.get("details") or []),
        }

    steps = [item for item in report.get("steps") or [] if isinstance(item, dict)]
    app_launch = _app_launch_projection(
        skip_app=bool(getattr(args, "skip_app", False)),
        steps=steps,
    )

    candidate_snapshot: Mapping[str, Any] | None = None
    candidate_error = ""
    try:
        candidate_snapshot = _stackctl.active_deployment_candidate_snapshot(
            requested_target
        )
    except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        candidate_error = str(exc)

    startup_receipt: Mapping[str, Any] | None = None
    startup_error = ""
    startup_path = _stackctl.startup_attempt_path(requested_target)
    try:
        startup_receipt = _stackctl.read_startup_attempt(requested_target)
    except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        startup_error = str(exc)

    startup_readback: dict[str, Any]
    liveness_report: dict[str, Any]
    if isinstance(startup_receipt, Mapping):
        startup_readback = {
            "status": "executed",
            "receiptRef": str(startup_path.resolve()),
            "receiptDigest": (
                sha256_file(startup_path)
                if startup_path.is_file() and not startup_path.is_symlink()
                else ""
            ),
            "identity": {
                field: startup_receipt.get(field)
                for field in (
                    "attemptId",
                    "candidateDigest",
                    "configurationDigest",
                    "providerRuntimeDigest",
                    "observabilityLogSinkDigest",
                    "composeProject",
                    "imageTransportTag",
                    "imageComposition",
                    "status",
                )
            },
        }
        try:
            liveness = verify_running_receipt_liveness(
                startup_receipt, runner=_stackctl.run
            )
        except ComposeProjectAbsent as exc:
            liveness_report = {"status": "not_applicable", "reason": str(exc)}
        except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
            liveness_report = {"status": "executed", "result": "failed", "issues": [str(exc)]}
        else:
            if liveness is None:
                liveness_report = {
                    "status": "not_applicable",
                    "reason": "startup receipt is not in running state",
                }
            else:
                liveness_report = {
                    "status": "executed",
                    "result": liveness.status,
                    "composeProject": liveness.compose_project,
                    "containers": [
                        {
                            "name": item.name,
                            "service": item.service,
                            "state": item.state,
                            "health": item.health,
                            "exitCode": item.exit_code,
                            "declaredOneShot": item.declared_one_shot,
                        }
                        for item in liveness.containers
                    ],
                    "issues": list(liveness.issues()),
                }
    else:
        startup_readback = {
            "status": "not_executed",
            "reason": startup_error or "no startup receipt was produced",
        }
        liveness_report = {
            "status": "not_applicable",
            "reason": "runtime liveness requires a running startup receipt",
        }

    candidate_digest = str(
        (candidate_snapshot or {}).get("baselineId") or ""
    ).strip()
    startup_candidate = str(
        (startup_receipt or {}).get("candidateDigest") or ""
    ).strip()
    generation_issues: list[str] = []
    if candidate_error:
        generation_issues.append(f"active candidate readback failed: {candidate_error}")
    if startup_error:
        generation_issues.append(f"startup receipt readback failed: {startup_error}")
    if candidate_digest and startup_candidate and candidate_digest != startup_candidate:
        generation_issues.append(
            "startup receipt candidateDigest does not match the active candidate"
        )

    envelope = build_evidence_generation_envelope(
        command="up",
        candidate_snapshot=candidate_snapshot,
        startup_receipt=startup_receipt,
        startup_status=(
            "executed" if isinstance(startup_receipt, Mapping) else "not_executed"
        ),
        startup_reason=startup_error or "no startup receipt was produced",
        upstream_status="not_applicable",
        upstream_reason="up is the startup evidence producer",
    )
    report.update(
        {
            "appLaunch": app_launch,
            "evidenceEnvelope": envelope,
            "startupReadback": startup_readback,
            "runtimeLiveness": liveness_report,
            "generationIssues": generation_issues,
        }
    )
    if generation_issues and int(payload.get("exitCode") or 0) == 0:
        payload.update(
            {
                "exitCode": 2,
                "summary": f"stackctl up is GATE_BLOCK for {requested_env or requested_target}",
                "details": generation_issues,
            }
        )
        report["status"] = "gate_block"
        report["details"] = generation_issues
    _stackctl.write_json(report_path, report)
    if not report_was_loaded:
        projected_exit_code = int(payload.get("exitCode") or 0)
        projected_status = (
            "ok"
            if projected_exit_code == 0
            else "gate_block"
            if projected_exit_code == 2
            else "failed"
        )
        _stackctl._write_summary_bundle(
            report_dir,
            command="up",
            target=requested_env or requested_target,
            status=projected_status,
            summary=str(payload.get("summary") or "stackctl up result"),
            details=[str(item) for item in payload.get("details") or []],
        )
    payload.update(
        {
            "appLaunch": app_launch,
            "evidenceEnvelope": envelope,
            "startupReadback": startup_readback,
            "runtimeLiveness": liveness_report,
        }
    )
    return payload


def _command_up_impl(args: argparse.Namespace) -> dict[str, Any]:
    return _up_evidence_projection(args, _runtime_command_up_impl(args))


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    import quwoquan_ops.cli.stackctl as _stackctl

    up_parser = subparsers.add_parser("up")
    up_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    up_parser.add_argument("--target", choices=_stackctl.TARGETS, default="")
    up_parser.add_argument("--env", choices=_stackctl.DEV_UP_ENVS, default="")
    up_parser.add_argument("--device-id", default="")
    up_parser.add_argument("--skip-app", action="store_true")
    up_parser.add_argument("--skip-build", action="store_true")
    up_parser.add_argument(
        "--formal-release",
        action="store_true",
        help="Fail-closed release mode: exact candidate images, no automatic repair or cleanup.",
    )
    up_parser.add_argument(
        "--release-manifest",
        default="",
        help="Canonical ReleaseEvidenceManifest required by --formal-release.",
    )
    up_parser.add_argument(
        "--build-only",
        action="store_true",
        help="仅构建 Gamma 本地服务镜像，不启动 Compose 或 App。",
    )
    up_parser.add_argument(
        "--build-services",
        default="",
        help="与 --build-only 配合，构建逗号分隔的 Gamma 服务镜像。",
    )
    up_parser.add_argument(
        "--workload",
        choices=["content-release", "content-commercial", "full"],
        default="full",
    )
    up_parser.add_argument(
        "--data-release-readiness",
        default="",
        help=(
            "prod-sim 媒体演练必须消费的 canonical Data "
            "release-readiness.json；也可由 DATA_RELEASE_READINESS_RECEIPT 提供"
        ),
    )
    up_parser.add_argument("--rollout-mode", choices=["canary", "5", "20", "50", "100"], default="")


def _fixed_candidate_runtime_identity(
    candidate_snapshot: Mapping[str, Any],
    *,
    environment_name: str,
    target_name: str,
) -> dict[str, Any]:
    """Derive every startup receipt identity from one immutable snapshot."""
    import quwoquan_ops.cli.stackctl as _stackctl

    baseline_id, _candidate_root, _candidate_manifest = _stackctl._fixed_candidate_identity(
        candidate_snapshot,
        environment_name=environment_name,
        target_name=target_name,
    )
    provider_binding, observability_binding = _stackctl._candidate_bindings_from_snapshot(
        candidate_snapshot,
        environment_name=environment_name,
        target_name=target_name,
    )
    image_binding = _stackctl._load_package_bound_local_image_composition(
        environment_name,
        target_name,
        candidate_snapshot=candidate_snapshot,
    )
    return {
        "candidateDigest": baseline_id,
        "configurationDigest": str(image_binding["configurationDigest"]),
        "providerRuntimeDigest": str(
            provider_binding["composition"]["runtimeCompositionDigest"]
        ),
        "observabilityLogSinkDigest": str(
            observability_binding["composition"]["composeDigest"]
        ),
        "imageComposition": image_binding["startupImageComposition"],
    }


def _runtime_identity_mismatches(
    startup_attempt: Mapping[str, Any],
    expected_identity: Mapping[str, Any],
) -> list[str]:
    """Return every immutable runtime identity field that is absent or different."""

    return [
        field
        for field, expected in expected_identity.items()
        if startup_attempt.get(field) != expected
    ]


def _reuse_running_full_for_bounded_workload(
    args: argparse.Namespace,
    *,
    candidate_snapshot: Mapping[str, Any] | None,
    target_name: str,
    env_name: str,
    report_target: str,
    report_dir: Path,
    started_monotonic: float,
    started_at: str,
) -> dict[str, Any] | None:
    import quwoquan_ops.cli.stackctl as _stackctl

    workload = str(getattr(args, "workload", "") or "").strip()
    if workload not in {"content-release", "content-commercial"}:
        return None
    try:
        active_attempt = _stackctl.load_startup_attempt(target_name)
    except (OSError, ValueError) as exc:
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        details = [f"active runtime receipt is unreadable: {exc}"]
        _stackctl.write_json(
            report_dir / "report.json",
            {
                "command": "up",
                "target": report_target,
                "resolvedTarget": target_name,
                "workload": workload,
                "status": "gate_block",
                "blockerKind": "runtime_receipt_unreadable",
                "details": details,
                **timing,
            },
        )
        return {
            "exitCode": 2,
            "summary": f"stackctl up is GATE_BLOCK for {report_target}",
            "details": details,
            "reportDir": str(report_dir.resolve()),
            "blockerKind": "runtime_receipt_unreadable",
            **timing,
        }
    if not (
        active_attempt
        and active_attempt.get("status") == "running"
        and active_attempt.get("workload") == "full"
    ):
        return None

    def gate_block(
        details: list[str],
        *,
        blocker_kind: str,
    ) -> dict[str, Any]:
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        report = {
            "command": "up",
            "target": report_target,
            "resolvedTarget": target_name,
            "environment": env_name,
            "workload": workload,
            "status": "gate_block",
            "blockerKind": blocker_kind,
            "runtimeReused": False,
            "details": details,
            **timing,
        }
        _stackctl.write_json(report_dir / "report.json", report)
        _stackctl._write_summary_bundle(
            report_dir,
            command="up",
            target=report_target,
            status="gate_block",
            summary=f"stackctl up is GATE_BLOCK for {report_target}",
            details=details,
            extra={
                "workload": workload,
                "runtimeReused": False,
                "blockerKind": blocker_kind,
            },
            timing=timing,
        )
        return {
            "exitCode": 2,
            "summary": f"stackctl up is GATE_BLOCK for {report_target}",
            "details": details,
            "reportDir": str(report_dir.resolve()),
            "runtimeReused": False,
            "blockerKind": blocker_kind,
            **timing,
        }

    if candidate_snapshot is None:
        return gate_block(
            ["bounded runtime reuse requires one fixed immutable candidate snapshot"],
            blocker_kind="candidate_snapshot_missing",
        )
    try:
        expected_identity = _stackctl._fixed_candidate_runtime_identity(
            candidate_snapshot,
            environment_name=env_name,
            target_name=target_name,
        )
    except (KeyError, OSError, TypeError, ValueError) as exc:
        return gate_block(
            [f"fixed candidate runtime identity is unavailable: {exc}"],
            blocker_kind="candidate_identity_unavailable",
        )
    mismatches = _stackctl._runtime_identity_mismatches(
        active_attempt,
        expected_identity,
    )
    if mismatches:
        return gate_block(
            [
                "running full startup receipt differs from the fixed candidate: "
                + ", ".join(mismatches),
                "old or partial receipts cannot be reused or supplemented",
            ],
            blocker_kind="candidate_identity_mismatch",
        )
    try:
        _stackctl.assert_active_deployment_candidate_snapshot(dict(candidate_snapshot))
    except (OSError, TypeError, ValueError) as exc:
        return gate_block(
            [f"active deployment candidate changed before bounded reuse: {exc}"],
            blocker_kind="candidate_pointer_changed",
        )

    health_report_dir = report_dir / "bounded-reuse-health"
    health_report_dir.mkdir(parents=True, exist_ok=True)
    health_result = _stackctl.command_health(
        argparse.Namespace(
            command="health",
            target=target_name,
            scope="full",
            workload="full",
            read_only=True,
            output_format="json",
            report_dir=str(health_report_dir),
        )
    )
    health_exit_code = health_result.get("exitCode")
    if health_exit_code is None or int(health_exit_code) != 0:
        health_details = [
            str(item)
            for item in (health_result.get("details") or [])
            if str(item).strip()
        ]
        return gate_block(
            [
                "running full startup receipt is present but full health scope failed",
                *health_details,
                f"healthReportDir={_stackctl.relpath(health_report_dir)}",
            ],
            blocker_kind="runtime_health_failed",
        )

    timing = _stackctl._finish_timing(started_monotonic, started_at)
    details = [
        f"{workload} reuses the healthy full runtime without changing its startup receipt",
        f"full attemptId={active_attempt.get('attemptId')}",
        f"fullHealthReportDir={_stackctl.relpath(health_report_dir)}",
    ]
    report = {
        "command": "up",
        "target": report_target,
        "resolvedTarget": target_name,
        "environment": env_name,
        "workload": workload,
        "status": "ok",
        "sessionKind": "hot",
        "runtimeReused": True,
        "baselineWorkload": "full",
        "startupAttempt": active_attempt,
        "details": details,
        **timing,
    }
    _stackctl.write_json(report_dir / "report.json", report)
    _stackctl._write_summary_bundle(
        report_dir,
        command="up",
        target=report_target,
        status="ok",
        summary=f"stackctl up reused full runtime for {report_target}",
        details=details,
        extra={
            "workload": workload,
            "sessionKind": "hot",
            "runtimeReused": True,
            "baselineWorkload": "full",
        },
        timing=timing,
    )
    return {
        "exitCode": 0,
        "summary": f"stackctl up reused full runtime for {report_target}",
        "details": details,
        "reportDir": str(report_dir.resolve()),
        "sessionKind": "hot",
        "runtimeReused": True,
        **timing,
    }


def command_up(args: argparse.Namespace) -> dict[str, Any]:
    """Hold the target operation lock for every return and exception path."""
    import quwoquan_ops.cli.stackctl as _stackctl

    requested_target = str(getattr(args, "target", "") or "").strip()
    requested_env = str(getattr(args, "env", "") or "").strip()
    if requested_target == "prod-hosted" or requested_env == "prod":
        from quwoquan_ops.cli.commands.hosted_read_only import rejection

        return rejection("up")
    if requested_target and requested_env:
        # Selector validation must run before target resolution, locks or
        # availability probes so an invalid command cannot be misreported as
        # an environment conflict.
        return _stackctl._command_up_impl(args)
    if not requested_target and requested_env:
        requested_target = str(_stackctl.DEV_UP_STACK_TARGETS.get(requested_env) or "")
        if not requested_target:
            requested_target = _stackctl.app_target_for_env(requested_env)
    local_targets = {"alpha-local", "beta-local", "gamma-local", "prod-sim"}
    if requested_target not in local_targets:
        return _stackctl._command_up_impl(args)
    operation_scope = contextlib.ExitStack()
    try:
        operation_scope.enter_context(_stackctl._local_stack_operation_lock(requested_target))
        topology = _stackctl.load_environment_topology()
        active_attempt = _stackctl.load_startup_attempt(requested_target)
        bounded_reuses_full = (
            str(getattr(args, "workload", "") or "")
            in {"content-release", "content-commercial"}
            and active_attempt is not None
            and active_attempt.get("status") == "running"
            and active_attempt.get("workload") == "full"
        )
        if not bounded_reuses_full:
            _stackctl.assert_local_runtime_available(topology, requested_target)
            if requested_target in {"alpha-local", "beta-local", "gamma-local"} and not bool(
                getattr(args, "build_only", False)
            ):
                _stackctl.assert_no_running_mutable_runtime(
                    _stackctl.load_test_live_startup_attempt(requested_target),
                    requested_target,
                )
    except (OSError, RuntimeError, ValueError) as exc:
        operation_scope.close()
        lock_error = exc
    else:
        with operation_scope:
            return _stackctl._command_up_impl(args)
    topology = _stackctl.load_environment_topology()
    target = _stackctl.get_target(topology, requested_target)
    env_name = str(target["env"])
    report_target = requested_env or requested_target
    details = [
        str(lock_error),
        "wait for the active operation or stop the conflicting local runtime",
    ]
    try:
        report_dir = _stackctl.validate_up_report_dir(
            _stackctl.resolve_report_dir(args, env_name, report_target),
            env_name=env_name,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return {
            "exitCode": 2,
            "summary": f"stackctl up is GATE_BLOCK for {report_target}",
            "details": [f"unsafe up report directory: {exc}", *details],
        }
    _stackctl.write_json(
        report_dir / "report.json",
        {
            "command": "up",
            "target": report_target,
            "resolvedTarget": requested_target,
            "workload": str(getattr(args, "workload", "") or ""),
            "status": "gate_block",
            "details": details,
        },
    )
    _stackctl._write_summary_bundle(
        report_dir,
        command="up",
        target=report_target,
        status="gate_block",
        summary=f"stackctl up is blocked for {report_target}",
        details=details,
    )
    return {
        "exitCode": 2,
        "summary": f"stackctl up is GATE_BLOCK for {report_target}",
        "details": details,
        "reportDir": str(report_dir.resolve()),
    }
