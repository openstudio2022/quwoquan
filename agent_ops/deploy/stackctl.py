#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_ops.deploy.lib.common import (
    artifact_run_dir,
    load_json_yaml,
    relpath,
    run,
    utc_now,
    write_json,
    write_markdown,
)
from agent_ops.deploy.lib.environment_topology import (
    ENVIRONMENTS,
    TARGETS,
    get_target,
    load_environment_topology,
)
from agent_ops.deploy.lib.port_manifest import canonical_port, load_port_manifest, profile_ports


VERIFY_COMMAND_GROUPS = {
    "topology": [
        ["python3", "agent_ops/gate/verify_stackctl_args_contract.py"],
        ["python3", "agent_ops/gate/verify_environment_topology_manifest.py"],
        ["python3", "agent_ops/gate/verify_local_env_port_manifest.py"],
        ["bash", "quwoquan_service/scripts/deploy/verify_deployment_domain_mapping.sh"],
    ],
    "config": [
        ["python3", "quwoquan_app/scripts/env/verify_public_vs_upstream_url_contract.py"],
        ["python3", "agent_ops/gate/verify_prod_rollout_stackctl_contract.py"],
    ],
    "packaging": [
        ["python3", "agent_ops/gate/verify_environment_packaging_contract.py"],
        ["python3", "agent_ops/gate/verify_env_artifact_isolation.py"],
        ["python3", "quwoquan_app/scripts/env/verify_prod_package_purity.py"],
    ],
}

DEFAULT_TARGET_BY_ENV = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
    "prod": "prod-hosted",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Unified environment packaging, startup, verification, inspection, and rollout control.",
    )
    parser.add_argument("--output-format", choices=["text", "json"], default="text")
    parser.add_argument("--report-dir", default="")
    subparsers = parser.add_subparsers(dest="command", required=True)

    package_parser = subparsers.add_parser("package")
    package_parser.add_argument("--env", choices=ENVIRONMENTS, required=True)
    package_parser.add_argument("--service", default="")
    package_parser.add_argument("--include-services", action="store_true")
    package_parser.add_argument("--target", choices=TARGETS, default="")

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--env", choices=ENVIRONMENTS, default="")
    verify_parser.add_argument("--target", choices=TARGETS, default="")
    verify_parser.add_argument(
        "--kind",
        choices=["topology", "config", "packaging", "all"],
        default="all",
    )
    verify_parser.add_argument(
        "--tier",
        choices=["t1", "t2", "t3", "t4", "all"],
        default="t1",
    )

    up_parser = subparsers.add_parser("up")
    up_parser.add_argument("--target", choices=TARGETS, required=True)
    up_parser.add_argument("--device-id", default="")
    up_parser.add_argument("--skip-app", action="store_true")
    up_parser.add_argument("--rollout-mode", choices=["gray-initial", "carry-on", "full"], default="")

    down_parser = subparsers.add_parser("down")
    down_parser.add_argument("--target", choices=TARGETS, required=True)

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--target", choices=TARGETS, required=True)

    health_parser = subparsers.add_parser("health")
    health_parser.add_argument("--target", choices=TARGETS, required=True)
    health_parser.add_argument(
        "--scope",
        choices=["edge", "media", "service", "full"],
        default="full",
    )

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--target", choices=TARGETS, required=True)
    inspect_parser.add_argument(
        "--scope",
        choices=["logs", "network", "data", "metrics", "config", "security", "all"],
        default="all",
    )
    inspect_parser.add_argument(
        "--kind",
        dest="scope",
        choices=["logs", "network", "data", "metrics", "config", "security", "all"],
    )

    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--target", choices=TARGETS, required=True)

    repair_parser = subparsers.add_parser("repair")
    repair_parser.add_argument("--target", choices=TARGETS, required=True)
    repair_parser.add_argument(
        "--fix",
        choices=["rebuild-packages", "restart-stack", "reclaim-ports"],
        required=True,
    )

    deploy_parser = subparsers.add_parser("deploy")
    deploy_parser.add_argument("--target", choices=("gamma-hosted", "prod-hosted"), required=True)
    deploy_parser.add_argument("--stage", default="")
    deploy_parser.add_argument("--image-version", default="")
    deploy_parser.add_argument("--previous-image-version", default="")
    deploy_parser.add_argument("--base-url", default="")
    deploy_parser.add_argument("--product-ops-base-url", default="")
    deploy_parser.add_argument("--media-base-url", default="")
    deploy_parser.add_argument("--media-origin-base-url", default="")
    deploy_parser.add_argument("--service", default="")
    deploy_parser.add_argument("--from-image", default="")
    deploy_parser.add_argument("--to-image", default="")
    deploy_parser.add_argument("--from-config", default="")
    deploy_parser.add_argument("--to-config", default="")
    deploy_parser.add_argument("--step", default="")
    deploy_parser.add_argument("--cloud-provider", choices=["aliyun", "volcengine", "huaweicloud"], default="aliyun")
    deploy_parser.add_argument("--dry-run", choices=["true", "false"], default="false")
    deploy_parser.add_argument("--error-rate", default="")
    deploy_parser.add_argument("--p95-ms", default="")
    deploy_parser.add_argument("--redis-error-rate", default="")
    return parser


def resolve_report_dir(args: argparse.Namespace, env_name: str, target: str) -> Path:
    if args.report_dir:
        return Path(args.report_dir)
    return artifact_run_dir(env_name, args.command, target=target or "local")


def _write_summary_bundle(
    report_dir: Path,
    *,
    command: str,
    target: str,
    status: str,
    summary: str,
    details: list[str],
    extra: dict[str, Any] | None = None,
) -> None:
    payload = {
        "command": command,
        "target": target,
        "status": status,
        "summary": summary,
        "details": details,
        "generatedAt": utc_now(),
    }
    if extra:
        payload.update(extra)
    write_json(report_dir / "summary.json", payload)
    write_markdown(
        report_dir / "summary.md",
        "\n".join(
            [
                f"# stackctl {command}",
                "",
                f"- target: `{target}`",
                f"- status: `{status}`",
                f"- summary: {summary}",
                *[f"- {line}" for line in details],
            ]
        ),
    )


def _write_stdout_markdown(report_dir: Path, sections: list[tuple[str, str]]) -> None:
    lines: list[str] = ["# stackctl stdout", ""]
    for title, content in sections:
        if not content.strip():
            continue
        lines.extend([f"## {title}", "", "```text", content.rstrip(), "```", ""])
    write_markdown(report_dir / "stdout.md", "\n".join(lines))


def _selected_verify_commands(kind: str) -> list[list[str]]:
    if kind == "all":
        commands: list[list[str]] = []
        for group_name in ("topology", "config", "packaging"):
            commands.extend(VERIFY_COMMAND_GROUPS[group_name])
        return commands
    return list(VERIFY_COMMAND_GROUPS[kind])


def _selected_tier_commands(env_name: str, target_name: str, tier: str) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    if tier in {"t2", "all"}:
        commands.extend(
            [
                {
                    "name": "content-media-url-tests",
                    "argv": [
                        "flutter",
                        "test",
                        "test/core/media/content_media_url_test.dart",
                        "test/cloud/chat/chat_avatar_url_resolution_test.dart",
                    ],
                    "cwd": ROOT / "quwoquan_app",
                },
                {
                    "name": "contract-seeded-mock-tests",
                    "argv": [
                        "flutter",
                        "test",
                        "--dart-define=CONTRACT_FIXTURE_PROFILE=full",
                        "test/cloud/services/contract_seeded_mock_repository_test.dart",
                    ],
                    "cwd": ROOT / "quwoquan_app",
                },
            ]
        )
    if tier in {"t3", "all"}:
        if env_name in {"alpha", "beta", "all"}:
            commands.append(
                {
                    "name": "alpha-beta-seed-matrix",
                    "argv": ["python3", "quwoquan_app/scripts/env/run_app_alpha_beta_seed_matrix.py"],
                }
            )
        if target_name == "gamma-local":
            commands.append(
                {
                    "name": "gamma-local-t3",
                    "argv": ["python3", "quwoquan_app/scripts/gamma/run_local_gamma_t3.py"],
                }
            )
        if target_name == "gamma-hosted":
            target = get_target(load_environment_topology(), target_name)
            public_bases = target.get("publicBases") or {}
            commands.append(
                {
                    "name": "gamma-hosted-readiness",
                    "argv": [
                        "python3",
                        "quwoquan_service/scripts/gamma/verify_gamma_environment_ready.py",
                        "--base-url",
                        str(public_bases["api"]),
                        "--product-ops-base-url",
                        str(public_bases["productOps"]),
                    ],
                }
            )
        if target_name == "prod-hosted":
            target = get_target(load_environment_topology(), target_name)
            public_bases = target.get("publicBases") or {}
            commands.append(
                {
                    "name": "prod-public-health",
                    "argv": [
                        "python3",
                        "agent_ops/deploy/stackctl.py",
                        "--output-format",
                        "json",
                        "health",
                        "--target",
                        "prod-hosted",
                        "--scope",
                        "full",
                    ],
                    "env": {
                        "CLOUD_GATEWAY_BASE_URL": str(public_bases["api"]),
                    },
                }
            )
    if tier in {"t4", "all"}:
        if target_name == "gamma-local":
            commands.append(
                {
                    "name": "gamma-local-t4-dry-run",
                    "argv": ["bash", "quwoquan_app/scripts/gamma/run_local_gamma_t4.sh", "--dry-run"],
                }
            )
        commands.append(
            {
                "name": "prod-rollout-stackctl-contract",
                "argv": ["python3", "agent_ops/gate/verify_prod_rollout_stackctl_contract.py"],
            }
        )
    return commands


def fetch_url(url: str, timeout: float = 6.0) -> tuple[bool, int | None, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return True, int(response.status), body[:500]
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return False, int(exc.code), body[:500]
    except Exception as exc:
        return False, None, str(exc)


def socket_probe(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def print_result(args: argparse.Namespace, payload: dict[str, Any]) -> int:
    if args.output_format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(payload["summary"])
        report_dir = payload.get("reportDir")
        if report_dir:
            print(f"report: {report_dir}")
        for line in payload.get("details", []):
            print(f"- {line}")
    return int(payload.get("exitCode", 0))


def command_package(args: argparse.Namespace) -> dict[str, Any]:
    topology = load_environment_topology()
    env_name = args.env
    target_name = args.target or DEFAULT_TARGET_BY_ENV[env_name]
    report_dir = resolve_report_dir(args, env_name, target_name)
    details: list[str] = []
    reports: list[dict[str, Any]] = []

    app_cmd = ["bash", "quwoquan_app/scripts/env/build_app_env_package.sh", "--env", env_name]
    app_result = run(app_cmd)
    reports.append(
        {
            "name": "app-package",
            "argv": app_cmd,
            "exitCode": app_result.returncode,
            "stdout": app_result.stdout,
            "stderr": app_result.stderr,
        }
    )
    if app_result.returncode != 0:
        write_json(report_dir / "report.json", {"status": "failed", "steps": reports})
        _write_summary_bundle(
            report_dir,
            command="package",
            target=target_name,
            status="failed",
            summary=f"stackctl package failed for {env_name}",
            details=[app_result.stderr.strip() or app_result.stdout.strip()],
            extra={"env": env_name},
        )
        _write_stdout_markdown(report_dir, [("app-package", "\n".join(filter(None, [app_result.stdout, app_result.stderr])))])
        return {
            "exitCode": app_result.returncode,
            "summary": f"stackctl package failed for {env_name}",
            "details": [app_result.stderr.strip() or app_result.stdout.strip()],
            "reportDir": relpath(report_dir),
        }
    details.append(f"app package ready: artifacts/app-env-packages/{env_name}")

    if args.include_services or args.service:
        services = [args.service] if args.service else _all_services()
        for service in services:
            svc_cmd = [
                "bash",
                "quwoquan_service/scripts/runtime/build_service_env_package.sh",
                "--service",
                service,
                "--env",
                env_name,
            ]
            svc_result = run(svc_cmd)
            reports.append(
                {
                    "name": f"service-package:{service}",
                    "argv": svc_cmd,
                    "exitCode": svc_result.returncode,
                    "stdout": svc_result.stdout,
                    "stderr": svc_result.stderr,
                }
            )
            if svc_result.returncode != 0:
                write_json(report_dir / "report.json", {"status": "failed", "steps": reports})
                _write_summary_bundle(
                    report_dir,
                    command="package",
                    target=target_name,
                    status="failed",
                    summary=f"stackctl package failed for {service}/{env_name}",
                    details=[svc_result.stderr.strip() or svc_result.stdout.strip()],
                    extra={"env": env_name},
                )
                _write_stdout_markdown(
                    report_dir,
                    [(f"service-package:{service}", "\n".join(filter(None, [svc_result.stdout, svc_result.stderr])))],
                )
                return {
                    "exitCode": svc_result.returncode,
                    "summary": f"stackctl package failed for {service}/{env_name}",
                    "details": [svc_result.stderr.strip() or svc_result.stdout.strip()],
                    "reportDir": relpath(report_dir),
                }
            details.append(f"service package ready: artifacts/service-env-packages/{service}/{env_name}")

    payload = {
        "status": "ok",
        "command": "package",
        "env": env_name,
        "target": target_name,
        "timestamp": utc_now(),
        "reportDir": relpath(report_dir),
        "topologyTarget": get_target(topology, target_name),
        "steps": reports,
    }
    write_json(report_dir / "report.json", payload)
    _write_summary_bundle(
        report_dir,
        command="package",
        target=target_name,
        status="ok",
        summary=f"stackctl package completed for {env_name}",
        details=details,
        extra={"env": env_name},
    )
    return {
        "exitCode": 0,
        "summary": f"stackctl package completed for {env_name}",
        "details": details,
        "reportDir": relpath(report_dir),
    }


def command_verify(args: argparse.Namespace) -> dict[str, Any]:
    env_name = args.env or (get_target(load_environment_topology(), args.target).get("env") if args.target else "all")
    target_name = args.target or (DEFAULT_TARGET_BY_ENV[env_name] if env_name in ENVIRONMENTS else "repo")
    report_dir = resolve_report_dir(args, env_name if env_name in ENVIRONMENTS else "repo", target_name)
    steps: list[dict[str, Any]] = []
    issues: list[str] = []
    package_envs = [env_name] if env_name in ENVIRONMENTS else list(ENVIRONMENTS)
    for package_env in package_envs:
        package_args = argparse.Namespace(
            command="package",
            env=package_env,
            service="",
            include_services=True,
            target=args.target or DEFAULT_TARGET_BY_ENV[package_env],
            output_format="json",
            report_dir=str(report_dir / f"package-{package_env}"),
        )
        package_payload = command_package(package_args)
        steps.append(
            {
                "kind": "package",
                "env": package_env,
                "exitCode": package_payload["exitCode"],
                "details": package_payload.get("details", []),
                "reportDir": package_payload.get("reportDir", ""),
            }
        )
        if package_payload["exitCode"] != 0:
            issues.append(f"package failed for {package_env}: {'; '.join(package_payload.get('details', []))}")
    stdout_sections: list[tuple[str, str]] = []
    commands = _selected_verify_commands(args.kind)
    for command in commands:
        result = run(command)
        command_key = " ".join(command)
        steps.append(
            {
                "kind": "verify",
                "group": args.kind,
                "argv": command,
                "exitCode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
        stdout_sections.append((command_key, "\n".join(filter(None, [result.stdout, result.stderr]))))
        if result.returncode != 0:
            issues.append(result.stderr.strip() or result.stdout.strip() or "unknown verify failure")
    for tier_command in _selected_tier_commands(env_name if env_name in ENVIRONMENTS else "all", target_name, args.tier):
        result = run(
            tier_command["argv"],
            cwd=tier_command.get("cwd"),
            env=tier_command.get("env"),
        )
        steps.append(
            {
                "kind": "tier",
                "tier": args.tier,
                "name": tier_command["name"],
                "argv": tier_command["argv"],
                "exitCode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
        stdout_sections.append((tier_command["name"], "\n".join(filter(None, [result.stdout, result.stderr]))))
        if result.returncode != 0:
            issues.append(
                f"{tier_command['name']} failed: "
                + (result.stderr.strip() or result.stdout.strip() or "unknown tier failure")
            )
    payload = {
        "status": "ok" if not issues else "failed",
        "command": "verify",
        "timestamp": utc_now(),
        "kind": args.kind,
        "tier": args.tier,
        "steps": steps,
    }
    write_json(report_dir / "report.json", payload)
    write_json(report_dir / "findings.json", {"issues": issues})
    _write_summary_bundle(
        report_dir,
        command="verify",
        target=target_name,
        status=payload["status"],
        summary="stackctl verify passed" if not issues else "stackctl verify failed",
        details=issues or [f"ran {len(steps)} checks"],
        extra={"kind": args.kind, "tier": args.tier},
    )
    _write_stdout_markdown(report_dir, stdout_sections)
    return {
        "exitCode": 0 if not issues else 1,
        "summary": "stackctl verify passed" if not issues else "stackctl verify failed",
        "details": issues or [f"ran {len(steps)} checks"],
        "reportDir": relpath(report_dir),
    }


def command_up(args: argparse.Namespace) -> dict[str, Any]:
    topology = load_environment_topology()
    target = get_target(topology, args.target)
    env_name = str(target["env"])
    report_dir = resolve_report_dir(args, env_name, args.target)
    steps: list[dict[str, Any]] = []

    if args.target == "beta-local":
        cmd = ["bash", "agent_ops/deploy/beta/start_beta_stack.sh", "up"]
        env = _beta_env_from_port_manifest()
        if args.device_id:
            env["DEVICE_ID"] = args.device_id
        if args.skip_app:
            env["START_APP"] = "0"
        result = run(cmd, env=env)
    elif args.target == "gamma-local":
        cmd = ["bash", "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"]
        env = _gamma_env_from_port_manifest(topology, args.target)
        result = run(cmd, env=env)
    elif args.target == "alpha-local":
        result = run(["bash", "agent_ops/deploy/alpha/start_alpha_mock_stack.sh", "up"])
        cmd = ["bash", "agent_ops/deploy/alpha/start_alpha_mock_stack.sh", "up"]
        if result.returncode == 0 and args.device_id and not args.skip_app:
            app_cmd = [
                "bash",
                "quwoquan_app/scripts/device/start_app_instance.sh",
                "--env",
                "alpha",
                "--device-id",
                args.device_id,
            ]
            app_result = run(app_cmd)
            steps.append(
                {
                    "argv": app_cmd,
                    "exitCode": app_result.returncode,
                    "stdout": app_result.stdout,
                    "stderr": app_result.stderr,
                }
            )
            if app_result.returncode != 0:
                result = app_result
    elif args.target == "prod-sim":
        if not args.device_id:
            return {
                "exitCode": 2,
                "summary": f"stackctl up failed for {args.target}",
                "details": [f"--device-id is required for {args.target} app launch"],
            }
        target_public_bases = target.get("publicBases") or {}
        cmd = [
            "bash",
            "quwoquan_app/scripts/device/start_app_instance.sh",
            "--env",
            "prod",
            "--device-id",
            args.device_id,
        ]
        cmd.extend(
            [
                "--gateway-base-url",
                str(target_public_bases["api"]),
                "--media-avatar-base-url",
                str(target_public_bases["mediaAvatar"]),
                "--media-image-base-url",
                str(target_public_bases["mediaImage"]),
                "--media-video-base-url",
                str(target_public_bases["mediaVideo"]),
                "--media-upload-base-url",
                str(target_public_bases["mediaUpload"]),
                "--instance-namespace",
                "prod-sim",
                "--service-mode",
                "prod-sim-app",
            ]
        )
        if args.rollout_mode:
            cmd.extend(["--rollout-mode", args.rollout_mode])
        result = run(cmd)
    else:
        return {
            "exitCode": 2,
            "summary": f"stackctl up is not implemented for {args.target}",
            "details": ["use deploy for hosted gamma/prod targets"],
        }

    steps.append(
        {
            "argv": cmd,
            "exitCode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    )
    write_json(report_dir / "report.json", {"command": "up", "target": args.target, "steps": steps})
    _write_summary_bundle(
        report_dir,
        command="up",
        target=args.target,
        status="ok" if result.returncode == 0 else "failed",
        summary=f"stackctl up {'completed' if result.returncode == 0 else 'failed'} for {args.target}",
        details=_command_details(result),
    )
    return {
        "exitCode": result.returncode,
        "summary": f"stackctl up {'completed' if result.returncode == 0 else 'failed'} for {args.target}",
        "details": _command_details(result),
        "reportDir": relpath(report_dir),
    }


def command_down(args: argparse.Namespace) -> dict[str, Any]:
    topology = load_environment_topology()
    target = get_target(topology, args.target)
    env_name = str(target["env"])
    report_dir = resolve_report_dir(args, env_name, args.target)

    if args.target == "beta-local":
        cmd = ["bash", "agent_ops/deploy/beta/start_beta_stack.sh", "down"]
        result = run(cmd)
    elif args.target == "gamma-local":
        cmd = ["bash", "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh", "--down"]
        result = run(cmd)
    elif args.target == "alpha-local":
        cmd = ["bash", "agent_ops/deploy/alpha/start_alpha_mock_stack.sh", "down"]
        result = run(cmd)
        app_result = run(
            [
                "bash",
                "quwoquan_app/scripts/device/stop_app_instance.sh",
                "--env",
                "alpha",
                "--quiet",
            ]
        )
        if app_result.returncode != 0 and result.returncode == 0:
            result = app_result
    elif args.target == "prod-sim":
        cmd = [
            "bash",
            "quwoquan_app/scripts/device/stop_app_instance.sh",
            "--env",
            "prod",
        ]
        result = run(cmd)
    else:
        return {
            "exitCode": 2,
            "summary": f"stackctl down is not implemented for {args.target}",
            "details": ["hosted targets should be rolled back or redeployed via deploy commands"],
        }

    write_json(
        report_dir / "report.json",
        {
            "command": "down",
            "target": args.target,
            "argv": cmd,
            "exitCode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
    )
    _write_summary_bundle(
        report_dir,
        command="down",
        target=args.target,
        status="ok" if result.returncode == 0 else "failed",
        summary=f"stackctl down {'completed' if result.returncode == 0 else 'failed'} for {args.target}",
        details=_command_details(result),
    )
    return {
        "exitCode": result.returncode,
        "summary": f"stackctl down {'completed' if result.returncode == 0 else 'failed'} for {args.target}",
        "details": _command_details(result),
        "reportDir": relpath(report_dir),
    }


def command_status(args: argparse.Namespace) -> dict[str, Any]:
    health_args = argparse.Namespace(
        command="health",
        target=args.target,
        scope="full",
        output_format=getattr(args, "output_format", "text"),
        report_dir=str(resolve_report_dir(args, str(get_target(load_environment_topology(), args.target)["env"]), args.target)),
    )
    return command_health(health_args)


def command_health(args: argparse.Namespace) -> dict[str, Any]:
    topology = load_environment_topology()
    target = get_target(topology, args.target)
    env_name = str(target["env"])
    report_dir = resolve_report_dir(args, env_name, args.target)
    checks = _health_checks_for_target(topology, args.target, args.scope)
    statuses: list[dict[str, Any]] = []
    findings: list[str] = []
    stdout_sections: list[tuple[str, str]] = []
    for item in checks:
        if item.get("skip"):
            statuses.append(
                {
                    "name": item["name"],
                    "scope": item["scope"],
                    "url": item["url"],
                    "ok": True,
                    "statusCode": None,
                    "bodyPreview": str(item.get("reason", "skipped")),
                    "skipped": True,
                }
            )
            continue
        ok, status_code, body = fetch_url(item["url"])
        if not ok:
            findings.append(f"{item['scope']}/{item['name']} failed: {status_code or 'ERR'} {item['url']}")
        statuses.append(
            {
                "name": item["name"],
                "scope": item["scope"],
                "url": item["url"],
                "ok": ok,
                "statusCode": status_code,
                "bodyPreview": body,
                "skipped": False,
            }
        )
        stdout_sections.append((item["name"], f"{status_code or 'ERR'} {item['url']}\n{body}"))
    ok_count = sum(1 for item in statuses if item["ok"])
    payload = {
        "command": "health",
        "target": args.target,
        "scope": args.scope,
        "checks": statuses,
        "findings": findings,
        "timestamp": utc_now(),
    }
    write_json(report_dir / "report.json", payload)
    write_json(report_dir / "health.json", {"target": args.target, "scope": args.scope, "checks": statuses})
    write_json(report_dir / "findings.json", {"target": args.target, "scope": args.scope, "issues": findings})
    _write_summary_bundle(
        report_dir,
        command="health",
        target=args.target,
        status="ok" if not findings else "failed",
        summary=f"stackctl health {args.target}: {ok_count}/{len(statuses)} healthy",
        details=findings or [f"scope={args.scope}", f"healthy checks={ok_count}/{len(statuses)}"],
        extra={"scope": args.scope},
    )
    _write_stdout_markdown(report_dir, stdout_sections)
    return {
        "exitCode": 0 if not findings else 1,
        "summary": f"stackctl health {args.target}: {ok_count}/{len(statuses)} healthy",
        "details": findings or [f"{item['name']} -> {item['statusCode'] or 'OK'} {item['url']}" for item in statuses],
        "reportDir": relpath(report_dir),
    }


def command_inspect(args: argparse.Namespace) -> dict[str, Any]:
    topology = load_environment_topology()
    target = get_target(topology, args.target)
    env_name = str(target["env"])
    report_dir = resolve_report_dir(args, env_name, args.target)
    scopes = (
        ["logs", "network", "data", "metrics", "config", "security"]
        if args.scope == "all"
        else [args.scope]
    )
    inspection: dict[str, Any] = {}
    if "network" in scopes:
        inspection["network"] = _network_report(args.target)
    if "config" in scopes:
        inspection["config"] = {
            "target": target,
            "portProfile": target.get("portProfile"),
        }
    if "logs" in scopes:
        inspection["logs"] = _local_log_report(args.target)
    if "data" in scopes:
        inspection["data"] = _data_report(args.target)
    if "metrics" in scopes:
        inspection["metrics"] = _metrics_report(topology, args.target)
    if "security" in scopes:
        inspection["security"] = _security_report(topology, args.target)
    write_json(report_dir / "report.json", {"command": "inspect", "inspection": inspection})
    for key, value in inspection.items():
        write_json(report_dir / f"{key}.json", value)
    details = [f"{key}: collected" for key in inspection]
    _write_summary_bundle(
        report_dir,
        command="inspect",
        target=args.target,
        status="ok",
        summary=f"stackctl inspect completed for {args.target}",
        details=details,
        extra={"scope": args.scope},
    )
    return {
        "exitCode": 0,
        "summary": f"stackctl inspect completed for {args.target}",
        "details": details,
        "reportDir": relpath(report_dir),
    }


def command_doctor(args: argparse.Namespace) -> dict[str, Any]:
    topology = load_environment_topology()
    target = get_target(topology, args.target)
    env_name = str(target["env"])
    report_dir = resolve_report_dir(args, env_name, args.target)
    findings: list[str] = []
    health = command_status(args)
    if health["exitCode"] != 0:
        findings.append("health checks are failing")
    if target.get("portProfile"):
        network = _network_report(args.target)
        closed = [item["name"] for item in network["ports"] if not item["open"]]
        if closed:
            findings.append(f"ports not listening: {', '.join(closed)}")
    packages = [
        ROOT / "artifacts" / "app-env-packages" / env_name / "report.json",
    ]
    if not all(path.exists() for path in packages):
        findings.append("packaged app artifact is missing")
    repair_plan = []
    if findings:
        if any("health checks" in item for item in findings):
            repair_plan.append("run `stackctl health --target <target> --scope full` to confirm failing probes")
        if any("ports not listening" in item for item in findings):
            repair_plan.append("run `stackctl repair --target <target> --fix restart-stack` for local targets")
        if any("artifact" in item for item in findings):
            repair_plan.append("run `stackctl repair --target <target> --fix rebuild-packages`")
    write_json(
        report_dir / "report.json",
        {
            "command": "doctor",
            "target": args.target,
            "findings": findings,
            "repairPlan": repair_plan,
            "timestamp": utc_now(),
        },
    )
    write_json(report_dir / "findings.json", {"target": args.target, "issues": findings})
    write_json(report_dir / "repair_plan.json", {"target": args.target, "actions": repair_plan})
    _write_summary_bundle(
        report_dir,
        command="doctor",
        target=args.target,
        status="ok" if not findings else "failed",
        summary="stackctl doctor found no issues" if not findings else "stackctl doctor found issues",
        details=findings or ["no issues found"],
    )
    return {
        "exitCode": 0 if not findings else 1,
        "summary": "stackctl doctor found no issues" if not findings else "stackctl doctor found issues",
        "details": findings or ["no issues found"],
        "reportDir": relpath(report_dir),
    }


def command_repair(args: argparse.Namespace) -> dict[str, Any]:
    topology = load_environment_topology()
    target = get_target(topology, args.target)
    env_name = str(target["env"])
    report_dir = resolve_report_dir(args, env_name, args.target)
    steps: list[dict[str, Any]] = []
    if args.fix == "rebuild-packages":
        package_args = argparse.Namespace(
            command="package",
            env=env_name,
            service="",
            include_services=True,
            target=args.target,
            output_format="json",
            report_dir=str(report_dir / "rebuild-packages"),
        )
        payload = command_package(package_args)
        write_json(report_dir / "report.json", {"command": "repair", "nested": payload})
        write_json(
            report_dir / "repair_plan.json",
            {"target": args.target, "fix": args.fix, "actions": ["rebuild environment packages"]},
        )
        return payload
    if args.fix == "restart-stack":
        down_args = argparse.Namespace(command="down", target=args.target, output_format="json", report_dir=str(report_dir / "down"))
        up_args = argparse.Namespace(command="up", target=args.target, device_id="", skip_app=False, output_format="json", report_dir=str(report_dir / "up"))
        down_payload = command_down(down_args)
        up_payload = command_up(up_args)
        steps = [down_payload, up_payload]
        write_json(report_dir / "report.json", {"command": "repair", "steps": steps})
        write_json(
            report_dir / "repair_plan.json",
            {"target": args.target, "fix": args.fix, "actions": ["stop stack", "start stack"]},
        )
        _write_summary_bundle(
            report_dir,
            command="repair",
            target=args.target,
            status="ok" if up_payload["exitCode"] == 0 else "failed",
            summary=f"stackctl repair restart-stack completed for {args.target}",
            details=[down_payload["summary"], up_payload["summary"]],
        )
        return {
            "exitCode": 0 if up_payload["exitCode"] == 0 else up_payload["exitCode"],
            "summary": f"stackctl repair restart-stack completed for {args.target}",
            "details": [down_payload["summary"], up_payload["summary"]],
            "reportDir": relpath(report_dir),
        }
    if args.fix == "reclaim-ports":
        ports = _network_report(args.target)["ports"]
        occupied = [item for item in ports if item["open"]]
        write_json(report_dir / "report.json", {"command": "repair", "target": args.target, "occupied": occupied})
        write_json(
            report_dir / "repair_plan.json",
            {
                "target": args.target,
                "fix": args.fix,
                "actions": [f"inspect listener on {item['name']}:{item['port']}" for item in occupied],
            },
        )
        _write_summary_bundle(
            report_dir,
            command="repair",
            target=args.target,
            status="ok",
            summary=f"stackctl repair reclaim-ports inspected {args.target}",
            details=[f"{item['name']} listens on {item['port']}" for item in occupied] or ["no occupied canonical ports"],
        )
        return {
            "exitCode": 0,
            "summary": f"stackctl repair reclaim-ports inspected {args.target}",
            "details": [f"{item['name']} listens on {item['port']}" for item in occupied] or ["no occupied canonical ports"],
            "reportDir": relpath(report_dir),
        }
    return {
        "exitCode": 2,
        "summary": f"unsupported repair fix: {args.fix}",
        "details": [],
    }


def command_deploy(args: argparse.Namespace) -> dict[str, Any]:
    report_dir = resolve_report_dir(args, "prod" if args.target == "prod-hosted" else "gamma", args.target)
    if args.target == "gamma-hosted":
        if not args.stage or not args.image_version or not args.previous_image_version:
            return {
                "exitCode": 2,
                "summary": "stackctl deploy gamma-hosted requires --stage --image-version --previous-image-version",
                "details": [],
            }
        cmd = [
            "bash",
            "agent_ops/deploy/gamma/deploy_gamma_ecs.sh",
        ]
        env = {}
        for key, value in {
            "STAGE": args.stage,
            "IMAGE_VERSION": args.image_version,
            "PREV_IMAGE_VERSION": args.previous_image_version,
            "BASE_URL": args.base_url,
            "PRODUCT_OPS_BASE_URL": args.product_ops_base_url,
            "MEDIA_BASE_URL": args.media_base_url,
            "MEDIA_ORIGIN_BASE_URL": args.media_origin_base_url,
        }.items():
            if value:
                env[key] = value
        result = run(cmd, env=env)
    else:
        required = [
            args.service,
            args.from_image,
            args.to_image,
            args.from_config,
            args.to_config,
            args.step,
            args.error_rate,
            args.p95_ms,
            args.redis_error_rate,
        ]
        if not all(required):
            return {
                "exitCode": 2,
                "summary": "stackctl deploy prod-hosted requires service/image/config/step/SLO arguments",
                "details": [],
            }
        cmd = [
            "bash",
            "agent_ops/deploy/prod/config_release_apply_stage.sh",
            "--service",
            args.service,
            "--from-image",
            args.from_image,
            "--to-image",
            args.to_image,
            "--from-config",
            args.from_config,
            "--to-config",
            args.to_config,
            "--step",
            args.step,
            "--error-rate",
            args.error_rate,
            "--p95-ms",
            args.p95_ms,
            "--redis-error-rate",
            args.redis_error_rate,
        ]
        replicas = str(_replicas_for_step(args.step))
        deploy_result = run(
            ["bash", "agent_ops/deploy/prod/deploy_to_prod.sh"],
            env={
                "CLOUD_PROVIDER": args.cloud_provider,
                "IMAGE_VERSION": args.to_image,
                "CONFIG_VERSION": args.to_config,
                "REPLICAS": replicas,
                "DRY_RUN": args.dry_run,
            },
        )
        if deploy_result.returncode != 0:
            write_json(
                report_dir / "report.json",
                {
                    "command": "deploy",
                    "target": args.target,
                    "stage": "apply",
                    "argv": ["bash", "agent_ops/deploy/prod/deploy_to_prod.sh"],
                    "exitCode": deploy_result.returncode,
                    "stdout": deploy_result.stdout,
                    "stderr": deploy_result.stderr,
                },
            )
            _write_summary_bundle(
                report_dir,
                command="deploy",
                target=args.target,
                status="failed",
                summary="stackctl deploy failed during prod apply",
                details=_command_details(deploy_result),
            )
            _write_stdout_markdown(
                report_dir,
                [("prod-apply", "\n".join(filter(None, [deploy_result.stdout, deploy_result.stderr])))],
            )
            return {
                "exitCode": deploy_result.returncode,
                "summary": "stackctl deploy failed during prod apply",
                "details": _command_details(deploy_result),
                "reportDir": relpath(report_dir),
            }
        result = run(cmd)
    write_json(
        report_dir / "report.json",
        {
            "command": "deploy",
            "target": args.target,
            "argv": cmd,
            "exitCode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
    )
    write_json(report_dir / "findings.json", {"target": args.target, "issues": []})
    _write_summary_bundle(
        report_dir,
        command="deploy",
        target=args.target,
        status="ok" if result.returncode == 0 else "failed",
        summary=f"stackctl deploy {'completed' if result.returncode == 0 else 'failed'} for {args.target}",
        details=(_command_details(deploy_result) if args.target == "prod-hosted" else []) + _command_details(result),
    )
    _write_stdout_markdown(
        report_dir,
        [
            ("deploy", "\n".join(filter(None, [result.stdout, result.stderr]))),
            *(
                [("prod-apply", "\n".join(filter(None, [deploy_result.stdout, deploy_result.stderr])))]
                if args.target == "prod-hosted"
                else []
            ),
        ],
    )
    return {
        "exitCode": result.returncode,
        "summary": f"stackctl deploy {'completed' if result.returncode == 0 else 'failed'} for {args.target}",
        "details": (_command_details(deploy_result) if args.target == "prod-hosted" else []) + _command_details(result),
        "reportDir": relpath(report_dir),
    }


def _all_services() -> list[str]:
    services: list[str] = []
    for path in ROOT.glob("quwoquan_service/services/*/configs/default/config.yaml"):
        services.append(path.parents[2].name)
    return sorted(set(services))


def _beta_env_from_port_manifest() -> dict[str, str]:
    manifest = load_port_manifest()
    ports = profile_ports(manifest, "beta-local")
    return {
        "GATEWAY_PORT": str(ports["api-edge"]),
        "PRODUCT_OPS_PORT": str(ports["product-ops-edge"]),
        "PLATFORM_OPS_PORT": str(ports["platform-ops-edge"]),
        "OPS_PORTAL_PORT": str(ports["ops-portal"]),
        "MEDIA_PORT": str(ports["media-edge"]),
        "ASSISTANT_PORT": str(ports["assistant-service"]),
        "CHAT_PORT": str(ports["chat-service"]),
    }


def _gamma_env_from_port_manifest(topology: dict[str, Any], target_name: str) -> dict[str, str]:
    manifest = load_port_manifest()
    profile_name = str(get_target(topology, target_name).get("portProfile"))
    ports = profile_ports(manifest, profile_name)
    target = get_target(topology, target_name)
    public_bases = target.get("publicBases") or {}
    return {
        "LOCAL_GAMMA_HTTP_PORT": str(ports["api-edge"]),
        "LOCAL_GAMMA_PRODUCT_OPS_PORT": str(ports["product-ops-edge"]),
        "LOCAL_GAMMA_PLATFORM_OPS_PORT": str(ports["platform-ops-edge"]),
        "LOCAL_GAMMA_MEDIA_EDGE_PORT": str(ports["media-edge"]),
        "LOCAL_GAMMA_MEDIA_ORIGIN_PORT": str(ports["media-origin"]),
        "LOCAL_GAMMA_MEDIA_PUBLIC_BASE_URL": str(public_bases["mediaImage"]),
        "LOCAL_GAMMA_MEDIA_BASE_URL": str(public_bases["mediaImage"]),
        # local-gamma 默认直接服务挂载的 curated media bundle；不要把容器内回源指向宿主 loopback。
        "LOCAL_GAMMA_MEDIA_ORIGIN_BASE_URL": "",
        "LOCAL_GAMMA_CONTENT_PORT": str(ports["content-service"]),
        "LOCAL_GAMMA_CHAT_PORT": str(ports["chat-service"]),
        "LOCAL_GAMMA_USER_PORT": str(ports["user-service"]),
        "LOCAL_GAMMA_ASSISTANT_PORT": str(ports["assistant-service"]),
        "LOCAL_GAMMA_REC_MODEL_PORT": str(ports["rec-model-service"]),
        "LOCAL_GAMMA_PRODUCT_OPS_SERVICE_PORT": str(ports["product-ops-service"]),
        "LOCAL_GAMMA_PLATFORM_OPS_SERVICE_PORT": str(ports["platform-ops-service"]),
        "LOCAL_GAMMA_TAG_PORT": str(ports["tag-service"]),
        "LOCAL_GAMMA_MONGO_PORT": str(ports["mongodb"]),
        "LOCAL_GAMMA_REDIS_PORT": str(ports["redis"]),
        "LOCAL_GAMMA_POSTGRES_PORT": str(ports["postgres"]),
    }


def _health_checks_for_target(topology: dict[str, Any], target_name: str, scope: str) -> list[dict[str, Any]]:
    target = get_target(topology, target_name)
    env_name = str(target["env"])
    env_cfg = topology["environments"][env_name]
    public_bases = target.get("publicBases") or {}
    origins = target.get("origins") or {}
    checks: list[dict[str, Any]] = []
    if scope in {"edge", "full"}:
        checks.extend(
            {
                "name": item_name,
                "scope": "edge",
                "url": item_url,
            }
            for item_name, item_url in (
                ("api-health", f"{str(public_bases['api']).rstrip('/')}/healthz"),
                ("product-ops-health", f"{str(public_bases['productOps']).rstrip('/')}/healthz"),
            )
        )
    if scope in {"media", "full"} and "mediaImage" in public_bases:
        checks.extend(
            [
                {
                    "name": "media-edge-health",
                    "scope": "media",
                    "url": f"{str(public_bases['mediaImage']).rstrip('/')}/healthz",
                },
                {
                    "name": "media-public-sample",
                    "scope": "media",
                    "url": f"{str(public_bases['mediaImage']).rstrip('/')}/media/image/post/fixture_photo_001/v1/cover.png",
                },
            ]
        )
        media_origin = str(origins.get("mediaOrigin") or "").rstrip("/")
        if media_origin:
            checks.append(
                {
                    "name": "media-origin-sample",
                    "scope": "media",
                    "url": f"{media_origin}/media/image/post/fixture_photo_001/v1/cover.png",
                }
            )
    if scope in {"service", "full"}:
        checks.extend(_service_health_checks_for_target(target_name))
    if scope == "full":
        checks.extend(_full_scope_health_checks(target_name, public_bases, env_cfg))
    return checks


def _service_health_checks_for_target(target_name: str) -> list[dict[str, Any]]:
    topology = load_environment_topology()
    target = get_target(topology, target_name)
    env_name = str(target["env"])
    mock_flags = (topology["environments"][env_name].get("mockBoundaryFlags") or {})
    if mock_flags.get("servicePlane"):
        return [
            {
                "name": "service-plane-mocked",
                "scope": "service",
                "url": "",
                "skip": True,
                "reason": "service plane is mocked in this target",
            }
        ]
    profile_name = target.get("portProfile")
    if not profile_name:
        return []
    manifest = load_port_manifest()
    checks: list[dict[str, Any]] = []
    for role_name in _expected_local_roles(target_name):
        if not role_name.endswith("-service"):
            continue
        port = canonical_port(manifest, str(profile_name), role_name)
        path = "/healthz"
        if role_name == "rec-model-service":
            path = "/health"
        checks.append(
            {
                "name": role_name,
                "scope": "service",
                "url": f"http://127.0.0.1:{port}{path}",
            }
        )
    return checks


def _full_scope_health_checks(
    target_name: str,
    public_bases: dict[str, Any],
    env_cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    env_name = str(env_cfg.get("artifactPolicy", {}).get("app", {}).get("runtimeEnv", ""))
    if target_name == "beta-local":
        checks.append(
            {
                "name": "app-config",
                "scope": "full",
                "url": f"{str(public_bases['api']).rstrip('/')}/v1/config/app",
            }
        )
        checks.extend(
            [
                {
                    "name": "content-feed",
                    "scope": "full",
                    "url": f"{str(public_bases['api']).rstrip('/')}/v1/content/feed",
                },
                {
                    "name": "chat-contacts",
                    "scope": "full",
                    "url": f"{str(public_bases['api']).rstrip('/')}/v1/chat/contacts",
                },
            ]
        )
    elif target_name == "gamma-local":
        checks.extend(
            [
                {
                    "name": "app-config",
                    "scope": "full",
                    "url": f"{str(public_bases['api']).rstrip('/')}/v1/config/app",
                },
                {
                    "name": "gamma-route-smoke",
                    "scope": "full",
                    "url": f"{str(public_bases['api']).rstrip('/')}/v1/content/feed?limit=1",
                },
                {
                    "name": "tag-shared-tags-smoke",
                    "scope": "full",
                    "url": (
                        f"{str(public_bases['api']).rstrip('/')}"
                        "/v1/tag/shared-tags?objectAId=u1&objectAType=user&objectBId=u2&objectBType=user"
                    ),
                },
            ]
        )
    elif target_name == "prod-hosted" and env_name == "prod":
        checks.append(
            {
                "name": "prod-smoke",
                "scope": "full",
                "url": f"{str(public_bases['api']).rstrip('/')}/healthz",
            }
        )
    return checks


def _network_report(target_name: str) -> dict[str, Any]:
    topology = load_environment_topology()
    target = get_target(topology, target_name)
    profile_name = target.get("portProfile")
    if not profile_name:
        return {"ports": []}
    manifest = load_port_manifest()
    ports = []
    for role in _expected_local_roles(target_name):
        if role not in manifest["roles"]:
            continue
        port = canonical_port(manifest, profile_name, role)
        ports.append({"name": role, "port": port, "open": socket_probe(port)})
    return {"profile": profile_name, "ports": ports}


def _expected_local_roles(target_name: str) -> list[str]:
    role_map = {
        "alpha-local": [
            "api-edge",
            "product-ops-edge",
            "media-edge",
            "media-origin",
        ],
        "beta-local": [
            "api-edge",
            "product-ops-edge",
            "platform-ops-edge",
            "ops-portal",
            "media-edge",
            "media-origin",
            "assistant-service",
            "chat-service",
        ],
        "gamma-local": [
            "api-edge",
            "product-ops-edge",
            "media-edge",
            "media-origin",
            "chat-service",
            "user-service",
            "content-service",
            "assistant-service",
            "rec-model-service",
            "product-ops-service",
            "tag-service",
        ],
        "prod-sim": [
            "api-edge",
            "product-ops-edge",
            "media-edge",
            "media-origin",
        ],
    }
    return role_map.get(target_name, [])


def _replicas_for_step(step: str) -> int:
    stages = load_json_yaml(ROOT / "deploy" / "shared" / "gray_rollout_stages.yaml")
    total = int((stages or {}).get("total_replicas", 2))
    try:
        numeric = int(step)
    except ValueError:
        return total
    replicas = max(1, numeric * total // 100)
    return min(replicas, total)


def _local_log_report(target_name: str) -> dict[str, Any]:
    candidates: dict[str, Path] = {
        "beta-state": ROOT / "tmp" / "beta_stack",
        "beta-manual": ROOT / "tmp" / "app_beta_manual",
        "app-instances": ROOT / "tmp" / "app-instances",
        "local-gamma": ROOT / "artifacts" / "local-gamma",
        "release-state": ROOT / ".release-state",
    }
    hits = []
    for name, path in candidates.items():
        if path.exists():
            hits.append({"name": name, "path": relpath(path)})
    return {"paths": hits}


def _data_report(target_name: str) -> dict[str, Any]:
    topology = load_environment_topology()
    target = get_target(topology, target_name)
    profile_name = target.get("portProfile")
    if not profile_name:
        return {"ports": []}
    manifest = load_port_manifest()
    return {
        "ports": {
            "postgres": canonical_port(manifest, profile_name, "postgres"),
            "mongodb": canonical_port(manifest, profile_name, "mongodb"),
            "redis": canonical_port(manifest, profile_name, "redis"),
        }
    }


def _metrics_report(topology: dict[str, Any], target_name: str) -> dict[str, Any]:
    checks = _health_checks_for_target(topology, target_name, "full")
    return {
        "probes": [
            {"name": item["name"], "url": item["url"]}
            for item in checks
        ]
    }


def _security_report(topology: dict[str, Any], target_name: str) -> dict[str, Any]:
    target = get_target(topology, target_name)
    env_name = str(target["env"])
    env_cfg = topology["environments"][env_name]
    return {
        "hostAllowlist": env_cfg.get("hostAllowlist", []),
        "forbiddenHostTokens": env_cfg.get("forbiddenHostTokens", []),
        "artifactPolicy": env_cfg.get("artifactPolicy", {}),
    }


def _command_details(result: Any) -> list[str]:
    details = []
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    if stdout:
        details.append(stdout.splitlines()[-1])
    if stderr:
        details.append(stderr.splitlines()[-1])
    if not details:
        details.append(f"exit={result.returncode}")
    return details


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    dispatch = {
        "package": command_package,
        "verify": command_verify,
        "up": command_up,
        "down": command_down,
        "status": command_status,
        "health": command_health,
        "inspect": command_inspect,
        "doctor": command_doctor,
        "repair": command_repair,
        "deploy": command_deploy,
    }
    payload = dispatch[args.command](args)
    return print_result(args, payload)


if __name__ == "__main__":
    raise SystemExit(main())
