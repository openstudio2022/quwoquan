"""stackctl app 预检子命令域(app-content-preflight / app-debug-preflight /
app-domain-api-integration)。

从 stackctl.py 逐字迁出;本模块保留三个子命令的 argparse 表面与命令主干:

- `register_parser`:三个子命令的 argparse 表面(在 build_parser 中相邻,
  帮助文案与参数集合逐字节保持不变);
- `command_app_content_preflight`:本地 Flutter 安装前 active candidate、
  商业内容回执与 live readback 验证;
- `command_app_domain_api_integration`:ContractGraph 派生的五域 generated
  typed Remote API integration 执行。

candidate/test-live 内容证据解析与 release probe 家族
(`_resolve_active_app_content_evidence` /
`_resolve_test_live_app_content_evidence` / `_app_content_uat_envelope` /
`_app_content_readback_summary` / `_run_app_content_release_probe`)在
`commands/app_preflight_evidence.py`;`command_app_debug_preflight` 与
`_execute_otp_login_journey` 在 `commands/app_preflight_debug.py`;本模块
以薄 re-export 保持对 stackctl 的符号面零漂移。

data readiness 真相源家族在 `commands/app_preflight_shared.py` 与
`commands/app_preflight_readiness.py`;`app-content-uat` 编排与 UAT dart
目标常量在 `commands/app_preflight_uat.py`;
`_run_environment_integration_probe` / `_read_json_object` /
`_resolve_test_auth_token` 等协作符号仍由 stackctl 命名空间拥有。测试经
``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号,因此
函数体内一律经函数内延迟导入 `_stackctl` 属性访问(含本模块符号互调),
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from quwoquan_ops.cli.lib.content_release_readiness import ReadinessPhase

from quwoquan_ops.cli.commands.app_preflight_debug import (
    _execute_otp_login_journey,
    command_app_debug_preflight,
)
from quwoquan_ops.cli.commands.app_preflight_evidence import (
    _app_content_readback_summary,
    _app_content_uat_envelope,
    _resolve_active_app_content_evidence,
    _resolve_test_live_app_content_evidence,
    _run_app_content_release_probe,
)


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    app_content_preflight_parser = subparsers.add_parser(
        "app-content-preflight",
        help="在本地 Flutter 安装前验证 active candidate、商业内容回执与 live readback",
    )
    app_content_preflight_parser.add_argument(
        "--report-dir", default=argparse.SUPPRESS
    )
    app_content_preflight_parser.add_argument(
        "--target",
        choices=("alpha-local", "beta-local", "gamma-local"),
        required=True,
    )
    app_debug_preflight_parser = subparsers.add_parser(
        "app-debug-preflight",
        help="在 Flutter Debug 启动前只读验证目标 runtime、TLS 与 SMS substitute",
    )
    app_debug_preflight_parser.add_argument(
        "--report-dir", default=argparse.SUPPRESS
    )
    app_debug_preflight_parser.add_argument(
        "--purpose",
        choices=("runtime", "content_live"),
        default="runtime",
        help="runtime diagnostics or strict content-live readiness",
    )
    app_debug_preflight_parser.add_argument(
        "--target",
        choices=("alpha-local", "beta-local", "gamma-local"),
        required=True,
    )
    app_debug_preflight_parser.add_argument(
        "--runtime-mode",
        choices=("immutable_candidate", "test_live"),
        required=True,
        help=(
            "显式选择 active immutable candidate 严格验证，或 non-promotable "
            "test_live 启动诊断"
        ),
    )
    app_domain_api_parser = subparsers.add_parser(
        "app-domain-api-integration",
        help=(
            "执行 ContractGraph 派生的五域 generated typed Remote API integration"
        ),
    )
    app_domain_api_parser.add_argument(
        "--report-dir", default=argparse.SUPPRESS
    )
    app_domain_api_parser.add_argument(
        "--target",
        choices=("gamma-local",),
        default="gamma-local",
    )
    app_domain_api_parser.add_argument(
        "--test-path",
        action="append",
        default=[],
        help=(
            "仅执行 ContractGraph 已登记的 App api_integration 测试；"
            "可重复指定，未指定时执行全部受治理领域"
        ),
    )


def command_app_content_preflight(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    target = str(args.target)
    purpose = str(getattr(args, "purpose", "readiness") or "readiness")
    environment = str(_stackctl.get_target(_stackctl.load_environment_topology(), target)["env"])
    report_dir = (
        Path(args.report_dir)
        if getattr(args, "report_dir", "")
        else _stackctl.repo_run_dir("app-content-preflight", target=target)
    )
    runtime_mode = str(
        getattr(args, "runtime_mode", "immutable_candidate")
        or "immutable_candidate"
    )
    content_binding = getattr(args, "content_binding", None)
    try:
        if runtime_mode == "test_live":
            if not isinstance(content_binding, Mapping):
                raise ValueError("test_live content preflight requires a validated binding")
            candidate, readiness, readiness_path, lifecycle_ref = (
                _stackctl._resolve_test_live_app_content_evidence(target, content_binding)
            )
        elif runtime_mode == "immutable_candidate":
            candidate, readiness, readiness_path, lifecycle_ref = (
                _stackctl._resolve_active_app_content_evidence(target)
            )
        else:
            raise ValueError("App content preflight runtime mode is invalid")
        app_uat_envelope = _stackctl._app_content_uat_envelope(readiness)
        app_uat_plan = _stackctl.build_app_content_uat_plan(readiness)
    except (OSError, ValueError) as exc:
        details = [str(exc)]
        payload = {
            "schema": "quwoquan_ops.app_content_preflight",
            "target": target,
            "environment": environment,
            "status": "gate_block",
            "details": details,
        }
        _stackctl.write_json(report_dir / "report.json", payload)
        _stackctl.write_json(report_dir / "findings.json", {"issues": details})
        return {
            **payload,
            "exitCode": 2,
            "summary": f"App content preflight is GATE_BLOCK for {target}",
            "reportDir": _stackctl.relpath(report_dir),
        }

    readiness_phase = ReadinessPhase(str(readiness["readinessPhase"]))
    readiness_result = _stackctl.command_content_readiness(
        argparse.Namespace(
            command="content-readiness",
            phase=readiness_phase.value,
            env=environment,
            release_id=str(readiness["releaseId"]),
            verify_run_id=str(readiness["verifyRunId"]),
            manifest_digest=str(readiness["manifestDigest"]),
            lifecycle_exit_ref=lifecycle_ref,
            output_format="json",
            report_dir=str(report_dir / "content-readiness"),
        )
    )
    passed = int(readiness_result.get("exitCode", 2)) == 0
    release_probe: dict[str, Any] = {}
    details = list(readiness_result.get("details", []))
    if passed and purpose == "content_live":
        try:
            release_probe = _stackctl._run_app_content_release_probe(
                target=target,
                readiness_path=readiness_path,
                app_uat_plan=app_uat_plan,
                report_dir=report_dir / "release-probe",
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            passed = False
            details.append(str(exc))
    receipt_digest = (
        str(content_binding.get("readinessReceiptDigest") or "")
        if runtime_mode == "test_live" and isinstance(content_binding, Mapping)
        else _stackctl._canonical_document_checksum(readiness)
    )
    receipt_ref = (
        str(content_binding.get("readinessReceiptRef") or "")
        if runtime_mode == "test_live" and isinstance(content_binding, Mapping)
        else _stackctl.relpath(readiness_path)
    )
    data_source_identity = (
        {
            "sourceIdentities": list(readiness.get("sourceIdentities") or []),
            "sourceIdentitySetDigest": str(
                readiness.get("sourceIdentitySetDigest") or ""
            ),
        }
        if "sourceIdentities" in readiness or "sourceIdentitySetDigest" in readiness
        else {
            key: str(readiness.get(key) or "")
            for key in (
                "sourceRevision",
                "sourceDigest",
                "entityCatalogDigest",
            )
        }
    )
    payload = {
        "schema": "quwoquan_ops.app_content_preflight",
        "target": target,
        "environment": environment,
        "status": "passed" if passed else "gate_block",
        "packageBaseline": candidate.get("baselineId", ""),
        "sourceRevision": candidate.get("sourceRevision", ""),
        "releaseId": readiness["releaseId"],
        "manifestDigest": readiness["manifestDigest"],
        "readinessReceiptRef": receipt_ref,
        "readinessReceiptDigest": receipt_digest,
        "dataSourceIdentity": data_source_identity,
        "activationEnvelope": dict(readiness.get("activationEnvelope") or {}),
        "activationEnvelopeDigest": str(
            readiness.get("activationEnvelopeDigest") or ""
        ),
        "lifecycleExitRef": lifecycle_ref,
        "appUatEnvelope": app_uat_envelope,
        "appUatEnvelopeDigest": str(
            readiness.get("appUatEnvelopeDigest") or ""
        ),
        "appUatPlan": app_uat_plan,
        "appUatPlanDigest": _stackctl._canonical_document_checksum(app_uat_plan),
        "contentReadback": _stackctl._app_content_readback_summary(readiness),
        "contentReadinessReportRef": _stackctl.relpath(
            report_dir / "content-readiness" / "report.json"
        ),
        "releaseProbe": release_probe,
        "details": details,
    }
    _stackctl.write_json(report_dir / "report.json", payload)
    _stackctl.write_json(
        report_dir / "findings.json",
        {"issues": [] if passed else payload["details"]},
    )
    return {
        **payload,
        "exitCode": 0 if passed else 2,
        "summary": (
            f"App content preflight passed for {target}"
            if passed
            else f"App content preflight is GATE_BLOCK for {target}"
        ),
        "reportDir": _stackctl.relpath(report_dir),
    }


def command_app_domain_api_integration(args: argparse.Namespace) -> dict[str, Any]:
    """Execute ContractGraph-derived generated typed Remote cases on Gamma."""
    import quwoquan_ops.cli.stackctl as _stackctl

    started_monotonic, started_at = _stackctl._start_timing()
    target_name = str(args.target)
    topology = _stackctl.load_environment_topology()
    target = _stackctl.get_target(topology, target_name)
    environment = str(target.get("env") or "")
    report_dir = _stackctl.resolve_report_dir(args, environment, target_name)
    issues: list[str] = []
    cases = []
    command: list[str] = []
    stdout = ""
    stderr = ""
    return_code = 2

    api_base_url = ""
    try:
        target_base = _stackctl.resolve_environment_target_base(
            topology,
            environment,
            target_name=target_name,
        )
        api_base_url = target_base.api_base
    except (KeyError, TypeError, ValueError) as error:
        issues.append(f"canonical App API target/base is unavailable: {error}")
    if environment != "gamma" or target_name != "gamma-local":
        issues.append("App domain API integration only supports gamma-local")
    try:
        active_candidate = _stackctl.active_deployment_candidate(target_name)
    except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as error:
        active_candidate = None
        issues.append(f"gamma-local active candidate is invalid: {error}")
    if active_candidate is None and not any(
        issue.startswith("gamma-local active candidate is invalid")
        for issue in issues
    ):
        issues.append("gamma-local active immutable candidate is required")
    try:
        startup = _stackctl.load_startup_attempt(target_name)
    except (OSError, ValueError) as error:
        startup = None
        issues.append(f"gamma-local startup receipt is unreadable: {error}")
    if (
        not isinstance(startup, dict)
        or startup.get("status") != "running"
        or startup.get("target") != target_name
        or startup.get("env") != environment
        or startup.get("workload") != "full"
    ):
        issues.append("gamma-local full startup receipt is required")
    elif (
        isinstance(active_candidate, dict)
        and startup.get("candidateDigest") != active_candidate.get("baselineId")
    ):
        issues.append("gamma-local startup receipt does not bind the active candidate")

    raw_test_paths = getattr(args, "test_path", ())
    if not isinstance(raw_test_paths, (list, tuple)):
        raw_test_paths = ()
    selected_test_paths = tuple(
        str(path).strip()
        for path in raw_test_paths
        if str(path).strip()
    )
    try:
        if selected_test_paths:
            discovered, discovery_issues = _stackctl.discover_selected_remote_api_cases(
                _stackctl.ROOT,
                selected_test_paths,
            )
            validated, validation_issues = _stackctl.validate_domain_remote_api_cases(
                _stackctl.ROOT,
                discovered,
                required_domains=(),
            )
        else:
            discovered, discovery_issues = _stackctl.discover_domain_remote_api_cases(_stackctl.ROOT)
            validated, validation_issues = _stackctl.validate_domain_remote_api_cases(
                _stackctl.ROOT,
                discovered,
            )
        cases = validated
        issues.extend(discovery_issues)
        issues.extend(validation_issues)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        issues.append(f"ContractGraph Remote API evidence is invalid: {error}")

    covered_domains = {case.domain for case in cases}
    if not selected_test_paths:
        missing_domains = sorted(
            set(_stackctl.REMOTE_API_INTEGRATION_DOMAINS) - covered_domains
        )
        if missing_domains:
            issues.append(
                "missing governed Remote API domains: " + ", ".join(missing_domains)
            )
    run_label = (
        "focused App generated Remote API integration"
        if selected_test_paths
        else "five-domain generated Remote API integration"
    )

    if not issues:
        command = [
            "flutter",
            "test",
            "--reporter=expanded",
            "--concurrency=1",
            "--dart-define=API_CONTRACT_ENV=gamma",
            f"--dart-define=API_CONTRACT_BASE_URL={api_base_url}",
            *[
                str((_stackctl.ROOT / case.test_path).relative_to(_stackctl.ROOT / "quwoquan_app"))
                for case in cases
            ],
        ]
        result = _stackctl.run(command, cwd=_stackctl.ROOT / "quwoquan_app")
        return_code = result.returncode
        stdout = result.stdout
        stderr = result.stderr
        if return_code != 0:
            issues.append(
                stderr.strip()
                or stdout.strip()
                or f"{run_label} failed"
            )

    timing = _stackctl._finish_timing(started_monotonic, started_at)
    passed = return_code == 0 and not issues
    payload = {
        "schema": "quwoquan_ops.app_domain_remote_api_integration",
        "command": "app-domain-api-integration",
        "target": target_name,
        "environment": environment,
        "status": "passed" if passed else "gate_block",
        "executed": len(cases) if passed else 0,
        "skipped": 0,
        "domains": (
            sorted(covered_domains)
            if selected_test_paths
            else list(_stackctl.REMOTE_API_INTEGRATION_DOMAINS)
        ),
        "cases": [case.document() for case in cases],
        "argv": command,
        "stdout": stdout,
        "stderr": stderr,
        "issues": issues,
        "candidateDigest": (
            str(startup.get("candidateDigest") or "")
            if isinstance(startup, dict)
            else ""
        ),
        **timing,
    }
    _stackctl.write_json(report_dir / "report.json", payload)
    _stackctl.write_json(report_dir / "findings.json", {"issues": issues})
    _stackctl._write_summary_bundle(
        report_dir,
        command="app-domain-api-integration",
        target=target_name,
        status="ok" if passed else "blocked",
        summary=(
            f"{run_label} passed"
            if passed
            else f"{run_label} is GATE_BLOCK"
        ),
        details=issues
        or [
            f"domains={len(_stackctl.REMOTE_API_INTEGRATION_DOMAINS)}",
            f"object cases={len(cases)}",
        ],
        extra={
            "executed": payload["executed"],
            "skipped": 0,
            "candidateDigest": payload["candidateDigest"],
        },
        timing=timing,
    )
    return {
        "exitCode": 0 if passed else 2,
        "summary": (
            f"{run_label} passed"
            if passed
            else f"{run_label} is GATE_BLOCK"
        ),
        "details": issues
        or [f"{len(cases)} object-level cases passed without skips"],
        "reportDir": _stackctl.relpath(report_dir),
        **timing,
    }
