#!/usr/bin/env python3
"""Execute or verify the canonical startup environment CaseResult matrix.

The script is a thin orchestration layer.  Repository wiring is only
``component_ready``; release readiness is delegated to
``verify_startup_environment_matrix.py`` and requires real launcher, readback
and observability evidence bound to one baseline and immutable release.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

# 同目录顶层 import：本脚本既被直跑（sys.path[0]=scripts/device）也被
# 测试经 sys.path 注入同目录后 import，包路径写法在两种场景下均不可达。
from verify_flutter_run_defines import (
    RUNTIME_VALUE_DEFINE_KEYS,
)

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "quwoquan_app"
DEFAULT_REPORT = (
    ROOT
    / ".qwq_output"
    / "env"
    / "repo"
    / "runs"
    / "startup-environment-matrix"
    / "case_result.json"
)
DEFAULT_EVIDENCE_ROOT = DEFAULT_REPORT.parent / "evidence"
COMPONENT_GATE = (
    APP / "scripts/runtime/platform/verify_dual_platform_usability_baseline.py"
)
CANONICAL_VERIFIER = (
    APP / "scripts/runtime/platform/verify_startup_environment_matrix.py"
)
STARTUP_PROBE = APP / "scripts/device/verify_startup_first_frame.py"
READBACK_RUNNER = (
    ROOT / "quwoquan_ops/cli/smoke/run_environment_patrol_smoke.py"
)
READBACK_TARGET = (
    "test/user_acceptance/journeys/app_startup/"
    "app_core_readback__user_acceptance_test.dart"
)
TARGET_ENVIRONMENTS = {
    "alpha-local": "alpha",
    "beta-local": "beta",
    "gamma-local": "gamma",
    "prod-sim": "prod",
    "prod-hosted": "prod",
}
READBACK_ENVIRONMENT_ALIASES = {
    "alpha-local": "alpha",
    "beta-local": "beta",
    "gamma-local": "gamma",
    "prod-sim": "local-prod-sim",
    "prod-hosted": "prod",
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
EXECUTION_INPUT_SCHEMA = "qwq.startup-matrix-execution-input"
RELEASE_DEFINE_ARGUMENTS = (
    ("DATA_RELEASE_HOMEPAGE_ID", "--data-release-homepage-id"),
    ("DATA_RELEASE_HOMEPAGE_TITLE", "--data-release-homepage-title"),
    ("DATA_RELEASE_ARTICLE_WORK_ID", "--data-release-article-work-id"),
    ("DATA_RELEASE_ARTICLE_TITLE", "--data-release-article-title"),
    ("DATA_RELEASE_IMAGE_WORK_ID", "--data-release-image-work-id"),
    ("DATA_RELEASE_IMAGE_TITLE", "--data-release-image-title"),
    ("DATA_RELEASE_CREATOR_NAME", "--data-release-creator-name"),
    ("DATA_RELEASE_CREATOR_USER_HANDLE", "--data-release-creator-user-handle"),
    ("DATA_RELEASE_CREATOR_PERSONA_ID", "--data-release-creator-persona-id"),
    (
        "DATA_RELEASE_CREATOR_AVATAR_ASSET_ID",
        "--data-release-creator-avatar-asset-id",
    ),
    ("DATA_RELEASE_TAG_LABEL", "--data-release-tag-label"),
    ("DATA_RELEASE_VIDEO_ATTRIBUTION", "--data-release-video-attribution"),
)
REMOTE_SESSION_INPUTS = (
    "TEST_AUTH_TOKEN",
    "TEST_REFRESH_TOKEN",
    "APP_CURRENT_OWNER_ID",
    "APP_CURRENT_PERSONA_ID",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_command(
    command: list[str],
    *,
    cwd: Path = ROOT,
) -> dict[str, Any]:
    started = utc_now()
    result = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )
    status = "passed" if result.returncode == 0 else (
        "gate_block" if result.returncode == 2 else "failed"
    )
    return {
        "command": command,
        "startedAt": started,
        "endedAt": utc_now(),
        "exitCode": result.returncode,
        "stdoutTail": (result.stdout or "")[-4000:],
        "stderrTail": (result.stderr or "")[-4000:],
        "status": status,
    }


def _absolute_path(value: str, *, base: Path = ROOT) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else base / path


def _device_profile(case: dict[str, Any]) -> tuple[str, str, str]:
    target = str(case.get("target") or "")
    platform = str(case.get("platform") or "")
    device_kind = str(case.get("deviceKind") or "")
    physical = device_kind == "physical"
    if target == "prod-hosted" and not physical:
        raise ValueError("prod-hosted execution requires a physical device")
    if target != "prod-hosted" and platform == "ios" and physical:
        raise ValueError(
            f"{target} iOS startup evidence requires an iOS Simulator"
        )
    if platform == "android":
        if physical:
            return "android-physical", "true_device", "physical"
        return "android-simulator", "simulator", "simulator"
    if physical:
        return "ios-physical", "physical", "physical"
    return "ios-simulator", "simulator", "simulator"


def _load_execution_input(
    path: Path,
    *,
    baseline_id: str,
    release_id: str,
    release_digest: str,
) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != EXECUTION_INPUT_SCHEMA:
        raise ValueError(
            f"execution input schema must equal {EXECUTION_INPUT_SCHEMA}"
        )
    for field, expected in (
        ("baselineId", baseline_id),
        ("releaseId", release_id),
        ("releaseDigest", release_digest),
    ):
        if payload.get(field) != expected:
            raise ValueError(f"execution input {field} does not match candidate")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("execution input must contain at least one real case")
    normalized: list[dict[str, Any]] = []
    identities: set[tuple[str, str]] = set()
    allowed = {
        "environment",
        "target",
        "platform",
        "deviceId",
        "deviceKind",
        "androidApk",
        "iosApp",
        "install",
        "remoteApiEvidenceReport",
        "releaseUatCases",
    }
    for index, value in enumerate(cases):
        if not isinstance(value, dict) or not set(value).issubset(allowed):
            raise ValueError(f"execution case {index + 1} has invalid fields")
        case = dict(value)
        environment = str(case.get("environment") or "").strip()
        target = str(case.get("target") or "").strip()
        platform = str(case.get("platform") or "").strip()
        device_id = str(case.get("deviceId") or "").strip()
        device_kind = str(case.get("deviceKind") or "").strip()
        if TARGET_ENVIRONMENTS.get(target) != environment:
            raise ValueError(
                f"execution case {index + 1} target/environment mismatch"
            )
        if platform not in {"android", "ios"}:
            raise ValueError(f"execution case {index + 1} platform is invalid")
        if device_id in {"", "unknown"}:
            raise ValueError(f"execution case {index + 1} deviceId is required")
        if device_kind not in {"emulator", "simulator", "physical"}:
            raise ValueError(f"execution case {index + 1} deviceKind is invalid")
        case.update(
            {
                "environment": environment,
                "target": target,
                "platform": platform,
                "deviceId": device_id,
                "deviceKind": device_kind,
                "install": bool(case.get("install", False)),
            }
        )
        evidence_stem, _, _ = _device_profile(case)
        identity = (target, evidence_stem)
        if identity in identities:
            raise ValueError(
                f"execution input duplicates canonical case {target}/{evidence_stem}"
            )
        identities.add(identity)
        normalized.append(case)
    return normalized


def _launcher_handoff(environment: str, target: str) -> dict[str, Any]:
    result = subprocess.run(
        [
            "python3",
            "scripts/device/build_launcher_handoff.py",
            "--env",
            environment,
            "--target",
            target,
            "--launch-provenance",
            "canonical_launcher",
        ],
        cwd=str(APP),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return json.loads(result.stdout)


def _readback_command(
    case: dict[str, Any],
    *,
    handoff: dict[str, Any],
    report_path: Path,
    release_id: str,
) -> list[str]:
    # endpoint 取值只来自 handoff 携带的签名 runtime package；编译期 define 已退役。
    runtime_values = dict(handoff["runtimeConfigPackage"]["runtime"])
    defines = {
        define_key: str(runtime_values[value_key])
        for value_key, define_key in RUNTIME_VALUE_DEFINE_KEYS.items()
    }
    command = [
        "python3",
        str(READBACK_RUNNER),
        "--report",
        str(report_path),
        "--target",
        READBACK_TARGET,
        "--env-name",
        READBACK_ENVIRONMENT_ALIASES[str(case["target"])],
        "--runtime-env",
        str(case["environment"]),
        "--api-contract-env",
        str(case["environment"]),
        "--platform",
        str(case["platform"]),
        "--device-id",
        str(case["deviceId"]),
        "--gateway-base-url",
        str(defines["CLOUD_GATEWAY_BASE_URL"]),
        "--product-ops-base-url",
        str(defines["CLOUD_GATEWAY_BASE_URL"]),
        "--media-avatar-base-url",
        str(defines["MEDIA_AVATAR_CDN_BASE_URL"]),
        "--media-image-base-url",
        str(defines["MEDIA_IMAGE_CDN_BASE_URL"]),
        "--media-video-base-url",
        str(defines["MEDIA_VIDEO_CDN_BASE_URL"]),
        "--media-upload-base-url",
        str(defines["MEDIA_UPLOAD_BASE_URL"]),
        "--rtc-media-connection-url",
        str(defines["RTC_MEDIA_CONNECTION_URL"]),
        "--data-release-id",
        release_id,
    ]
    video_work_id = os.environ.get("VIDEO_PLAYBACK_CANARY_WORK_ID", "").strip()
    if video_work_id:
        command.extend(["--video-playback-canary-work-id", video_work_id])
    for environment_name, argument in RELEASE_DEFINE_ARGUMENTS:
        value = os.environ.get(environment_name, "").strip()
        if value:
            command.extend([argument, value])
    remote_api = str(case.get("remoteApiEvidenceReport") or "").strip()
    if remote_api:
        command.extend(
            ["--remote-api-evidence-report", str(_absolute_path(remote_api))]
        )
    release_uat = str(case.get("releaseUatCases") or "").strip()
    if release_uat:
        command.extend(["--release-uat-cases", str(_absolute_path(release_uat))])
    return command


def _startup_command(
    case: dict[str, Any],
    *,
    evidence_root: Path,
    output_dir: Path,
    minimum_runtime_runs: int,
) -> list[str]:
    command = [
        "python3",
        str(STARTUP_PROBE),
        "--output-dir",
        str(output_dir),
        "--runtime-env",
        str(case["environment"]),
        "--runtime-target",
        str(case["target"]),
        "--matrix-evidence-root",
        str(evidence_root),
        "--runs",
        str(minimum_runtime_runs),
        "--require-startup-sequence-events",
        "--require-no-native-recovery",
        "--require-telemetry-ack",
        "--require-branded-visible",
        "--enforce-shell-target",
    ]
    if case["platform"] == "android":
        command.extend(["--android-device", str(case["deviceId"])])
        artifact = str(case.get("androidApk") or "").strip()
        if artifact:
            command.extend(["--android-apk", str(_absolute_path(artifact))])
        if case.get("install") is True:
            command.append("--android-install")
    else:
        command.extend(["--ios-device", str(case["deviceId"])])
        artifact = str(case.get("iosApp") or "").strip()
        if artifact:
            command.extend(["--ios-app", str(_absolute_path(artifact))])
        if case.get("install") is True:
            command.append("--ios-install")
        if case["deviceKind"] == "physical":
            command.append("--ios-physical")
    return command


def _validate_execution_preconditions(case: dict[str, Any]) -> None:
    missing = [
        name
        for name, _ in RELEASE_DEFINE_ARGUMENTS
        if not os.environ.get(name, "").strip()
    ]
    if not os.environ.get("VIDEO_PLAYBACK_CANARY_WORK_ID", "").strip():
        missing.append("VIDEO_PLAYBACK_CANARY_WORK_ID")
    if case["target"] != "prod-sim":
        missing.extend(
            name
            for name in REMOTE_SESSION_INPUTS
            if not os.environ.get(name, "").strip()
        )
    if missing:
        raise RuntimeError(
            "GATE_BLOCK: missing release-bound execution inputs: "
            + ", ".join(sorted(missing))
        )
    platform_artifact = (
        "androidApk" if case["platform"] == "android" else "iosApp"
    )
    artifact_value = str(case.get(platform_artifact) or "").strip()
    if case.get("install") is True and not artifact_value:
        raise RuntimeError(
            f"GATE_BLOCK: install=true requires {platform_artifact}"
        )
    if artifact_value and not _absolute_path(artifact_value).exists():
        raise RuntimeError(
            f"GATE_BLOCK: candidate artifact missing: {artifact_value}"
        )
    for field in ("remoteApiEvidenceReport", "releaseUatCases"):
        value = str(case.get(field) or "").strip()
        if value and not _absolute_path(value).is_file():
            raise RuntimeError(f"GATE_BLOCK: {field} is missing: {value}")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: JSON payload must be an object")
    return payload


def _write_readback_evidence(
    *,
    raw_report_path: Path,
    evidence_path: Path,
    execution: dict[str, Any],
    case: dict[str, Any],
    handoff: dict[str, Any],
    baseline_id: str,
    release_id: str,
    release_digest: str,
) -> dict[str, Any]:
    try:
        raw = _read_json(raw_report_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raw = {}
        load_error = str(exc)
    else:
        load_error = ""
    case_results = raw.get("caseResults")
    if not isinstance(case_results, list):
        case_results = []
    executed = 0
    failed = 0
    skipped = 0
    for result in case_results:
        if not isinstance(result, dict):
            failed += 1
            continue
        summary = result.get("testExecution")
        if isinstance(summary, dict) and isinstance(summary.get("executed"), int):
            executed += int(summary["executed"])
            failed += int(summary.get("failed") or 0)
        if result.get("status") == "skipped":
            skipped += 1
        elif result.get("status") != "passed":
            failed += 1
    passed = (
        not load_error
        and execution["exitCode"] == 0
        and raw.get("status") == "passed"
        and executed > 0
        and skipped == 0
        and failed == 0
        and bool(case_results)
        and raw.get("sessionSource") == "provided_remote_session"
    )
    session_blocked = (
        not load_error
        and raw.get("status") == "passed"
        and raw.get("sessionSource") != "provided_remote_session"
    )
    evidence = {
        "schema": "qwq.app-core-readback-evidence",
        "status": "passed" if passed else (
            "gate_block"
            if execution["exitCode"] == 2 or session_blocked
            else "failed"
        ),
        "baselineId": baseline_id,
        "releaseId": release_id,
        "releaseDigest": release_digest,
        "environment": case["environment"],
        "target": case["target"],
        "platform": case["platform"],
        "deviceId": case["deviceId"],
        "deviceKind": _device_profile(case)[2],
        "effectiveLaunchManifestDigest": handoff[
            "effectiveLaunchManifestDigest"
        ],
        "required": 1,
        "executed": executed,
        "skipped": skipped,
        "failed": failed,
        "specRefs": list(SPEC_REFS),
        "caseResults": case_results,
        "sourceReport": str(raw_report_path),
        "failureReason": (
            load_error
            or str(raw.get("failureReason") or "")
            or (
                "formal provided_remote_session is required"
                if session_blocked
                else ""
            )
        ),
    }
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return evidence


def _bind_startup_evidence(
    path: Path,
    *,
    case: dict[str, Any],
    baseline_id: str,
    release_id: str,
    release_digest: str,
) -> None:
    payload = _read_json(path)
    payload.update(
        {
            "baselineId": baseline_id,
            "releaseId": release_id,
            "releaseDigest": release_digest,
            "runtimeEnv": case["environment"],
            "runtimeTarget": case["target"],
            "platform": case["platform"],
            "deviceId": case["deviceId"],
            "deviceKind": case["deviceKind"],
        }
    )
    samples = payload.get("samples")
    if isinstance(samples, list):
        for sample in samples:
            if isinstance(sample, dict):
                sample["deviceId"] = case["deviceId"]
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _execute_case(
    case: dict[str, Any],
    *,
    evidence_root: Path,
    execution_root: Path,
    minimum_runtime_runs: int,
    baseline_id: str,
    release_id: str,
    release_digest: str,
) -> dict[str, Any]:
    _validate_execution_preconditions(case)
    target = str(case["target"])
    platform = str(case["platform"])
    evidence_stem, _, _ = _device_profile(case)
    case_root = execution_root / target / evidence_stem
    case_root.mkdir(parents=True, exist_ok=True)
    handoff = _launcher_handoff(str(case["environment"]), target)

    raw_readback_path = case_root / "app_core_readback.raw.json"
    readback_execution = run_command(
        _readback_command(
            case,
            handoff=handoff,
            report_path=raw_readback_path,
            release_id=release_id,
        )
    )
    readback_path = evidence_root / target / f"{evidence_stem}.readback.json"
    readback = _write_readback_evidence(
        raw_report_path=raw_readback_path,
        evidence_path=readback_path,
        execution=readback_execution,
        case=case,
        handoff=handoff,
        baseline_id=baseline_id,
        release_id=release_id,
        release_digest=release_digest,
    )

    generated_startup_path = evidence_root / target / f"{platform}.json"
    startup_path = evidence_root / target / f"{evidence_stem}.json"
    generated_startup_path.unlink(missing_ok=True)
    startup_path.unlink(missing_ok=True)
    startup_execution = run_command(
        _startup_command(
            case,
            evidence_root=evidence_root,
            output_dir=case_root / "startup",
            minimum_runtime_runs=minimum_runtime_runs,
        )
    )
    if generated_startup_path.is_file():
        _bind_startup_evidence(
            generated_startup_path,
            case=case,
            baseline_id=baseline_id,
            release_id=release_id,
            release_digest=release_digest,
        )
        generated_startup_path.replace(startup_path)
    status = "passed"
    if readback.get("status") == "gate_block" or startup_execution["status"] == "gate_block":
        status = "gate_block"
    elif readback.get("status") != "passed" or startup_execution["status"] != "passed":
        status = "failed"
    return {
        "caseId": f"execute:{target}/{evidence_stem}",
        "kind": "launcher_and_readback_execution",
        "required": True,
        "status": status,
        "environment": case["environment"],
        "target": target,
        "platform": platform,
        "deviceProfile": evidence_stem,
        "deviceId": case["deviceId"],
        "deviceKind": case["deviceKind"],
        "effectiveLaunchManifestDigest": handoff[
            "effectiveLaunchManifestDigest"
        ],
        "specRefs": list(SPEC_REFS),
        "readbackExecution": readback_execution,
        "startupExecution": startup_execution,
        "startupEvidenceRef": str(startup_path),
        "readbackEvidenceRef": str(readback_path),
    }


def _canonical_verify_command(
    *,
    evidence_root: Path,
    report_path: Path,
    minimum_runtime_runs: int,
    baseline_id: str,
    release_id: str,
    release_digest: str,
) -> list[str]:
    return [
        "python3",
        str(CANONICAL_VERIFIER),
        "--evidence-root",
        str(evidence_root),
        "--require-runtime-evidence",
        "--require-readback",
        "--require-observability",
        "--require-physical-release",
        "--minimum-runtime-runs",
        str(minimum_runtime_runs),
        "--baseline-id",
        baseline_id,
        "--release-id",
        release_id,
        "--release-digest",
        release_digest,
        "--report",
        str(report_path),
    ]


def _recount(report: dict[str, Any]) -> None:
    cases = [
        case for case in report.get("cases", []) if isinstance(case, dict)
    ]
    required_cases = [case for case in cases if case.get("required") is True]
    report["required"] = len(required_cases)
    report["executed"] = sum(
        case.get("status") in {"component_ready", "passed", "failed"}
        for case in required_cases
    )
    report["skipped"] = sum(
        case.get("status") == "skipped" for case in required_cases
    )
    report["failed"] = sum(
        case.get("status") == "failed" for case in required_cases
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--evidence-root", default=str(DEFAULT_EVIDENCE_ROOT))
    parser.add_argument("--baseline-id", default="")
    parser.add_argument("--release-id", default="")
    parser.add_argument("--release-digest", default="")
    parser.add_argument("--execution-input", default="")
    parser.add_argument("--minimum-runtime-runs", type=int, default=20)
    parser.add_argument(
        "--skip-alpha-launch",
        action="store_true",
        help="Diagnostic only; forces GATE_BLOCK and cannot produce readiness.",
    )
    parser.add_argument(
        "--skip-gamma-release-consumer",
        action="store_true",
        help="Diagnostic only; forces GATE_BLOCK and cannot produce readiness.",
    )
    args = parser.parse_args()

    report_path = _absolute_path(args.report)
    evidence_root = _absolute_path(args.evidence_root)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_root.mkdir(parents=True, exist_ok=True)
    canonical_report_path = report_path.parent / "canonical_case_result.json"
    execution_root = report_path.parent / "executions"

    component = run_command(["python3", str(COMPONENT_GATE)])
    component_status = (
        "component_ready" if component["exitCode"] == 0 else "failed"
    )
    orchestration_cases: list[dict[str, Any]] = [
        {
            "caseId": "component:wiring",
            "kind": "component_readiness",
            "required": True,
            "status": component_status,
            "specRefs": list(SPEC_REFS),
            "execution": component,
        }
    ]

    candidate_fields = {
        "baselineId": args.baseline_id.strip(),
        "releaseId": args.release_id.strip(),
        "releaseDigest": args.release_digest.strip(),
    }
    for field, value in candidate_fields.items():
        if not value:
            orchestration_cases.append(
                {
                    "caseId": f"candidate-identity:{field}",
                    "kind": "candidate_identity",
                    "required": True,
                    "status": "gate_block",
                    "reason": f"{field} is required",
                    "specRefs": list(SPEC_REFS),
                }
            )

    diagnostic_overrides: list[str] = []
    if args.skip_alpha_launch:
        diagnostic_overrides.append("skip-alpha-launch")
    if args.skip_gamma_release_consumer:
        diagnostic_overrides.append("skip-gamma-release-consumer")
    for override in diagnostic_overrides:
        orchestration_cases.append(
            {
                "caseId": f"diagnostic-override:{override}",
                "kind": "diagnostic_override",
                "required": True,
                "status": "gate_block",
                "reason": "diagnostic skip cannot produce release evidence",
                "specRefs": list(SPEC_REFS),
            }
        )

    if args.execution_input:
        try:
            execution_cases = _load_execution_input(
                _absolute_path(args.execution_input),
                baseline_id=candidate_fields["baselineId"],
                release_id=candidate_fields["releaseId"],
                release_digest=candidate_fields["releaseDigest"],
            )
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            orchestration_cases.append(
                {
                    "caseId": "execution-input",
                    "kind": "execution_input",
                    "required": True,
                    "status": "gate_block",
                    "reason": str(exc),
                    "specRefs": list(SPEC_REFS),
                }
            )
            execution_cases = []
        for case in execution_cases:
            if args.skip_alpha_launch and case["environment"] == "alpha":
                continue
            if args.skip_gamma_release_consumer and case["environment"] == "gamma":
                continue
            try:
                orchestration_cases.append(
                    _execute_case(
                        case,
                        evidence_root=evidence_root,
                        execution_root=execution_root,
                        minimum_runtime_runs=max(args.minimum_runtime_runs, 1),
                        baseline_id=candidate_fields["baselineId"],
                        release_id=candidate_fields["releaseId"],
                        release_digest=candidate_fields["releaseDigest"],
                    )
                )
            except (RuntimeError, OSError, KeyError, json.JSONDecodeError) as exc:
                orchestration_cases.append(
                    {
                        "caseId": (
                            "execute:"
                            f"{case['target']}/{_device_profile(case)[0]}"
                        ),
                        "kind": "launcher_and_readback_execution",
                        "required": True,
                        "status": "gate_block",
                        "reason": str(exc),
                        "environment": case["environment"],
                        "target": case["target"],
                        "platform": case["platform"],
                        "deviceId": case["deviceId"],
                        "specRefs": list(SPEC_REFS),
                    }
                )

    canonical = run_command(
        _canonical_verify_command(
            evidence_root=evidence_root,
            report_path=canonical_report_path,
            minimum_runtime_runs=max(args.minimum_runtime_runs, 1),
            baseline_id=candidate_fields["baselineId"],
            release_id=candidate_fields["releaseId"],
            release_digest=candidate_fields["releaseDigest"],
        )
    )
    try:
        report = _read_json(canonical_report_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        report = {
            "schema": "qwq.startup-environment-case-result",
            "status": "failed",
            "baselineId": candidate_fields["baselineId"],
            "releaseId": candidate_fields["releaseId"],
            "releaseDigest": candidate_fields["releaseDigest"],
            "specRefs": list(SPEC_REFS),
            "cases": [],
            "issues": [str(exc)],
        }
    report.setdefault("cases", []).extend(orchestration_cases)
    report["orchestrator"] = {
        "startedAt": component["startedAt"],
        "endedAt": utc_now(),
        "canonicalVerifier": canonical,
        "executionInput": args.execution_input,
        "diagnosticOverrides": diagnostic_overrides,
    }
    _recount(report)
    required_cases = [
        case
        for case in report.get("cases", [])
        if isinstance(case, dict) and case.get("required") is True
    ]
    if any(case.get("status") == "failed" for case in required_cases):
        report["status"] = "failed"
    elif any(
        case.get("status") in {"gate_block", "missing", "skipped"}
        for case in required_cases
    ):
        report["status"] = "gate_block"
    else:
        report["status"] = "passed"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "required": report["required"],
                "executed": report["executed"],
                "skipped": report["skipped"],
                "failed": report["failed"],
                "report": str(report_path),
            },
            ensure_ascii=False,
        )
    )
    if report["status"] == "passed":
        return 0
    return 2 if report["status"] == "gate_block" else 1


if __name__ == "__main__":
    sys.exit(main())
