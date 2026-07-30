#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STACKCTL = ROOT / "quwoquan_ops" / "cli" / "stackctl.py"
PORT_PROFILE = ROOT / "quwoquan_ops" / "cli" / "print_local_port_profile.py"
TMP = ROOT / ".qwq_output" / "env" / "repo" / "local" / "stackctl-contract" / "process"
DEPLOY_WORK_ROOT = tempfile.TemporaryDirectory(prefix="qwq-stackctl-contract-")


def run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["QWQ_DEPLOY_WORK_ROOT"] = DEPLOY_WORK_ROOT.name
    return subprocess.run(
        argv,
        cwd=str(ROOT),
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> int:
    issues: list[str] = []

    help_result = run(["python3", str(STACKCTL), "--help"])
    required_commands = (
        "package",
        "content-readiness",
        "account-enforcement-uat",
        "data-execution-fleet",
        "filter-catalog",
        "deploy",
        "roll",
        "matrix",
    )
    if help_result.returncode != 0 or any(command not in help_result.stdout for command in required_commands):
        issues.append(
            "stackctl --help must list package, content-readiness, data-execution-fleet, "
            "account-enforcement-uat, filter-catalog, roll, deploy and matrix commands"
        )

    readiness_help = run(["python3", str(STACKCTL), "content-readiness", "--help"])
    if (
        readiness_help.returncode != 0
        or "--target" in readiness_help.stdout
        or "--phase" not in readiness_help.stdout
        or "--env" not in readiness_help.stdout
    ):
        issues.append("stackctl content-readiness must require phase/env and forbid target override")

    fleet_result = run(
        ["python3", str(STACKCTL), "--output-format", "json", "data-execution-fleet"]
    )
    if fleet_result.returncode != 0:
        issues.append("stackctl data-execution-fleet failed")
    else:
        try:
            fleet_payload = json.loads(fleet_result.stdout)
            fleet = fleet_payload.get("fleet") or {}
            if set(fleet) != {"target", "mongoUri", "redisAddr"}:
                issues.append("stackctl data-execution-fleet must return the exact fleet endpoint contract")
        except json.JSONDecodeError:
            issues.append("stackctl data-execution-fleet must return JSON with --output-format json")

    verify_help = run(["python3", str(STACKCTL), "verify", "--help"])
    if (
        verify_help.returncode != 0
        or "--kind" not in verify_help.stdout
        or "--profile" not in verify_help.stdout
        or "--reuse-package" in verify_help.stdout
        or "--" + "tier" in verify_help.stdout
    ):
        issues.append(
            "stackctl verify --help must expose --kind/--profile and forbid --reuse-package/--tier"
        )

    matrix_help = run(["python3", str(STACKCTL), "matrix", "--help"])
    if (
        matrix_help.returncode != 0
        or "--profile" not in matrix_help.stdout
        or "local-env-gate" not in matrix_help.stdout
        or "--targets" not in matrix_help.stdout
        or "--cache-mode" in matrix_help.stdout
        or "--no-auto-wipe-drift" in matrix_help.stdout
    ):
        issues.append(
            "stackctl matrix must require canonical targets and forbid cache/auto-wipe shortcuts"
        )

    health_help = run(["python3", str(STACKCTL), "health", "--help"])
    if health_help.returncode != 0 or "--scope" not in health_help.stdout:
        issues.append("stackctl health --help must expose --scope")

    inspect_help = run(["python3", str(STACKCTL), "inspect", "--help"])
    if inspect_help.returncode != 0 or "--kind" not in inspect_help.stdout:
        issues.append("stackctl inspect --help must expose --kind alias")

    up_help = run(["python3", str(STACKCTL), "up", "--help"])
    if (
        up_help.returncode != 0
        or "--env" not in up_help.stdout
        or "--device-id" not in up_help.stdout
        or "--workload" not in up_help.stdout
    ):
        issues.append("stackctl up --help must expose --env/--device-id/--workload")
    if "--gateway-base-url" in up_help.stdout:
        issues.append("stackctl up user surface must not expose gateway override flags")

    filter_catalog_help = run(["python3", str(STACKCTL), "filter-catalog", "--help"])
    if (
        filter_catalog_help.returncode != 0
        or "--target" not in filter_catalog_help.stdout
        or "--action" not in filter_catalog_help.stdout
        or "--base-url" in filter_catalog_help.stdout
        or "prod-hosted" not in filter_catalog_help.stdout
    ):
        issues.append(
            "stackctl filter-catalog must bind target/action and forbid API URL overrides"
        )

    account_enforcement_help = run(
        ["python3", str(STACKCTL), "account-enforcement-uat", "--help"]
    )
    if (
        account_enforcement_help.returncode != 0
        or "--target" not in account_enforcement_help.stdout
        or "--action" not in account_enforcement_help.stdout
        or "device-suspended" not in account_enforcement_help.stdout
        or "device-restored" not in account_enforcement_help.stdout
        or "verify" not in account_enforcement_help.stdout
        or "--gateway-base-url" in account_enforcement_help.stdout
        or "--product-ops-base-url" in account_enforcement_help.stdout
    ):
        issues.append(
            "stackctl account-enforcement-uat must expose only canonical "
            "Gamma action/evidence inputs and forbid topology URL overrides"
        )

    roll_help = run(["python3", str(STACKCTL), "roll", "--help"])
    if roll_help.returncode != 0 or "--mode" not in roll_help.stdout or "--target" not in roll_help.stdout:
        issues.append("stackctl roll --help must expose --mode/--target")

    deploy_help = run(["python3", str(STACKCTL), "deploy", "--help"])
    if (
        deploy_help.returncode != 0
        or "--mode" not in deploy_help.stdout
        or "--stage" not in deploy_help.stdout
        or "carry-on" not in deploy_help.stdout
    ):
        issues.append("stackctl deploy --help must expose --mode and all rollout stages")

    profile_result = run(
        ["python3", str(PORT_PROFILE), "--profile", "beta-local", "--format", "json"]
    )
    if profile_result.returncode != 0:
        issues.append("print_local_port_profile beta-local failed")
    else:
        payload = json.loads(profile_result.stdout)
        env_map = payload.get("env") or {}
        if "GATEWAY_PORT" not in env_map or "MEDIA_PORT" not in env_map or "MEDIA_ORIGIN_PORT" not in env_map:
            issues.append("beta-local port profile missing gateway/media env exports")

    package_help_pre_subcommand = run(
        [
            "python3",
            str(STACKCTL),
            "--report-dir",
            str(TMP / "package-alpha"),
            "package",
            "--help",
        ]
    )
    if package_help_pre_subcommand.returncode != 0:
        issues.append("stackctl package must accept --report-dir before the subcommand")

    package_help_post_subcommand = run(
        [
            "python3",
            str(STACKCTL),
            "package",
            "--report-dir",
            str(TMP / "package-alpha-post-subcommand"),
            "--help",
        ]
    )
    if (
        package_help_post_subcommand.returncode != 0
        or "--report-dir" not in package_help_post_subcommand.stdout
    ):
        issues.append("stackctl package must accept --report-dir after the subcommand")

    if issues:
        print("[verify_stackctl_args_contract] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print("[verify_stackctl_args_contract] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
