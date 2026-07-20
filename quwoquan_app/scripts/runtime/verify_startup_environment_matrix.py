#!/usr/bin/env python3
"""Validate startup packages and optional cross-platform UAT evidence."""

from __future__ import annotations

import argparse
import base64
import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any


APP_DIR = Path(__file__).resolve().parents[2]
ENVIRONMENTS = ("alpha", "beta", "gamma", "prod")
PLATFORMS = ("android", "ios", "web")
REQUIRED_DEFINES = {
    "APP_RUNTIME_ENV",
    "CLOUD_GATEWAY_BASE_URL",
    "APP_LEGAL_BASE_URL",
    "MEDIA_AVATAR_CDN_BASE_URL",
    "MEDIA_IMAGE_CDN_BASE_URL",
    "MEDIA_VIDEO_CDN_BASE_URL",
    "MEDIA_UPLOAD_BASE_URL",
}


def _run(*argv: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=APP_DIR,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _runtime_defines(environment: str) -> dict[str, str]:
    result = _run(
        "python3",
        "scripts/env/print_app_env_dart_defines.py",
        "--env",
        environment,
        "--format",
        "json",
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return json.loads(result.stdout)


def _ios_defines(environment: str) -> dict[str, str]:
    process_env = dict(os.environ)
    process_env["QWQ_APP_RUNTIME_ENV"] = environment
    process_env.pop("DART_DEFINES", None)
    result = _run("bash", "scripts/ios/prepare_dart_defines.sh", env=process_env)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    export_line = next(
        line
        for line in result.stdout.splitlines()
        if line.startswith("export DART_DEFINES=")
    )
    assignment = shlex.split(export_line.removeprefix("export "))[0]
    encoded = assignment.split("=", 1)[1]
    values: dict[str, str] = {}
    for item in encoded.split(","):
        decoded = base64.b64decode(item).decode("utf-8")
        key, value = decoded.split("=", 1)
        values[key] = value
    return values


def _validate_defines(environment: str, values: dict[str, str]) -> list[str]:
    issues = [
        f"{environment}: missing {key}"
        for key in sorted(REQUIRED_DEFINES)
        if not values.get(key, "").strip()
    ]
    if values.get("APP_RUNTIME_ENV") != environment:
        issues.append(f"{environment}: APP_RUNTIME_ENV mismatch")
    return issues


def _validate_runtime_evidence(
    path: Path,
    *,
    expected_environment: str = "",
) -> tuple[list[str], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    issues: list[str] = []
    if not str(payload.get("attemptId") or "").strip():
        issues.append(f"{path}: attemptId missing")
    if expected_environment and payload.get("runtimeEnv") != expected_environment:
        issues.append(
            f"{path}: runtimeEnv must equal {expected_environment}"
        )
    if not str(payload.get("launchMode") or "").strip() or payload.get(
        "launchMode"
    ) == "unknown":
        issues.append(f"{path}: launchMode missing from runtime evidence")
    if payload.get("runtimeConfigurationState") != "complete":
        issues.append(f"{path}: runtime configuration was not complete")
    if payload.get("missingDefineKeys"):
        issues.append(f"{path}: missing define keys reported at runtime")
    if not isinstance(payload.get("failureCode"), str):
        issues.append(f"{path}: failureCode missing from runtime evidence")
    for key in (
        "rendererFirstFrameMs",
        "safeTerminalMs",
        "reportedSafeTerminalMs",
        "nativeReceivedSafeTerminalMs",
    ):
        value = payload.get(key)
        if not isinstance(value, (int, float)):
            issues.append(f"{path}: {key} missing")
        elif value > 6000:
            issues.append(f"{path}: {key} must be <= 6000")
    if payload.get("watchdogOutcome") == "native_recovery":
        issues.append(f"{path}: native watchdog recovery observed")
    if payload.get("canonicalTerminal") != "routerShell":
        issues.append(f"{path}: canonical terminal must be routerShell")
    return issues, payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", default="")
    parser.add_argument("--require-runtime-evidence", action="store_true")
    parser.add_argument("--require-observability", action="store_true")
    parser.add_argument("--report", default="")
    args = parser.parse_args()

    issues: list[str] = []
    packages: dict[str, Any] = {}
    runtime_evidence: dict[str, Any] = {}
    root = Path(args.evidence_root) if args.evidence_root else None

    for environment in ENVIRONMENTS:
        runtime = _runtime_defines(environment)
        ios = _ios_defines(environment)
        package_issues = [
            *_validate_defines(environment, runtime),
            *_validate_defines(environment, ios),
        ]
        issues.extend(package_issues)
        packages[environment] = {
            "runtimeDefineKeys": sorted(runtime),
            "iosDefineKeys": sorted(ios),
            "status": "passed" if not package_issues else "failed",
        }

        if root is not None:
            for platform in PLATFORMS:
                evidence_path = root / environment / f"{platform}.json"
                key = f"{environment}/{platform}"
                if not evidence_path.is_file():
                    runtime_evidence[key] = {"status": "missing"}
                    if args.require_runtime_evidence:
                        issues.append(f"{evidence_path}: runtime evidence missing")
                    continue
                evidence_issues, payload = _validate_runtime_evidence(
                    evidence_path,
                    expected_environment=environment,
                )
                issues.extend(evidence_issues)
                runtime_evidence[key] = {
                    "status": "passed" if not evidence_issues else "failed",
                    "evidence": payload,
                }

            observability_path = root / environment / "observability.json"
            observability_ready = False
            if observability_path.is_file():
                observability = json.loads(
                    observability_path.read_text(encoding="utf-8")
                )
                observability_ready = observability.get("status") == "passed"
            if args.require_observability and environment != "alpha" and not observability_ready:
                issues.append(
                    f"{observability_path}: observability report gate not passed"
                )

    report = {
        "status": "passed" if not issues else "failed",
        "packages": packages,
        "runtimeEvidence": runtime_evidence,
        "issues": issues,
    }
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
