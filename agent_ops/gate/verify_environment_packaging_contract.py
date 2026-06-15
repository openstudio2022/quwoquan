#!/usr/bin/env python3
from __future__ import annotations

import json
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_ops.deploy.lib.environment_topology import (
    ENVIRONMENTS,
    app_artifact_policy,
    load_environment_topology,
)


def expected_services() -> list[str]:
    services: list[str] = []
    for path in ROOT.glob("quwoquan_service/services/*/configs/default/config.yaml"):
        services.append(path.parents[2].name)
    return sorted(set(services))


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=ENVIRONMENTS, default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = load_environment_topology()
    issues: list[str] = []
    envs = [args.env] if args.env else list(ENVIRONMENTS)

    for env_name in envs:
        app_dir = ROOT / "artifacts" / "app-env-packages" / env_name
        report_path = app_dir / "report.json"
        cfg_path = app_dir / "app_runtime.yaml"
        if not report_path.is_file():
            issues.append(f"missing app package report: {report_path.relative_to(ROOT)}")
            continue
        if not cfg_path.is_file():
            issues.append(f"missing app package runtime: {cfg_path.relative_to(ROOT)}")
            continue
        report = load_json(report_path)
        policy = app_artifact_policy(manifest, env_name)
        if report.get("env") != env_name:
            issues.append(f"{report_path.relative_to(ROOT)} env mismatch")
        if report.get("runtimeEnv") != policy.get("runtimeEnv"):
            issues.append(f"{report_path.relative_to(ROOT)} runtimeEnv mismatch")
        if report.get("dataSource") != policy.get("dataSource"):
            issues.append(f"{report_path.relative_to(ROOT)} dataSource mismatch")

    services = expected_services()
    for service in services:
        for env_name in envs:
            service_dir = (
                ROOT / "artifacts" / "service-env-packages" / service / env_name
            )
            report_path = service_dir / "report.json"
            cfg_path = service_dir / "config.yaml"
            default_cfg_path = service_dir / "default_config.yaml"
            if not report_path.is_file():
                issues.append(
                    f"missing service package report: {report_path.relative_to(ROOT)}"
                )
                continue
            if not cfg_path.is_file() or not default_cfg_path.is_file():
                issues.append(
                    f"missing service package config(s): {service_dir.relative_to(ROOT)}"
                )
                continue
            report = load_json(report_path)
            if report.get("service") != service:
                issues.append(f"{report_path.relative_to(ROOT)} service mismatch")
            if report.get("env") != env_name:
                issues.append(f"{report_path.relative_to(ROOT)} env mismatch")
            if report.get("configLayout") != "default+env":
                issues.append(f"{report_path.relative_to(ROOT)} configLayout mismatch")

    if issues:
        print("[verify_environment_packaging_contract] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print("[verify_environment_packaging_contract] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
