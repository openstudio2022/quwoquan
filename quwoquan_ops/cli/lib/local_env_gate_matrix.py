"""stackctl matrix：固定候选上的 Alpha → Beta → Gamma 串行门禁。"""
from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator
from uuid import uuid4

from quwoquan_ops.cli.lib import (
    external_provider_governance,
    provider_conformance,
)
from quwoquan_ops.cli.lib.deployment_candidate_manifest import (
    validate_packaged_provider_runtime,
)
from quwoquan_ops.cli.lib.local_env_gate_timing import (
    PhaseTimer,
    load_local_env_matrix_budgets,
    utc_now,
    write_timing_bundle,
)
from quwoquan_ops.cli.lib.local_postgres_migration_drift import (
    format_drift_gate_block,
    probe_migration_drift,
)
from quwoquan_ops.cli.lib.output_paths import output_root
from quwoquan_ops.cli.lib.startup_attempt_receipt import load_startup_attempt

ROOT = Path(__file__).resolve().parents[3]
PROFILE_LOCAL_ENV_GATE = "local-env-gate"
DEVICE_PROFILE_FULL = "full"
DEVICE_PROFILE_EMULATOR_ONLY = "emulator_only"
DEVICE_PROFILES = (DEVICE_PROFILE_FULL, DEVICE_PROFILE_EMULATOR_ONLY)
EMULATOR_ONLY_CLAIM = "ALPHA_BETA_GAMMA_EMULATOR_ONLY_FUNCTIONAL_GREEN"
CANONICAL_TARGETS = ("alpha-local", "beta-local", "gamma-local")
TARGET_ENVIRONMENTS = {
    "alpha-local": "alpha",
    "beta-local": "beta",
    "gamma-local": "gamma",
}
SPEC_REFS = (
    "AppRoot/JNY-002/SCN-005/UAT-003",
    "AppRoot/JNY-001/SCN-004/UAT-009",
    "runtime/runtime-config/environment-topology-and-packaging/GWT-001",
    "runtime/runtime-config/environment-topology-and-packaging/GWT-002",
    "runtime/runtime-config/environment-ops-cli-and-skill/GWT-001",
    "runtime/deliver-deploy-prod-pipeline/SIT-001",
    "runtime/system-architecture-and-engineering-guide/SIT-003",
    "runtime/runtime-data-engineering/SIT-001",
    "runtime/runtime-external-integration/provider-adapter-conformance-suite/GWT-002",
)

EnvRunner = Callable[..., dict[str, Any]]
DataRunner = Callable[..., dict[str, Any]]
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}")
_ATTEMPT_ID = re.compile(r"(?!unknown\b)[A-Za-z0-9][A-Za-z0-9._:-]{5,}")
_PROVIDER_CAPABILITY_ID = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+")
_PROVIDER_LAYERS = ("local_contract", "api_integration", "user_acceptance")


def _new_matrix_run_id() -> str:
    return (
        "matrix-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid4().hex[:12]
    )


def _matrix_lease_path() -> Path:
    path = (
        output_root()
        / "env"
        / "repo"
        / "local"
        / "process"
        / "local-env-gate.lock"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


class MatrixExecutionLeaseBusy(RuntimeError):
    """Another live local environment matrix still owns the repository lease."""


@contextmanager
def _matrix_execution_lease(matrix_run_id: str) -> Iterator[Path]:
    """Bind live matrix exclusion to one process lifetime via an OS lock."""
    path = _matrix_lease_path()
    with path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.seek(0)
            owner = handle.read().strip()
            detail = owner if owner else "owner metadata unavailable"
            raise MatrixExecutionLeaseBusy(
                f"live local environment matrix lease is already held: {detail}"
            ) from exc

        owner = {
            "schema": "quwoquan_ops.local_env_gate_matrix_lease",
            "status": "active",
            "matrixRunId": matrix_run_id,
            "pid": os.getpid(),
            "startedAt": utc_now(),
        }
        handle.seek(0)
        handle.truncate()
        json.dump(owner, handle, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
        handle.flush()
        try:
            yield path
        finally:
            released = {
                **owner,
                "status": "released",
                "releasedAt": utc_now(),
            }
            try:
                handle.seek(0)
                handle.truncate()
                json.dump(released, handle, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
                handle.flush()
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _repo_matrix_dir(matrix_run_id: str) -> Path:
    path = (
        output_root()
        / "env"
        / "repo"
        / "runs"
        / "local-env-gate"
        / matrix_run_id
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


def _evidence_path(path: Path) -> str:
    """Keep repo evidence relative while allowing isolated test/output roots."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _namespace(**kwargs: Any) -> Any:
    import argparse

    return argparse.Namespace(**kwargs)


def _run_commit_gate() -> dict[str, Any]:
    started = time.monotonic()
    result = subprocess.run(
        ["make", "commit-gate"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    summary_path = (
        ROOT
        / ".qwq_output"
        / "env"
        / "repo"
        / "runs"
        / "commit-gate"
        / "summary.json"
    )
    summary: dict[str, Any] = {}
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    return {
        "exitCode": result.returncode,
        "durationMs": int((time.monotonic() - started) * 1000),
        "summary": summary,
        "stdout": result.stdout[-2000:],
        "stderr": result.stderr[-2000:],
        "reportDir": (
            str(summary_path.parent.relative_to(ROOT)) if summary_path.exists() else ""
        ),
    }


def _docker_daemon_ready() -> tuple[bool, str]:
    result = subprocess.run(
        ["docker", "info"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        return True, "docker daemon ready"
    detail = (result.stderr or result.stdout or "docker info failed").strip()
    return False, detail[:300]


def _device_uat_bindings(
    *,
    device_profile: str,
    ios_simulator_device: str,
    android_emulator_device: str,
    android_physical_device: str,
) -> tuple[tuple[str, str, str], ...]:
    if device_profile not in DEVICE_PROFILES:
        raise ValueError(
            "device_profile must be one of " + ", ".join(DEVICE_PROFILES)
        )
    bindings = [
        ("iosSimulatorUAT", "ios-simulator", ios_simulator_device),
        ("androidEmulatorUAT", "android", android_emulator_device),
    ]
    if device_profile == DEVICE_PROFILE_FULL:
        bindings.append(
            ("androidPhysicalUAT", "android", android_physical_device)
        )
    return tuple(bindings)


def _device_binding_errors(
    *,
    device_profile: str = DEVICE_PROFILE_FULL,
    ios_simulator_device: str,
    android_emulator_device: str,
    android_physical_device: str,
) -> list[str]:
    """Reject absent or misclassified device bindings before mutating runtimes."""

    errors: list[str] = []
    try:
        uat_bindings = _device_uat_bindings(
            device_profile=device_profile,
            ios_simulator_device=ios_simulator_device,
            android_emulator_device=android_emulator_device,
            android_physical_device=android_physical_device,
        )
    except ValueError as exc:
        return [str(exc)]
    labels = {
        "iosSimulatorUAT": "iOS Simulator",
        "androidEmulatorUAT": "Android Emulator",
        "androidPhysicalUAT": "Android physical device",
    }
    bindings = {
        labels[key]: device_id.strip()
        for key, _, device_id in uat_bindings
    }
    for label, device_id in bindings.items():
        if not device_id:
            errors.append(f"{label} device id is required")
    if device_profile == DEVICE_PROFILE_FULL:
        android_ids = {
            android_emulator_device.strip(),
            android_physical_device.strip(),
        }
        android_ids.discard("")
        if len(android_ids) != 2 and len(android_ids) > 0:
            errors.append("Android Emulator and physical device must be distinct")
    if errors:
        return errors

    try:
        simulator = subprocess.run(
            ["xcrun", "simctl", "list", "devices", "available", "--json"],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        errors.append("xcrun simctl is unavailable")
        return errors
    try:
        simulator_payload = json.loads(simulator.stdout)
    except json.JSONDecodeError:
        simulator_payload = {}
    available_ids = {
        str(item.get("udid") or "")
        for items in (simulator_payload.get("devices") or {}).values()
        if isinstance(items, list)
        for item in items
        if isinstance(item, dict) and item.get("isAvailable") is not False
    }
    if simulator.returncode != 0 or ios_simulator_device not in available_ids:
        errors.append("configured iOS Simulator is not available")

    for key, platform, device_id in uat_bindings:
        if platform != "android":
            continue
        label = labels[key]
        expected_qemu = "1" if key == "androidEmulatorUAT" else "0"
        try:
            state = subprocess.run(
                ["adb", "-s", device_id, "get-state"],
                text=True,
                capture_output=True,
                check=False,
            )
            qemu = subprocess.run(
                ["adb", "-s", device_id, "shell", "getprop", "ro.kernel.qemu"],
                text=True,
                capture_output=True,
                check=False,
            )
        except OSError:
            errors.append("adb is unavailable")
            break
        actual_qemu = (qemu.stdout or "0").strip() or "0"
        if state.returncode != 0 or state.stdout.strip() != "device":
            errors.append(f"configured {label} is not connected")
        elif actual_qemu != expected_qemu:
            errors.append(f"configured {label} has the wrong device class")
    return errors


def _release_binding(attestation: str, *, label: str) -> dict[str, str]:
    path = Path(str(attestation or "").strip()).expanduser()
    if not str(attestation or "").strip():
        raise ValueError(f"{label} release attestation is required")
    try:
        payload = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} release attestation is unreadable: {exc}") from exc
    release_id = str(payload.get("releaseId") or "").strip() if isinstance(payload, dict) else ""
    digest = str(payload.get("payloadSha256") or "").strip() if isinstance(payload, dict) else ""
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != "quwoquan_data.release_attestation"
        or not release_id
        or _SHA256.fullmatch(digest) is None
    ):
        raise ValueError(f"{label} release attestation identity is invalid")
    return {"releaseId": release_id, "releaseDigest": digest, "attestation": str(path.resolve())}


def _data_cli_runner(*, argv: list[str], report_path: Path, **_: Any) -> dict[str, Any]:
    started = time.monotonic()
    result = subprocess.run(
        argv,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    stdout_payload: dict[str, Any] | None = None
    try:
        parsed = json.loads(result.stdout)
        if isinstance(parsed, dict):
            stdout_payload = parsed
    except json.JSONDecodeError:
        pass
    return {
        "exitCode": result.returncode,
        "summary": " ".join(argv[2:5]) + (" passed" if result.returncode == 0 else " failed"),
        "details": [
            line.strip()
            for line in (result.stderr or result.stdout or "").splitlines()
            if line.strip()
        ][-8:],
        "reportDir": _evidence_path(report_path.parent),
        "reportPath": _evidence_path(report_path),
        "payload": stdout_payload,
        "durationMs": int((time.monotonic() - started) * 1000),
    }


def _data_run_ids(matrix_run_id: str, environment: str) -> dict[str, str]:
    prefix = f"{matrix_run_id}-{environment}"
    return {
        "originalImport": f"{prefix}-original-import",
        "originalVerify": f"{prefix}-original-verify",
        "rollbackImport": f"{prefix}-rollback-import",
        "rollbackVerify": f"{prefix}-rollback-verify",
        "replayImport": f"{prefix}-replay-import",
        "replayVerify": f"{prefix}-replay-verify",
        "lifecycleExit": f"{prefix}-lifecycle-exit",
    }


def _data_readiness_path(environment: str, release_id: str, run_id: str) -> Path:
    return (
        output_root()
        / "env"
        / environment
        / "runs"
        / "data-release"
        / release_id
        / run_id
        / "release-readiness.json"
    )


def _lifecycle_exit_path(environment: str, release_id: str, run_id: str) -> Path:
    return (
        output_root()
        / "env"
        / environment
        / "runs"
        / "release-lifecycle-exit"
        / release_id
        / run_id
        / "lifecycle-exit.json"
    )


def _homepage_release_evidence(
    *,
    readiness_path: Path,
    environment: str,
    release_id: str,
) -> dict[str, Any]:
    try:
        payload = json.loads(readiness_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {
            "exitCode": 2,
            "summary": "homepage release readiness is unreadable",
            "details": [str(exc)],
            "reportDir": _evidence_path(readiness_path.parent),
        }
    feed_queries = payload.get("feedQueries") if isinstance(payload, dict) else None
    homepage = next(
        (
            item
            for item in feed_queries or []
            if isinstance(item, dict) and item.get("name") == "homepage_recommend"
        ),
        None,
    )
    matched = list(homepage.get("matchedPostIds") or []) if isinstance(homepage, dict) else []
    passed = (
        payload.get("schema") == "quwoquan_data.environment_release_readiness"
        and payload.get("environment") == environment
        and payload.get("releaseId") == release_id
        and payload.get("readinessPhase") in {"consumer", "commercial"}
        and isinstance(homepage, dict)
        and homepage.get("status") == 200
        and homepage.get("releaseBound") is True
        and bool(matched)
    )
    return {
        "exitCode": 0 if passed else 2,
        "summary": (
            "homepage recommendation release evidence passed"
            if passed
            else "homepage recommendation release evidence is GATE_BLOCK"
        ),
        "details": [
            f"environment={environment}",
            f"releaseId={release_id}",
            f"outcome={'content' if matched else 'empty'}",
            f"emptyReason={'none' if matched else 'release_content_missing'}",
            f"itemCount={len(matched)}",
        ],
        "reportDir": _evidence_path(readiness_path.parent),
        "reportPath": _evidence_path(readiness_path),
        "outcome": "content" if matched else "empty",
        "emptyReason": None if matched else "release_content_missing",
        "itemCount": len(matched),
    }


def _acceptance_lease_event(
    payload: dict[str, Any],
    *,
    action: str,
    environment: str,
    release_id: str,
    lease_id: str,
) -> dict[str, Any]:
    event = payload.get("payload")
    if (
        not isinstance(event, dict)
        or event.get("schema") != "quwoquan_data.release_acceptance_lease_event"
        or event.get("action") != action
        or event.get("environment") != environment
        or event.get("releaseId") != release_id
        or event.get("leaseId") != lease_id
        or not str(event.get("eventRef") or "").strip()
    ):
        raise ValueError(
            f"Data acceptance lease {action} returned identity-drifted evidence"
        )
    return event


def _run_data_phase(
    phases: list[dict[str, Any]],
    *,
    phase_name: str,
    environment: str,
    action: str,
    argv: list[str],
    report_path: Path,
    data_fn: DataRunner,
) -> tuple[int, dict[str, Any]]:
    started = time.monotonic()
    try:
        payload = data_fn(
            environment=environment,
            action=action,
            argv=argv,
            report_path=report_path,
        )
    except Exception as exc:
        payload = {
            "exitCode": 2,
            "summary": f"{action} raised an exception",
            "details": [f"{type(exc).__name__}: {exc}"],
            "reportDir": _evidence_path(report_path.parent),
            "durationMs": int((time.monotonic() - started) * 1000),
        }
    return (
        _record_phase(phases, name=phase_name, payload=payload),
        payload,
    )


def _record_phase(
    phases: list[dict[str, Any]],
    *,
    name: str,
    payload: dict[str, Any],
) -> int:
    raw_exit_code = payload.get("exitCode")
    exit_code = int(raw_exit_code) if isinstance(raw_exit_code, int) else 2
    phase = PhaseTimer(name).finish(
        status="passed" if exit_code == 0 else "gate_block",
        details=[str(payload.get("summary") or "")]
        + [str(item) for item in list(payload.get("details") or [])[:8]],
        report_dir=str(payload.get("reportDir") or ""),
    )
    duration_ms = payload.get("durationMs")
    if isinstance(duration_ms, int) and duration_ms >= 0:
        phase["durationMs"] = duration_ms
    phases.append(phase)
    return exit_code


def _invoke_env(fn: EnvRunner, args: Any, *, action: str) -> dict[str, Any]:
    started = time.monotonic()
    try:
        payload = fn(args)
        if not isinstance(payload, dict):
            raise TypeError("runner returned a non-object payload")
        return payload
    except Exception as exc:
        return {
            "exitCode": 2,
            "summary": f"{action} raised an exception",
            "details": [f"{type(exc).__name__}: {exc}"],
            "reportDir": "",
            "durationMs": int((time.monotonic() - started) * 1000),
        }


def _provider_local_functional_errors(
    payload: dict[str, Any],
    *,
    environment: str,
    target: str,
    compiled_provider_governance: dict[str, Any],
) -> list[str]:
    """Reject an aggregate missing any compiled Provider capability/layer cell."""
    errors: list[str] = []
    capability_ids = provider_conformance.provider_conformance_capability_ids(
        compiled_provider_governance
    )
    expected = {
        (capability_id, layer)
        for capability_id in capability_ids
        for layer in _PROVIDER_LAYERS
    }
    expected_count = len(expected)
    if not capability_ids:
        errors.append(
            "Provider local functional compiled governance has no required capabilities"
        )
    expected_scalars = {
        "schema": "stackctl-provider-conformance-environment-matrix",
        "readinessScope": "local_functional",
        "releasePromotionClaimed": False,
        "status": "passed",
        "environment": environment,
        "target": target,
        "capabilityCount": len(capability_ids),
        "expectedCells": expected_count,
        "executed": expected_count,
        "skipped": 0,
        "attemptEvidenceCount": expected_count,
        "exitCode": 0,
    }
    for field, expected_value in expected_scalars.items():
        if payload.get(field) != expected_value:
            errors.append(
                f"Provider local functional {field} must be {expected_value!r}, "
                f"got {payload.get(field)!r}"
            )
    issues = payload.get("issues")
    if not isinstance(issues, list) or issues:
        errors.append("Provider local functional issues must be an empty list")
    cells = payload.get("cells")
    observed: list[tuple[str, str]] = []
    if not isinstance(cells, list) or len(cells) != expected_count:
        errors.append(
            "Provider local functional cells must contain exactly the compiled "
            f"{expected_count} entries"
        )
        cells = []
    for index, cell in enumerate(cells):
        if not isinstance(cell, dict):
            errors.append(f"Provider local functional cell[{index}] must be an object")
            continue
        capability_id = cell.get("capabilityId")
        adapter_id = cell.get("adapterId")
        layer = cell.get("layer")
        if (
            not isinstance(capability_id, str)
            or _PROVIDER_CAPABILITY_ID.fullmatch(capability_id) is None
            or capability_id not in capability_ids
            or not isinstance(adapter_id, str)
            or not adapter_id
            or layer not in _PROVIDER_LAYERS
            or cell.get("exitCode") != 0
        ):
            errors.append(f"Provider local functional cell[{index}] is malformed")
            continue
        observed.append((capability_id, str(layer)))
    if (
        len(observed) != len(set(observed))
        or set(observed) != expected
    ):
        errors.append(
            "Provider local functional cells must contain every compiled capability "
            "exactly once across all three layers"
        )
    return errors


def _down_target(target: str, *, down_fn: EnvRunner) -> dict[str, Any]:
    """Only use stackctl down; never kill listeners, clear locks, or wipe state."""
    return _invoke_env(
        down_fn,
        _namespace(
            command="down",
            target=target,
            formal_release_teardown=False,
            release_manifest="",
            output_format="json",
            report_dir="",
        ),
        action=f"{target} down",
    )


def _live_matrix_evidence_errors(
    environments: dict[str, Any],
    *,
    baseline_id: str,
    device_profile: str = DEVICE_PROFILE_FULL,
) -> list[str]:
    errors: list[str] = []
    required_steps = [
        "package",
        "up",
        "health",
        "telemetryBefore",
        "providerMatrix",
        "candidateApply",
        "candidateVerify",
        "rollbackApply",
        "rollbackVerify",
        "replayApply",
        "verify",
        "replayVerify",
        "homepageReleaseEvidence",
        "lifecycleExit",
        "iosSimulatorUAT",
        "androidEmulatorUAT",
        "telemetryAfter",
        "acceptanceLeaseAcquire",
        "acceptanceLeaseRevoke",
        "down",
    ]
    if device_profile == DEVICE_PROFILE_FULL:
        required_steps.insert(
            required_steps.index("telemetryAfter"),
            "androidPhysicalUAT",
        )
    for target in CANONICAL_TARGETS:
        block = environments.get(target)
        if not isinstance(block, dict):
            errors.append(f"{target}: environment evidence block is missing")
            continue
        if (
            block.get("target") != target
            or block.get("environment") != TARGET_ENVIRONMENTS[target]
        ):
            errors.append(f"{target}: environment evidence identity drifted")
        package = block.get("package")
        if not isinstance(package, dict) or package.get("baselineId") != baseline_id:
            errors.append(f"{target}: package baselineId is missing or drifted")
        elif (
            _SHA256.fullmatch(str(package.get("packageDigest") or "")) is None
            or _SHA256.fullmatch(str(package.get("imageDigest") or "")) is None
            or not isinstance(package.get("observabilityLogSink"), dict)
            or package["observabilityLogSink"].get("adapterId")
            != "ext.obs.elasticsearch"
            or package["observabilityLogSink"].get("deploymentMode")
            != "package-bound-local"
        ):
            errors.append(f"{target}: package/OCI/Elasticsearch identity is incomplete")
        else:
            try:
                candidate_dir = Path(
                    str(package.get("candidateDir") or "")
                ).resolve()
                validate_packaged_provider_runtime(
                    package.get("providerRuntime"),
                    expected_environment=TARGET_ENVIRONMENTS[target],
                    expected_target=target,
                    candidate_root=candidate_dir,
                )
            except (OSError, TypeError, ValueError) as exc:
                errors.append(
                    f"{target}: package-bound Provider runtime is incomplete: {exc}"
                )
        if block.get("workload") != "full" or block.get("profile") != "integration":
            errors.append(f"{target}: Green closure did not use full/integration")
        for step in required_steps:
            evidence = block.get(step)
            if (
                not isinstance(evidence, dict)
                or evidence.get("exitCode") != 0
                or not str(evidence.get("reportDir") or "").strip()
            ):
                errors.append(f"{target}: {step} has no successful report-bound evidence")
        attempt = block.get("startupAttempt")
        if (
            not isinstance(attempt, dict)
            or attempt.get("status") != "running"
            or attempt.get("target") != target
            or attempt.get("env") != TARGET_ENVIRONMENTS[target]
        ):
            errors.append(f"{target}: running startup attempt evidence is missing")
        homepage = block.get("homepageReleaseEvidence")
        if (
            not isinstance(homepage, dict)
            or homepage.get("outcome") != "content"
            or homepage.get("emptyReason") is not None
            or int(homepage.get("itemCount") or 0) <= 0
        ):
            errors.append(f"{target}: homepage content outcome is not canonical")
        provider = block.get("providerMatrix")
        if (
            not isinstance(provider, dict)
            or provider.get("status") != "passed"
            or int(provider.get("capabilityCount") or 0) <= 0
            or int(provider.get("executed") or 0)
            != int(provider.get("capabilityCount") or 0) * 3
            or int(provider.get("skipped") or 0) != 0
        ):
            errors.append(f"{target}: Provider three-layer matrix is incomplete")
        for step in ("telemetryBefore", "telemetryAfter"):
            telemetry = block.get(step)
            if (
                not isinstance(telemetry, dict)
                or ((telemetry.get("logSink") or {}).get("adapterId"))
                != "ext.obs.elasticsearch"
                or int(telemetry.get("executed") or 0) <= 0
                or int(telemetry.get("skipped") or 0) != 0
            ):
                errors.append(f"{target}: {step} has no Elasticsearch execution evidence")
        for step, _, _ in _device_uat_bindings(
            device_profile=device_profile,
            ios_simulator_device="ios-simulator",
            android_emulator_device="android-emulator",
            android_physical_device="android-physical",
        ):
            uat = block.get(step)
            if (
                not isinstance(uat, dict)
                or uat.get("status") != "passed"
                or int(uat.get("executed") or 0) <= 0
                or int(uat.get("skipped") or 0) != 0
                or uat.get("packageBaseline") != baseline_id
                or not _contains_non_unknown_attempt(uat)
            ):
                errors.append(f"{target}: {step} has no release-bound device attempt")
        verify = block.get("verify")
        if not _integration_verify_has_required_nonprod_case(verify):
            errors.append(f"{target}: integration verify has no executed nonprod CaseResult")
    return errors


def _contains_non_unknown_attempt(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == "attemptId" and _ATTEMPT_ID.fullmatch(str(nested or "")):
                return True
            if _contains_non_unknown_attempt(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_non_unknown_attempt(item) for item in value)
    return False


def _integration_verify_has_required_nonprod_case(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    report_ref = str(value.get("reportDir") or "").strip()
    if not report_ref:
        return False
    report_path = Path(report_ref)
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    try:
        report = json.loads((report_path / "report.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    if report.get("profile") != "integration" or report.get("status") != "ok":
        return False
    for step in report.get("steps") or []:
        if not isinstance(step, dict) or step.get("kind") != "nonprod-business-data":
            continue
        case = step.get("caseResult")
        return (
            isinstance(case, dict)
            and case.get("status") == "passed"
            and int(case.get("executed") or 0) > 0
            and int(case.get("skipped") or 0) == 0
        )
    return False


def _write_matrix_result(
    *,
    matrix_dir: Path,
    phases: list[dict[str, Any]],
    environments: dict[str, Any],
    budgets: dict[str, Any],
    wall_seconds: float,
    exit_code: int,
    failure_category: str,
    baseline_id: str,
    release: dict[str, str],
    matrix_run_id: str,
    execution_class: str,
    device_profile: str,
) -> dict[str, Any]:
    passed = exit_code == 0 and tuple(environments) == CANONICAL_TARGETS
    live_evidence = execution_class == "live"
    claim = (
        EMULATOR_ONLY_CLAIM
        if passed
        and live_evidence
        and device_profile == DEVICE_PROFILE_EMULATOR_ONLY
        else "ALPHA_BETA_GAMMA_LOCAL_GREEN"
        if passed and live_evidence
        else "CONTRACT_SIMULATION_PASSED"
        if passed
        else "GATE_BLOCK"
    )
    status = "passed" if passed else "gate_block"
    executed = len(phases)
    skipped = 0
    timing_path = write_timing_bundle(
        matrix_dir,
        phases=phases,
        wall_clock_seconds=wall_seconds,
        budgets=budgets,
        claim=claim,
        cache_mode="package-bound",
        extras={
            "failureCategory": failure_category,
            "targets": list(CANONICAL_TARGETS),
            "executed": executed,
            "skipped": skipped,
            "matrixRunId": matrix_run_id,
            "executionClass": execution_class,
            "deviceProfile": device_profile,
            "nonPromotable": device_profile == DEVICE_PROFILE_EMULATOR_ONLY,
        },
    )
    payload = {
        "schema": "quwoquan.test.case-result",
        "generatedAt": utc_now(),
        "caseId": "stackctl.local-env-gate.alpha-beta-gamma",
        "status": status,
        "claim": claim,
        "executed": executed,
        "skipped": skipped,
        "specRefs": list(SPEC_REFS),
        "targets": list(CANONICAL_TARGETS),
        "wallClockSeconds": round(wall_seconds, 3),
        "softBudgetSeconds": budgets["softBudgetSeconds"],
        "hardBudgetSeconds": budgets["hardBudgetSeconds"],
        "failureCategory": failure_category,
        "matrixRunId": matrix_run_id,
        "executionClass": execution_class,
        "deviceProfile": device_profile,
        "baselineId": baseline_id,
        "releaseId": release.get("releaseId", ""),
        "releaseDigest": release.get("releaseDigest", ""),
        "timingPath": _evidence_path(timing_path),
        "phases": phases,
        "environments": environments,
    }
    if device_profile == DEVICE_PROFILE_EMULATOR_ONLY:
        payload["nonPromotable"] = True
        payload["deviceCoverage"] = [
            "ios-simulator",
            "android-emulator",
        ]
        payload["waivers"] = [
            {
                "scope": "android-physical-device",
                "effect": "release-promotion-blocked",
                "reason": "emulator_only execution profile",
            }
        ]
    (matrix_dir / "matrix.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (matrix_dir / "matrix.md").write_text(
        "\n".join(
            [
                "# Alpha / Beta / Gamma local gate",
                "",
                f"- status: `{status}`",
                f"- claim: `{claim}`",
                f"- executed/skipped: `{executed}/{skipped}`",
                f"- failureCategory: `{failure_category or 'none'}`",
                f"- timing: `{_evidence_path(timing_path)}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "exitCode": 0 if passed else (exit_code or 2),
        "summary": f"stackctl matrix {PROFILE_LOCAL_ENV_GATE}: {claim}",
        "details": [
            f"status={status}",
            f"executed={executed}",
            f"skipped={skipped}",
            f"timing={_evidence_path(timing_path)}",
            f"failureCategory={failure_category or 'none'}",
            f"deviceProfile={device_profile}",
        ],
        "reportDir": _evidence_path(matrix_dir),
        "claim": claim,
        "status": status,
        "executed": executed,
        "skipped": skipped,
        "wallClockSeconds": round(wall_seconds, 3),
    }


def _run_local_env_gate_matrix(
    *,
    package_fn: EnvRunner,
    up_fn: EnvRunner,
    health_fn: EnvRunner,
    verify_fn: EnvRunner,
    down_fn: EnvRunner,
    telemetry_fn: EnvRunner | None = None,
    provider_fn: EnvRunner | None = None,
    app_uat_fn: EnvRunner | None = None,
    filter_catalog_fn: EnvRunner | None = None,
    targets: tuple[str, ...] = CANONICAL_TARGETS,
    include_l0: bool = True,
    release_attestation: str = "",
    rollback_release_attestation: str = "",
    nonprod_data_evidence: dict[str, str] | None = None,
    ios_simulator_device: str = "",
    android_emulator_device: str = "",
    android_physical_device: str = "",
    device_profile: str = DEVICE_PROFILE_FULL,
    data_fn: DataRunner = _data_cli_runner,
    execution_class: str = "live",
    matrix_run_id: str,
) -> dict[str, Any]:
    """Run one package-bound full integration state machine per local environment."""
    if execution_class not in {"live", "contract-simulation"}:
        raise ValueError("execution_class must be live or contract-simulation")
    if device_profile not in DEVICE_PROFILES:
        raise ValueError(
            "device_profile must be one of " + ", ".join(DEVICE_PROFILES)
        )
    if tuple(targets) != CANONICAL_TARGETS:
        return {
            "exitCode": 2,
            "summary": "stackctl matrix target set is GATE_BLOCK",
            "details": [
                "--targets must be exactly alpha-local,beta-local,gamma-local in order"
            ],
            "claim": "GATE_BLOCK",
            "status": "gate_block",
            "executed": 0,
            "skipped": 0,
        }
    compiled_provider_governance: dict[str, Any] = {}
    try:
        candidate_release = _release_binding(release_attestation, label="candidate")
        rollback_release = _release_binding(
            rollback_release_attestation,
            label="rollback",
        )
        if candidate_release["releaseId"] == rollback_release["releaseId"]:
            raise ValueError("candidate and rollback release must be different")
        evidence_by_target = dict(nonprod_data_evidence or {})
        if execution_class == "live":
            compiled_provider_governance, provider_governance_issues = (
                external_provider_governance.load_and_compile()
            )
            if provider_governance_issues:
                raise ValueError(
                    "canonical Provider governance is invalid: "
                    + "; ".join(issue.render() for issue in provider_governance_issues)
                )
            if not provider_conformance.provider_conformance_capability_ids(
                compiled_provider_governance
            ):
                raise ValueError(
                    "canonical Provider governance defines no required capabilities"
                )
            if set(evidence_by_target) != set(CANONICAL_TARGETS):
                raise ValueError(
                    "live matrix requires one --nonprod-data-evidence for every target"
                )
            for target, raw_path in sorted(evidence_by_target.items()):
                evidence_path = Path(str(raw_path or "").strip()).expanduser()
                if not evidence_path.is_absolute():
                    evidence_path = ROOT / evidence_path
                if not evidence_path.is_file():
                    raise ValueError(f"{target} nonprod data evidence is unavailable")
            if telemetry_fn is None or provider_fn is None or app_uat_fn is None:
                raise ValueError(
                    "live matrix requires telemetry, Provider, and App UAT runners"
                )
            device_errors = _device_binding_errors(
                device_profile=device_profile,
                ios_simulator_device=ios_simulator_device,
                android_emulator_device=android_emulator_device,
                android_physical_device=android_physical_device,
            )
            if device_errors:
                raise ValueError("; ".join(device_errors))
    except ValueError as exc:
        return {
            "exitCode": 2,
            "summary": "stackctl matrix release/data inputs are GATE_BLOCK",
            "details": [str(exc)],
            "claim": "GATE_BLOCK",
            "status": "gate_block",
            "executed": 0,
            "skipped": 0,
        }

    budgets = load_local_env_matrix_budgets()
    matrix_dir = _repo_matrix_dir(matrix_run_id)
    wall_started = time.monotonic()
    phases: list[dict[str, Any]] = []
    environments: dict[str, Any] = {}
    overall_exit = 0
    failure_category = ""
    matrix_baseline_id = ""

    docker_ok, docker_detail = _docker_daemon_ready()
    phases.append(
        PhaseTimer("docker_daemon_preflight").finish(
            status="passed" if docker_ok else "gate_block",
            details=[docker_detail],
        )
    )
    if not docker_ok:
        overall_exit = 2
        failure_category = "docker"

    if overall_exit == 0 and include_l0:
        l0 = _run_commit_gate()
        phases.append(
            PhaseTimer("L0_commit_gate").finish(
                status="passed" if l0["exitCode"] == 0 else "gate_block",
                details=[f"exit={l0['exitCode']}"],
                report_dir=l0.get("reportDir", ""),
            )
        )
        if l0["exitCode"] != 0:
            overall_exit = int(l0["exitCode"] or 2)
            failure_category = "l0"

    for target in targets:
        if overall_exit != 0:
            break
        if time.monotonic() - wall_started > int(budgets["hardBudgetSeconds"]):
            overall_exit = 2
            failure_category = "budget"
            phases.append(
                PhaseTimer(f"{target}_budget").finish(
                    status="gate_block",
                    details=["hard budget exhausted before target execution"],
                )
            )
            break

        env_name = TARGET_ENVIRONMENTS[target]
        block: dict[str, Any] = {
            "target": target,
            "environment": env_name,
            "workload": "full",
            "profile": "integration",
            "matrixRunId": matrix_run_id,
            "release": candidate_release,
            "rollbackRelease": rollback_release,
        }
        data_ids = _data_run_ids(matrix_run_id, env_name)
        block["dataRunIds"] = data_ids

        # The local targets share resources. Normal down is the sole cleanup path.
        for other in CANONICAL_TARGETS:
            down_payload = _down_target(other, down_fn=down_fn)
            down_exit = _record_phase(
                phases,
                name=f"{target}_pre_down_{other}",
                payload=down_payload,
            )
            if down_exit != 0:
                block["preDown"] = down_payload
                overall_exit = down_exit
                failure_category = "down"
                break
        if overall_exit != 0:
            environments[target] = block
            break

        package_payload = _invoke_env(
            package_fn,
            _namespace(
                command="package",
                kind="runtime",
                env=env_name,
                service="",
                include_services=True,
                target=target,
                output_format="json",
                report_dir="",
                apk_path="",
                verify_remote_apk=False,
                release_attestation=release_attestation,
                rollback_release_attestation=rollback_release_attestation,
            ),
            action=f"{target} package",
        )
        block["package"] = package_payload
        package_exit = _record_phase(
            phases,
            name=f"{target}_package",
            payload=package_payload,
        )
        if package_exit != 0:
            overall_exit = package_exit
            failure_category = "package"
            environments[target] = block
            break
        package_baseline = str(package_payload.get("baselineId") or "").strip()
        if _SHA256.fullmatch(package_baseline) is None:
            overall_exit = 2
            failure_category = "package_identity"
            phases.append(
                PhaseTimer(f"{target}_package_identity").finish(
                    status="gate_block",
                    details=["package result is missing canonical baselineId"],
                )
            )
            environments[target] = block
            break
        if matrix_baseline_id and package_baseline != matrix_baseline_id:
            overall_exit = 2
            failure_category = "workspace_drift"
            phases.append(
                PhaseTimer(f"{target}_package_identity").finish(
                    status="gate_block",
                    details=[
                        "Alpha/Beta/Gamma package baselineId drifted during the serial matrix",
                        f"expected={matrix_baseline_id}",
                        f"actual={package_baseline}",
                    ],
                )
            )
            environments[target] = block
            break
        matrix_baseline_id = package_baseline

        if target in {"alpha-local", "beta-local"}:
            drift = probe_migration_drift(target)
            phases.append(
                PhaseTimer(f"{target}_migration_drift_probe").finish(
                    status="gate_block" if drift.has_drift else "passed",
                    details=[
                        format_drift_gate_block(drift) if drift.has_drift else drift.detail
                    ],
                )
            )
            if drift.has_drift:
                overall_exit = 2
                failure_category = "migration_drift"
                environments[target] = block
                break

        up_payload = _invoke_env(
            up_fn,
            _namespace(
                command="up",
                env=env_name,
                target="",
                workload="full",
                skip_app=True,
                skip_build=True,
                build_only=False,
                build_services="",
                formal_release=False,
                release_manifest="",
                rollout_mode="",
                device_id="",
                output_format="json",
                report_dir="",
            ),
            action=f"{target} up",
        )
        block["up"] = up_payload
        up_exit = _record_phase(phases, name=f"{target}_up", payload=up_payload)
        if up_exit != 0:
            overall_exit = up_exit
            failure_category = "up"
            cleanup_payload = _down_target(target, down_fn=down_fn)
            block["failedUpCleanup"] = cleanup_payload
            cleanup_exit = _record_phase(
                phases,
                name=f"{target}_failed_up_cleanup",
                payload=cleanup_payload,
            )
            if cleanup_exit != 0:
                overall_exit = cleanup_exit
                failure_category = "down"
            environments[target] = block
            break

        if execution_class == "live":
            try:
                startup_attempt = load_startup_attempt(target)
            except ValueError as exc:
                startup_attempt = None
                startup_detail = str(exc)
            else:
                startup_detail = ""
            block["startupAttempt"] = startup_attempt
            startup_identity_ok = (
                isinstance(startup_attempt, dict)
                and startup_attempt.get("status") == "running"
                and startup_attempt.get("target") == target
                and startup_attempt.get("env") == env_name
                and startup_attempt.get("workload") == "full"
                and str(startup_attempt.get("composeProject") or "").strip()
                and _SHA256.fullmatch(
                    str(startup_attempt.get("configurationDigest") or "")
                )
                is not None
                and _SHA256.fullmatch(
                    str(startup_attempt.get("imageTransportTag") or "")
                )
                is not None
            )
            phases.append(
                PhaseTimer(f"{target}_startup_attempt_identity").finish(
                    status="passed" if startup_identity_ok else "gate_block",
                    details=[
                        "running startup attempt identity verified"
                        if startup_identity_ok
                        else startup_detail
                        or "running startup attempt identity is missing or drifted"
                    ],
                )
            )
            if not startup_identity_ok:
                overall_exit = 2
                failure_category = "startup_identity"

        if overall_exit != 0:
            cleanup_payload = _down_target(target, down_fn=down_fn)
            block["startupIdentityCleanup"] = cleanup_payload
            cleanup_exit = _record_phase(
                phases,
                name=f"{target}_startup_identity_cleanup",
                payload=cleanup_payload,
            )
            if cleanup_exit != 0:
                overall_exit = cleanup_exit
                failure_category = "down"
            environments[target] = block
            break

        health_payload = _invoke_env(
            health_fn,
            _namespace(
                command="health",
                target=target,
                scope="full",
                output_format="json",
                report_dir="",
                request_timeout_seconds=0,
                retry_attempts=0,
                retry_sleep_seconds=-1.0,
            ),
            action=f"{target} health",
        )
        block["health"] = health_payload
        health_exit = _record_phase(
            phases,
            name=f"{target}_health",
            payload=health_payload,
        )
        if health_exit != 0:
            overall_exit = health_exit
            failure_category = "health"

        if overall_exit == 0 and execution_class == "live":
            telemetry_payload = _invoke_env(
                telemetry_fn,
                _namespace(
                    command="product-telemetry-log-sink",
                    target=target,
                    action="all",
                    output_format="json",
                    report_dir=str(matrix_dir / target / "telemetry-before"),
                ),
                action=f"{target} Elasticsearch telemetry preflight",
            )
            block["telemetryBefore"] = telemetry_payload
            telemetry_exit = _record_phase(
                phases,
                name=f"{target}_elasticsearch_telemetry_before",
                payload=telemetry_payload,
            )
            if telemetry_exit != 0:
                overall_exit = telemetry_exit
                failure_category = "elasticsearch"

        if overall_exit == 0 and execution_class == "live":
            provider_payload = _invoke_env(
                provider_fn,
                _namespace(
                    command="provider-conformance",
                    adapter_id="",
                    capability_id="",
                    env=env_name,
                    layer="",
                    matrix=False,
                    environment_matrix=True,
                    execute=True,
                    image_digest="",
                    data_digest="",
                    output_format="json",
                    report_dir=str(matrix_dir / target / "provider-matrix"),
                ),
                action=f"{target} Provider environment matrix",
            )
            provider_contract_errors = _provider_local_functional_errors(
                provider_payload,
                environment=env_name,
                target=target,
                compiled_provider_governance=compiled_provider_governance,
            )
            if provider_contract_errors:
                provider_payload = {
                    **provider_payload,
                    "exitCode": 2,
                    "status": "gate_block",
                    "summary": "Provider local functional evidence is GATE_BLOCK",
                    "details": [
                        *list(provider_payload.get("details") or []),
                        *provider_contract_errors,
                    ],
                    "issues": [
                        *list(provider_payload.get("issues") or []),
                        *provider_contract_errors,
                    ],
                }
            block["providerMatrix"] = provider_payload
            provider_exit = _record_phase(
                phases,
                name=f"{target}_provider_matrix",
                payload=provider_payload,
            )
            if provider_exit != 0:
                overall_exit = provider_exit
                failure_category = "provider"

        if overall_exit == 0:
            data_root = ["python3", "quwoquan_data/scripts/cli.py"]
            original_readiness = _data_readiness_path(
                env_name,
                candidate_release["releaseId"],
                data_ids["originalVerify"],
            )
            data_exit, data_payload = _run_data_phase(
                phases,
                phase_name=f"{target}_data_candidate_apply",
                environment=env_name,
                action="candidate-apply",
                argv=[
                    *data_root,
                    "ship",
                    "apply",
                    "--release-id",
                    candidate_release["releaseId"],
                    "--env",
                    env_name,
                    "--run-id",
                    data_ids["originalImport"],
                    "--import",
                    "--full-sync",
                ],
                report_path=(original_readiness.parent.parent / data_ids["originalImport"] / "result.json"),
                data_fn=data_fn,
            )
            block["candidateApply"] = data_payload
            if data_exit != 0:
                overall_exit = data_exit
                failure_category = "data_candidate_apply"

        if overall_exit == 0:
            data_exit, data_payload = _run_data_phase(
                phases,
                phase_name=f"{target}_data_candidate_verify",
                environment=env_name,
                action="candidate-verify",
                argv=[
                    "python3",
                    "quwoquan_data/scripts/cli.py",
                    "ship",
                    "verify",
                    "--release-id",
                    candidate_release["releaseId"],
                    "--env",
                    env_name,
                    "--import-run-id",
                    data_ids["originalImport"],
                    "--run-id",
                    data_ids["originalVerify"],
                    "--readiness-phase",
                    "consumer",
                ],
                report_path=original_readiness,
                data_fn=data_fn,
            )
            block["candidateVerify"] = data_payload
            if data_exit != 0:
                overall_exit = data_exit
                failure_category = "data_candidate_verify"

        if overall_exit == 0:
            rollback_readiness = _data_readiness_path(
                env_name,
                rollback_release["releaseId"],
                data_ids["rollbackVerify"],
            )
            data_exit, data_payload = _run_data_phase(
                phases,
                phase_name=f"{target}_data_rollback_apply",
                environment=env_name,
                action="rollback-apply",
                argv=[
                    "python3",
                    "quwoquan_data/scripts/cli.py",
                    "ship",
                    "rollback",
                    "--to-release",
                    rollback_release["releaseId"],
                    "--from-release-id",
                    candidate_release["releaseId"],
                    "--env",
                    env_name,
                    "--run-id",
                    data_ids["rollbackImport"],
                    "--import",
                ],
                report_path=(rollback_readiness.parent.parent / data_ids["rollbackImport"] / "result.json"),
                data_fn=data_fn,
            )
            block["rollbackApply"] = data_payload
            if data_exit != 0:
                overall_exit = data_exit
                failure_category = "data_rollback"

        if overall_exit == 0:
            data_exit, data_payload = _run_data_phase(
                phases,
                phase_name=f"{target}_data_rollback_verify",
                environment=env_name,
                action="rollback-verify",
                argv=[
                    "python3",
                    "quwoquan_data/scripts/cli.py",
                    "ship",
                    "verify",
                    "--release-id",
                    rollback_release["releaseId"],
                    "--env",
                    env_name,
                    "--import-run-id",
                    data_ids["rollbackImport"],
                    "--run-id",
                    data_ids["rollbackVerify"],
                    "--readiness-phase",
                    "consumer",
                ],
                report_path=rollback_readiness,
                data_fn=data_fn,
            )
            block["rollbackVerify"] = data_payload
            if data_exit != 0:
                overall_exit = data_exit
                failure_category = "data_rollback_verify"

        if overall_exit == 0:
            replay_readiness = _data_readiness_path(
                env_name,
                candidate_release["releaseId"],
                data_ids["replayVerify"],
            )
            data_exit, data_payload = _run_data_phase(
                phases,
                phase_name=f"{target}_data_replay_apply",
                environment=env_name,
                action="replay-apply",
                argv=[
                    "python3",
                    "quwoquan_data/scripts/cli.py",
                    "ship",
                    "apply",
                    "--release-id",
                    candidate_release["releaseId"],
                    "--env",
                    env_name,
                    "--run-id",
                    data_ids["replayImport"],
                    "--import",
                    "--full-sync",
                ],
                report_path=(replay_readiness.parent.parent / data_ids["replayImport"] / "result.json"),
                data_fn=data_fn,
            )
            block["replayApply"] = data_payload
            if data_exit != 0:
                overall_exit = data_exit
                failure_category = "data_replay"

        if overall_exit == 0:
            data_exit, data_payload = _run_data_phase(
                phases,
                phase_name=f"{target}_data_replay_verify",
                environment=env_name,
                action="replay-verify",
                argv=[
                    "python3",
                    "quwoquan_data/scripts/cli.py",
                    "ship",
                    "verify",
                    "--release-id",
                    candidate_release["releaseId"],
                    "--env",
                    env_name,
                    "--import-run-id",
                    data_ids["replayImport"],
                    "--run-id",
                    data_ids["replayVerify"],
                    "--readiness-phase",
                    "commercial",
                ],
                report_path=replay_readiness,
                data_fn=data_fn,
            )
            block["replayVerify"] = data_payload
            if data_exit != 0:
                overall_exit = data_exit
                failure_category = "data_replay_verify"

        if overall_exit == 0 and execution_class == "live":
            homepage_payload = _homepage_release_evidence(
                readiness_path=replay_readiness,
                environment=env_name,
                release_id=candidate_release["releaseId"],
            )
            block["homepageReleaseEvidence"] = homepage_payload
            homepage_exit = _record_phase(
                phases,
                name=f"{target}_homepage_release_evidence",
                payload=homepage_payload,
            )
            if homepage_exit != 0:
                overall_exit = homepage_exit
                failure_category = "homepage_release_evidence"

        if overall_exit == 0:
            lifecycle_path = _lifecycle_exit_path(
                env_name,
                candidate_release["releaseId"],
                data_ids["lifecycleExit"],
            )
            data_exit, data_payload = _run_data_phase(
                phases,
                phase_name=f"{target}_data_lifecycle_exit",
                environment=env_name,
                action="lifecycle-exit",
                argv=[
                    "python3",
                    "quwoquan_data/scripts/cli.py",
                    "release",
                    "lifecycle-exit",
                    "--env",
                    env_name,
                    "--original-release-id",
                    candidate_release["releaseId"],
                    "--original-import-run-id",
                    data_ids["originalImport"],
                    "--original-verify-run-id",
                    data_ids["originalVerify"],
                    "--rollback-to-release-id",
                    rollback_release["releaseId"],
                    "--rollback-run-id",
                    data_ids["rollbackImport"],
                    "--rollback-verify-run-id",
                    data_ids["rollbackVerify"],
                    "--replay-import-run-id",
                    data_ids["replayImport"],
                    "--replay-verify-run-id",
                    data_ids["replayVerify"],
                    "--run-id",
                    data_ids["lifecycleExit"],
                ],
                report_path=lifecycle_path,
                data_fn=data_fn,
            )
            block["lifecycleExit"] = data_payload
            if data_exit != 0:
                overall_exit = data_exit
                failure_category = "data_lifecycle_exit"

        if overall_exit == 0:
            integration_payload = _invoke_env(
                verify_fn,
                _namespace(
                    command="verify",
                    kind="all",
                    env=env_name,
                    target=target,
                    profile="integration",
                    service="",
                    output_format="json",
                    report_dir="",
                    backup_recovery_receipt="",
                    data_release_id=candidate_release["releaseId"],
                    data_verify_run_id=data_ids["replayVerify"],
                    data_manifest_digest=candidate_release["releaseDigest"],
                    nonprod_data_evidence=str(evidence_by_target.get(target) or ""),
                    data_lifecycle_exit_ref=_evidence_path(lifecycle_path),
                    distribution_root="",
                    verify_hosted=False,
                ),
                action=f"{target} full integration verify",
            )
            block["verify"] = integration_payload
            integration_exit = _record_phase(
                phases,
                name=f"{target}_full_integration_verify",
                payload=integration_payload,
            )
            if integration_exit != 0:
                overall_exit = integration_exit
                failure_category = "integration_verify"

        lease_id = f"{matrix_run_id}-{env_name}-device-uat"
        lease_acquire_event: dict[str, Any] | None = None
        if overall_exit == 0:
            lease_exit, lease_payload = _run_data_phase(
                phases,
                phase_name=f"{target}_acceptance_lease_acquire",
                environment=env_name,
                action="acceptance-lease-acquire",
                argv=[
                    "python3",
                    "quwoquan_data/scripts/cli.py",
                    "release",
                    "acceptance-lease",
                    "acquire",
                    "--env",
                    env_name,
                    "--release-id",
                    candidate_release["releaseId"],
                    "--lease-id",
                    lease_id,
                    "--import-run-id",
                    data_ids["replayImport"],
                    "--verify-run-id",
                    data_ids["replayVerify"],
                ],
                report_path=lifecycle_path.parent / "acceptance-lease-acquire.json",
                data_fn=data_fn,
            )
            block["acceptanceLeaseAcquire"] = lease_payload
            if lease_exit != 0:
                overall_exit = lease_exit
                failure_category = "acceptance_lease_acquire"
            else:
                try:
                    lease_acquire_event = _acceptance_lease_event(
                        lease_payload,
                        action="acquire",
                        environment=env_name,
                        release_id=candidate_release["releaseId"],
                        lease_id=lease_id,
                    )
                except ValueError as exc:
                    overall_exit = 2
                    failure_category = "acceptance_lease_acquire"
                    phases.append(
                        PhaseTimer(f"{target}_acceptance_lease_identity").finish(
                            status="gate_block",
                            details=[str(exc)],
                        )
                    )

        if lease_acquire_event is not None and execution_class == "live":
            for key, platform, device_id in _device_uat_bindings(
                device_profile=device_profile,
                ios_simulator_device=ios_simulator_device,
                android_emulator_device=android_emulator_device,
                android_physical_device=android_physical_device,
            ):
                uat_payload = _invoke_env(
                    app_uat_fn,
                    _namespace(
                        command="app-content-uat",
                        targets=target,
                        platform=platform,
                        device_id=device_id,
                        dry_run=False,
                        output_format="json",
                        report_dir=str(
                            matrix_dir / target / "device-uat" / key
                        ),
                    ),
                    action=f"{target} {key}",
                )
                block[key] = uat_payload
                uat_exit = _record_phase(
                    phases,
                    name=f"{target}_{key}",
                    payload=uat_payload,
                )
                if uat_exit != 0:
                    if overall_exit == 0:
                        overall_exit = uat_exit
                        failure_category = "device_uat"
                    break

            telemetry_after = _invoke_env(
                telemetry_fn,
                _namespace(
                    command="product-telemetry-log-sink",
                    target=target,
                    action="all",
                    output_format="json",
                    report_dir=str(matrix_dir / target / "telemetry-after"),
                ),
                action=f"{target} Elasticsearch telemetry readback",
            )
            block["telemetryAfter"] = telemetry_after
            telemetry_after_exit = _record_phase(
                phases,
                name=f"{target}_elasticsearch_telemetry_after",
                payload=telemetry_after,
            )
            if telemetry_after_exit != 0 and overall_exit == 0:
                overall_exit = telemetry_after_exit
                failure_category = "elasticsearch_readback"

        if lease_acquire_event is not None:
            revoke_exit, revoke_payload = _run_data_phase(
                phases,
                phase_name=f"{target}_acceptance_lease_revoke",
                environment=env_name,
                action="acceptance-lease-revoke",
                argv=[
                    "python3",
                    "quwoquan_data/scripts/cli.py",
                    "release",
                    "acceptance-lease",
                    "revoke",
                    "--env",
                    env_name,
                    "--release-id",
                    candidate_release["releaseId"],
                    "--lease-id",
                    lease_id,
                    "--acquire-event-ref",
                    str(lease_acquire_event["eventRef"]),
                ],
                report_path=lifecycle_path.parent / "acceptance-lease-revoke.json",
                data_fn=data_fn,
            )
            block["acceptanceLeaseRevoke"] = revoke_payload
            if revoke_exit == 0:
                try:
                    _acceptance_lease_event(
                        revoke_payload,
                        action="revoke",
                        environment=env_name,
                        release_id=candidate_release["releaseId"],
                        lease_id=lease_id,
                    )
                except ValueError as exc:
                    revoke_exit = 2
                    phases.append(
                        PhaseTimer(f"{target}_acceptance_lease_revoke_identity").finish(
                            status="gate_block",
                            details=[str(exc)],
                        )
                    )
            if revoke_exit != 0:
                overall_exit = revoke_exit
                failure_category = "acceptance_lease_revoke"

        down_payload = _down_target(target, down_fn=down_fn)
        block["down"] = down_payload
        down_exit = _record_phase(
            phases,
            name=f"{target}_down",
            payload=down_payload,
        )
        if down_exit != 0:
            overall_exit = down_exit
            failure_category = "down"

        environments[target] = block
        if overall_exit != 0:
            break

    if overall_exit == 0 and execution_class == "live":
        evidence_errors = _live_matrix_evidence_errors(
            environments,
            baseline_id=matrix_baseline_id,
            device_profile=device_profile,
        )
        phases.append(
            PhaseTimer("live_matrix_evidence_identity").finish(
                status="gate_block" if evidence_errors else "passed",
                details=evidence_errors or ["all live evidence identities are report-bound"],
            )
        )
        if evidence_errors:
            overall_exit = 2
            failure_category = "evidence_identity"

    wall_seconds = time.monotonic() - wall_started
    if wall_seconds > int(budgets["hardBudgetSeconds"]) and overall_exit == 0:
        overall_exit = 2
        failure_category = "budget"
    return _write_matrix_result(
        matrix_dir=matrix_dir,
        phases=phases,
        environments=environments,
        budgets=budgets,
        wall_seconds=wall_seconds,
        exit_code=overall_exit,
        failure_category=failure_category,
        baseline_id=matrix_baseline_id,
        release=candidate_release,
        matrix_run_id=matrix_run_id,
        execution_class=execution_class,
        device_profile=device_profile,
    )


def run_local_env_gate_matrix(
    *,
    package_fn: EnvRunner,
    up_fn: EnvRunner,
    health_fn: EnvRunner,
    verify_fn: EnvRunner,
    down_fn: EnvRunner,
    telemetry_fn: EnvRunner | None = None,
    provider_fn: EnvRunner | None = None,
    app_uat_fn: EnvRunner | None = None,
    filter_catalog_fn: EnvRunner | None = None,
    targets: tuple[str, ...] = CANONICAL_TARGETS,
    include_l0: bool = True,
    release_attestation: str = "",
    rollback_release_attestation: str = "",
    nonprod_data_evidence: dict[str, str] | None = None,
    ios_simulator_device: str = "",
    android_emulator_device: str = "",
    android_physical_device: str = "",
    device_profile: str = DEVICE_PROFILE_FULL,
    data_fn: DataRunner = _data_cli_runner,
    execution_class: str = "live",
) -> dict[str, Any]:
    """Run the matrix under a process-bound lease for live execution only."""
    if execution_class not in {"live", "contract-simulation"}:
        raise ValueError("execution_class must be live or contract-simulation")
    matrix_run_id = _new_matrix_run_id()
    kwargs = {
        "package_fn": package_fn,
        "up_fn": up_fn,
        "health_fn": health_fn,
        "verify_fn": verify_fn,
        "down_fn": down_fn,
        "telemetry_fn": telemetry_fn,
        "provider_fn": provider_fn,
        "app_uat_fn": app_uat_fn,
        "filter_catalog_fn": filter_catalog_fn,
        "targets": targets,
        "include_l0": include_l0,
        "release_attestation": release_attestation,
        "rollback_release_attestation": rollback_release_attestation,
        "nonprod_data_evidence": nonprod_data_evidence,
        "ios_simulator_device": ios_simulator_device,
        "android_emulator_device": android_emulator_device,
        "android_physical_device": android_physical_device,
        "device_profile": device_profile,
        "data_fn": data_fn,
        "execution_class": execution_class,
        "matrix_run_id": matrix_run_id,
    }
    if execution_class == "contract-simulation":
        return _run_local_env_gate_matrix(**kwargs)
    try:
        with _matrix_execution_lease(matrix_run_id):
            return _run_local_env_gate_matrix(**kwargs)
    except MatrixExecutionLeaseBusy as exc:
        return {
            "exitCode": 2,
            "summary": "stackctl live matrix execution lease is GATE_BLOCK",
            "details": [str(exc)],
            "claim": "GATE_BLOCK",
            "status": "gate_block",
            "executed": 0,
            "skipped": 0,
            "matrixRunId": matrix_run_id,
            "executionClass": execution_class,
        }
