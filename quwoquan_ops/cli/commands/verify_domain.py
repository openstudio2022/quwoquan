"""stackctl `verify` 子命令域（argparse 表面、命令选择器与主编排）。

从 stackctl.py 逐字迁出：

- `register_parser`：`verify` 子命令的 argparse 表面（帮助文案与参数
  集合逐字节保持不变）；
- `_selected_verify_commands`：按 kind/profile 选择静态验证命令组
  （命令组真相源 `VERIFY_COMMAND_GROUPS` 仍由 stackctl 拥有）；
- `_selected_profile_commands`：按环境/target/profile 组合 profile 命令表
  （工厂本体在 `commands/verify_profiles.py`）；
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


def _selected_verify_commands(
    kind: str,
    env_name: str = "",
    *,
    target_name: str = "",
    profile: VerificationProfile,
) -> list[list[str]]:
    import quwoquan_ops.cli.stackctl as _stackctl

    packaging_commands = [
        ["python3", "quwoquan_ops/gate/verify_environment_packaging_contract.py"]
        + (["--env", env_name] if env_name in _stackctl.ENVIRONMENTS else []),
        ["python3", "quwoquan_ops/gate/verify_env_artifact_isolation.py"]
        + (["--env", env_name] if env_name in _stackctl.ENVIRONMENTS else []),
        [
            "python3",
            "quwoquan_app/scripts/env/verify_prod_package_purity.py",
            "--target",
            target_name
            if env_name == "prod" and target_name
            else _stackctl.DEFAULT_TARGET_BY_ENV["prod"],
        ],
    ]
    if target_name:
        packaging_commands[0].extend(["--target", target_name])
        packaging_commands[1].extend(["--target", target_name])
    if kind == "all":
        commands: list[list[str]] = []
        group_names = ("topology", "config")
        if profile is not VerificationProfile.BASELINE:
            group_names = (*group_names, "packaging")
        for group_name in group_names:
            if group_name == "packaging":
                commands.extend(packaging_commands)
                continue
            commands.extend(_stackctl.VERIFY_COMMAND_GROUPS[group_name])
        return commands
    if kind == "packaging":
        return packaging_commands
    return list(_stackctl.VERIFY_COMMAND_GROUPS[kind])


def _selected_profile_commands(
    env_name: str,
    target_name: str,
    profile: VerificationProfile,
    report_dir: Path | None = None,
    service: str = "",
    data_readiness_path: Path | None = None,
) -> list[dict[str, Any]]:
    import quwoquan_ops.cli.stackctl as _stackctl

    commands: list[dict[str, Any]] = []
    if profile.requires_environment and target_name in {
        "alpha-local",
        "beta-local",
        "gamma-local",
        "prod-sim",
    }:
        # verify is read-only with respect to package/build/deployment selection.
        # A missing or unhealthy runtime must block instead of triggering nested up.
        # Follow the active workload health scope: content-release must not be
        # forced through full commercial service probes.
        health_scope = _stackctl._current_runtime_health_scope(target_name)
        commands.append(
            {
                "name": f"{target_name}-health-preflight",
                "argv": [
                    "python3",
                    "quwoquan_ops/cli/stackctl.py",
                    "--output-format",
                    "json",
                    "health",
                    "--target",
                    target_name,
                    "--scope",
                    health_scope,
                ],
                "cwd": _stackctl.ROOT,
            }
        )
    domain_remote_api_command = (
        _stackctl._app_domain_remote_api_integration_profile_command(
            target_name,
            profile,
            report_dir,
        )
        if not service
        else None
    )
    if domain_remote_api_command is not None:
        commands.append(domain_remote_api_command)
    if service:
        if (
            service == "assistant-service"
            and target_name == "gamma-local"
            and profile
            in {
                VerificationProfile.INTEGRATION,
                VerificationProfile.RELEASE,
            }
        ):
            command = _stackctl._assistant_learning_gamma_api_integration_profile_command(
                target_name,
                profile,
                report_dir,
            )
            if command is not None:
                commands.append(command)
        if (
            service == "user-service"
            and target_name == "gamma-local"
            and profile
            in {
                VerificationProfile.INTEGRATION,
                VerificationProfile.RELEASE,
            }
        ):
            command = _stackctl._profile_proposal_gamma_api_integration_profile_command(
                target_name,
                profile,
                report_dir,
            )
            if command is not None:
                commands.append(command)
        return commands
    if profile is VerificationProfile.SMOKE:
        commands.extend(
            [
                {
                    "name": "content-media-url-tests",
                    "argv": [
                        "python3",
                        "quwoquan_app/scripts/env/run_flutter_test_guarded.py",
                        "test/local_contract/service/content_service/media/media_asset/content_media_url__local_contract_test.dart",
                        "test/local_contract/service/chat_service/chat/conversation/chat_avatar_url_resolution__local_contract_test.dart",
                    ],
                    "cwd": _stackctl.ROOT,
                },
            ]
        )
    if (
        profile in {VerificationProfile.INTEGRATION, VerificationProfile.RELEASE}
        and target_name in {"beta-local", "gamma-local", "prod-hosted"}
    ):
        commands.append(
            {
                "name": "filter-catalog-active-release",
                "argv": [
                    "python3",
                    "quwoquan_ops/cli/stackctl.py",
                    "--output-format",
                    "json",
                    "filter-catalog",
                    "--target",
                    target_name,
                    "--action",
                    "verify",
                ],
                "cwd": _stackctl.ROOT,
            }
        )
    report_feedback_command = _stackctl._report_feedback_lifecycle_profile_command(
        env_name,
        target_name,
        profile,
        report_dir,
    )
    if (
        report_feedback_command is not None
        and _stackctl._current_runtime_health_scope(target_name)
        not in {"content-consumer", "content-commercial"}
    ):
        # content-release 不启 notification/product-ops；举报回流依赖
        # /app-messages，只能在 full workload 上证明。
        commands.append(report_feedback_command)
    media_publication_command = _stackctl._media_publication_lifecycle_profile_command(
        env_name,
        target_name,
        profile,
        report_dir,
    )
    if media_publication_command is not None:
        commands.append(media_publication_command)
    chat_group_lifecycle_command = _stackctl._chat_group_lifecycle_profile_command(
        env_name,
        target_name,
        profile,
        report_dir,
    )
    if (
        chat_group_lifecycle_command is not None
        and _stackctl._current_runtime_health_scope(target_name)
        not in {"content-consumer", "content-commercial"}
    ):
        # content-release 不启 chat-service；建群到 inbox 旅程仅 full workload 证明。
        commands.append(chat_group_lifecycle_command)
    reliabletask_command = _stackctl._reliabletask_gamma_api_integration_profile_command(
        target_name,
        profile,
        report_dir,
    )
    if reliabletask_command is not None:
        commands.append(reliabletask_command)
    onboarding_author_impact_command = (
        _stackctl._onboarding_author_impact_gamma_api_integration_profile_command(
            target_name,
            profile,
            report_dir,
        )
    )
    if onboarding_author_impact_command is not None:
        commands.append(onboarding_author_impact_command)
    search_remote_api_command = _stackctl._search_remote_api_integration_profile_command(
        target_name,
        profile,
        report_dir,
        data_readiness_path=data_readiness_path,
    )
    if search_remote_api_command is not None:
        commands.append(search_remote_api_command)
    if profile is VerificationProfile.RELEASE:
        if target_name == "prod-hosted":
            target = _stackctl.get_target(_stackctl.load_environment_topology(), target_name)
            public_bases = target.get("publicBases") or {}
            commands.append(
                {
                    "name": "prod-public-health",
                    "argv": [
                        "python3",
                        "quwoquan_ops/cli/stackctl.py",
                        "--output-format",
                        "json",
                        "health",
                        "--target",
                        "prod-hosted",
                        "--scope",
                        "full",
                    ],
                    "env": {"CLOUD_GATEWAY_BASE_URL": str(public_bases["api"])},
                }
            )
        media_preflight_command = _stackctl._target_media_preflight_profile_command(
            target_name,
            report_dir,
            data_readiness_path=data_readiness_path,
        )
        if media_preflight_command is not None:
            commands.append(media_preflight_command)
        smoke_command = _stackctl._environment_page_smoke_profile_command(
            env_name,
            target_name,
            report_dir,
            data_readiness_path=data_readiness_path,
        )
        if smoke_command is not None:
            commands.append(smoke_command)
        if env_name in {"beta", "gamma"} and target_name in {
            "beta-local",
            "gamma-local",
        }:
            runtime_recovery_command = _stackctl._environment_page_smoke_profile_command(
                env_name,
                target_name,
                report_dir,
                suite_name="runtime-recovery-patrol",
                patrol_target=_stackctl.RUNTIME_RECOVERY_UAT_TEST_TARGET,
                persisted_device_session=True,
            )
            if runtime_recovery_command is not None:
                commands.append(runtime_recovery_command)
        if env_name == "gamma" and target_name == "gamma-local":
            account_enforcement_command = (
                _stackctl._account_enforcement_gamma_uat_profile_command(
                    target_name,
                    profile,
                    report_dir,
                )
            )
            if account_enforcement_command is not None:
                commands.append(account_enforcement_command)
            search_api_report = (
                report_dir
                / "search-remote-api-integration"
                / "search_remote_api_uat_report.json"
                if report_dir is not None
                else _stackctl.env_runs_root("gamma")
                / "search-remote-api-integration"
                / target_name
                / "search_remote_api_uat_report.json"
            )
            search_smoke_command = _stackctl._environment_page_smoke_profile_command(
                env_name,
                target_name,
                report_dir,
                suite_name="search-remote-patrol",
                patrol_target=(
                    "test/user_acceptance/journeys/cross_domain_search/"
                    "cross_domain_search_journey__user_acceptance_test.dart"
                ),
                remote_api_evidence_report=search_api_report,
            )
            if search_smoke_command is not None:
                commands.append(search_smoke_command)
    return commands


def command_verify(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

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
    phase = profile.readiness_phase

    def readiness_call() -> dict[str, Any]:
        assert phase is not None
        return _stackctl.command_content_readiness(
            argparse.Namespace(
                command="content-readiness",
                phase=phase.value,
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
        readiness_call=readiness_call if phase is not None else None,
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
    test_data_content_readiness_ready = True
    if phase is not None and readiness_payload is not None:
        steps.append(
            {
                "kind": "readiness",
                "phase": phase.value,
                "exitCode": readiness_payload["exitCode"],
                "reportDir": readiness_payload.get("reportDir", ""),
                "details": readiness_payload.get("details", []),
            }
        )
        if readiness_payload["exitCode"] != 0:
            test_data_content_readiness_ready = False
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
        test_data_package_ready and test_data_content_readiness_ready
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
        **timing,
    }
