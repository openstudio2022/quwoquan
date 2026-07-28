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
PLATFORMS = ("android", "ios")
RUNTIME_TARGETS = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
    "prod": "prod-sim",
}
RUNTIME_CASES = (
    ("alpha", "alpha-local"),
    ("beta", "beta-local"),
    ("gamma", "gamma-local"),
    ("prod", "prod-sim"),
    ("prod", "prod-hosted"),
)
REQUIRED_DEFINES = {
    "APP_RUNTIME_ENV",
    "CLOUD_GATEWAY_BASE_URL",
    "APP_LEGAL_BASE_URL",
    "PUBLIC_WEB_BASE_URL",
    "MEDIA_AVATAR_CDN_BASE_URL",
    "MEDIA_IMAGE_CDN_BASE_URL",
    "MEDIA_VIDEO_CDN_BASE_URL",
    "MEDIA_UPLOAD_BASE_URL",
    "RTC_MEDIA_CONNECTION_URL",
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
    handoff = _launcher_handoff(environment)
    process_env["QWQ_APP_RUNTIME_ENV"] = environment
    process_env["QWQ_APP_LAUNCH_MODE"] = str(handoff["launchMode"])
    process_env["QWQ_LAUNCH_TARGET"] = str(handoff["target"])
    process_env["QWQ_DART_DEFINES_DIGEST"] = str(handoff["dartDefinesDigest"])
    process_env["QWQ_EXPECTED_RUNTIME_CONFIG_DIGEST"] = str(
        handoff["runtimeConfigDigest"]
    )
    process_env["QWQ_EFFECTIVE_LAUNCH_MANIFEST_DIGEST"] = str(
        handoff["effectiveLaunchManifestDigest"]
    )
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


def _launcher_handoff(
    environment: str,
    target: str | None = None,
) -> dict[str, Any]:
    result = _run(
        "python3",
        "scripts/device/build_launcher_handoff.py",
        "--env",
        environment,
        "--target",
        target or RUNTIME_TARGETS[environment],
        "--launch-mode",
        "matrix_verify",
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return json.loads(result.stdout)


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
    expected_target: str = "",
    expected_platform: str = "",
    expected_effective_manifest_digest: str = "",
    expected_device_kind: str = "",
    minimum_runs: int = 1,
) -> tuple[list[str], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    samples = payload.get("samples")
    if not isinstance(samples, list):
        samples = [payload]
    issues: list[str] = []
    declared_runs = payload.get("runs")
    if declared_runs is not None and declared_runs != len(samples):
        issues.append(
            f"{path}: declared runs {declared_runs} does not match "
            f"{len(samples)} samples"
        )
    if len(samples) < minimum_runs:
        issues.append(
            f"{path}: runtime evidence has {len(samples)} runs; "
            f"at least {minimum_runs} required"
        )
    if payload.get("passed") is False:
        issues.append(f"{path}: runtime probe aggregate did not pass")
    attempt_ids = [
        str(sample.get("attemptId") or "")
        for sample in samples
        if isinstance(sample, dict)
    ]
    if len(set(attempt_ids)) != len(attempt_ids):
        issues.append(f"{path}: runtime samples reuse an attemptId")
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict):
            issues.append(f"{path}: sample {index + 1} is not an object")
            continue
        issues.extend(
            _validate_runtime_sample(
                sample,
                label=f"{path}#run-{index + 1:02d}",
                expected_environment=expected_environment,
                expected_target=expected_target,
                expected_platform=expected_platform,
                expected_effective_manifest_digest=(
                    expected_effective_manifest_digest
                ),
                expected_device_kind=expected_device_kind,
            )
        )
    return issues, payload


def _validate_runtime_sample(
    payload: dict[str, Any],
    *,
    label: str,
    expected_environment: str,
    expected_target: str,
    expected_platform: str,
    expected_effective_manifest_digest: str,
    expected_device_kind: str,
) -> list[str]:
    issues: list[str] = []
    if payload.get("passed") is not True:
        issues.append(f"{label}: startup probe did not pass")
    attempt_id = str(payload.get("attemptId") or "").strip()
    if attempt_id in {"", "unknown"}:
        issues.append(f"{label}: attemptId missing")
    if expected_environment and payload.get("runtimeEnv") != expected_environment:
        issues.append(
            f"{label}: runtimeEnv must equal {expected_environment}"
        )
    if expected_target and payload.get("runtimeTarget") != expected_target:
        issues.append(f"{label}: runtimeTarget must equal {expected_target}")
    if expected_device_kind and payload.get("deviceKind") != expected_device_kind:
        issues.append(f"{label}: deviceKind must equal {expected_device_kind}")
    if not str(payload.get("launchMode") or "").strip() or payload.get(
        "launchMode"
    ) == "unknown":
        issues.append(f"{label}: launchMode missing from runtime evidence")
    if payload.get("runtimeConfigurationState") != "complete":
        issues.append(f"{label}: runtime configuration was not complete")
    if payload.get("missingDefineKeys"):
        issues.append(f"{label}: missing define keys reported at runtime")
    if not isinstance(payload.get("failureCode"), str):
        issues.append(f"{label}: failureCode missing from runtime evidence")
    for key in (
        "rendererFirstFrameMs",
        "safeTerminalMs",
        "reportedSafeTerminalMs",
        "nativeReceivedSafeTerminalMs",
    ):
        value = payload.get(key)
        if not isinstance(value, (int, float)):
            issues.append(f"{label}: {key} missing")
        elif value > 6000:
            issues.append(f"{label}: {key} must be <= 6000")
    if payload.get("watchdogOutcome") == "native_recovery":
        issues.append(f"{label}: native watchdog recovery observed")
    if payload.get("canonicalTerminal") != "routerShell":
        issues.append(f"{label}: canonical terminal must be routerShell")
    if payload.get("startupSequenceMotionCurrent") is not True:
        issues.append(f"{label}: startup motion evidence is missing or stale")
    if payload.get("telemetryAcknowledged") is not True:
        issues.append(f"{label}: startup telemetry was not acknowledged")
    if (
        expected_effective_manifest_digest
        and payload.get("effectiveLaunchManifestDigest")
        != expected_effective_manifest_digest
    ):
        issues.append(
            f"{label}: effective launch manifest digest does not match package"
        )
    if expected_platform == "android":
        if payload.get("launcherIntentUsed") is not True:
            issues.append(f"{label}: Android MAIN/LAUNCHER intent was not used")
        if payload.get("launcherStarted") is not True:
            issues.append(f"{label}: Android resolved launcher did not start")
        resolution = payload.get("launcherResolution")
        if (
            not isinstance(resolution, dict)
            or resolution.get("matchesExpectedGate") is not True
        ):
            issues.append(
                f"{label}: Android launcher did not resolve to native Gate"
            )
        if payload.get("gateMainOrderObserved") is not True:
            issues.append(f"{label}: Android Gate/Main order was not observed")
        task = payload.get("taskSnapshot")
        if (
            not isinstance(task, dict)
            or task.get("singleMainTask") is not True
            or task.get("mainActivityInstances") != 1
        ):
            issues.append(f"{label}: Android MainActivity task is not singular")
        visual = payload.get("launchVisual")
        if (
            not isinstance(visual, dict)
            or visual.get("contractVerified") is not True
            or len(str(visual.get("sourceDigest") or "")) != 64
            or visual.get("profile") not in {
                "default",
                "sw360dp",
                "sw393dp",
                "sw430dp",
            }
        ):
            issues.append(
                f"{label}: Android launch visual provenance is incomplete"
            )
    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", default="")
    parser.add_argument("--require-runtime-evidence", action="store_true")
    parser.add_argument("--require-observability", action="store_true")
    parser.add_argument(
        "--require-physical-release",
        action="store_true",
        help="Require prod-hosted Android and iOS samples from physical devices.",
    )
    parser.add_argument(
        "--minimum-runtime-runs",
        type=int,
        default=1,
        help="Minimum independently validated cold-start samples per target/platform.",
    )
    parser.add_argument("--report", default="")
    args = parser.parse_args()

    issues: list[str] = []
    packages: dict[str, Any] = {}
    runtime_evidence: dict[str, Any] = {}
    root = Path(args.evidence_root) if args.evidence_root else None

    for environment in ENVIRONMENTS:
        runtime = _runtime_defines(environment)
        ios = _ios_defines(environment)
        handoff = _launcher_handoff(environment)
        package_issues = [
            *_validate_defines(environment, runtime),
            *_validate_defines(environment, ios),
        ]
        issues.extend(package_issues)
        packages[environment] = {
            "runtimeDefineKeys": sorted(runtime),
            "iosDefineKeys": sorted(ios),
            "runtimeTarget": handoff["target"],
            "entrypoint": handoff["entrypoint"],
            "dartDefinesDigest": handoff["dartDefinesDigest"],
            "runtimeConfigDigest": handoff["runtimeConfigDigest"],
            "effectiveLaunchManifestDigest": handoff[
                "effectiveLaunchManifestDigest"
            ],
            "status": "passed" if not package_issues else "failed",
        }

    if root is not None:
        for environment, target in RUNTIME_CASES:
            handoff = _launcher_handoff(environment, target)
            for platform in PLATFORMS:
                evidence_path = root / target / f"{platform}.json"
                key = f"{target}/{platform}"
                if not evidence_path.is_file():
                    runtime_evidence[key] = {"status": "missing"}
                    if args.require_runtime_evidence:
                        issues.append(f"{evidence_path}: runtime evidence missing")
                    continue
                evidence_issues, payload = _validate_runtime_evidence(
                    evidence_path,
                    expected_environment=environment,
                    expected_target=target,
                    expected_platform=platform,
                    expected_effective_manifest_digest=str(
                        handoff["effectiveLaunchManifestDigest"]
                    ),
                    expected_device_kind=(
                        "physical"
                        if args.require_physical_release
                        and target == "prod-hosted"
                        else ""
                    ),
                    minimum_runs=max(args.minimum_runtime_runs, 1),
                )
                issues.extend(evidence_issues)
                runtime_evidence[key] = {
                    "status": "passed" if not evidence_issues else "failed",
                    "evidence": payload,
                }

            observability_path = root / target / "observability.json"
            observability_ready = False
            if observability_path.is_file():
                observability = json.loads(
                    observability_path.read_text(encoding="utf-8")
                )
                observed_attempts = observability.get("attemptIds")
                expected_attempts = {
                    str(sample.get("attemptId") or "")
                    for platform_payload in (
                        runtime_evidence.get(f"{target}/{platform}", {}).get(
                            "evidence",
                            {},
                        )
                        for platform in PLATFORMS
                    )
                    for sample in platform_payload.get("samples", [])
                    if isinstance(sample, dict)
                }
                observability_ready = (
                    observability.get("status") == "passed"
                    and isinstance(observed_attempts, list)
                    and expected_attempts
                    and expected_attempts.issubset(
                        {str(value) for value in observed_attempts}
                    )
                    and observability.get("effectiveLaunchManifestDigest")
                    == handoff["effectiveLaunchManifestDigest"]
                )
            if args.require_observability and not observability_ready:
                issues.append(
                    f"{observability_path}: telemetry readback is missing "
                    "attempt IDs or launch manifest identity"
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
