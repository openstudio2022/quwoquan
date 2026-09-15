"""stackctl `verify` 子命令域（argparse 表面、命令选择器与主编排）。

从 stackctl.py 逐字迁出：

- `register_parser`：`verify` 子命令的 argparse 表面（帮助文案与参数
  集合逐字节保持不变）；
- 命令选择器（`_selected_verify_commands` / `_selected_profile_commands`）
  已迁至 `commands/verify_selection.py`；
- `command_verify`：Prod test-data 拒绝、Provider readiness、备份恢复
  receipt、distribution、静态波次、content readiness、profile 调度、
  选中 test-data 与 runtime-media 播放证据的主编排。

kind 子实现在 `commands/verify_kinds.py`，执行调度与证据聚合在
`commands/verify_shared.py`。`_run_provider_readiness_preflight` /
`_verify_child_environment` / `_current_runtime_health_scope` /
`_current_runtime_workload` / `can_reuse_package` 等仍由 stackctl
命名空间拥有（up / deploy / app-content 留守域共用）。测试经
``mock.patch.object(stackctl, ...)`` patch 本模块符号与上述协作符号，
因此函数体内一律经函数内延迟导入 `_stackctl` 属性访问（含本模块
符号互调），保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Mapping

from quwoquan_ops.cli.lib.content_release_readiness import (
    ProbeOutcome,
    VerificationProfile,
)
from quwoquan_ops.cli.lib.test_data.model import TestDataContext
from quwoquan_ops.cli.lib.test_data.operations import TestDataRuntime


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    import quwoquan_ops.cli.stackctl as _stackctl

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    verify_parser.add_argument("--env", choices=_stackctl.ENVIRONMENTS, default="")
    verify_parser.add_argument("--target", choices=_stackctl.TARGETS, default="")
    verify_parser.add_argument("--service", default="")
    verify_parser.add_argument(
        "--kind",
        choices=[
            "topology",
            "config",
            "packaging",
            "distribution",
            "legal-static",
            "config-slo",
            "content-delivery",
            "all",
        ],
        default="all",
    )
    verify_parser.add_argument(
        "--profile",
        choices=[profile.value for profile in VerificationProfile],
        default=VerificationProfile.BASELINE.value,
    )
    verify_parser.add_argument("--error-rate", default="")
    verify_parser.add_argument("--p95-ms", default="")
    verify_parser.add_argument("--redis-error-rate", default="")
    verify_parser.add_argument(
        "--prometheus-url",
        default="",
        help="config-slo 决策的 Prometheus base URL；SLO 值只从监控读回，禁止人工数字",
    )
    verify_parser.add_argument("--data-release-id", default="")
    verify_parser.add_argument("--data-verify-run-id", default="")
    verify_parser.add_argument("--data-manifest-digest", default="")
    verify_parser.add_argument(
        "--test-data-request",
        default="",
        help="选中用例导出的强类型 test-data request graph JSON",
    )
    verify_parser.add_argument(
        "--test-data-evidence",
        default="",
        help="请求依赖闭包所需的候选绑定 Provider evidence JSON",
    )
    verify_parser.add_argument(
        "--test-data-handoff",
        default="",
        help="冻结当前 candidate/request/evidence 的 environment-bound exact handoff",
    )
    verify_parser.add_argument(
        "--test-data-benchmark-policy",
        choices=("normal", "serial-no-cache"),
        default="normal",
        help=(
            "仅性能取证可用；serial-no-cache 不得作为环境正式绿色回执"
        ),
    )
    verify_parser.add_argument(
        "--data-lifecycle-exit-ref",
        default="",
        help="release profile 绑定的 canonical rollback/replay lifecycle Exit ref",
    )
    verify_parser.add_argument(
        "--backup-recovery-receipt",
        default="",
        help="prod release 的 hosted 灾备隔离恢复 receipt；缺失即阻断",
    )
    verify_parser.add_argument("--distribution-root", default="")
    verify_parser.add_argument("--verify-hosted", action="store_true")
    verify_parser.add_argument(
        "--verification-purpose",
        choices=("formal-readiness", "core-diagnostic"),
        default="formal-readiness",
    )
    verify_parser.add_argument(
        "--feature",
        action="append",
        choices=(
            "identity",
            "feed-detail",
            "search-recommendation",
            "image-video-range",
            "post-write-readback",
            "chat-write-readback",
        ),
        default=[],
    )
    verify_parser.add_argument(
        "--deployment-instance", choices=("prevalidate", "prod"), default=""
    )
    verify_parser.add_argument(
        "--data-mode", choices=("isolated", "external"), default=""
    )
    verify_parser.add_argument(
        "--app-core-diagnostic-report",
        default="",
        help="现有 app-content-uat core_diagnostic receipt；账号写用例由 Ops 汇总",
    )


def _command_core_diagnostic(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    features = tuple(dict.fromkeys(getattr(args, "feature", ()) or ()))
    if not features:
        features = (
            "identity", "feed-detail", "search-recommendation",
            "image-video-range",
        )
    env_name = str(getattr(args, "env", "") or "").strip()
    target_name = str(getattr(args, "target", "") or "").strip()
    if not target_name and env_name in _stackctl.ENVIRONMENTS:
        target_name = _stackctl.DEFAULT_TARGET_BY_ENV[env_name]
    issue = ""
    if env_name == "gamma" and target_name != "gamma-local":
        issue = "Gamma core diagnostic requires target=gamma-local"
    elif env_name == "prod" and (
        target_name != "prod-hosted"
        or str(getattr(args, "deployment_instance", "") or "") != "prevalidate"
        or str(getattr(args, "data_mode", "") or "") != "isolated"
    ):
        issue = "Prod core diagnostic requires prod-hosted prevalidate with isolated data mode"
    elif env_name not in {"gamma", "prod"}:
        issue = "core diagnostic only supports gamma or prod"

    report_dir = _stackctl.resolve_report_dir(args, env_name or "repo", target_name or "repo")
    cases: list[dict[str, str]] = []
    data_report: Mapping[str, Any] | None = None
    data_path = _stackctl.env_runs_root(env_name) / "data-release" / str(args.data_release_id) / str(args.data_verify_run_id) / "core-diagnostic-report.json"
    if not issue:
        try:
            loaded = json.loads(data_path.read_text(encoding="utf-8"))
            if isinstance(loaded, Mapping):
                data_report = loaded
        except (OSError, json.JSONDecodeError):
            data_report = None
        if (
            data_report is None
            or data_report.get("releaseId") != str(args.data_release_id)
            or data_report.get("manifestDigest") != str(args.data_manifest_digest)
            or data_report.get("nonPromotable") is not True
            or data_report.get("releaseEligibility") != "GATE_BLOCK"
            or data_report.get("readinessWritten") is not False
        ):
            issue = "exact Data core diagnostic report is missing or identity-drifted"
    source = {
        str(row.get("feature")): row
        for row in list((data_report or {}).get("caseResults") or [])
        if isinstance(row, Mapping)
    }
    write_features = {"post-write-readback", "chat-write-readback"} & set(features)
    if write_features and not issue:
        app_ref = str(getattr(args, "app_core_diagnostic_report", "") or "").strip()
        try:
            app_path = Path(app_ref).expanduser()
            if not app_path.is_absolute():
                app_path = _stackctl.output_root() / app_path
            app_path = app_path.resolve()
            app_path.relative_to(_stackctl.output_root().expanduser().resolve())
            app_report = json.loads(app_path.read_text(encoding="utf-8"))
            selected_suites = set(
                ((app_report.get("suitePlan") or {}).get("selected") or [])
            )
            evidence_suites = {
                str(row.get("suite") or "")
                for row in (app_report.get("evidenceRefs") or [])
                if isinstance(row, Mapping) and str(row.get("reportRef") or "")
            }
            readbacks = list(
                ((app_report.get("diagnosticBindings") or {}).get("releaseReadbacks") or {}).values()
            )
            exact_release = bool(readbacks) and all(
                isinstance(row, Mapping)
                and row.get("releaseId") == str(args.data_release_id)
                and row.get("manifestDigest") == str(args.data_manifest_digest)
                and row.get("activationEnvelopeDigest")
                for row in readbacks
            )
            if (
                app_report.get("verificationPurpose") != "core_diagnostic"
                or app_report.get("nonPromotable") is not True
                or app_report.get("status") != "diagnostic_complete"
                or not exact_release
            ):
                raise ValueError("App diagnostic identity or terminal status drifted")
            suite_by_feature = {
                "post-write-readback": "post-write-readback",
                "chat-write-readback": "chat-send-readback",
            }
            for feature in write_features:
                suite = suite_by_feature[feature]
                source[feature] = {
                    "feature": feature,
                    "status": (
                        "passed"
                        if suite in selected_suites and suite in evidence_suites
                        else "not_executed"
                    ),
                    "detail": "existing App core diagnostic evidence",
                }
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            issue = f"App core diagnostic report is invalid: {exc}"
    for feature in (
        "identity",
        "feed-detail",
        "search-recommendation",
        "image-video-range",
        "post-write-readback",
        "chat-write-readback",
    ):
        row = source.get(feature)
        status = str((row or {}).get("status") or "not_executed")
        detail = str((row or {}).get("detail") or "not selected")
        cases.append({"feature": feature, "status": status, "detail": detail})
        if feature in features and status != "passed" and not issue:
            issue = f"selected required case is {status}: {feature}"
    payload = {
        "status": "failed" if issue else "passed",
        "command": "verify",
        "verificationPurpose": "core-diagnostic",
        "environment": env_name,
        "target": target_name,
        "deploymentInstance": str(getattr(args, "deployment_instance", "") or ""),
        "dataMode": str(getattr(args, "data_mode", "") or ""),
        "releaseId": str(getattr(args, "data_release_id", "") or ""),
        "manifestDigest": str(getattr(args, "data_manifest_digest", "") or ""),
        "selectedFeatures": list(features),
        "caseResults": cases,
        "nonPromotable": True,
        "releaseEligibility": "GATE_BLOCK",
        "readinessWritten": False,
        "issues": [issue] if issue else [],
    }
    _stackctl.write_json(report_dir / "core-diagnostic-report.json", payload)
    return {
        "exitCode": 2 if issue else 0,
        "summary": "stackctl core diagnostic is GATE_BLOCK" if issue else "stackctl core diagnostic completed (non-promotable)",
        "details": [issue] if issue else [f"passed {len(features)} selected cases"],
        "reportDir": _stackctl.relpath(report_dir),
        "nonPromotable": True,
        "releaseEligibility": "GATE_BLOCK",
        "readinessWritten": False,
    }


def command_verify(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    if str(getattr(args, "verification_purpose", "formal-readiness")) == "core-diagnostic":
        return _command_core_diagnostic(args)

    service_name = str(getattr(args, "service", "") or "").strip()
    if service_name:
        return _stackctl._command_verify_service_environment(args)
    if args.kind == "config-slo":
        return _stackctl._command_verify_config_slo(args)
    if args.kind == "distribution":
        return _stackctl._command_verify_distribution(args)
    if args.kind == "content-delivery":
        return _stackctl._command_verify_content_delivery(args)
    profile = VerificationProfile(args.profile)
    if args.kind == "legal-static":
        if profile is VerificationProfile.BASELINE:
            return {
                "exitCode": 2,
                "summary": "stackctl verify baseline does not verify legal-static",
                "details": [
                    "baseline must not create or read disposable release output; "
                    "use smoke, integration, or release"
                ],
            }
        return _stackctl._command_verify_legal_static(args, profile)

    env_name = args.env or (_stackctl.get_target(_stackctl.load_environment_topology(), args.target).get("env") if args.target else "")
    if profile is VerificationProfile.BASELINE and env_name:
        return {
            "exitCode": 2,
            "summary": "stackctl verify baseline does not accept an environment",
            "details": ["baseline must run without --env or --target"],
        }
    if profile.requires_environment and env_name not in _stackctl.ENVIRONMENTS:
        return {
            "exitCode": 2,
            "summary": f"stackctl verify {profile.value} requires --env or --target",
            "details": ["environment-scoped profiles must name one environment"],
        }
    if profile is VerificationProfile.BASELINE and args.kind == "packaging":
        return {
            "exitCode": 2,
            "summary": "stackctl verify baseline does not verify packaging",
            "details": [
                "baseline must not read disposable release output; use an environment profile"
            ],
        }
    target_name = args.target or (_stackctl.DEFAULT_TARGET_BY_ENV[env_name] if env_name in _stackctl.ENVIRONMENTS else "repo")
    report_dir = _stackctl.resolve_report_dir(args, env_name if env_name in _stackctl.ENVIRONMENTS else "repo", target_name)
    started_monotonic, started_at = _stackctl._start_timing()
    steps: list[dict[str, Any]] = []
    issues: list[str] = []
    provider_readiness: dict[str, Any] = {}
    force_deadline_rollback = False
    test_data_request = str(
        getattr(args, "test_data_request", "") or ""
    ).strip()
    if env_name == "prod" and test_data_request:
        issue = (
            "Prod rejects test-data mutation before Provider discovery, "
            "ActorLease acquisition, or any business operation"
        )
        request_digest = ""
        try:
            request_path = Path(test_data_request).expanduser()
            if not request_path.is_absolute():
                request_path = _stackctl.ROOT / request_path
            request_path = request_path.resolve()
            request_path.relative_to(_stackctl.output_root().expanduser().resolve())
            request_document = json.loads(
                request_path.read_text(encoding="utf-8")
            )
            if isinstance(request_document, Mapping):
                request_digest = str(
                    request_document.get("requestDigest") or ""
                ).strip()
        except (OSError, ValueError, json.JSONDecodeError):
            request_digest = ""
        case_result = {
            "schema": "qwq.case_result",
            "caseId": "prod-test-data-mutation-boundary",
            "status": "GATE_BLOCK",
            "preparationStatus": "GATE_BLOCK",
            "executed": 0,
            "skipped": 0,
            "target": target_name,
            "environment": env_name,
            "requestDigest": request_digest,
            "operationCount": 0,
            "executedOperationIds": [],
            "loadedProviders": [],
            "requiredProviders": [],
            "baselineEligible": False,
            "issues": [issue],
        }
        _stackctl.write_json(report_dir / "test-data/case-result.json", case_result)
        steps.append(
            {
                "kind": "test-data",
                "profile": profile.value,
                "exitCode": 2,
                "reportPath": _stackctl.relpath(
                    report_dir / "test-data/case-result.json"
                ),
                "details": [issue],
                "caseResult": case_result,
            }
        )
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        payload = {
            "status": ProbeOutcome.GATE_BLOCK.value,
            "command": "verify",
            "timestamp": _stackctl.utc_now(),
            "kind": args.kind,
            "profile": profile.value,
            "environment": env_name,
            "target": target_name,
            "providerReadiness": {},
            "steps": steps,
            **timing,
        }
        _stackctl.write_json(report_dir / "report.json", payload)
        _stackctl.write_json(report_dir / "findings.json", {"issues": [issue]})
        _stackctl._write_summary_bundle(
            report_dir,
            command="verify",
            target=target_name,
            status="blocked",
            summary="stackctl verify rejected Prod test-data mutation",
            details=[issue],
            extra={"kind": args.kind, "profile": profile.value},
            timing=timing,
        )
        return {
            "exitCode": 2,
            "summary": "stackctl verify rejected Prod test-data mutation",
            "details": [issue],
            "reportDir": _stackctl.relpath(report_dir),
            **timing,
        }
    if (
        profile is VerificationProfile.RELEASE
        and env_name in {"gamma", "prod"}
    ):
        provider_preflight = _stackctl._run_provider_readiness_preflight(env_name, report_dir)
        provider_readiness = provider_preflight["report"]
        steps.append(
            {
                "kind": provider_preflight["kind"],
                "environment": env_name,
                "argv": provider_preflight["argv"],
                "exitCode": provider_preflight["exitCode"],
                "reportPath": provider_preflight["reportPath"],
                "details": provider_preflight["details"],
            }
        )
        if provider_preflight["exitCode"] != 0:
            issues.extend(
                f"provider readiness: {detail}"
                for detail in provider_preflight["details"]
            )
            if not test_data_request:
                timing = _stackctl._finish_timing(started_monotonic, started_at)
                payload = {
                    "status": ProbeOutcome.GATE_BLOCK.value,
                    "command": "verify",
                    "timestamp": _stackctl.utc_now(),
                    "kind": args.kind,
                    "profile": profile.value,
                    "environment": env_name,
                    "target": target_name,
                    "providerReadiness": provider_readiness,
                    "steps": steps,
                    **timing,
                }
                _stackctl.write_json(report_dir / "report.json", payload)
                _stackctl.write_json(report_dir / "findings.json", {"issues": issues})
                _stackctl._write_summary_bundle(
                    report_dir,
                    command="verify",
                    target=target_name,
                    status="blocked",
                    summary="stackctl verify is GATE_BLOCK by Provider readiness",
                    details=issues,
                    extra={"kind": args.kind, "profile": profile.value},
                    timing=timing,
                )
                return {
                    "exitCode": 2,
                    "summary": "stackctl verify is GATE_BLOCK by Provider readiness",
                    "details": issues,
                    "reportDir": _stackctl.relpath(report_dir),
                    **timing,
                }
            # The full release remains blocked, but the selected typed request
            # owns an independently projected Provider evidence closure.  Keep
            # collecting its provision/readback/CaseResult/cleanup evidence.
    if profile is VerificationProfile.RELEASE and target_name == "prod-hosted":
        receipt = str(
            getattr(args, "backup_recovery_receipt", "")
            or os.environ.get("QWQ_PROD_BACKUP_RECOVERY_RECEIPT", "")
        ).strip()
        backup_report = report_dir / "backup-recovery.json"
        command = [
            "python3",
            "quwoquan_ops/cli/prod/backup_recovery.py",
            "--plan",
            "quwoquan_ops/environments/prod/backup-recovery.yaml",
            "--receipt",
            receipt,
            "--output",
            str(backup_report),
        ]
        if not receipt:
            steps.append(
                {
                    "kind": "backup-recovery",
                    "exitCode": 2,
                    "details": ["QWQ_PROD_BACKUP_RECOVERY_RECEIPT is required"],
                }
            )
            issues.append("backup recovery hosted receipt is required for prod release")
        else:
            result = _stackctl.run(
                command,
                env=_stackctl._verify_child_environment(target_name),
            )
            steps.append(
                {
                    "kind": "backup-recovery",
                    "argv": command,
                    "exitCode": result.returncode,
                    "reportPath": str(backup_report),
                    "details": _stackctl._command_details(result),
                }
            )
            if result.returncode != 0:
                issues.append("backup recovery receipt validation failed")
    if profile is VerificationProfile.RELEASE and args.kind == "all":
        try:
            distribution, _, _ = _stackctl._inspect_distribution_for_target(
                args,
                target_name=target_name,
            )
            distribution_issues = list(distribution.get("issues") or [])
        except (OSError, ValueError, _stackctl.OfficialDistributionReleaseError) as error:
            distribution = {
                "status": ProbeOutcome.GATE_BLOCK.value,
                "issues": [str(error)],
            }
            distribution_issues = [str(error)]
        steps.append(
            {
                "kind": "distribution",
                "exitCode": 0 if not distribution_issues else 2,
                "details": distribution_issues,
                "inspection": distribution,
            }
        )
        issues.extend(
            f"distribution: {issue}" for issue in distribution_issues
        )
    candidate_snapshot: Mapping[str, Any] | None = None
    startup_receipt: Mapping[str, Any] | None = None
    generation_issues: list[str] = []
    if target_name != "repo":
        try:
            candidate_snapshot = _stackctl.active_deployment_candidate_snapshot(
                target_name
            )
        except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as error:
            generation_issues.append(f"active candidate readback failed: {error}")
        try:
            startup_receipt = _stackctl.read_startup_attempt(target_name)
        except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as error:
            generation_issues.append(f"startup receipt readback failed: {error}")
        candidate_digest = str((candidate_snapshot or {}).get("baselineId") or "")
        startup_candidate = str((startup_receipt or {}).get("candidateDigest") or "")
        if candidate_digest and startup_candidate and candidate_digest != startup_candidate:
            generation_issues.append(
                "startup receipt candidateDigest does not match the active candidate"
            )
    from quwoquan_ops.cli.lib.evidence_generation import (
        build_evidence_generation_envelope,
    )
    evidence_envelope = build_evidence_generation_envelope(
        command="verify",
        candidate_snapshot=candidate_snapshot,
        startup_receipt=startup_receipt,
        startup_status=(
            "executed"
            if isinstance(startup_receipt, Mapping)
            else ("not_applicable" if target_name == "repo" else "not_executed")
        ),
        startup_reason=(
            "baseline verify has no runtime startup layer"
            if target_name == "repo"
            else "no startup receipt is available for verify"
        ),
        upstream_status="not_applicable",
        upstream_reason="verify consumes candidate and runtime evidence directly",
    )
    package_envs = [env_name] if env_name in _stackctl.ENVIRONMENTS and profile.requires_environment else []
    test_data_package_ready = True
    for package_env in package_envs:
        package_target = args.target or _stackctl.DEFAULT_TARGET_BY_ENV[package_env]
        ok, package_detail = _stackctl.can_reuse_package(
            package_env,
            package_target,
            include_services=True,
        )
        steps.append(
            {
                "kind": "package",
                "env": package_env,
                "exitCode": 0 if ok else 2,
                "consumed": ok,
                "details": [package_detail],
                "reportDir": "",
            }
        )
        if not ok:
            test_data_package_ready = False
            issues.append(
                f"fixed package is unavailable for {package_env}/{package_target}: "
                f"{package_detail}; run stackctl package explicitly"
            )
    stdout_sections: list[tuple[str, str]] = []
    commands = _stackctl._selected_verify_commands(
        args.kind,
        env_name if env_name in _stackctl.ENVIRONMENTS else "",
        target_name=target_name,
        profile=profile,
    )
    requires_content_readiness = profile in {
        VerificationProfile.INTEGRATION,
        VerificationProfile.RELEASE,
    }

    def readiness_call() -> dict[str, Any]:
        return _stackctl.command_content_readiness(
            argparse.Namespace(
                command="content-readiness",
                require_lifecycle_exit=True,
                env=env_name,
                release_id=getattr(args, "data_release_id", ""),
                verify_run_id=getattr(args, "data_verify_run_id", ""),
                manifest_digest=getattr(args, "data_manifest_digest", ""),
                lifecycle_exit_ref=getattr(
                    args,
                    "data_lifecycle_exit_ref",
                    "",
                ),
                output_format="json",
                report_dir=str(report_dir / "content-readiness"),
            )
        )

    static_results, readiness_payload, static_gate_ms = _stackctl._run_static_verify_wave(
        commands,
        target_name=target_name,
        readiness_call=readiness_call if requires_content_readiness else None,
    )
    for command, result, duration_ms in static_results:
        command_key = " ".join(command)
        steps.append(
            {
                "kind": "verify",
                "group": args.kind,
                "argv": command,
                "exitCode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "durationMs": duration_ms,
            }
        )
        stdout_sections.append((command_key, "\n".join(filter(None, [result.stdout, result.stderr]))))
        if result.returncode != 0:
            issues.append(result.stderr.strip() or result.stdout.strip() or "unknown verify failure")
    content_readiness_ready = True
    if requires_content_readiness and readiness_payload is not None:
        steps.append(
            {
                "kind": "readiness",
                "requireLifecycleExit": True,
                "exitCode": readiness_payload["exitCode"],
                "reportDir": readiness_payload.get("reportDir", ""),
                "details": readiness_payload.get("details", []),
            }
        )
        if readiness_payload["exitCode"] != 0:
            content_readiness_ready = False
            issues.extend(
                f"content readiness: {detail}"
                for detail in readiness_payload.get("details", [])
            )
    # Only the active candidate/package and its content readiness gate the
    # selected request graph. The graph's evidence document validates the
    # exact Provider capability closure itself. Global Provider, distribution,
    # backup and unrelated static/profile failures still block the full verify,
    # but must not suppress independently safe data evidence.
    test_data_prerequisites_passed = (
        test_data_package_ready and content_readiness_ready
    )
    profile_actor_context: TestDataContext | None = None
    profile_actor_runtime = TestDataRuntime()
    profile_commands = _stackctl._selected_profile_commands(
        env_name,
        target_name,
        profile,
        report_dir,
        service=service_name,
        data_readiness_path=_stackctl._data_readiness_path_from_verify_args(
            args,
            environment=env_name,
            profile=profile,
        ),
    )
    if any(command.get("testDataActorCase") is not None for command in profile_commands):
        try:
            profile_actor_context = _stackctl._typed_profile_actor_context(
                args,
                environment=env_name,
                target_name=target_name,
                report_dir=report_dir,
                runtime=profile_actor_runtime,
            )
        except (OSError, RuntimeError, TypeError, ValueError):
            # Only Actor-bound nodes will fail closed in the scheduler; pure
            # read-only and independently authenticated nodes still produce
            # useful evidence.
            profile_actor_context = None
    profile_started = time.monotonic()
    profile_results = _stackctl._run_profile_commands_parallel(
        profile_commands,
        target_name=target_name,
        actor_context=profile_actor_context,
    )
    profile_gate_ms = max(
        0,
        round((time.monotonic() - profile_started) * 1000),
    )
    for profile_command, result, duration_ms, skipped in profile_results:
        blocking = bool(profile_command.get("blocking", True))
        steps.append(
            {
                "kind": "profile",
                "profile": profile.value,
                "name": profile_command["name"],
                "argv": profile_command["argv"],
                "exitCode": result.returncode,
                "blocking": blocking,
                "skipped": skipped,
                "durationMs": duration_ms,
                "reportPath": profile_command.get("reportPath", ""),
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
        stdout_sections.append(
            (
                profile_command["name"],
                "\n".join(filter(None, [result.stdout, result.stderr])),
            )
        )
        if result.returncode != 0 and blocking:
            issues.append(
                f"{profile_command['name']} failed: "
                + (result.stderr.strip() or result.stdout.strip() or "unknown profile failure")
            )
    if (
        profile in {
            VerificationProfile.INTEGRATION,
            VerificationProfile.RELEASE,
        }
        and args.kind == "all"
        and target_name in _stackctl.TEST_DATA_TARGETS
        and bool(test_data_request)
    ):
        runtime_workload = _stackctl._current_runtime_workload(target_name)
        if runtime_workload in {"content-release", "content-commercial"}:
            # content-release proves import/API/media via data-release bindings;
            # Provider/share/fault nonprod mutations require the full commercial
            # plane and must not block this workload.
            steps.append(
                {
                    "kind": "test-data",
                    "profile": profile.value,
                    "exitCode": 0,
                    "reportPath": "",
                    "details": [
                        f"skipped: active workload={runtime_workload}; "
                        "data-release ship verify is the content-plane evidence"
                    ],
                    "caseResult": {
                        "schema": "qwq.case_result",
                        "caseId": "alpha-beta-gamma-selected-test-data",
                        "status": "skipped",
                        "executed": 0,
                        "skipped": 1,
                        "target": target_name,
                        "environment": env_name,
                        "issues": [],
                    },
                }
            )
            if profile is VerificationProfile.RELEASE:
                issues.append(
                    "release test-data Journey requires the full runtime workload"
                )
        else:
            test_data_result = _stackctl._run_test_data_profile(
                args,
                profile=profile,
                environment=env_name,
                target_name=target_name,
                report_dir=report_dir,
                prerequisites_passed=test_data_prerequisites_passed,
                static_gate_ms=static_gate_ms,
                environment_start_ms=round(
                    (time.monotonic() - started_monotonic) * 1000
                ),
            )
            test_data_passed = (
                test_data_result.get("status") == "passed"
                and int(test_data_result.get("executed") or 0) > 0
                and int(test_data_result.get("skipped") or 0) == 0
            )
            steps.append(
                {
                    "kind": "test-data",
                    "profile": profile.value,
                    "exitCode": 0 if test_data_passed else 2,
                    "reportPath": _stackctl.relpath(
                        report_dir / "test-data/case-result.json"
                    ),
                    "details": list(test_data_result.get("issues") or []),
                    "caseResult": test_data_result,
                }
            )
            if not test_data_passed:
                details = list(test_data_result.get("issues") or [])
                issues.append(
                    "selected test-data verification failed: "
                    + ("; ".join(details) if details else "invalid CaseResult")
                )
    timing = _stackctl._finish_timing(started_monotonic, started_at)
    playback_evidence_path = ""
    if (
        profile is VerificationProfile.RELEASE
        and target_name
        in {"alpha-local", "beta-local", "gamma-local", "prod-sim", "prod-hosted"}
    ):
        playback_evidence = _stackctl._runtime_media_playback_evidence(
            target_name=target_name,
            steps=steps,
            started_at=timing["startedAt"],
            ended_at=timing["endedAt"],
        )
        playback_evidence_file = report_dir / "runtime_media_playback_evidence.json"
        _stackctl.write_json(playback_evidence_file, playback_evidence)
        playback_evidence_path = _stackctl.relpath(playback_evidence_file)
        if playback_evidence["status"] != "passed":
            issues.append(
                "runtime-media playback evidence is incomplete; "
                f"inspect {playback_evidence_path}",
            )
    blocked = bool(issues) and profile is VerificationProfile.RELEASE
    payload = {
        "status": "ok" if not issues else "failed",
        "command": "verify",
        "timestamp": _stackctl.utc_now(),
        "kind": args.kind,
        "profile": profile.value,
        "providerReadiness": provider_readiness,
        "evidenceEnvelope": evidence_envelope,
        "generationIssues": generation_issues,
        "staticGateMs": static_gate_ms,
        "profileGateMs": profile_gate_ms,
        "steps": steps,
        "runtimeMediaPlaybackEvidencePath": playback_evidence_path,
        **timing,
    }
    _stackctl.write_json(report_dir / "report.json", payload)
    _stackctl.write_json(report_dir / "findings.json", {"issues": issues})
    _stackctl._write_summary_bundle(
        report_dir,
        command="verify",
        target=target_name,
        status=payload["status"],
        summary=(
            "stackctl verify passed"
            if not issues
            else "stackctl verify is GATE_BLOCK"
            if blocked
            else "stackctl verify failed"
        ),
        details=issues or [f"ran {len(steps)} checks"],
        extra={"kind": args.kind, "profile": profile.value},
        timing=timing,
    )
    _stackctl._write_stdout_markdown(report_dir, stdout_sections)
    return {
        "exitCode": 0 if not issues else 2 if blocked else 1,
        "summary": (
            "stackctl verify passed"
            if not issues
            else "stackctl verify is GATE_BLOCK"
            if blocked
            else "stackctl verify failed"
        ),
        "details": issues or [f"ran {len(steps)} checks"],
        "reportDir": _stackctl.relpath(report_dir),
        "staticGateMs": static_gate_ms,
        "profileGateMs": profile_gate_ms,
        "evidenceEnvelope": evidence_envelope,
        **timing,
    }
