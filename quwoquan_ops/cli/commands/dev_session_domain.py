"""stackctl `dev-session` 子命令域主入口: 目标执行、launcher handoff
与 test-live 内容绑定。

从 stackctl.py 逐字迁出（改写规则与 down_domain 相同）:
`_dev_session_test_live_content_binding_readiness_issues` /
`_dev_session_content_binding_request` / `_dev_session_launcher_handoff` /
`_run_dev_session_target` / `_command_dev_session_bind_content` /
`command_dev_session`。

测试经 ``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号，
因此函数体内一律经函数内延迟导入 `_stackctl` 属性访问（含本模块符号互调），
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
import time

from pathlib import Path
from typing import Any

# HEAD 上 stackctl.py 未导入 summarize_output（潜伏 NameError 死分支），
# 迁出时改为显式引用 dev_up 的实现。
from quwoquan_ops.cli.lib.dev_up import summarize_output
from typing import Mapping


def _dev_session_test_live_content_binding_readiness_issues(
    *,
    environment: str,
    startup_receipt: Mapping[str, Any],
    preflight: Mapping[str, Any],
) -> list[str]:
    """Require the live App/API/Provider edge before using a content binding."""

    issues: list[str] = []
    tls = preflight.get("tls")
    if not isinstance(tls, Mapping) or (
        tls.get("profile") != "local-managed" or tls.get("status") != "ready"
    ):
        issues.append("target local-managed TLS is not ready")
    provider = preflight.get("provider")
    expected_provider = {
        "adapterId": "ext.sms.local_capture",
        "environment": environment,
        "configurationDigest": startup_receipt.get("configurationDigest"),
        "nonPromotable": True,
        "ready": True,
    }
    if not isinstance(provider, Mapping) or any(
        provider.get(field) != value for field, value in expected_provider.items()
    ):
        issues.append("target SMS capture Provider is not ready or identity-bound")
    checks = preflight.get("runtimeChecks")
    observed = {
        str(item.get("name") or ""): item.get("ready") is True
        for item in checks
        if isinstance(item, Mapping)
    } if isinstance(checks, list) else {}
    if observed.get("user-service") is not True:
        issues.append("user-service is not ready")
    for name, ready in observed.items():
        if name and not ready:
            issues.append(f"{name} is not ready")
    return list(dict.fromkeys(issues))


def _dev_session_content_binding_request(args: argparse.Namespace) -> dict[str, str]:
    """Return one explicit test-live content identity or fail on partial input."""

    values = {
        "releaseId": str(getattr(args, "release_id", "") or "").strip(),
        "verifyRunId": str(getattr(args, "verify_run_id", "") or "").strip(),
        "manifestDigest": str(getattr(args, "manifest_digest", "") or "").strip(),
        "lifecycleExitRef": str(
            getattr(args, "lifecycle_exit_ref", "") or ""
        ).strip(),
    }
    mandatory = ("releaseId", "verifyRunId", "manifestDigest")
    populated = [field for field in mandatory if values[field]]
    if not populated and not values["lifecycleExitRef"]:
        return {}
    if len(populated) != len(mandatory):
        missing = sorted(field for field in mandatory if not values[field])
        raise ValueError(
            "test-live content identity is partial; missing " + ", ".join(missing)
        )
    if re.fullmatch(r"sha256:[0-9a-f]{64}", values["manifestDigest"]) is None:
        raise ValueError(
            "test-live content manifestDigest must be sha256:<64 lowercase hex>"
        )
    return values


def _dev_session_launcher_handoff(
    *,
    environment: str,
    target: str,
    content_binding: Mapping[str, Any],
) -> dict[str, Any]:
    """Render the App handoff from the exact run-bound content selection."""
    import quwoquan_ops.cli.stackctl as _stackctl


    command = [
        sys.executable,
        str(_stackctl.ROOT / "quwoquan_app/scripts/device/build_launcher_handoff.py"),
        "--env",
        environment,
        "--target",
        target,
        "--launch-mode",
        "canonical_launcher",
        "--launch-policy",
        "test_live",
        "--app-instance-namespace",
        f"{environment}-test-live",
    ]
    if content_binding:
        command.extend(
            (
                "--content-release-id",
                str(content_binding.get("releaseId") or ""),
                "--content-manifest-digest",
                str(content_binding.get("manifestDigest") or ""),
                "--content-readiness-receipt-digest",
                str(content_binding.get("readinessReceiptDigest") or ""),
            )
        )
    try:
        result = subprocess.run(
            command,
            cwd=_stackctl.ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"test_live launcher handoff failed: {exc}") from exc
    if result.returncode != 0:
        raise ValueError(
            result.stderr.strip()
            or result.stdout.strip()
            or "test_live launcher handoff failed"
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"test_live launcher handoff is not JSON: {exc}") from exc
    expected_state = "bound" if content_binding else "unbound"
    expected_content = {
        "contentReleaseId": str(content_binding.get("releaseId") or ""),
        "contentManifestDigest": str(content_binding.get("manifestDigest") or ""),
        "contentReadinessReceiptDigest": str(
            content_binding.get("readinessReceiptDigest") or ""
        ),
    }
    if (
        not isinstance(payload, dict)
        or payload.get("launchPolicy") != "test_live"
        or payload.get("contentBindingState") != expected_state
        or (
            bool(content_binding)
            and any(
                payload.get(field) != value
                for field, value in expected_content.items()
            )
        )
    ):
        raise ValueError("test_live launcher handoff policy/content binding mismatch")
    return dict(payload)


def _run_dev_session_target(
    *,
    environment: str,
    target: str,
    device_id: str,
    launch_app_requested: bool,
    report_dir: Path,
    content_binding_request: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Render one mutable non-production session without immutable packaging."""
    import quwoquan_ops.cli.stackctl as _stackctl


    phases: list[dict[str, Any]] = []
    warnings: list[str] = []
    mutable_workspace_warnings: list[str] = []
    beginning_snapshot: dict[str, Any] = {}
    ending_snapshot: dict[str, Any] = {}
    try:
        active_attempt, conflict = _stackctl._dev_session_runtime_preflight(
            topology=_stackctl.load_environment_topology(),
            target=target,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        active_attempt = None
        conflict = None
        warnings.append(f"stale runtime receipt ignored for test_live: {exc}")
    if conflict is not None:
        return _stackctl._dev_session_workload_conflict(conflict)

    try:
        beginning_snapshot = _stackctl._mutable_workspace_snapshot()
    except (OSError, RuntimeError, ValueError) as exc:
        warning = f"mutable workspace start digest unavailable: {exc}"
        warnings.append(warning)
        mutable_workspace_warnings.append(warning)

    report_dir.mkdir(parents=True, exist_ok=True)
    runtime_payload: dict[str, Any] | None = None
    preflight_payload: dict[str, Any] | None = None
    runtime_was_started = False
    resume_requested = not launch_app_requested and bool(content_binding_request)
    if resume_requested:
        try:
            resume_candidate, resume_warnings = (
                _stackctl._dev_session_resume_running_mutable_runtime(
                    environment=environment,
                    target=target,
                    workspace_snapshot=beginning_snapshot,
                    required_running_services=(
                        _stackctl._TEST_LIVE_CONTENT_BINDING_REQUIRED_SERVICES
                        if content_binding_request
                        else frozenset()
                    ),
                )
            )
            warnings.extend(resume_warnings)
            mutable_workspace_warnings.extend(resume_warnings)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            resume_candidate = None
            warnings.append(
                "running mutable session cannot be reused; refreshing it: "
                + str(exc)
            )
        if resume_candidate is not None:
            runtime_payload = resume_candidate
    if runtime_payload is None:
        runtime_was_started = True
        runtime_payload = _stackctl._start_mutable_test_live_runtime(
            environment=environment,
            target=target,
            report_dir=report_dir,
            workspace_snapshot=beginning_snapshot,
        )
    phases.extend(list(runtime_payload.get("phases") or []))
    if int(runtime_payload.get("exitCode", 2)) != 0:
        return {
            "exitCode": int(runtime_payload.get("exitCode", 2)),
            "sessionKind": "mutable",
            "blockerKind": str(
                runtime_payload.get("blockerKind")
                or "mutable_runtime_start_failed"
            ),
            "details": list(runtime_payload.get("details") or []),
            "fullRuntimeSelected": False,
            "runtimeMayBeRunning": bool(
                runtime_payload.get("runtimeMayBeRunning", False)
            ),
            "startupAttempt": dict(
                runtime_payload.get("startupAttempt") or {}
            ),
            "phases": phases,
        }

    content_binding: dict[str, Any] = {}
    if content_binding_request:
        startup_attempt = dict(runtime_payload.get("startupAttempt") or {})
        if runtime_was_started:
            try:
                validated_runtime, validation_warnings = (
                    _stackctl._dev_session_resume_running_mutable_runtime(
                        environment=environment,
                        target=target,
                        workspace_snapshot=beginning_snapshot,
                        required_running_services=(
                            _stackctl._TEST_LIVE_CONTENT_BINDING_REQUIRED_SERVICES
                        ),
                    )
                )
                validated_attempt = dict(
                    (validated_runtime or {}).get("startupAttempt") or {}
                )
                if (
                    validated_runtime is None
                    or validated_attempt.get("attemptId")
                    != startup_attempt.get("attemptId")
                ):
                    raise ValueError(
                        "new mutable runtime identity changed before content binding"
                    )
                warnings.extend(validation_warnings)
                mutable_workspace_warnings.extend(validation_warnings)
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                return {
                    "exitCode": 1,
                    "sessionKind": "mutable",
                    "blockerKind": "test_live_content_runtime_unready",
                    "details": [str(exc)],
                    "fullRuntimeSelected": True,
                    "startupAttempt": startup_attempt,
                    "phases": phases,
                }
        try:
            content_binding = _stackctl.create_test_live_content_binding(
                environment=environment,
                target=target,
                startup_attempt_id=str(startup_attempt.get("attemptId") or ""),
                release_id=str(content_binding_request.get("releaseId") or ""),
                verify_run_id=str(content_binding_request.get("verifyRunId") or ""),
                manifest_digest=str(
                    content_binding_request.get("manifestDigest") or ""
                ),
                lifecycle_exit_ref=str(
                    content_binding_request.get("lifecycleExitRef") or ""
                ),
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            return {
                "exitCode": 2,
                "sessionKind": "mutable",
                "blockerKind": "test_live_content_binding_invalid",
                "details": [str(exc)],
                "fullRuntimeSelected": True,
                "startupAttempt": startup_attempt,
                "phases": phases,
            }
        phases.append(
            {
                "name": "test-live-content-binding",
                "exitCode": 0,
                "summary": "running mutable attempt bound to explicit Data evidence",
                "details": [
                    f"releaseId={content_binding['releaseId']}",
                    f"verifyRunId={content_binding['verifyRunId']}",
                    f"readinessPhase={content_binding['readinessPhase']}",
                ],
                "reportDir": _stackctl.relpath(report_dir),
            }
        )

    if preflight_payload is None:
        preflight_payload = _stackctl.command_app_debug_preflight(
            _stackctl._dev_session_child_args(
                "app-debug-preflight",
                report_dir=report_dir / "preflight",
                argv=["--target", target, "--runtime-mode", "test_live"],
            )
        )
    phases.append(_stackctl._dev_session_phase("preflight", preflight_payload))
    if int(preflight_payload.get("exitCode", 1)) != 0:
        return {
            "exitCode": int(preflight_payload.get("exitCode", 2)),
            "sessionKind": "mutable",
            "blockerKind": "test_live_safety_failed",
            "details": list(preflight_payload.get("details") or []),
            "fullRuntimeSelected": False,
            "phases": phases,
        }
    if content_binding:
        content_preflight_issues = (
            _stackctl._dev_session_test_live_content_binding_readiness_issues(
                environment=environment,
                startup_receipt=dict(
                    runtime_payload.get("startupAttempt") or {}
                ),
                preflight=preflight_payload,
            )
        )
        if content_preflight_issues:
            return {
                "exitCode": 1,
                "sessionKind": "mutable",
                "blockerKind": "test_live_content_runtime_unready",
                "details": content_preflight_issues,
                "fullRuntimeSelected": True,
                "startupAttempt": dict(
                    runtime_payload.get("startupAttempt") or {}
                ),
                "contentBinding": content_binding,
                "phases": phases,
            }
    warnings.extend(str(item) for item in preflight_payload.get("warnings") or [])
    mutable_workspace_warnings.extend(
        str(item) for item in preflight_payload.get("mutableWorkspaceWarnings") or []
    )

    try:
        handoff_payload = _stackctl._dev_session_launcher_handoff(
            environment=environment,
            target=target,
            content_binding=content_binding,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return {
            "exitCode": 2,
            "sessionKind": "mutable",
            "blockerKind": "launcher_handoff_invalid",
            "details": [str(exc)],
            "fullRuntimeSelected": True,
            "startupAttempt": dict(runtime_payload.get("startupAttempt") or {}),
            "contentBinding": content_binding,
            "phases": phases,
        }
    handoff_path = report_dir / "test-live-launcher-handoff.json"
    _stackctl.write_json(handoff_path, handoff_payload)
    phases.append(
        {
            "name": "launcher-handoff",
            "exitCode": 0,
            "summary": "current workspace test_live handoff rendered",
            "details": [f"handoff={_stackctl.relpath(handoff_path)}"],
            "reportDir": _stackctl.relpath(report_dir),
        }
    )

    health_payload = _stackctl.command_health(
        _stackctl._dev_session_child_args(
            "health",
            report_dir=report_dir / "health",
            argv=["--target", target, "--scope", "full"],
        )
    )
    phases.append(_stackctl._dev_session_phase("health", health_payload))
    if int(health_payload.get("exitCode", 1)) != 0:
        warnings.extend(
            "runtime health warning: " + str(item)
            for item in list(
                health_payload.get("details") or [health_payload.get("summary")]
            )
            if item
        )

    if launch_app_requested:
        selected_device = device_id or _stackctl.resolve_device_id(
            include_mobile=True,
            include_web=False,
            include_desktop=False,
            label="[stackctl dev-session]",
        )
        launch_log = report_dir / f"app-launch-{selected_device.replace('/', '_')}.log"
        launch_log.parent.mkdir(parents=True, exist_ok=True)
        with launch_log.open("a", encoding="utf-8") as log_handle:
            process = subprocess.Popen(
                ["bash", "run.sh", "--env", environment, "-d", selected_device],
                cwd=_stackctl.ROOT / "quwoquan_app",
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
        time.sleep(1.5)
        if process.poll() is not None:
            return {
                "exitCode": 1,
                "sessionKind": "mutable",
                "blockerKind": "app_launch_failed",
                "details": [summarize_output(launch_log.read_text(encoding="utf-8"))],
                "fullRuntimeSelected": False,
                "phases": phases,
            }
        phases.append(
            {
                "name": "app-launch",
                "exitCode": 0,
                "summary": f"test_live App launch started with pid={process.pid}",
                "details": [f"device={selected_device}"],
                "reportDir": _stackctl.relpath(report_dir),
            }
        )

    try:
        ending_snapshot = _stackctl._mutable_workspace_snapshot()
    except (OSError, RuntimeError, ValueError) as exc:
        warning = f"mutable workspace end digest unavailable: {exc}"
        warnings.append(warning)
        mutable_workspace_warnings.append(warning)
    if beginning_snapshot and ending_snapshot:
        changed = [
            field
            for field in (
                "sourceRevision",
                "workspaceStatusDigest",
                "mutableStateDigest",
            )
            if beginning_snapshot.get(field) != ending_snapshot.get(field)
        ]
        if changed:
            warning = "mutable workspace changed during dev-session: " + ", ".join(changed)
            warnings.append(warning)
            mutable_workspace_warnings.append(warning)

    handoff = ["./run.sh", "--env", environment]
    if device_id:
        handoff.extend(("-d", device_id))
    return {
        "exitCode": 0,
        "status": "warning" if warnings else "passed",
        "launchPolicy": "test_live",
        "contentBindingState": "bound" if content_binding else "unbound",
        "sessionKind": "mutable",
        "blockerKind": "",
        "details": [
            "App handoff: cd quwoquan_app && "
            + " ".join(shlex.quote(item) for item in handoff)
        ],
        "warnings": sorted(set(warnings)),
        "mutableWorkspaceWarnings": sorted(set(mutable_workspace_warnings)),
        "workspaceStart": beginning_snapshot,
        "workspaceEnd": ending_snapshot,
        "fullRuntimeSelected": bool(
            runtime_payload.get("runtime")
        ),
        "runtime": dict(runtime_payload.get("runtime") or {}),
        "startupAttempt": dict(
            runtime_payload.get("startupAttempt") or {}
        ),
        "contentBinding": content_binding,
        "launcherHandoff": handoff_payload,
        "phases": phases,
    }


def _command_dev_session_bind_content(args: argparse.Namespace) -> dict[str, Any]:
    """Bind exact Data evidence to one running attempt without materialization."""
    import quwoquan_ops.cli.stackctl as _stackctl


    started_monotonic, started_at = _stackctl._start_timing()
    target = str(getattr(args, "target", "") or "").strip()
    attempt_id = str(getattr(args, "startup_attempt_id", "") or "").strip()
    release_id = str(getattr(args, "release_id", "") or "").strip()
    verify_run_id = str(getattr(args, "verify_run_id", "") or "").strip()
    manifest_digest = str(getattr(args, "manifest_digest", "") or "").strip()
    readiness_digest = str(getattr(args, "readiness_digest", "") or "").strip()
    lifecycle_exit_ref = str(
        getattr(args, "lifecycle_exit_ref", "") or ""
    ).strip()
    invalid: list[str] = []
    if target not in {"alpha-local", "beta-local", "gamma-local"}:
        invalid.append("--target must select alpha-local, beta-local, or gamma-local")
    for option, value in (
        ("--startup-attempt-id", attempt_id),
        ("--release-id", release_id),
        ("--verify-run-id", verify_run_id),
        ("--manifest-digest", manifest_digest),
        ("--readiness-digest", readiness_digest),
    ):
        if not value:
            invalid.append(f"{option} is required")
    for option, value in (
        ("--manifest-digest", manifest_digest),
        ("--readiness-digest", readiness_digest),
    ):
        if value and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
            invalid.append(f"{option} must be sha256:<64 lowercase hex>")
    environment = target.removesuffix("-local")
    report_dir = _stackctl.resolve_report_dir(args, environment, target)
    if invalid:
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        result = {
            "exitCode": 2,
            "summary": "stackctl dev-session bind-content is GATE_BLOCK",
            "details": invalid,
            "blockerKind": "invalid_content_binding_selection",
            **timing,
        }
        report_dir.mkdir(parents=True, exist_ok=True)
        _stackctl.write_json(report_dir / "report.json", result)
        return {**result, "reportDir": _stackctl.relpath(report_dir)}

    try:
        with _stackctl._local_stack_operation_lock(target):
            workspace = _stackctl._mutable_workspace_snapshot()
            before_runtime, before_warnings = (
                _stackctl._dev_session_resume_running_mutable_runtime(
                    environment=environment,
                    target=target,
                    workspace_snapshot=workspace,
                    required_running_services=(
                        _stackctl._TEST_LIVE_CONTENT_BINDING_REQUIRED_SERVICES
                    ),
                )
            )
            before_attempt = dict(
                (before_runtime or {}).get("startupAttempt") or {}
            )
            if before_runtime is None or before_attempt.get("attemptId") != attempt_id:
                raise ValueError(
                    "bind-content requires the exact current running startup attempt"
                )
            binding = _stackctl.create_test_live_content_binding(
                environment=environment,
                target=target,
                startup_attempt_id=attempt_id,
                release_id=release_id,
                verify_run_id=verify_run_id,
                manifest_digest=manifest_digest,
                expected_readiness_receipt_digest=readiness_digest,
                lifecycle_exit_ref=lifecycle_exit_ref,
            )
            after_runtime, after_warnings = (
                _stackctl._dev_session_resume_running_mutable_runtime(
                    environment=environment,
                    target=target,
                    workspace_snapshot=workspace,
                    required_running_services=(
                        _stackctl._TEST_LIVE_CONTENT_BINDING_REQUIRED_SERVICES
                    ),
                )
            )
            after_attempt = dict((after_runtime or {}).get("startupAttempt") or {})
            if (
                after_runtime is None
                or after_attempt.get("attemptId") != attempt_id
                or after_attempt != before_attempt
            ):
                raise ValueError(
                    "running mutable runtime identity changed during content binding"
                )
            handoff = _stackctl._dev_session_launcher_handoff(
                environment=environment,
                target=target,
                content_binding=binding,
            )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        result = {
            "exitCode": 2,
            "summary": "stackctl dev-session bind-content is GATE_BLOCK",
            "details": [str(exc)],
            "blockerKind": "test_live_content_binding_invalid",
            **timing,
        }
        report_dir.mkdir(parents=True, exist_ok=True)
        _stackctl.write_json(report_dir / "report.json", result)
        return {**result, "reportDir": _stackctl.relpath(report_dir)}

    report_dir.mkdir(parents=True, exist_ok=True)
    _stackctl.write_json(report_dir / "test-live-launcher-handoff.json", handoff)
    timing = _stackctl._finish_timing(started_monotonic, started_at)
    warnings = sorted(set([*before_warnings, *after_warnings]))
    report = {
        "command": "dev-session bind-content",
        "target": target,
        "status": "warning" if warnings else "passed",
        "startupAttempt": after_attempt,
        "contentBinding": binding,
        "launcherHandoff": handoff,
        "warnings": warnings,
        "details": [
            f"attemptId={attempt_id}",
            f"releaseId={binding['releaseId']}",
            f"verifyRunId={binding['verifyRunId']}",
            f"readinessReceiptDigest={binding['readinessReceiptDigest']}",
        ],
        "blockerKind": "",
        **timing,
    }
    _stackctl.write_json(report_dir / "report.json", report)
    return {
        "exitCode": 0,
        "summary": f"stackctl dev-session bind-content completed for {target}",
        "reportDir": _stackctl.relpath(report_dir),
        **report,
    }


def command_dev_session(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    if str(getattr(args, "dev_session_action", "start") or "start") == "bind-content":
        return _stackctl._command_dev_session_bind_content(args)
    started_monotonic, started_at = _stackctl._start_timing()
    topology = _stackctl.load_environment_topology()
    all_nonprod = bool(getattr(args, "all_nonprod", False))
    requested_env = str(getattr(args, "env", "") or "").strip()
    requested_target = str(getattr(args, "target", "") or "").strip()
    try:
        content_binding_request = _stackctl._dev_session_content_binding_request(args)
    except ValueError as exc:
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        return {
            "exitCode": 2,
            "summary": "stackctl dev-session is GATE_BLOCK",
            "details": [str(exc)],
            "blockerKind": "invalid_content_binding_selection",
            **timing,
        }
    if all_nonprod:
        if (
            requested_env
            or requested_target
            or bool(getattr(args, "launch_app", False))
            or content_binding_request
        ):
            timing = _stackctl._finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": "stackctl dev-session is GATE_BLOCK",
                "details": [
                    "--all-nonprod cannot be combined with --env, --target, "
                    "--launch-app or content binding arguments"
                ],
                "blockerKind": "invalid_session_selection",
                **timing,
            }
        selections = [
            (environment, _stackctl.DEV_UP_STACK_TARGETS[environment])
            for environment in ("alpha", "beta", "gamma")
        ]
        report_env = "repo"
        report_target = "all-nonprod"
    else:
        if bool(requested_env) == bool(requested_target):
            timing = _stackctl._finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": "stackctl dev-session is GATE_BLOCK",
                "details": ["provide exactly one of --env, --target or use --all-nonprod"],
                "blockerKind": "environment_missing",
                **timing,
            }
        if requested_env:
            requested_target = _stackctl.DEV_UP_STACK_TARGETS[requested_env]
        else:
            requested_env = str(_stackctl.get_target(topology, requested_target)["env"])
        selections = [(requested_env, requested_target)]
        report_env = requested_env
        report_target = requested_target

    report_dir = _stackctl.resolve_report_dir(args, report_env, report_target)
    sessions: list[dict[str, Any]] = []
    terminal_exit = 0
    blocker_kind = ""
    details: list[str] = []

    if terminal_exit == 0:
        try:
            with _stackctl._local_stack_operation_lock(selections[0][1]):
                for environment, target in selections:
                    session = _stackctl._run_dev_session_target(
                        environment=environment,
                        target=target,
                        device_id=str(getattr(args, "device_id", "") or ""),
                        launch_app_requested=bool(getattr(args, "launch_app", False)),
                        report_dir=report_dir / target,
                        content_binding_request=content_binding_request,
                    )
                    sessions.append(
                        {
                            "environment": environment,
                            "target": target,
                            **session,
                        }
                    )
                    terminal_exit = int(session["exitCode"])
                    if terminal_exit != 0:
                        blocker_kind = str(
                            session.get("blockerKind") or "session_failed"
                        )
                        details = list(session.get("details") or [])
                    if terminal_exit != 0:
                        break
        except (OSError, RuntimeError, ValueError) as exc:
            terminal_exit = 2
            blocker_kind = "runtime_operation_conflict"
            details = [str(exc)]

    timing = _stackctl._finish_timing(started_monotonic, started_at)
    has_warnings = any(session.get("warnings") for session in sessions)
    status = (
        "warning"
        if terminal_exit == 0 and has_warnings
        else "passed"
        if terminal_exit == 0
        else "gate_block"
        if terminal_exit == 2
        else "failed"
    )
    summary = (
        f"stackctl dev-session completed for {report_target}"
        if terminal_exit == 0
        else f"stackctl dev-session is {status.upper()} for {report_target}"
    )
    if terminal_exit == 0 and not details:
        details = [
            item
            for session in sessions
            for item in list(session.get("details") or [])
        ]
    report = {
        "command": "dev-session",
        "target": report_target,
        "status": status,
        "allNonprod": all_nonprod,
        "blockerKind": blocker_kind,
        "sessions": sessions,
        "details": details,
        **timing,
    }
    _stackctl.write_json(report_dir / "report.json", report)
    _stackctl._write_summary_bundle(
        report_dir,
        command="dev-session",
        target=report_target,
        status=status,
        summary=summary,
        details=details,
        extra={
            "allNonprod": all_nonprod,
            "blockerKind": blocker_kind,
            "sessions": sessions,
        },
        timing=timing,
    )
    return {
        "exitCode": terminal_exit,
        "summary": summary,
        "details": details,
        "reportDir": _stackctl.relpath(report_dir),
        "blockerKind": blocker_kind,
        "sessions": sessions,
        **timing,
    }


def register_parser(subparsers: "argparse._SubParsersAction") -> None:
    """向 stackctl build_parser 注册本域子命令（从 build_parser 逐字迁出）。"""
    dev_session_parser = subparsers.add_parser(
        "dev-session",
        help="实时编排可变非生产 handoff、健康诊断与可选 App 启动。",
    )
    dev_session_parser.add_argument(
        "dev_session_action",
        nargs="?",
        choices=("start", "bind-content"),
        default="start",
    )
    dev_session_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    dev_session_parser.add_argument(
        "--env",
        choices=("alpha", "beta", "gamma"),
        default="",
    )
    dev_session_parser.add_argument(
        "--target",
        choices=("alpha-local", "beta-local", "gamma-local"),
        default="",
    )
    dev_session_parser.add_argument("--all-nonprod", action="store_true")
    dev_session_parser.add_argument("--device-id", default="")
    dev_session_parser.add_argument("--launch-app", action="store_true")
    dev_session_parser.add_argument("--startup-attempt-id", default="")
    dev_session_parser.add_argument(
        "--release-id",
        default="",
        help="显式绑定当前test-live target的canonical Data releaseId；禁止latest。",
    )
    dev_session_parser.add_argument(
        "--verify-run-id",
        default="",
        help="显式绑定当前test-live target的Data verifyRunId；禁止latest。",
    )
    dev_session_parser.add_argument(
        "--manifest-digest",
        default="",
        help="显式绑定Data immutable payload digest（sha256:...）。",
    )
    dev_session_parser.add_argument(
        "--readiness-digest",
        default="",
        help="bind-content 必需的 exact release-readiness.json sha256。",
    )
    dev_session_parser.add_argument(
        "--lifecycle-exit-ref",
        default="",
        help="commercial readiness必需；consumer readiness可省略。",
    )

