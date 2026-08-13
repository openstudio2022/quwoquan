"""Provider 本地功能面、live 矩阵证据身份与 down 收口校验（自原单文件逐字搬移）。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib import provider_conformance
from quwoquan_ops.cli.lib.deployment_candidate_manifest import (
    validate_packaged_provider_runtime,
)

from quwoquan_ops.cli.lib.local_env_gate_matrix.data_phases import _invoke_env
from quwoquan_ops.cli.lib.local_env_gate_matrix.identity import (
    CANONICAL_TARGETS,
    DEVICE_PROFILE_FULL,
    EnvRunner,
    ROOT,
    TARGET_ENVIRONMENTS,
    _ATTEMPT_ID,
    _namespace,
    _PROVIDER_CAPABILITY_ID,
    _PROVIDER_LAYERS,
    _SHA256,
)
from quwoquan_ops.cli.lib.local_env_gate_matrix.preflight import _device_uat_bindings


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
        if not _integration_verify_has_required_test_data_case(verify):
            errors.append(
                f"{target}: integration verify has no executed test-data CaseResult"
            )
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


def _integration_verify_has_required_test_data_case(value: Any) -> bool:
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
        if not isinstance(step, dict) or step.get("kind") != "test-data":
            continue
        case = step.get("caseResult")
        return (
            isinstance(case, dict)
            and case.get("status") == "passed"
            and int(case.get("executed") or 0) > 0
            and int(case.get("skipped") or 0) == 0
        )
    return False
