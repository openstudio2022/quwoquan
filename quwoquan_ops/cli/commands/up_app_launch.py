"""stackctl `up` 域 prod-sim / prod-hosted App 启动实现。

从 commands/up_domain.py 逐字迁出仅被 up 编排主干消费的 App 启动家族:

- `tail_beta_background_logs` / `tail_alpha_background_logs` /
  `tail_prod_sim_background_logs`:startup 阶段的后台 runtime 日志跟随;
- `_launch_prod_sim_stack`:prod-sim 栈启动、后台日志跟随与 App 启动
  steady-state 判定;
- `_launch_prod_hosted_session`:prod-hosted edge health 门与 App 启动
  会话;early-return payload 作为首元素返回,由调用方原样 return。

`_command_up_impl` 编排主干在 `commands/up_runtime.py`;`register_parser` /
`command_up` 在 `commands/up_domain.py`。`run_stage` / `announce` /
`maybe_resolve_device_id` / `start_app_process` 等 `_command_up_impl`
局部闭包经参数注入,不在本模块重建。测试经
``mock.patch.object(stackctl, ...)`` patch 协作符号,因此函数体内一律经
函数内延迟导入 `_stackctl` 属性访问(本模块符号互调经 `_up_app_launch`),
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path
from typing import Any, Callable


def tail_beta_background_logs() -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    beta_log_dir = _stackctl._local_runtime_log_root("beta-local")
    return _stackctl._tail_multiple_logs_for_startup(
        [
            ("beta-app", beta_log_dir / "app-beta" / "local" / "runtime.log"),
            ("beta-product-ops", beta_log_dir / "product-ops" / "local" / "runtime.log"),
            ("beta-platform-ops", beta_log_dir / "platform-ops" / "local" / "runtime.log"),
            ("beta-ops-portal", beta_log_dir / "ops-portal" / "local" / "runtime.log"),
        ],
        idle_timeout_seconds=4.0,
        max_follow_seconds=35.0,
    )


def tail_alpha_background_logs() -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    alpha_log_dir = _stackctl._local_runtime_log_root("alpha-local")
    return _stackctl._tail_multiple_logs_for_startup(
        [
            ("alpha-content", alpha_log_dir / "content-service" / "local" / "runtime.log"),
            ("alpha-user", alpha_log_dir / "user-service" / "local" / "runtime.log"),
            ("alpha-entity", alpha_log_dir / "entity-service" / "local" / "runtime.log"),
            ("alpha-media", alpha_log_dir / "media-origin" / "local" / "runtime.log"),
        ],
        idle_timeout_seconds=4.0,
        max_follow_seconds=20.0,
    )


def tail_prod_sim_background_logs() -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    prod_sim_log_dir = _stackctl._local_runtime_log_root("prod-sim")
    return _stackctl._tail_multiple_logs_for_startup(
        [
            ("prod-sim-api-edge", prod_sim_log_dir / "api-edge" / "local" / "runtime.log"),
            ("prod-sim-product-ops", prod_sim_log_dir / "product-ops" / "local" / "runtime.log"),
            ("prod-sim-media-edge", prod_sim_log_dir / "media-edge" / "local" / "runtime.log"),
            ("prod-sim-media-origin", prod_sim_log_dir / "media-origin" / "local" / "runtime.log"),
        ],
        idle_timeout_seconds=4.0,
        max_follow_seconds=20.0,
    )


def _launch_prod_sim_stack(
    args: argparse.Namespace,
    *,
    steps: list[dict[str, Any]],
    run_stage: Callable[..., subprocess.CompletedProcess[str]],
    announce: Callable[..., None],
    maybe_resolve_device_id: Callable[..., str],
    start_app_process: Callable[..., dict[str, Any]],
    candidate_snapshot: dict[str, Any] | None,
    assert_fixed_candidate_selected: Callable[[], None],
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    import quwoquan_ops.cli.stackctl as _stackctl
    from quwoquan_ops.cli.commands import up_app_launch as _up_app_launch

    cmd = ["bash", "quwoquan_ops/cli/prod_sim/start_prod_sim_stack.sh", "up"]
    if candidate_snapshot is None:
        return (
            subprocess.CompletedProcess(
                cmd,
                2,
                stdout="",
                stderr="GATE_BLOCK: fixed prod-sim candidate snapshot is missing",
            ),
            cmd,
        )
    manifest = candidate_snapshot.get("manifest")
    candidate_root = Path(str(candidate_snapshot.get("candidateDir") or ""))
    if not isinstance(manifest, dict) or not candidate_root.is_absolute():
        return (
            subprocess.CompletedProcess(
                cmd,
                2,
                stdout="",
                stderr="GATE_BLOCK: fixed prod-sim candidate snapshot is invalid",
            ),
            cmd,
        )
    try:
        assert_fixed_candidate_selected()
        launch_bundle = _stackctl.prod_sim_app_launch_bundle_from_candidate(
            manifest,
            candidate_root=candidate_root,
        )
    except (OSError, TypeError, ValueError) as exc:
        return (
            subprocess.CompletedProcess(
                cmd,
                2,
                stdout="",
                stderr=f"GATE_BLOCK: prod-sim candidate App launch bundle invalid: {exc}",
            ),
            cmd,
        )
    readiness_value = str(
        getattr(args, "data_release_readiness", "")
        or os.environ.get("DATA_RELEASE_READINESS_RECEIPT", "")
    ).strip()
    result = run_stage(
        "prod-sim",
        cmd,
        env={"DATA_RELEASE_READINESS_RECEIPT": readiness_value},
        live_prefix="[prod-sim] ",
    )
    if result.returncode == 0:
        try:
            background_tail = _up_app_launch.tail_prod_sim_background_logs()
        except RuntimeError as exc:
            steps.append(
                {
                    "kind": "prod-sim-background-tail",
                    "exitCode": 1,
                    "stdout": "",
                    "stderr": str(exc),
                }
            )
            result = subprocess.CompletedProcess(
                cmd, 1, stdout=result.stdout, stderr=str(exc)
            )
        else:
            steps.append(
                {
                    "kind": "prod-sim-background-tail",
                    "exitCode": 0,
                    "stdout": "tailed prod-sim background logs",
                    "stderr": "",
                    "tail": background_tail,
                }
            )
    if result.returncode == 0 and not args.skip_app:
        args.device_id = maybe_resolve_device_id(include_web=True)
        try:
            assert_fixed_candidate_selected()
            app_launch = start_app_process(
                "prod-sim",
                args.device_id,
                launch_bundle=launch_bundle,
            )
        except RuntimeError as exc:
            result = subprocess.CompletedProcess(cmd, 1, stdout="", stderr=str(exc))
            app_launch = None
        if app_launch is not None:
            try:
                assert_fixed_candidate_selected()
            except (OSError, TypeError, ValueError) as exc:
                result = subprocess.CompletedProcess(
                    app_launch["command"],
                    2,
                    stdout="",
                    stderr=f"active candidate changed during App launch: {exc}",
                )
            else:
                announce("prod-sim", "candidate-bound App launch receipt is ready")
                cmd = app_launch["command"]
                result = subprocess.CompletedProcess(
                    cmd,
                    0,
                    stdout=f"pid={app_launch['process'].pid}",
                    stderr=f"log={_stackctl.relpath(app_launch['log_path'])}",
                )
            steps.append(
                {
                    "argv": app_launch["command"],
                    "exitCode": result.returncode,
                    "stdout": f"pid={app_launch['process'].pid}",
                    "stderr": f"log={_stackctl.relpath(app_launch['log_path'])}",
                    "tail": {"requireReady": False, "source": "diagnostic-only"},
                }
            )
    return result, cmd


def _launch_prod_hosted_session(
    args: argparse.Namespace,
    *,
    cmd: list[str],
    report_dir: Path,
    started_monotonic: float,
    started_at: str,
    steps: list[dict[str, Any]],
    announce: Callable[..., None],
    maybe_resolve_device_id: Callable[..., str],
    start_app_process: Callable[[str, str], dict[str, Any]],
) -> tuple[dict[str, Any] | None, subprocess.CompletedProcess[str] | None, list[str]]:
    import quwoquan_ops.cli.stackctl as _stackctl

    announce("prod-hosted", "running edge health check")
    health_args = argparse.Namespace(
        command="health",
        target="prod-hosted",
        scope="edge",
        output_format="json",
        report_dir=str(report_dir / "health"),
    )
    health = _stackctl.command_health(health_args)
    steps.append(
        {
            "argv": ["python3", "quwoquan_ops/cli/stackctl.py", "health", "--target", "prod-hosted", "--scope", "edge"],
            "exitCode": int(health.get("exitCode", 1)),
            "stdout": health.get("summary", ""),
            "stderr": "\n".join(health.get("details", [])),
        }
    )
    if int(health.get("exitCode", 1)) != 0:
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        return (
            {
                "exitCode": 1,
                "summary": "stackctl up failed for prod-hosted",
                "details": ["prod-hosted health failed; run `stackctl deploy --target prod-hosted ...` first", *health.get("details", [])],
                "reportDir": _stackctl.relpath(report_dir),
                **timing,
            },
            None,
            cmd,
        )
    if args.skip_app:
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        return (
            {
                "exitCode": 0,
                "summary": "stackctl up completed for prod",
                "details": ["prod-hosted edge health passed; app launch skipped"],
                "reportDir": _stackctl.relpath(report_dir),
                **timing,
            },
            None,
            cmd,
        )
    args.device_id = maybe_resolve_device_id(include_web=True)
    try:
        app_launch = start_app_process("prod", args.device_id)
    except RuntimeError as exc:
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        return (
            {
                "exitCode": 1,
                "summary": "stackctl up failed for prod-hosted",
                "details": [str(exc)],
                "reportDir": _stackctl.relpath(report_dir),
                **timing,
            },
            None,
            cmd,
        )
    tail_result = _stackctl._tail_file_for_startup(
        app_launch["log_path"],
        process=app_launch["process"],
        prefix=f"[{app_launch['stageHeader']} app] ",
        idle_timeout_seconds=6.0,
        max_follow_seconds=60.0,
        ready_patterns=(
            "Syncing files to device",
            "Flutter run key commands",
            "A Dart VM Service",
            "The Flutter DevTools debugger",
        ),
        failure_patterns=(
            "Failed to build",
            "Error launching application on",
            "Lost connection to device.",
            "Target kernel_snapshot_program failed",
            "app launch exited before reaching steady state",
        ),
        ready_idle_timeout_seconds=3.0,
    )
    app_exit_code = app_launch["process"].poll()
    failure_detail = _stackctl._app_launch_failure_detail(
        tail_result,
        default_message="prod app launch failed",
        process_exit_code=app_exit_code,
    )
    app_failed = failure_detail is not None
    if not app_failed:
        announce("prod-hosted", "app launch reached steady state")
        cmd = app_launch["command"]
        result = subprocess.CompletedProcess(
            cmd,
            0,
            stdout=f"pid={app_launch['process'].pid}",
            stderr=f"log={_stackctl.relpath(app_launch['log_path'])}",
        )
    else:
        result = subprocess.CompletedProcess(
            app_launch["command"],
            1,
            stdout="",
            stderr=str(failure_detail),
        )
    steps.append(
        {
            "argv": app_launch["command"],
            "exitCode": app_exit_code or 0,
            "stdout": f"pid={app_launch['process'].pid}",
            "stderr": f"log={_stackctl.relpath(app_launch['log_path'])}",
            "tail": tail_result,
        }
    )
    return None, result, cmd
