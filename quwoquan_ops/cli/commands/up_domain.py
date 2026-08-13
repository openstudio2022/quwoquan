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
from pathlib import Path
from typing import Any, Mapping

from quwoquan_ops.cli.commands.up_runtime import _command_up_impl as _command_up_impl


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
            "reportDir": _stackctl.relpath(report_dir),
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
            "reportDir": _stackctl.relpath(report_dir),
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
        "reportDir": _stackctl.relpath(report_dir),
        "sessionKind": "hot",
        "runtimeReused": True,
        **timing,
    }


def command_up(args: argparse.Namespace) -> dict[str, Any]:
    """Hold the target operation lock for every return and exception path."""
    import quwoquan_ops.cli.stackctl as _stackctl

    requested_target = str(getattr(args, "target", "") or "").strip()
    requested_env = str(getattr(args, "env", "") or "").strip()
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
    report_dir = _stackctl.resolve_report_dir(args, env_name, report_target)
    details = [
        str(lock_error),
        "wait for the active operation or stop the conflicting local runtime",
    ]
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
        "reportDir": _stackctl.relpath(report_dir),
    }
