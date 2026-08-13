"""stackctl verify 域按 kind 的子实现（legal-static / config-slo / service /
distribution / content-delivery）。

从 stackctl.py 逐字迁出仅被 `command_verify` 分发消费的 kind 实现：

- `_command_verify_legal_static` + `_legal_static_command`：四环境
  legal-static 包的 package→verify 闭环；
- `_command_verify_config_slo`：Prometheus 读回驱动的配置灰度 SLO 决策
  （拒绝人工数字旁路）；
- `_command_verify_service_environment`：单服务只读候选包验证与
  service-scoped profile 执行；
- `_official_distribution_root` / `_inspect_distribution_for_target` /
  `_command_verify_distribution`：Web/PWA 与 Android 官方分发检查；
- `_command_verify_content_delivery`：immutable Research 内容交付闭环；
- `_service_verify_report_action`：service verify 的报告目录动作名。

`_read_prometheus_slo` / `_SloSamplesInsufficient` / `_run_provider_readiness_preflight`
/ `command_package` 等仍由 stackctl 命名空间拥有（deploy / package 留守域
共用）。测试经 ``mock.patch.object(stackctl, ...)`` patch 本模块符号与
上述协作符号，因此函数体内一律经函数内延迟导入 `_stackctl` 属性访问
（含本模块符号互调），保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Mapping

from quwoquan_ops.cli.lib.content_release_readiness import (
    ProbeOutcome,
    VerificationProfile,
)

# 与 stackctl.ROOT 同源同值(仓库根);仅用于函数默认参数,
# 函数体内仍统一经 `_stackctl.ROOT` 访问。
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _legal_static_command(
    subcommand: str,
    env_name: str,
    *,
    target: str = "",
    source_root: Path = _REPO_ROOT,
    environment: Mapping[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    import quwoquan_ops.cli.stackctl as _stackctl

    cmd = [
        "python3",
        "quwoquan_ops/cli/legal_static.py",
        subcommand,
        "--env",
        env_name,
    ]
    if target:
        cmd.extend(["--target", target])
    command_environment = dict(environment or {})
    if target:
        command_environment["QWQ_DEPLOY_TARGET"] = target
    result = _stackctl.run(
        cmd,
        cwd=source_root,
        env=command_environment or None,
    )
    payload: dict[str, Any] = {}
    if result.stdout.strip():
        try:
            loaded = json.loads(result.stdout)
            if isinstance(loaded, dict):
                payload = loaded
        except json.JSONDecodeError:
            payload = {}
    payload.setdefault("argv", cmd)
    payload.setdefault("exitCode", result.returncode)
    return result, payload


def _command_verify_legal_static(
    args: argparse.Namespace,
    profile: VerificationProfile,
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    env_name = args.env or (_stackctl.get_target(_stackctl.load_environment_topology(), args.target).get("env") if args.target else "all")
    target_name = args.target or (_stackctl.DEFAULT_TARGET_BY_ENV[env_name] if env_name in _stackctl.ENVIRONMENTS else "repo")
    report_dir = _stackctl.resolve_report_dir(args, env_name if env_name in _stackctl.ENVIRONMENTS else "repo", target_name)
    started_monotonic, started_at = _stackctl._start_timing()
    package_envs = [env_name] if env_name in _stackctl.ENVIRONMENTS else list(_stackctl.ENVIRONMENTS)
    steps: list[dict[str, Any]] = []
    issues: list[str] = []
    stdout_sections: list[tuple[str, str]] = []

    for package_env in package_envs:
        package_args = argparse.Namespace(
            command="package",
            kind="legal-static",
            env=package_env,
            service="",
            include_services=False,
            target=args.target or _stackctl.DEFAULT_TARGET_BY_ENV[package_env],
            output_format="json",
            report_dir=str(report_dir / f"package-{package_env}"),
        )
        package_payload = _stackctl.command_package(package_args)
        steps.append(
            {
                "kind": "package",
                "packageKind": "legal-static",
                "env": package_env,
                "exitCode": package_payload["exitCode"],
                "details": package_payload.get("details", []),
                "reportDir": package_payload.get("reportDir", ""),
            }
        )
        if package_payload["exitCode"] != 0:
            issues.append(
                f"legal-static package failed for {package_env}: "
                + "; ".join(package_payload.get("details", []))
            )
            continue

        verify_result, verify_payload = _stackctl._legal_static_command(
            "verify-package",
            package_env,
            target=package_args.target,
        )
        steps.append(
            {
                "kind": "verify",
                "packageKind": "legal-static",
                "env": package_env,
                "exitCode": verify_result.returncode,
                "stdout": verify_result.stdout,
                "stderr": verify_result.stderr,
                "payload": verify_payload,
            }
        )
        stdout_sections.append(
            (
                f"legal-static-verify:{package_env}",
                "\n".join(filter(None, [verify_result.stdout, verify_result.stderr])),
            )
        )
        if verify_result.returncode != 0:
            verify_issues = verify_payload.get("issues") if isinstance(verify_payload.get("issues"), list) else []
            detail = "; ".join(str(issue) for issue in verify_issues)
            issues.append(
                f"legal-static verify failed for {package_env}: "
                + (detail or verify_result.stderr.strip() or verify_result.stdout.strip())
            )

    timing = _stackctl._finish_timing(started_monotonic, started_at)
    blocked = bool(issues) and (
        profile is VerificationProfile.RELEASE
        or (
            profile is VerificationProfile.INTEGRATION
            and args.kind == "all"
            and target_name in _stackctl.TEST_DATA_TARGETS
        )
    )
    payload = {
        "status": (
            "ok"
            if not issues
            else ProbeOutcome.GATE_BLOCK.value
            if blocked
            else "failed"
        ),
        "command": "verify",
        "kind": "legal-static",
        "profile": profile.value,
        "timestamp": _stackctl.utc_now(),
        "steps": steps,
        **timing,
    }
    _stackctl.write_json(report_dir / "report.json", payload)
    _stackctl.write_json(report_dir / "findings.json", {"issues": issues})
    _stackctl._write_summary_bundle(
        report_dir,
        command="verify",
        target=target_name,
        status=payload["status"],
        summary="stackctl legal-static verify passed" if not issues else "stackctl legal-static verify failed",
        details=issues or [f"ran {len(steps)} legal-static checks"],
        extra={"kind": "legal-static", "profile": profile.value},
        timing=timing,
    )
    _stackctl._write_stdout_markdown(report_dir, stdout_sections)
    return {
        "exitCode": 0 if not issues else 1,
        "summary": "stackctl legal-static verify passed" if not issues else "stackctl legal-static verify failed",
        "details": issues or [f"ran {len(steps)} legal-static checks"],
        "reportDir": _stackctl.relpath(report_dir),
        **timing,
    }


def _command_verify_config_slo(args: argparse.Namespace) -> dict[str, Any]:
    """以 stackctl 作为配置灰度 SLO 决策的唯一公开入口。

    SLO 数值只从 Prometheus 读回（最小样本与窗口由 slo_thresholds.yaml
    策略约束）；调用方直接传数字属于被 OPEN-004 关闭的旁路，命中即失败。
    """
    import quwoquan_ops.cli.stackctl as _stackctl

    report_dir = _stackctl.resolve_report_dir(args, "prod", "prod-hosted")
    started_monotonic, started_at = _stackctl._start_timing()

    def _config_slo_failure(details: list[str], *, exit_code: int = 2) -> dict[str, Any]:
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        _stackctl._write_summary_bundle(
            report_dir,
            command="verify",
            target="prod-hosted",
            status="failed",
            summary="stackctl config-slo verification failed",
            details=details,
            extra={"kind": "config-slo"},
            timing=timing,
        )
        return {
            "exitCode": exit_code,
            "summary": "stackctl config-slo verification failed",
            "details": details,
            "reportDir": _stackctl.relpath(report_dir),
            **timing,
        }

    manual_values = [
        flag
        for flag, value in (
            ("--error-rate", str(getattr(args, "error_rate", "") or "").strip()),
            ("--p95-ms", str(getattr(args, "p95_ms", "") or "").strip()),
            (
                "--redis-error-rate",
                str(getattr(args, "redis_error_rate", "") or "").strip(),
            ),
        )
        if value
    ]
    if manual_values:
        return _config_slo_failure(
            [
                "config-slo rejects caller-supplied SLO numbers: "
                + ", ".join(manual_values),
                "provide --prometheus-url; values are read back from monitoring only",
            ]
        )
    prometheus_url = str(getattr(args, "prometheus_url", "") or "").strip()
    if not prometheus_url:
        return _config_slo_failure(
            ["config-slo requires --prometheus-url for real monitoring readback"]
        )
    try:
        slo_readback = _stackctl._read_prometheus_slo(
            prometheus_url,
            "content-service",
            deadline_epoch=int(time.time()) + 120,
        )
    except _stackctl._SloSamplesInsufficient as error:
        return _config_slo_failure(
            ["decision=pause reason=insufficient_samples", str(error)],
            exit_code=10,
        )
    except RuntimeError as error:
        return _config_slo_failure([f"Prometheus SLO readback failed: {error}"])
    values = {
        "--error-rate": str(slo_readback["values"]["errorRate"]),
        "--p95-ms": str(slo_readback["values"]["p95Ms"]),
        "--redis-error-rate": str(slo_readback["values"]["redisErrorRate"]),
    }
    _stackctl.write_json(report_dir / "slo_readback.json", slo_readback)
    command = ["bash", "quwoquan_ops/cli/prod/config_release_slo_gate.sh"]
    for flag, value in values.items():
        command.extend((flag, value))
    result = _stackctl.run(command)
    timing = _stackctl._finish_timing(started_monotonic, started_at)
    details = _stackctl._command_details(result)
    status = "ok" if result.returncode == 0 else "failed"
    _stackctl.write_json(
        report_dir / "report.json",
        {
            "status": status,
            "command": "verify",
            "kind": "config-slo",
            "target": "prod-hosted",
            "argv": command,
            "exitCode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            **timing,
        },
    )
    _stackctl._write_summary_bundle(
        report_dir,
        command="verify",
        target="prod-hosted",
        status=status,
        summary=(
            "stackctl config-slo verification passed"
            if status == "ok"
            else "stackctl config-slo verification failed"
        ),
        details=details,
        extra={"kind": "config-slo"},
        timing=timing,
    )
    _stackctl._write_stdout_markdown(
        report_dir,
        [("config-slo", "\n".join(filter(None, [result.stdout, result.stderr])))],
    )
    return {
        "exitCode": result.returncode,
        "summary": (
            "stackctl config-slo verification passed"
            if status == "ok"
            else "stackctl config-slo verification failed"
        ),
        "details": details,
        "reportDir": _stackctl.relpath(report_dir),
        **timing,
    }


def _command_verify_service_environment(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    if not args.env:
        return {
            "exitCode": 2,
            "summary": "stackctl verify --service requires --env",
            "details": [],
        }
    env_name = args.env
    target_name = args.target or _stackctl.DEFAULT_TARGET_BY_ENV[env_name]
    profile = VerificationProfile(args.profile)
    report_dir = (
        Path(args.report_dir)
        if args.report_dir
        else _stackctl.artifact_run_dir(
            env_name,
            _stackctl._service_verify_report_action(
                args.command,
                args.service,
                profile,
            ),
            target=target_name,
        )
    )
    started_monotonic, started_at = _stackctl._start_timing()
    issues: list[str] = []
    steps: list[dict[str, Any]] = []
    package_dir: Path | None = None
    package_digest_before = ""
    try:
        active_candidate = _stackctl.active_deployment_candidate(target_name)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        active_candidate = None
        issues.append(f"active immutable candidate is invalid: {error}")
    if active_candidate is None and not issues:
        issues.append(
            f"active immutable candidate is required for read-only service verification: {target_name}"
        )
    if active_candidate is not None:
        package_dir = _stackctl.service_deployment_package_dir(
            env_name,
            args.service,
            target=target_name,
        )
        expected_package_dir = (
            Path(active_candidate["candidateDir"])
            / "packages"
            / "services"
            / args.service
        ).resolve()
        if package_dir.resolve() != expected_package_dir:
            issues.append("service package is not owned by the active immutable candidate")
        elif package_dir.is_dir():
            package_digest_before = _stackctl._sha256_tree(package_dir)
        steps.append(
            {
                "kind": "candidate-package",
                "mode": "read-only",
                "target": target_name,
                "baselineId": active_candidate["baselineId"],
                "packageDir": str(package_dir),
                "contentDigestBefore": package_digest_before,
            }
        )
    required = (
        (
            package_dir / "image.lock",
            package_dir / "config/config.yaml",
            package_dir / "manifests/all.yaml",
            package_dir / "provenance.json",
        )
        if package_dir is not None
        else ()
    )
    for path in required:
        if not path.is_file():
            issues.append(f"missing service package artifact: {path}")
    if not issues:
        try:
            provenance = json.loads((package_dir / "provenance.json").read_text(encoding="utf-8"))
            if provenance.get("service") != args.service or provenance.get("environment") != env_name:
                issues.append("service package provenance identity mismatch")
            for value in (provenance.get("digests") or {}).values():
                if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(value)):
                    issues.append(f"invalid package digest: {value}")
        except (OSError, json.JSONDecodeError, TypeError) as error:
            issues.append(f"invalid service package provenance: {error}")
    if (
        not issues
        and profile is VerificationProfile.RELEASE
        and env_name in {"gamma", "prod"}
    ):
        provider_preflight = _stackctl._run_provider_readiness_preflight(
            env_name,
            report_dir,
        )
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
            issues.extend(provider_preflight["details"])
    if not issues:
        for profile_command in _stackctl._selected_profile_commands(
            env_name,
            target_name,
            profile,
            report_dir,
            service=args.service,
            data_readiness_path=_stackctl._data_readiness_path_from_verify_args(
                args,
                environment=env_name,
                profile=profile,
            ),
        ):
            profile_result = _stackctl.run(
                profile_command["argv"],
                cwd=profile_command.get("cwd"),
                env=profile_command.get("env"),
            )
            blocking = bool(profile_command.get("blocking", True))
            steps.append(
                {
                    "kind": "profile",
                    "profile": profile.value,
                    "name": profile_command["name"],
                    "argv": profile_command["argv"],
                    "exitCode": profile_result.returncode,
                    "blocking": blocking,
                    "reportPath": profile_command.get("reportPath", ""),
                    "stdout": profile_result.stdout,
                    "stderr": profile_result.stderr,
                }
            )
            if profile_result.returncode != 0 and blocking:
                issues.append(
                    f"{profile_command['name']} failed: "
                    + (
                        profile_result.stderr.strip()
                        or profile_result.stdout.strip()
                        or "unknown profile failure"
                    )
                )
                if profile_command.get("stopOnFailure"):
                    break
    if package_dir is not None and package_digest_before:
        if not package_dir.is_dir():
            issues.append("active immutable service package disappeared during verification")
            package_digest_after = ""
        else:
            package_digest_after = _stackctl._sha256_tree(package_dir)
            if package_digest_after != package_digest_before:
                issues.append("active immutable service package changed during verification")
        steps[0]["contentDigestAfter"] = package_digest_after
        steps[0]["unchanged"] = package_digest_after == package_digest_before
    timing = _stackctl._finish_timing(started_monotonic, started_at)
    payload = {
        "status": "ok" if not issues else "failed",
        "command": "verify",
        "service": args.service,
        "environment": env_name,
        "profile": profile.value,
        "packageDir": str(package_dir) if package_dir is not None else "",
        "steps": steps,
        "issues": issues,
        **timing,
    }
    _stackctl.write_json(report_dir / "report.json", payload)
    return {
        "exitCode": 0 if not issues else 1,
        "summary": (
            f"stackctl verify passed for {args.service}/{env_name}"
            if not issues
            else f"stackctl verify failed for {args.service}/{env_name}"
        ),
        "details": issues
        or [f"package and {profile.value} profile verified: {package_dir}"],
        "reportDir": _stackctl.relpath(report_dir),
        **timing,
    }


def _service_verify_report_action(
    command: str,
    service: str,
    profile: VerificationProfile,
) -> str:
    return f"{command}-{service}-{profile.value}"


def _official_distribution_root(
    args: argparse.Namespace,
    *,
    target_name: str,
) -> tuple[Path, bool]:
    import quwoquan_ops.cli.stackctl as _stackctl

    configured = str(
        getattr(args, "distribution_root", "")
        or os.environ.get("QWQ_DISTRIBUTION_ROOT", "")
    ).strip()
    if configured:
        return Path(configured).expanduser().resolve(), True
    return _stackctl.deployment_target_path(target_name, "distribution-origin"), False


def _inspect_distribution_for_target(
    args: argparse.Namespace,
    *,
    target_name: str,
) -> tuple[dict[str, Any], Path, bool]:
    import quwoquan_ops.cli.stackctl as _stackctl

    topology = _stackctl.load_environment_topology()
    target = _stackctl.get_target(topology, target_name)
    public_bases = target.get("publicBases") or {}
    distribution_root, explicitly_configured = _stackctl._official_distribution_root(
        args,
        target_name=target_name,
    )
    inspection = _stackctl.inspect_official_distribution(
        distribution_root=distribution_root,
        public_origin=str(public_bases.get("publicWeb") or ""),
        download_origin=str(public_bases.get("appDownload") or ""),
        verify_hosted=bool(getattr(args, "verify_hosted", False)),
    )
    if target_name == "prod-hosted" and not explicitly_configured:
        inspection["status"] = ProbeOutcome.GATE_BLOCK.value
        inspection.setdefault("issues", []).append(
            "prod distribution inspection requires QWQ_DISTRIBUTION_ROOT or --distribution-root"
        )
    inspection["distributionRoot"] = str(distribution_root)
    inspection["explicitlyConfigured"] = explicitly_configured
    return inspection, distribution_root, explicitly_configured


def _command_verify_distribution(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    env_name = args.env or (
        str(_stackctl.get_target(_stackctl.load_environment_topology(), args.target).get("env"))
        if args.target
        else ""
    )
    if env_name not in _stackctl.ENVIRONMENTS:
        return {
            "exitCode": 2,
            "summary": "stackctl verify distribution requires --env or --target",
            "details": ["distribution verification is environment-scoped"],
        }
    target_name = args.target or _stackctl.DEFAULT_TARGET_BY_ENV[env_name]
    report_dir = _stackctl.resolve_report_dir(args, env_name, target_name)
    started_monotonic, started_at = _stackctl._start_timing()
    try:
        inspection, _, _ = _stackctl._inspect_distribution_for_target(
            args,
            target_name=target_name,
        )
        issues = list(inspection.get("issues") or [])
    except (OSError, ValueError, _stackctl.OfficialDistributionReleaseError) as error:
        inspection = {"status": ProbeOutcome.GATE_BLOCK.value, "issues": [str(error)]}
        issues = [str(error)]
    timing = _stackctl._finish_timing(started_monotonic, started_at)
    _stackctl.write_json(
        report_dir / "distribution.json",
        {"command": "verify", "kind": "distribution", **inspection, **timing},
    )
    _stackctl.write_json(report_dir / "findings.json", {"issues": issues})
    return {
        "exitCode": 0 if not issues else 2,
        "summary": (
            f"stackctl distribution verification passed for {target_name}"
            if not issues
            else f"stackctl distribution verification is GATE_BLOCK for {target_name}"
        ),
        "details": issues or ["Web/PWA and Android distribution are ready"],
        "reportDir": _stackctl.relpath(report_dir),
        **timing,
    }


def _command_verify_content_delivery(args: argparse.Namespace) -> dict[str, Any]:
    """Verify only the immutable Research content delivery closure."""
    import quwoquan_ops.cli.stackctl as _stackctl

    environment = str(getattr(args, "env", "") or "").strip()
    profile = str(getattr(args, "profile", "") or "").strip()
    release_id = str(getattr(args, "data_release_id", "") or "").strip()
    verify_run_id = str(
        getattr(args, "data_verify_run_id", "") or ""
    ).strip()
    manifest_digest = str(
        getattr(args, "data_manifest_digest", "") or ""
    ).strip()
    missing = [
        label
        for label, value in (
            ("--env", environment),
            ("--data-release-id", release_id),
            ("--data-verify-run-id", verify_run_id),
            ("--data-manifest-digest", manifest_digest),
        )
        if not value
    ]
    if profile != VerificationProfile.INTEGRATION.value:
        return {
            "exitCode": 2,
            "summary": "content-delivery requires --profile integration",
            "details": [
                "Provider, device UAT and commercial rollout are outside this check"
            ],
        }
    if environment not in {"alpha", "beta", "gamma"} or missing:
        return {
            "exitCode": 2,
            "summary": "content-delivery arguments are incomplete",
            "details": missing
            or ["content-delivery supports alpha, beta or gamma"],
        }
    report_dir = _stackctl.resolve_report_dir(
        args,
        environment,
        str(getattr(args, "target", "") or _stackctl.DEFAULT_TARGET_BY_ENV[environment]),
    )
    readiness_path = _stackctl._data_release_readiness_path(
        environment=environment,
        release_id=release_id,
        verify_run_id=verify_run_id,
    )
    report = _stackctl.verify_content_delivery(
        output_root=_stackctl.output_root(),
        readiness_path=readiness_path,
        environment=environment,
        release_id=release_id,
        manifest_digest=manifest_digest,
    )
    _stackctl.write_json(report_dir / "report.json", report)
    passed = report["result"] == "ready"
    details = list(report.get("issues") or [])
    if passed:
        counts = report.get("counts") or {}
        details = [
            "delivery ready: "
            f"posts={counts.get('manifestPosts', 0)} "
            f"homepages={counts.get('homepages', 0)} "
            f"personas={counts.get('personas', 0)}"
        ]
    return {
        "exitCode": 0 if passed else 1,
        "summary": (
            "content delivery verification passed"
            if passed
            else "content delivery verification failed"
        ),
        "details": details,
        "reportDir": _stackctl.relpath(report_dir),
    }
