#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_ops.deploy.lib.dev_up import resolve_app_endpoint_overrides
from agent_ops.deploy.lib.environment_topology import load_environment_topology

STACKCTL = ROOT / "agent_ops" / "deploy" / "stackctl.py"


def run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> int:
    issues: list[str] = []

    up_help = run(["python3", str(STACKCTL), "up", "--help"])
    if up_help.returncode != 0:
        issues.append("stackctl up --help failed")
        help_stdout = up_help.stdout + up_help.stderr
    else:
        help_stdout = up_help.stdout

    if "--env" not in help_stdout:
        issues.append("stackctl up --help must expose --env")
    if "--gateway-base-url" in help_stdout:
        issues.append("stackctl up must not expose --gateway-base-url to users")

    conflict = run(["python3", str(STACKCTL), "up", "--env", "beta", "--target", "beta-local", "--skip-app"])
    if conflict.returncode == 0 or "provide exactly one of --env or --target" not in (conflict.stdout + conflict.stderr):
        issues.append("stackctl up must reject simultaneous --env and --target")

    missing = run(["python3", str(STACKCTL), "up", "--skip-app"])
    missing_output = missing.stdout + missing.stderr
    if missing.returncode == 0 or "dev-up environment is missing" not in missing_output:
        issues.append("stackctl up must prompt or fail clearly when env selector is missing")

    topology = load_environment_topology()
    beta_android = resolve_app_endpoint_overrides("beta", "android_emulator", topology=topology)
    if beta_android["gatewayBaseUrl"] != "http://10.0.2.2:18000":
        issues.append("beta android emulator must map gateway to 10.0.2.2:18000")
    gamma_web = resolve_app_endpoint_overrides("gamma", "web", topology=topology)
    if gamma_web["gatewayBaseUrl"] != "http://127.0.0.1:19000":
        issues.append("gamma web must map gateway to 127.0.0.1:19000")

    if issues:
        print("[verify_dev_up_cli_surface] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print("[verify_dev_up_cli_surface] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
