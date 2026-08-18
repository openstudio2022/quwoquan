"""runtime / readback / observability 三类 CaseResult 证据的结构化校验。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .behavior_fingerprint import fingerprint_equivalence_issues
from .context import (
    OBSERVABILITY_EVIDENCE_SCHEMA,
    READBACK_EVIDENCE_SCHEMA,
    RUNTIME_EVIDENCE_SCHEMA,
    SPEC_REFS,
)


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
    # 同一环境与服务端状态下，改变入口（launch provenance / install
    # channel / BuildMode / 设备形态）不得改变规范化行为指纹。
    issues.extend(
        fingerprint_equivalence_issues(
            [sample for sample in samples if isinstance(sample, dict)],
            label=str(path),
            release_id=expected_release_id,
            release_digest=expected_release_digest,
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
