#!/usr/bin/env python3
"""Validate the canonical startup environment CaseResult evidence flow.

Package/define checks are component-readiness evidence only.  A release-bound
matrix can pass only when every required launcher, readback and observability
case exists and validates against one baseline/release identity.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any


APP_DIR = Path(__file__).resolve().parents[2]
ENVIRONMENTS = ("alpha", "beta", "gamma", "prod")
RUNTIME_TARGETS = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
    "prod": "prod-hosted",
}
RUNTIME_CASES = (
    ("alpha", "alpha-local"),
    ("beta", "beta-local"),
    ("gamma", "gamma-local"),
    ("prod", "prod-hosted"),
)
DEVICE_PROFILES = {
    "alpha-local": (
        ("android", "simulator", "android-simulator"),
        ("android", "true_device", "android-physical"),
        ("ios", "simulator", "ios-simulator"),
    ),
    "beta-local": (
        ("android", "simulator", "android-simulator"),
        ("android", "true_device", "android-physical"),
        ("ios", "simulator", "ios-simulator"),
    ),
    "gamma-local": (
        ("android", "simulator", "android-simulator"),
        ("android", "true_device", "android-physical"),
        ("ios", "simulator", "ios-simulator"),
    ),
    "prod-hosted": (
        ("android", "true_device", "android-physical"),
        ("ios", "physical", "ios-physical"),
    ),
}
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
SPEC_REFS = (
    "specs/feature-tree/spec.md#uat-003",
    (
        "specs/feature-tree/runtime/runtime-data-engineering/"
        "spec.md#sit-001"
    ),
    (
        "specs/feature-tree/runtime/runtime-client-foundation/"
        "cold-start-performance/spec.md#gwt-004"
    ),
    (
        "specs/feature-tree/runtime/runtime-config/"
        "environment-topology-and-packaging/spec.md#gwt-001"
    ),
    (
        "specs/feature-tree/runtime/runtime-config/"
        "environment-topology-and-packaging/spec.md#gwt-002"
    ),
)
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
RUNTIME_EVIDENCE_SCHEMA = "qwq.startup-runtime-evidence"
READBACK_EVIDENCE_SCHEMA = "qwq.app-core-readback-evidence"
OBSERVABILITY_EVIDENCE_SCHEMA = "qwq.startup-observability-readback"


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


def _missing_spec_refs(payload: dict[str, Any]) -> list[str]:
    values = payload.get("specRefs")
    if not isinstance(values, list) or any(
        not isinstance(value, str) for value in values
    ):
        return list(SPEC_REFS)
    return sorted(set(SPEC_REFS) - set(values))


def _validate_runtime_evidence(
    path: Path,
    *,
    expected_environment: str = "",
    expected_target: str = "",
    expected_platform: str = "",
    expected_effective_manifest_digest: str = "",
    expected_device_kind: str = "",
    expected_baseline_id: str = "",
    expected_release_id: str = "",
    expected_release_digest: str = "",
    require_device_identity: bool = False,
    minimum_runs: int = 1,
) -> tuple[list[str], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    release_bound = any(
        (expected_baseline_id, expected_release_id, expected_release_digest)
    )
    raw_samples = payload.get("samples")
    samples = raw_samples
    if not isinstance(samples, list):
        samples = [payload]
    issues: list[str] = []
    if release_bound and payload.get("schema") != RUNTIME_EVIDENCE_SCHEMA:
        issues.append(
            f"{path}: schema must equal {RUNTIME_EVIDENCE_SCHEMA}"
        )
    if release_bound and not isinstance(raw_samples, list):
        issues.append(f"{path}: release-bound samples must be an array")
    if payload.get("passed") is not True:
        issues.append(f"{path}: runtime probe aggregate did not pass")
    for field, expected in (
        ("baselineId", expected_baseline_id),
        ("releaseId", expected_release_id),
        ("releaseDigest", expected_release_digest),
    ):
        if expected and payload.get(field) != expected:
            issues.append(f"{path}: {field} does not match candidate")
    if expected_environment and payload.get("runtimeEnv") not in {
        None,
        expected_environment,
    }:
        issues.append(f"{path}: runtimeEnv must equal {expected_environment}")
    if expected_target and payload.get("runtimeTarget") not in {
        None,
        expected_target,
    }:
        issues.append(f"{path}: runtimeTarget must equal {expected_target}")
    if expected_platform and payload.get("platform") not in {
        None,
        expected_platform,
    }:
        issues.append(f"{path}: platform must equal {expected_platform}")
    declared_runs = payload.get("runs")
    if release_bound and not isinstance(declared_runs, int):
        issues.append(f"{path}: release-bound runs must be an integer")
    elif declared_runs is not None and declared_runs != len(samples):
        issues.append(
            f"{path}: declared runs {declared_runs} does not match "
            f"{len(samples)} samples"
        )
    if len(samples) < minimum_runs:
        issues.append(
            f"{path}: runtime evidence has {len(samples)} runs; "
            f"at least {minimum_runs} required"
        )
    if release_bound:
        missing_refs = _missing_spec_refs(payload)
        if missing_refs:
            issues.append(
                f"{path}: release-bound specRefs are incomplete: "
                + ", ".join(missing_refs)
            )
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
                require_device_identity=require_device_identity,
                require_source_report=release_bound,
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
    require_device_identity: bool = False,
    require_source_report: bool = False,
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
    if expected_platform and payload.get("platform") != expected_platform:
        issues.append(f"{label}: platform must equal {expected_platform}")
    if expected_device_kind and payload.get("deviceKind") != expected_device_kind:
        issues.append(f"{label}: deviceKind must equal {expected_device_kind}")
    if require_device_identity and str(payload.get("deviceId") or "").strip() in {
        "",
        "unknown",
    }:
        issues.append(f"{label}: deviceId missing")
    if require_source_report and not str(payload.get("sourceReport") or "").strip():
        issues.append(f"{label}: sourceReport missing")
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
    elif expected_platform == "ios":
        if payload.get("sceneLaunchUsed") is not True:
            issues.append(f"{label}: iOS scene launcher was not used")
        if payload.get("sceneStarted") is not True:
            issues.append(f"{label}: iOS scene did not start")
        if payload.get("sceneLauncher") not in {
            "xcrun_simctl",
            "xcrun_devicectl",
        }:
            issues.append(f"{label}: iOS scene launcher provenance is invalid")
    return issues


def _validate_readback_evidence(
    path: Path,
    *,
    expected_environment: str,
    expected_target: str,
    expected_platform: str,
    expected_effective_manifest_digest: str,
    expected_baseline_id: str,
    expected_release_id: str,
    expected_release_digest: str,
    expected_device_kind: str = "",
) -> tuple[list[str], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    issues: list[str] = []
    if payload.get("schema") != READBACK_EVIDENCE_SCHEMA:
        issues.append(
            f"{path}: schema must equal {READBACK_EVIDENCE_SCHEMA}"
        )
    expected_values = {
        "baselineId": expected_baseline_id,
        "releaseId": expected_release_id,
        "releaseDigest": expected_release_digest,
        "environment": expected_environment,
        "target": expected_target,
        "platform": expected_platform,
        "effectiveLaunchManifestDigest": expected_effective_manifest_digest,
        "deviceKind": expected_device_kind,
    }
    for field, expected in expected_values.items():
        if expected and payload.get(field) != expected:
            issues.append(f"{path}: {field} does not match candidate")
    if payload.get("status") != "passed":
        issues.append(f"{path}: app core readback did not pass")
    executed = payload.get("executed")
    skipped = payload.get("skipped")
    failed = payload.get("failed")
    required = payload.get("required")
    if not isinstance(required, int) or required <= 0:
        issues.append(f"{path}: required must be greater than zero")
    if not isinstance(executed, int) or executed <= 0:
        issues.append(f"{path}: executed must be greater than zero")
    if skipped != 0:
        issues.append(f"{path}: skipped must equal zero")
    if failed != 0:
        issues.append(f"{path}: failed must equal zero")
    if str(payload.get("deviceId") or "").strip() in {"", "unknown"}:
        issues.append(f"{path}: deviceId missing")
    case_results = payload.get("caseResults")
    if not isinstance(case_results, list) or not case_results:
        issues.append(f"{path}: real caseResults are required")
    else:
        if isinstance(required, int) and len(case_results) < required:
            issues.append(f"{path}: required CaseResult is missing")
        case_ids: set[str] = set()
        for index, case in enumerate(case_results):
            if not isinstance(case, dict) or case.get("status") != "passed":
                issues.append(f"{path}: every real CaseResult must pass")
                continue
            case_id = str(case.get("caseId") or "").strip()
            if not case_id or case_id in case_ids:
                issues.append(f"{path}: CaseResult identity is missing or reused")
            case_ids.add(case_id)
            execution = case.get("testExecution")
            if not isinstance(execution, dict):
                issues.append(
                    f"{path}: CaseResult {index + 1} testExecution is missing"
                )
                continue
            if not isinstance(execution.get("executed"), int) or execution[
                "executed"
            ] <= 0:
                issues.append(
                    f"{path}: CaseResult {index + 1} executed must be greater than zero"
                )
            if execution.get("skipped", 0) != 0:
                issues.append(
                    f"{path}: CaseResult {index + 1} skipped must equal zero"
                )
            if execution.get("failed") != 0:
                issues.append(
                    f"{path}: CaseResult {index + 1} failed must equal zero"
                )
    missing_refs = _missing_spec_refs(payload)
    if missing_refs:
        issues.append(
            f"{path}: readback specRefs are incomplete: "
            + ", ".join(missing_refs)
        )
    return issues, payload


def _validate_observability_evidence(
    path: Path,
    *,
    expected_environment: str,
    expected_target: str,
    expected_effective_manifest_digest: str,
    expected_baseline_id: str,
    expected_release_id: str,
    expected_release_digest: str,
    expected_attempt_ids: list[str],
    expected_device_ids: list[str],
) -> tuple[list[str], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    issues: list[str] = []
    if payload.get("schema") != OBSERVABILITY_EVIDENCE_SCHEMA:
        issues.append(
            f"{path}: schema must equal {OBSERVABILITY_EVIDENCE_SCHEMA}"
        )
    for field, expected in (
        ("environment", expected_environment),
        ("target", expected_target),
        ("effectiveLaunchManifestDigest", expected_effective_manifest_digest),
        ("baselineId", expected_baseline_id),
        ("releaseId", expected_release_id),
        ("releaseDigest", expected_release_digest),
    ):
        if payload.get(field) != expected:
            issues.append(f"{path}: {field} does not match candidate")
    if payload.get("status") != "passed":
        issues.append(f"{path}: telemetry backend readback did not pass")
    telemetry_backend = str(payload.get("telemetryBackend") or "").strip()
    if telemetry_backend in {"", "unknown"}:
        issues.append(f"{path}: telemetryBackend is missing")
    backend_receipt = str(payload.get("backendReceiptRef") or "").strip()
    if backend_receipt in {"", "unknown"}:
        issues.append(f"{path}: backendReceiptRef is missing")

    observed_attempts = payload.get("attemptIds")
    normalized_attempts = (
        [str(value).strip() for value in observed_attempts]
        if isinstance(observed_attempts, list)
        else []
    )
    if (
        not normalized_attempts
        or any(value in {"", "unknown"} for value in normalized_attempts)
        or len(set(normalized_attempts)) != len(normalized_attempts)
        or set(normalized_attempts) != set(expected_attempt_ids)
    ):
        issues.append(f"{path}: attemptIds do not exactly match startup samples")

    observed_devices = payload.get("deviceIds")
    normalized_devices = (
        [str(value).strip() for value in observed_devices]
        if isinstance(observed_devices, list)
        else []
    )
    expected_devices = set(expected_device_ids)
    if (
        not normalized_devices
        or any(value in {"", "unknown"} for value in normalized_devices)
        or len(set(normalized_devices)) != len(normalized_devices)
        or set(normalized_devices) != expected_devices
    ):
        issues.append(f"{path}: deviceIds do not exactly match startup samples")

    required = payload.get("required")
    executed = payload.get("executed")
    if required != len(expected_attempt_ids) or required <= 0:
        issues.append(f"{path}: required does not match startup attempts")
    if executed != required:
        issues.append(f"{path}: executed must equal required")
    if payload.get("skipped") != 0:
        issues.append(f"{path}: skipped must equal zero")
    if payload.get("failed") != 0:
        issues.append(f"{path}: failed must equal zero")
    missing_refs = _missing_spec_refs(payload)
    if missing_refs:
        issues.append(
            f"{path}: observability specRefs are incomplete: "
            + ", ".join(missing_refs)
        )
    return issues, payload


def _case(
    case_id: str,
    *,
    kind: str,
    status: str,
    required: bool,
    spec_refs: tuple[str, ...] = SPEC_REFS,
    **fields: Any,
) -> dict[str, Any]:
    return {
        "caseId": case_id,
        "kind": kind,
        "required": required,
        "status": status,
        "specRefs": list(spec_refs),
        **fields,
    }


def _case_counts(cases: list[dict[str, Any]]) -> dict[str, int]:
    required_cases = [case for case in cases if case.get("required") is True]
    executed_statuses = {"component_ready", "passed", "failed"}
    return {
        "required": len(required_cases),
        "executed": sum(
            case.get("status") in executed_statuses for case in required_cases
        ),
        "skipped": sum(case.get("status") == "skipped" for case in required_cases),
        "failed": sum(case.get("status") == "failed" for case in required_cases),
    }


def _report_status(
    cases: list[dict[str, Any]],
    *,
    release_gate: bool,
) -> str:
    required_cases = [case for case in cases if case.get("required") is True]
    if any(case.get("status") == "failed" for case in required_cases):
        return "failed"
    if any(
        case.get("status") in {"gate_block", "missing", "skipped"}
        for case in required_cases
    ):
        return "gate_block"
    return "passed" if release_gate else "component_ready"


def _write_report(path_value: str, report: dict[str, Any]) -> None:
    if not path_value:
        return
    report_path = Path(path_value)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", default="")
    parser.add_argument("--require-runtime-evidence", action="store_true")
    parser.add_argument("--require-readback", action="store_true")
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
    parser.add_argument("--baseline-id", default="")
    parser.add_argument("--release-id", default="")
    parser.add_argument("--release-digest", default="")
    parser.add_argument("--report", default="")
    args = parser.parse_args()

    issues: list[str] = []
    packages: dict[str, Any] = {}
    runtime_evidence: dict[str, Any] = {}
    readback_evidence: dict[str, Any] = {}
    observability_evidence: dict[str, Any] = {}
    cases: list[dict[str, Any]] = []
    root = Path(args.evidence_root) if args.evidence_root else None
    release_requirements = {
        "runtime-evidence": args.require_runtime_evidence,
        "app-core-readback": args.require_readback,
        "observability-readback": args.require_observability,
    }
    release_gate = any(release_requirements.values())

    if release_gate:
        for evidence_kind, enabled in release_requirements.items():
            if not enabled:
                cases.append(
                    _case(
                        f"matrix-policy:{evidence_kind}",
                        kind="matrix_policy",
                        status="gate_block",
                        required=True,
                        reason=(
                            "release-bound startup verification requires "
                            f"{evidence_kind}"
                        ),
                    )
                )
        if not args.require_physical_release:
            cases.append(
                _case(
                    "matrix-policy:physical-release",
                    kind="matrix_policy",
                    status="gate_block",
                    required=True,
                    reason=(
                        "release-bound startup evidence must explicitly require "
                        "the physical-device matrix"
                    ),
                )
            )
        for name, value in (
            ("baselineId", args.baseline_id),
            ("releaseId", args.release_id),
            ("releaseDigest", args.release_digest),
        ):
            if str(value).strip() in {"", "unknown"}:
                cases.append(
                    _case(
                        f"candidate-identity:{name}",
                        kind="candidate_identity",
                        status="gate_block",
                        required=True,
                        reason=f"{name} is required for release-bound evidence",
                    )
                )
        if args.release_digest and not SHA256_PATTERN.fullmatch(
            args.release_digest
        ):
            issues.append("releaseDigest must use sha256:<64 lowercase hex>")
            cases.append(
                _case(
                    "candidate-identity:releaseDigest-format",
                    kind="candidate_identity",
                    status="failed",
                    required=True,
                    reason=issues[-1],
                )
            )
        if root is None:
            cases.append(
                _case(
                    "evidence-root",
                    kind="evidence_root",
                    status="gate_block",
                    required=True,
                    reason="evidence root is required for release-bound verification",
                )
            )

    for environment in ENVIRONMENTS:
        package_issues: list[str] = []
        runtime: dict[str, str] = {}
        ios: dict[str, str] = {}
        handoff: dict[str, Any] = {}
        try:
            runtime = _runtime_defines(environment)
            ios = _ios_defines(environment)
            handoff = _launcher_handoff(environment)
            package_issues.extend(_validate_defines(environment, runtime))
            package_issues.extend(_validate_defines(environment, ios))
            manifest_digest = str(
                handoff.get("effectiveLaunchManifestDigest") or ""
            )
            if not SHA256_PATTERN.fullmatch(manifest_digest):
                package_issues.append(
                    f"{environment}: effective launch manifest digest invalid"
                )
        except (RuntimeError, KeyError, json.JSONDecodeError) as exc:
            package_issues.append(f"{environment}: {exc}")
        issues.extend(package_issues)
        packages[environment] = {
            "runtimeDefineKeys": sorted(runtime),
            "iosDefineKeys": sorted(ios),
            "runtimeTarget": handoff.get("target", ""),
            "entrypoint": handoff.get("entrypoint", ""),
            "dartDefinesDigest": handoff.get("dartDefinesDigest", ""),
            "runtimeConfigDigest": handoff.get("runtimeConfigDigest", ""),
            "effectiveLaunchManifestDigest": handoff.get(
                "effectiveLaunchManifestDigest",
                "",
            ),
            "status": "component_ready" if not package_issues else "failed",
        }
        cases.append(
            _case(
                f"component:{environment}",
                kind="component_readiness",
                status=packages[environment]["status"],
                required=True,
                environment=environment,
                target=handoff.get("target", ""),
                effectiveLaunchManifestDigest=handoff.get(
                    "effectiveLaunchManifestDigest",
                    "",
                ),
                issues=package_issues,
            )
        )

    if root is not None:
        for environment, target in RUNTIME_CASES:
            try:
                handoff = _launcher_handoff(environment, target)
            except (RuntimeError, KeyError, json.JSONDecodeError) as exc:
                handoff = {}
                issues.append(f"{target}: {exc}")
            for platform, device_kind, evidence_stem in DEVICE_PROFILES[target]:
                evidence_path = root / target / f"{evidence_stem}.json"
                key = f"{target}/{evidence_stem}"
                if not evidence_path.is_file():
                    runtime_evidence[key] = {"status": "gate_block"}
                    if args.require_runtime_evidence:
                        cases.append(
                            _case(
                                f"startup:{key}",
                                kind="startup_runtime",
                                status="gate_block",
                                required=True,
                                environment=environment,
                                target=target,
                                platform=platform,
                                deviceKind=device_kind,
                                evidenceRef=str(evidence_path),
                                reason="runtime evidence missing",
                            )
                        )
                else:
                    try:
                        evidence_issues, payload = _validate_runtime_evidence(
                            evidence_path,
                            expected_environment=environment,
                            expected_target=target,
                            expected_platform=platform,
                            expected_effective_manifest_digest=str(
                                handoff.get(
                                    "effectiveLaunchManifestDigest",
                                    "",
                                )
                            ),
                            expected_device_kind=device_kind,
                            expected_baseline_id=args.baseline_id,
                            expected_release_id=args.release_id,
                            expected_release_digest=args.release_digest,
                            require_device_identity=args.require_runtime_evidence,
                            minimum_runs=max(args.minimum_runtime_runs, 1),
                        )
                    except (OSError, json.JSONDecodeError) as exc:
                        payload = {}
                        evidence_issues = [f"{evidence_path}: {exc}"]
                    issues.extend(evidence_issues)
                    runtime_status = (
                        "passed" if not evidence_issues else "failed"
                    )
                    runtime_evidence[key] = {
                        "status": runtime_status,
                        "evidence": payload,
                    }
                    if args.require_runtime_evidence:
                        cases.append(
                            _case(
                                f"startup:{key}",
                                kind="startup_runtime",
                                status=runtime_status,
                                required=True,
                                environment=environment,
                                target=target,
                                platform=platform,
                                deviceKind=device_kind,
                                effectiveLaunchManifestDigest=handoff.get(
                                    "effectiveLaunchManifestDigest",
                                    "",
                                ),
                                evidenceRef=str(evidence_path),
                                issues=evidence_issues,
                            )
                        )

                readback_path = root / target / f"{evidence_stem}.readback.json"
                if args.require_readback:
                    if not readback_path.is_file():
                        readback_evidence[key] = {"status": "gate_block"}
                        cases.append(
                            _case(
                                f"readback:{key}",
                                kind="app_core_readback",
                                status="gate_block",
                                required=True,
                                environment=environment,
                                target=target,
                                platform=platform,
                                deviceKind=device_kind,
                                evidenceRef=str(readback_path),
                                reason="app core readback evidence missing",
                            )
                        )
                    else:
                        try:
                            readback_issues, readback_payload = (
                                _validate_readback_evidence(
                                    readback_path,
                                    expected_environment=environment,
                                    expected_target=target,
                                    expected_platform=platform,
                                    expected_effective_manifest_digest=str(
                                        handoff.get(
                                            "effectiveLaunchManifestDigest",
                                            "",
                                        )
                                    ),
                                    expected_baseline_id=args.baseline_id,
                                    expected_release_id=args.release_id,
                                    expected_release_digest=args.release_digest,
                                    expected_device_kind=(
                                        "physical"
                                        if device_kind in {
                                            "physical",
                                            "true_device",
                                        }
                                        else "simulator"
                                    ),
                                )
                            )
                        except (OSError, json.JSONDecodeError) as exc:
                            readback_payload = {}
                            readback_issues = [f"{readback_path}: {exc}"]
                        issues.extend(readback_issues)
                        readback_status = (
                            "passed"
                            if not readback_issues
                            else (
                                "gate_block"
                                if readback_payload.get("status")
                                == "gate_block"
                                else "failed"
                            )
                        )
                        readback_evidence[key] = {
                            "status": readback_status,
                            "evidence": readback_payload,
                        }
                        cases.append(
                            _case(
                                f"readback:{key}",
                                kind="app_core_readback",
                                status=readback_status,
                                required=True,
                                environment=environment,
                                target=target,
                                platform=platform,
                                deviceKind=device_kind,
                                effectiveLaunchManifestDigest=handoff.get(
                                    "effectiveLaunchManifestDigest",
                                    "",
                                ),
                                evidenceRef=str(readback_path),
                                issues=readback_issues,
                            )
                        )

            observability_path = root / target / "observability.json"
            observability: dict[str, Any] = {}
            observability_issues: list[str] = []
            if observability_path.is_file():
                try:
                    expected_attempt_values = [
                        str(sample.get("attemptId") or "")
                        for platform_payload in (
                            runtime_evidence.get(
                                f"{target}/{evidence_stem}",
                                {},
                            ).get(
                                "evidence",
                                {},
                            )
                            for _, _, evidence_stem in DEVICE_PROFILES[target]
                        )
                        for sample in platform_payload.get("samples", [])
                        if isinstance(sample, dict)
                    ]
                    expected_device_values = [
                        str(sample.get("deviceId") or "")
                        for platform_payload in (
                            runtime_evidence.get(
                                f"{target}/{evidence_stem}",
                                {},
                            ).get(
                                "evidence",
                                {},
                            )
                            for _, _, evidence_stem in DEVICE_PROFILES[target]
                        )
                        for sample in platform_payload.get("samples", [])
                        if isinstance(sample, dict)
                    ]
                    observability_issues, observability = (
                        _validate_observability_evidence(
                            observability_path,
                            expected_environment=environment,
                            expected_target=target,
                            expected_effective_manifest_digest=str(
                                handoff.get(
                                    "effectiveLaunchManifestDigest",
                                    "",
                                )
                            ),
                            expected_baseline_id=args.baseline_id,
                            expected_release_id=args.release_id,
                            expected_release_digest=args.release_digest,
                            expected_attempt_ids=expected_attempt_values,
                            expected_device_ids=expected_device_values,
                        )
                    )
                except (OSError, json.JSONDecodeError) as exc:
                    observability_issues = [f"{observability_path}: {exc}"]
                    observability = {}
                issues.extend(observability_issues)
            observability_ready = (
                observability_path.is_file() and not observability_issues
            )
            observability_evidence[target] = {
                "status": (
                    "passed"
                    if observability_ready
                    else "gate_block"
                    if not observability_path.is_file()
                    else "failed"
                ),
                "evidence": observability,
                "issues": observability_issues,
            }
            if args.require_observability:
                cases.append(
                    _case(
                        f"observability:{target}",
                        kind="startup_observability",
                        status=(
                            "passed"
                            if observability_ready
                            else "gate_block"
                            if not observability_path.is_file()
                            else "failed"
                        ),
                        required=True,
                        environment=environment,
                        target=target,
                        effectiveLaunchManifestDigest=handoff.get(
                            "effectiveLaunchManifestDigest",
                            "",
                        ),
                        evidenceRef=str(observability_path),
                        reason=(
                            ""
                            if observability_ready
                            else (
                                "telemetry readback is missing attempt IDs or "
                                "candidate launch identity"
                            )
                        ),
                    )
                )

    counts = _case_counts(cases)
    status = _report_status(cases, release_gate=release_gate)
    report = {
        "schema": "qwq.startup-environment-case-result",
        "status": status,
        **counts,
        "baselineId": args.baseline_id,
        "releaseId": args.release_id,
        "releaseDigest": args.release_digest,
        "specRefs": list(SPEC_REFS),
        "packages": packages,
        "runtimeEvidence": runtime_evidence,
        "readbackEvidence": readback_evidence,
        "observabilityEvidence": observability_evidence,
        "cases": cases,
        "issues": issues,
    }
    _write_report(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if status in {"passed", "component_ready"}:
        return 0
    return 2 if status == "gate_block" else 1


if __name__ == "__main__":
    raise SystemExit(main())
