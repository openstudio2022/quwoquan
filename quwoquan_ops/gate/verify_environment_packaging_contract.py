#!/usr/bin/env python3
from __future__ import annotations

import json
import argparse
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.environment_topology import (
    ENVIRONMENTS,
    app_artifact_policy,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.output_paths import (
    app_deployment_package_dir,
    deployment_target_for_env,
    service_deployment_package_dir,
)


def expected_services() -> list[str]:
    services: list[str] = []
    for path in ROOT.glob("quwoquan_service/services/*/configs/default/config.yaml"):
        services.append(path.parents[2].name)
    return sorted(set(services))


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _display(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def validate_provenance(report: dict[str, object], package_dir: Path) -> list[str]:
    provenance = report.get("provenance")
    if not isinstance(provenance, dict):
        return ["missing provenance"]
    revision = str(provenance.get("gitRevision") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        return ["invalid provenance gitRevision"]
    files = provenance.get("files")
    if not isinstance(files, dict) or not files:
        return ["missing provenance files"]
    issues: list[str] = []
    for label, expected in files.items():
        if not isinstance(label, str) or not isinstance(expected, str):
            issues.append("invalid provenance file entry")
            continue
        candidates = {
            "defaultAppRuntime": package_dir / "default_app_runtime.yaml",
            "appRuntime": package_dir / "app_runtime.yaml",
            "defaultConfig": package_dir / "default_config.yaml",
            "environmentConfig": package_dir / "config.yaml",
            "topologyManifest": package_dir / "environment_topology_manifest.yaml",
        }
        path = candidates.get(label)
        if path is None or not path.is_file():
            issues.append(f"unknown or missing provenance file {label}")
        elif _sha256(path) != expected:
            issues.append(f"provenance digest mismatch for {label}")
    releases = provenance.get("releaseFiles", {})
    if not isinstance(releases, dict):
        issues.append("invalid provenance releaseFiles")
    else:
        for name, expected in releases.items():
            path = package_dir / "releases" / str(name)
            if not isinstance(expected, str) or not path.is_file():
                issues.append(f"invalid provenance release file {name}")
            elif _sha256(path) != expected:
                issues.append(f"provenance digest mismatch for release {name}")
    return issues


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=ENVIRONMENTS, default="")
    parser.add_argument("--target", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = load_environment_topology()
    issues: list[str] = []
    envs = [args.env] if args.env else list(ENVIRONMENTS)

    for env_name in envs:
        try:
            target_name = deployment_target_for_env(env_name, target=args.target)
        except ValueError as exc:
            issues.append(str(exc))
            continue
        app_dir = app_deployment_package_dir(env_name, target=target_name)
        report_path = app_dir / "report.json"
        cfg_path = app_dir / "app_runtime.yaml"
        if not report_path.is_file():
            issues.append(f"missing app package report: {_display(report_path)}")
            continue
        if not cfg_path.is_file():
            issues.append(f"missing app package runtime: {_display(cfg_path)}")
            continue
        report = load_json(report_path)
        policy = app_artifact_policy(manifest, env_name)
        if report.get("env") != env_name:
            issues.append(f"{_display(report_path)} env mismatch")
        if report.get("runtimeEnv") != policy.get("runtimeEnv"):
            issues.append(f"{_display(report_path)} runtimeEnv mismatch")
        if report.get("dataSource") != policy.get("dataSource"):
            issues.append(f"{_display(report_path)} dataSource mismatch")
        for issue in validate_provenance(report, app_dir):
            issues.append(f"{_display(report_path)} {issue}")

    services = expected_services()
    for service in services:
        for env_name in envs:
            try:
                target_name = deployment_target_for_env(env_name, target=args.target)
            except ValueError:
                continue
            service_dir = service_deployment_package_dir(
                env_name,
                service,
                target=target_name,
            )
            report_path = service_dir / "report.json"
            cfg_path = service_dir / "config.yaml"
            default_cfg_path = service_dir / "default_config.yaml"
            if not report_path.is_file():
                issues.append(
                    f"missing service package report: {_display(report_path)}"
                )
                continue
            if not cfg_path.is_file() or not default_cfg_path.is_file():
                issues.append(
                    f"missing service package config(s): {_display(service_dir)}"
                )
                continue
            report = load_json(report_path)
            if report.get("service") != service:
                issues.append(f"{_display(report_path)} service mismatch")
            if report.get("env") != env_name:
                issues.append(f"{_display(report_path)} env mismatch")
            if report.get("configLayout") != "default+env":
                issues.append(f"{_display(report_path)} configLayout mismatch")
            for issue in validate_provenance(report, service_dir):
                issues.append(f"{_display(report_path)} {issue}")

    if issues:
        print("[verify_environment_packaging_contract] FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print("[verify_environment_packaging_contract] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
