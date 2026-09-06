"""stackctl `deploy` 子命令域入口: 服务环境部署、environment assembly、
prod prevalidation（不可提升）与官方分发部署的分发器。

从 stackctl.py 逐字迁出（改写规则与 down_domain 相同）:
- `command_deploy` 与 `_command_deploy_service_environment` /
  `_command_environment_assembly` / `_command_deploy_distribution`;
- prevalidation: `_prod_prevalidation_executor` /
  `_validate_prod_prevalidation_public_bases` / `_command_prod_prevalidate`。

`_command_deploy_with_lock` 在 `commands/deploy_rollout.py`。

测试经 ``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号，
因此函数体内一律经函数内延迟导入 `_stackctl` 属性访问（含本模块符号互调），
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
import urllib
import urllib.error
import urllib.parse
import urllib.request

from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4


def _command_deploy_service_environment(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    env_name = args.env
    target_name = args.target or _stackctl.DEFAULT_TARGET_BY_ENV[env_name]
    report_dir = _stackctl.resolve_report_dir(args, env_name, target_name)
    started_monotonic, started_at = _stackctl._start_timing()
    package_command = [
        "bash",
        "quwoquan_service/scripts/runtime/packaging/build_service_env_package.sh",
        "--service",
        args.service,
        "--env",
        env_name,
    ]
    package_result = _stackctl.run(package_command, env={"QWQ_DEPLOY_TARGET": target_name})
    if package_result.returncode != 0:
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        return {
            "exitCode": package_result.returncode,
            "summary": f"stackctl deploy packaging failed for {args.service}/{env_name}",
            "details": [package_result.stderr.strip() or package_result.stdout.strip()],
            **timing,
        }
    manifest = _stackctl.service_deployment_package_dir(
        env_name,
        args.service,
        target=target_name,
    ) / "manifests/all.yaml"
    dry_run = str(getattr(args, "dry_run", "false")).strip().lower() == "true"
    if env_name == "prod" and not dry_run:
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        return {
            "exitCode": 2,
            "summary": "stackctl service deploy blocked: prod requires the rollout transaction command",
            "details": ["use --target prod-hosted with ProdActivationAdmission and SLO readback"],
            **timing,
        }
    apply_command = ["kubectl", "apply", "-f", str(manifest)]
    if dry_run:
        apply_command.extend(["--dry-run=client"])
    apply_result = _stackctl.run(apply_command)
    timing = _stackctl._finish_timing(started_monotonic, started_at)
    payload = {
        "status": "ok" if apply_result.returncode == 0 else "failed",
        "command": "deploy",
        "service": args.service,
        "environment": env_name,
        "dryRun": dry_run,
        "manifest": str(manifest),
        "apply": {
            "argv": apply_command,
            "exitCode": apply_result.returncode,
            "stdout": apply_result.stdout,
            "stderr": apply_result.stderr,
        },
        **timing,
    }
    _stackctl.write_json(report_dir / "report.json", payload)
    return {
        "exitCode": apply_result.returncode,
        "summary": (
            f"stackctl deploy completed for {args.service}/{env_name}"
            if apply_result.returncode == 0
            else f"stackctl deploy failed for {args.service}/{env_name}"
        ),
        "details": _stackctl._command_details(apply_result),
        "reportDir": _stackctl.relpath(report_dir),
        **timing,
    }


def _command_environment_assembly(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    env_name = str(getattr(args, "env", "") or "").strip()
    if env_name not in {"beta", "gamma"} or getattr(args, "target", ""):
        return {
            "exitCode": 2,
            "summary": "stackctl environment assembly failed",
            "details": [
                "environment-assembly requires --env beta|gamma and no --target"
            ],
        }
    target_name = _stackctl.DEFAULT_TARGET_BY_ENV[env_name]
    report_dir = _stackctl.resolve_report_dir(args, env_name, target_name)
    started_monotonic, started_at = _stackctl._start_timing()
    command = ["bash", "quwoquan_ops/cli/shared/deploy_integration_k8s.sh"]
    result = _stackctl.run(command, env={"DEPLOY_ENV": env_name})
    timing = _stackctl._finish_timing(started_monotonic, started_at)
    details = _stackctl._command_details(result)
    status = "ok" if result.returncode == 0 else "failed"
    _stackctl.write_json(
        report_dir / "report.json",
        {
            "status": status,
            "command": "deploy",
            "operation": "environment-assembly",
            "env": env_name,
            "target": target_name,
            "argv": command,
            "exitCode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            **timing,
        },
    )
    _stackctl._write_summary_bundle(
        report_dir,
        command="deploy",
        target=target_name,
        status=status,
        summary=(
            f"stackctl environment assembly completed for {env_name}"
            if status == "ok"
            else f"stackctl environment assembly failed for {env_name}"
        ),
        details=details,
        extra={"env": env_name, "operation": "environment-assembly"},
        timing=timing,
    )
    return {
        "exitCode": result.returncode,
        "summary": (
            f"stackctl environment assembly completed for {env_name}"
            if status == "ok"
            else f"stackctl environment assembly failed for {env_name}"
        ),
        "details": details,
        "reportDir": _stackctl.relpath(report_dir),
        **timing,
    }


def _prod_prevalidation_executor(
    args: argparse.Namespace,
    *,
    manifest_path: Path,
    image_transport_tag: str,
    candidate_digest: str,
    dry_run: bool,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    import quwoquan_ops.cli.stackctl as _stackctl

    argv = [
        "python3",
        "quwoquan_ops/cli/prod/prevalidate_prod_hosted.py",
        "--frozen-diagnostic-snapshot",
        str(manifest_path),
        "--image-transport-tag",
        image_transport_tag,
        "--candidate-digest",
        candidate_digest,
        "--data-mode",
        str(args.data_mode),
        "--scope",
        str(args.prevalidate_scope),
    ]
    if args.ssh_host:
        argv.extend(["--host", str(args.ssh_host)])
    for host_id in getattr(args, "host_id", []) or []:
        argv.extend(["--host-id", str(host_id)])
    if dry_run:
        argv.append("--dry-run")
    result = _stackctl.run(argv)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = {
            "containerDeployment": {
                "status": "GATE_BLOCK",
                "issues": [
                    result.stderr.strip()
                    or result.stdout.strip()
                    or "prevalidation executor returned no JSON"
                ],
            },
            "releaseEligibility": {
                "status": "GATE_BLOCK",
                "promotable": False,
                "ledgerWritten": False,
                "receiptWritten": False,
            },
        }
    return result, payload


def _validate_prod_prevalidation_public_bases() -> None:
    import quwoquan_ops.cli.stackctl as _stackctl

    topology = _stackctl.load_environment_topology()
    target = _stackctl.get_target(topology, "prod-hosted")
    public_bases = target.get("publicBases") or {}
    for name, value in public_bases.items():
        parsed = urllib.parse.urlparse(str(value))
        host = parsed.hostname or ""
        if (
            parsed.scheme not in {"https", "wss"}
            or not host
            or re.fullmatch(r"\d+(?:\.\d+){3}", host)
            or host.endswith((".test", ".example", ".localhost"))
        ):
            raise RuntimeError(
                f"prod-hosted publicBases.{name} must remain canonical public HTTPS DNS"
            )


def _command_prod_prevalidate(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    report_dir = _stackctl.resolve_report_dir(args, "prod", "prod-hosted")
    started_monotonic, started_at = _stackctl._start_timing()
    timing: dict[str, Any]
    request_issues: list[str] = []
    formal_fields = {
        name: str(getattr(args, name, "") or "").strip()
        for name in (
            "stage",
            "service",
            "from_candidate_digest",
            "to_candidate_digest",
            "step",
            "prometheus_url",
            "release_image_digest",
            "release_config_digest",
            "contract_graph_digest",
            "adapter_digest",
            "prod_activation_admission",
        )
    }
    if args.target != "prod-hosted" or args.env:
        request_issues.append("prevalidate requires --target prod-hosted and no --env")
    if args.prevalidate_scope != "first-party":
        request_issues.append("prevalidate requires --prevalidate-scope first-party")
    if args.data_mode not in {"isolated", "external"}:
        request_issues.append("prevalidate requires --data-mode isolated|external")
    if any(formal_fields.values()):
        names = sorted(name.replace("_", "-") for name, value in formal_fields.items() if value)
        request_issues.append(
            "prevalidate rejects formal rollout/SLO/rollback arguments: " + ", ".join(names)
        )
    ssh_host = str(args.ssh_host or "").strip()
    if ssh_host and (
        "://" in ssh_host
        or re.fullmatch(r"[A-Za-z0-9.-]+", ssh_host) is None
    ):
        request_issues.append("prevalidate --ssh-host must be a valid SSH-only host")
    try:
        _stackctl._validate_prod_prevalidation_public_bases()
    except RuntimeError as error:
        request_issues.append(str(error))

    manifest_value = str(
        getattr(args, "frozen_diagnostic_snapshot", "") or ""
    ).strip()
    manifest_path = (
        Path(manifest_value).expanduser().resolve()
        if manifest_value and not manifest_value.startswith("oci://")
        else _stackctl.ROOT
    )
    artifact_digest = ""
    manifest_payload: dict[str, Any] = {}
    image_transport_tag = "unresolved"
    candidate_digest = "unresolved"
    if not manifest_value:
        request_issues.append("immutable Service Pipeline --frozen-diagnostic-snapshot is required")
    else:
        try:
            (
                manifest_path,
                artifact_digest,
                manifest_payload,
                image_transport_tag,
                candidate_digest,
            ) = _stackctl._frozen_diagnostic_snapshot(manifest_value)
        except RuntimeError as error:
            request_issues.append(str(error))

    host_payload: dict[str, Any] = {}
    host_result: subprocess.CompletedProcess[str] | None = None
    if args.data_mode and args.prevalidate_scope:
        host_result, host_payload = _stackctl._prod_prevalidation_executor(
            args,
            manifest_path=manifest_path,
            image_transport_tag=image_transport_tag,
            candidate_digest=candidate_digest,
            dry_run=True,
        )
        host_issues = (
            (host_payload.get("hostPreflight") or {}).get("issues")
            or (host_payload.get("containerDeployment") or {}).get("issues")
            or []
        )
        request_issues.extend(str(item) for item in host_issues if str(item) not in request_issues)

    deployment_payload = host_payload.get("containerDeployment") or {
        "status": "not-run"
    }
    package_step: dict[str, Any] | None = None
    executor_step: dict[str, Any] | None = None
    dry_run = str(getattr(args, "dry_run", "false")).strip().lower() == "true"
    exit_code = 2 if request_issues else 0
    if not request_issues:
        package_result = _stackctl.run(
            [
                "python3",
                "quwoquan_ops/cli/stackctl.py",
                "package",
                "--env",
                "prod",
                "--target",
                "prod-hosted",
                "--include-services",
            ],
            env={"QWQ_PROD_RELEASE_ARTIFACT_ROOT": str(manifest_path.parent)},
        )
        package_step = {
            "exitCode": package_result.returncode,
            "stdout": package_result.stdout,
            "stderr": package_result.stderr,
        }
        if package_result.returncode != 0:
            exit_code = package_result.returncode or 2
            request_issues.append(
                package_result.stderr.strip()
                or package_result.stdout.strip()
                or "prod package failed"
            )
            deployment_payload = {
                "status": "GATE_BLOCK",
                "issues": list(request_issues),
            }
        elif not dry_run:
            executor_result, executor_payload = _stackctl._prod_prevalidation_executor(
                args,
                manifest_path=manifest_path,
                image_transport_tag=image_transport_tag,
                candidate_digest=candidate_digest,
                dry_run=False,
            )
            executor_step = {
                "exitCode": executor_result.returncode,
                "stderr": executor_result.stderr,
            }
            deployment_payload = executor_payload.get("containerDeployment") or {
                "status": "GATE_BLOCK"
            }
            exit_code = executor_result.returncode
            if exit_code != 0:
                request_issues.extend(
                    str(item)
                    for item in deployment_payload.get("issues") or []
                    if str(item) not in request_issues
                )

    release_eligibility = {
        "status": "GATE_BLOCK",
        "promotable": False,
        "ledgerWritten": False,
        "receiptWritten": False,
        "reason": (
            "first-party container prevalidation cannot satisfy Provider, SFU, "
            "production data, observability, disaster recovery, or rollout evidence"
        ),
    }
    access = _stackctl.load_json_yaml(
        _stackctl.ROOT / "quwoquan_ops/environments/prod/access-isolation.yaml"
    )
    prevalidation = access.get("prevalidation") if isinstance(access, dict) else {}
    excluded = prevalidation.get("excluded") if isinstance(prevalidation, dict) else {}
    provider_readiness = host_payload.get("providerReadiness") or {
        "status": "GATE_BLOCK",
        "excludedCapabilities": list(
            (excluded.get("capabilities") or [])
            if isinstance(excluded, dict)
            else []
        ),
    }
    timing = _stackctl._finish_timing(started_monotonic, started_at)
    report = {
        "schema": "prod-hosted-first-party-prevalidation-report",
        "command": "deploy",
        "target": "prod-hosted",
        "mode": "prevalidate",
        "sshHost": ssh_host,
        "dataMode": str(args.data_mode),
        "scope": str(args.prevalidate_scope),
        "dryRun": dry_run,
        "releaseEvidence": {
            "path": str(manifest_path) if manifest_value else "",
            "artifactDigest": artifact_digest,
            "candidateId": manifest_payload.get("candidateId") or "",
            "source": manifest_payload.get("source") or {},
        },
        "hostPreflight": host_payload.get("hostPreflight") or {},
        "containerDeployment": deployment_payload,
        "providerReadiness": provider_readiness,
        "releaseEligibility": release_eligibility,
        "issues": request_issues,
        "package": package_step,
        "executor": executor_step,
        **timing,
    }
    _stackctl.write_json(report_dir / "report.json", report)
    status = "ok" if exit_code == 0 else "gate_block"
    details = [
        f"containerDeployment={deployment_payload.get('status', 'unknown')}",
        f"providerReadiness={provider_readiness.get('status', 'GATE_BLOCK')}",
        "releaseEligibility=GATE_BLOCK",
        *request_issues,
    ]
    _stackctl._write_summary_bundle(
        report_dir,
        command="deploy",
        target="prod-hosted",
        status=status,
        summary=(
            "stackctl prod-hosted first-party prevalidation completed"
            if exit_code == 0
            else "stackctl prod-hosted first-party prevalidation is GATE_BLOCK"
        ),
        details=details,
        extra={
            "mode": "prevalidate",
            "containerDeployment": deployment_payload.get("status"),
            "providerReadiness": provider_readiness.get("status", "GATE_BLOCK"),
            "releaseEligibility": "GATE_BLOCK",
        },
        timing=timing,
    )
    return {
        "exitCode": exit_code,
        "summary": (
            "stackctl prod-hosted first-party prevalidation completed; release remains GATE_BLOCK"
            if exit_code == 0
            else "stackctl prod-hosted first-party prevalidation is GATE_BLOCK"
        ),
        "details": details,
        "reportDir": _stackctl.relpath(report_dir),
        "containerDeployment": deployment_payload.get("status"),
        "providerReadiness": provider_readiness.get("status", "GATE_BLOCK"),
        "releaseEligibility": "GATE_BLOCK",
        **timing,
    }


def _controlled_distribution_input_root(value: str, *, option: str) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError(f"{option} is required")
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"{option} must be an absolute controlled path")
    if candidate.is_symlink():
        raise ValueError(f"{option} must not be a symbolic link")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"{option} must be an existing controlled directory") from error
    if resolved != candidate or not resolved.is_dir():
        raise ValueError(f"{option} must be one canonical symlink-free controlled directory")
    return resolved


def _official_distribution_graph_root_argument(value: str) -> Path:
    try:
        return _controlled_distribution_input_root(
            value,
            option="--official-distribution-graph-root",
        )
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _app_factory_root_argument(value: str) -> Path:
    try:
        return _controlled_distribution_input_root(
            value,
            option="--app-factory-root",
        )
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _stable_tag_admission_argument(value: str) -> dict[str, str]:
    raw = str(value or "").strip()
    if raw.count("=") != 1:
        raise argparse.ArgumentTypeError(
            "--stable-tag-admission must use exact ref=sha256:<64 lowercase hex>"
        )
    ref, digest = (part.strip() for part in raw.split("=", 1))
    relative = PurePosixPath(ref)
    if (
        not ref
        or relative.is_absolute()
        or relative.as_posix() != ref
        or "\\" in ref
        or any(part in {"", ".", "..", "latest", "current"} for part in relative.parts)
    ):
        raise argparse.ArgumentTypeError(
            "--stable-tag-admission ref must be one immutable safe relative path"
        )
    if re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
        raise argparse.ArgumentTypeError(
            "--stable-tag-admission digest must be sha256:<64 lowercase hex>"
        )
    return {"ref": ref, "digest": digest}


def _official_distribution_cli_inputs(
    args: argparse.Namespace,
) -> tuple[Path, dict[str, str], Path]:
    retired = [
        option
        for attribute, option in (
            ("artifact_manifest", "--artifact-manifest"),
            ("release_manifest", "--release-manifest"),
        )
        if str(getattr(args, attribute, "") or "").strip()
    ]
    if retired:
        raise ValueError(
            "formal distribution rejects retired inputs: " + ", ".join(retired)
        )

    graph_root = getattr(args, "official_distribution_graph_root", None)
    stable_ref = getattr(args, "stable_tag_admission", None)
    app_factory_root = getattr(args, "app_factory_root", None)
    missing = [
        option
        for value, option in (
            (graph_root, "--official-distribution-graph-root"),
            (stable_ref, "--stable-tag-admission"),
            (app_factory_root, "--app-factory-root"),
        )
        if value is None or value == ""
    ]
    if missing:
        raise ValueError(
            "formal distribution requires exact inputs: " + ", ".join(missing)
        )
    if not isinstance(stable_ref, Mapping) or set(stable_ref) != {"ref", "digest"}:
        raise ValueError(
            "--stable-tag-admission must be parsed from exact ref=sha256:<digest>"
        )
    try:
        graph_root = _controlled_distribution_input_root(
            str(graph_root),
            option="--official-distribution-graph-root",
        )
        app_factory_root = _controlled_distribution_input_root(
            str(app_factory_root),
            option="--app-factory-root",
        )
        normalized_stable_ref = _stable_tag_admission_argument(
            f"{stable_ref.get('ref', '')}={stable_ref.get('digest', '')}"
        )
    except (ValueError, argparse.ArgumentTypeError) as error:
        raise ValueError(str(error)) from error
    return graph_root, normalized_stable_ref, app_factory_root


def _command_deploy_distribution(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    try:
        graph_root, stable_tag_admission_ref, app_factory_root = (
            _official_distribution_cli_inputs(args)
        )
    except ValueError as error:
        return {
            "exitCode": 2,
            "summary": "stackctl distribution deploy is GATE_BLOCK",
            "details": [str(error)],
        }

    env_name = str(getattr(args, "env", "") or "").strip()
    target_name = str(getattr(args, "target", "") or "").strip()
    topology = _stackctl.load_environment_topology()
    if target_name:
        target_env = str(_stackctl.get_target(topology, target_name).get("env") or "")
        if env_name and env_name != target_env:
            return {
                "exitCode": 2,
                "summary": "stackctl distribution deploy is GATE_BLOCK",
                "details": ["--env and --target resolve to different environments"],
            }
        env_name = target_env
    elif env_name in _stackctl.ENVIRONMENTS:
        target_name = _stackctl.DEFAULT_TARGET_BY_ENV[env_name]
    else:
        return {
            "exitCode": 2,
            "summary": "stackctl distribution deploy is GATE_BLOCK",
            "details": ["distribution deploy requires --env or --target"],
        }

    dry_run = str(getattr(args, "dry_run", "false")).lower() == "true"
    distribution_root, explicitly_configured = _stackctl._official_distribution_root(
        args,
        target_name=target_name,
    )
    if target_name == "prod-hosted" and not dry_run and not explicitly_configured:
        return {
            "exitCode": 2,
            "summary": "stackctl production distribution deploy is GATE_BLOCK",
            "details": [
                "prod non-dry-run requires --distribution-root or QWQ_DISTRIBUTION_ROOT "
                "mounted to the official CDN/origin publishing root"
            ],
        }

    started_monotonic, started_at = _stackctl._start_timing()
    try:
        if dry_run:
            dry_run_root = Path(tempfile.gettempdir()).resolve() / (
                f"qwq-distribution-dry-run-{uuid4().hex}"
            )
            try:
                receipt = _stackctl.deploy_official_distribution(
                    kind=str(args.artifact_kind),
                    graph_root=graph_root,
                    stable_tag_admission_ref=stable_tag_admission_ref,
                    app_factory_root=app_factory_root,
                    distribution_root=dry_run_root,
                )
            finally:
                if dry_run_root.exists():
                    shutil.rmtree(dry_run_root)
            receipt["status"] = "validated"
            receipt["dryRun"] = True
            receipt.pop("receiptPath", None)
        else:
            receipt = _stackctl.deploy_official_distribution(
                kind=str(args.artifact_kind),
                graph_root=graph_root,
                stable_tag_admission_ref=stable_tag_admission_ref,
                app_factory_root=app_factory_root,
                distribution_root=distribution_root,
                expected_current=str(getattr(args, "expected_current", "") or ""),
            )
            receipt["status"] = "deployed"
            receipt["dryRun"] = False
    except (OSError, ValueError, _stackctl.OfficialDistributionReleaseError) as error:
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        return {
            "exitCode": 2,
            "summary": f"stackctl {args.artifact_kind} distribution is GATE_BLOCK",
            "details": [str(error)],
            **timing,
        }

    issues: list[str] = []
    hosted_inspection: dict[str, Any] = {}
    if bool(getattr(args, "verify_hosted", False)) and not dry_run:
        try:
            target = _stackctl.get_target(topology, target_name)
            public_bases = target.get("publicBases") or {}
            hosted_inspection = _stackctl.inspect_official_distribution(
                distribution_root=distribution_root,
                public_origin=str(public_bases.get("publicWeb") or ""),
                download_origin=str(public_bases.get("appDownload") or ""),
                verify_hosted=True,
            )
            issues.extend(hosted_inspection.get("issues") or [])
        except (OSError, ValueError, _stackctl.OfficialDistributionReleaseError) as error:
            issues.append(str(error))

    timing = _stackctl._finish_timing(started_monotonic, started_at)
    report_dir = _stackctl.resolve_report_dir(args, env_name, target_name)
    payload = {
        "schema": "stackctl-official-distribution-deploy-report",
        "command": "deploy",
        "artifactKind": args.artifact_kind,
        "environment": env_name,
        "target": target_name,
        "distributionRoot": str(distribution_root),
        "explicitlyConfigured": explicitly_configured,
        "receipt": receipt,
        "hostedInspection": hosted_inspection,
        "issues": issues,
        **timing,
    }
    _stackctl.write_json(report_dir / "report.json", payload)
    _stackctl.write_json(report_dir / "findings.json", {"issues": issues})
    return {
        "exitCode": 0 if not issues else 2,
        "summary": (
            f"stackctl {args.artifact_kind} distribution "
            + ("validated" if dry_run else "deployed")
            if not issues
            else f"stackctl {args.artifact_kind} distribution is GATE_BLOCK"
        ),
        "details": issues or [
            f"candidateMaterialId={receipt.get('candidateMaterialId')}",
            f"selectedAppArtifactDigest={receipt.get('selectedAppArtifactDigest')}",
            f"stableTag={receipt.get('stableTag')}",
            f"receiptSHA256={receipt.get('receiptSHA256')}",
        ],
        "reportDir": _stackctl.relpath(report_dir),
        **timing,
    }


def command_deploy(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    if str(getattr(args, "artifact_kind", "") or ""):
        return _stackctl._command_deploy_distribution(args)
    if args.mode == "environment-assembly":
        return _stackctl._command_environment_assembly(args)
    if args.mode == "prevalidate":
        return _stackctl._command_prod_prevalidate(args)
    if getattr(args, "service", "") and getattr(args, "env", ""):
        return _stackctl._command_deploy_service_environment(args)
    if not args.target:
        return {
            "exitCode": 2,
            "summary": "stackctl deploy requires --service/--env or --target",
            "details": [],
        }
    dry_run = str(getattr(args, "dry_run", "false")).strip().lower() == "true"
    if args.target != "prod-hosted" or dry_run:
        return _stackctl._command_deploy_with_lock(args)
    try:
        with _stackctl._prod_release_lock():
            return _stackctl._command_deploy_with_lock(args)
    except RuntimeError as error:
        return {
            "exitCode": 2,
            "summary": "stackctl deploy blocked by prod release transaction",
            "details": [str(error)],
        }


def register_parser(subparsers: "argparse._SubParsersAction") -> None:
    """向 stackctl build_parser 注册本域子命令（从 build_parser 逐字迁出）。"""
    import quwoquan_ops.cli.stackctl as _stackctl

    deploy_parser = subparsers.add_parser("deploy")
    deploy_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    deploy_parser.add_argument("--target", choices=_stackctl.TARGETS, default="")
    deploy_parser.add_argument("--env", choices=_stackctl.ENVIRONMENTS, default="")
    deploy_parser.add_argument(
        "--mode",
        choices=(
            "restart",
            "rollout",
            "cold-build",
            "environment-assembly",
            "prevalidate",
        ),
        default="",
    )
    deploy_parser.add_argument(
        "--stage",
        choices=("canary", "5", "20", "50", "100"),
        default="",
        help="显式 rollout stage；仅允许 canary/5/20/50/100 固定事务",
    )
    deploy_parser.add_argument("--service", default="")
    deploy_parser.add_argument(
        "--from-candidate-digest",
        default="",
        help="hosted ledger 当前稳定候选的 sha256 摘要；只用于发布 CAS",
    )
    deploy_parser.add_argument(
        "--to-candidate-digest",
        default="",
        help="ProdActivationAdmission 绑定的候选 identity；formal rollout 时由 envelope 覆盖",
    )
    deploy_parser.add_argument("--step", default="")
    deploy_parser.add_argument("--cloud-provider", choices=["aliyun", "volcengine", "huaweicloud"], default="aliyun")
    deploy_parser.add_argument("--dry-run", choices=["true", "false"], default="false")
    deploy_parser.add_argument(
        "--artifact-kind",
        choices=("web", "app-release"),
        default="",
        help="沿 stable admission exact graph 部署官方 Web 或 Android 分发物",
    )
    deploy_parser.add_argument(
        "--official-distribution-graph-root",
        type=_official_distribution_graph_root_argument,
        default=None,
        help=(
            "controller 已物化的 stable/Qualification/CMM/request/allocation exact graph 根"
        ),
    )
    deploy_parser.add_argument(
        "--stable-tag-admission",
        type=_stable_tag_admission_argument,
        default=None,
        metavar="REF=SHA256",
        help="stable ReleaseTagAdmissionFact 的 exact REF=SHA256 locator；SHA256 为 64 位小写十六进制摘要",
    )
    deploy_parser.add_argument(
        "--app-factory-root",
        type=_app_factory_root_argument,
        default=None,
        help="controller 已物化并验证来源的 actual app factory OCI 根",
    )
    deploy_parser.add_argument(
        "--distribution-root",
        default="",
        help="CDN/origin 挂载的目标根；prod 非 dry-run 必须显式提供或注入 QWQ_DISTRIBUTION_ROOT",
    )
    deploy_parser.add_argument(
        "--expected-current",
        default="",
        help="Web releaseId 或 Android buildNumber 的 CAS 前值",
    )
    deploy_parser.add_argument("--verify-hosted", action="store_true")
    deploy_parser.add_argument(
        "--frozen-diagnostic-snapshot",
        default="",
        help=(
            "仅 prevalidate 可消费的 frozen diagnostic-only Service 快照；不可进入 formal Prod rollout"
        ),
    )
    deploy_parser.add_argument(
        "--prometheus-url",
        default="",
        help="生产 SLO readback 的 Prometheus base URL；非 dry-run 必须提供",
    )
    deploy_parser.add_argument(
        "--prod-activation-admission",
        default="",
        help=(
            "controller 已物化的 canonical prod_activation_input.v1 JSON；正式 "
            "Prod rollout 必填，stackctl 只验证其中选定的 exact admission graph"
        ),
    )
    deploy_parser.add_argument(
        "--promotion-evidence",
        default="",
        help=(
            "受保护生产 runner 已物化的阶段观测 JSON；正式 Prod 晋级必须位于 "
            "QWQ_PROD_ROLLOUT_EVIDENCE_ROOT 内"
        ),
    )
    deploy_parser.add_argument(
        "--promotion-deadline-epoch",
        type=int,
        default=0,
        help="停止 Prod 晋级并切入回滚的绝对 UTC epoch；正式发布必须提供",
    )
    deploy_parser.add_argument(
        "--hard-deadline-epoch",
        type=int,
        default=0,
        help="Prod 发布或回滚必须完成的绝对 UTC epoch；正式发布必须提供",
    )
    deploy_parser.add_argument(
        "--rollback-budget-seconds",
        type=int,
        default=300,
        help="Prod 自动回滚与 ready 恢复的硬预算",
    )
    deploy_parser.add_argument(
        "--release-image-digest",
        default="",
        help="候选 OCI image 的 sha256；hosted receipt 必须绑定",
    )
    deploy_parser.add_argument(
        "--release-config-digest",
        default="",
        help="候选配置 bundle 的 sha256；hosted receipt 必须绑定",
    )
    deploy_parser.add_argument(
        "--contract-graph-digest",
        default="",
        help="候选 ContractGraph 的 sha256；hosted receipt 必须绑定",
    )
    deploy_parser.add_argument(
        "--adapter-digest",
        default="",
        help="候选 Provider adapter 的 sha256；hosted receipt 必须绑定",
    )
    deploy_parser.add_argument(
        "--ssh-host",
        default="",
        help=(
            "prevalidate/break-glass 单 host SSH 覆盖；formal rollout "
            "必须由 access-isolation inventory 驱动，禁止成为 App public base"
        ),
    )
    deploy_parser.add_argument(
        "--host-id",
        action="append",
        default=[],
        help="选择 access-isolation.yaml 中的一个或多个 prod-hosted 主机",
    )
    deploy_parser.add_argument(
        "--data-mode",
        choices=("isolated", "external"),
        default="",
    )
    deploy_parser.add_argument(
        "--prevalidate-scope",
        choices=("first-party",),
        default="",
    )

