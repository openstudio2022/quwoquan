"""stackctl `dev-session bind-content`: test-live 内容绑定的准入与执行。

从 `dev_session_domain` 逐字迁出（改写规则与该模块相同）:
`_dev_session_test_live_content_binding_readiness_issues` /
`_dev_session_content_binding_request` / `_command_dev_session_bind_content`。
绑定「哪份 Data 证据挂在哪个 running attempt 上」自成一条职责，与
dev-session 的目标执行、launcher handoff 分开承载。

测试经 ``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号，
因此函数体内一律经函数内延迟导入 `_stackctl` 属性访问（含本模块符号互调），
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import re

from typing import Any, Mapping


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


def _command_dev_session_bind_content(args: argparse.Namespace) -> dict[str, Any]:
    """Bind exact Data evidence to one running attempt without materialization."""
    import quwoquan_ops.cli.stackctl as _stackctl


    started_monotonic, started_at = _stackctl._start_timing()
    requested_env = str(getattr(args, "env", "") or "").strip()
    target = str(getattr(args, "target", "") or "").strip()
    # 与 start 同一套 env/target 互推：两个子命令作用于同一个 attempt，选择语义
    # 分叉会让「start 能用的参数 bind-content 不能用」。且选择无效时必须在这里
    # 就返回 typed 阻断——报告目录本身要按 target 落盘，拿无效 target 去算路径
    # 会先抛 ValueError，把选择错误伪装成内部故障。
    if bool(requested_env) == bool(target):
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        return {
            "exitCode": 2,
            "summary": "stackctl dev-session bind-content is GATE_BLOCK",
            "details": ["provide exactly one of --env or --target"],
            "blockerKind": "environment_missing",
            **timing,
        }
    if requested_env:
        target = _stackctl.DEV_UP_STACK_TARGETS[requested_env]
    elif target not in {"alpha-local", "beta-local", "gamma-local"}:
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        return {
            "exitCode": 2,
            "summary": "stackctl dev-session bind-content is GATE_BLOCK",
            "details": [
                "--target must select alpha-local, beta-local, or gamma-local"
            ],
            "blockerKind": "invalid_content_binding_selection",
            **timing,
        }
    attempt_id = str(getattr(args, "startup_attempt_id", "") or "").strip()
    release_id = str(getattr(args, "release_id", "") or "").strip()
    verify_run_id = str(getattr(args, "verify_run_id", "") or "").strip()
    manifest_digest = str(getattr(args, "manifest_digest", "") or "").strip()
    readiness_digest = str(getattr(args, "readiness_digest", "") or "").strip()
    lifecycle_exit_ref = str(
        getattr(args, "lifecycle_exit_ref", "") or ""
    ).strip()
    invalid: list[str] = []
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
