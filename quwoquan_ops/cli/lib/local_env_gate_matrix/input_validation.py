"""矩阵发布、测试数据、Provider 与设备输入的无副作用解析校验。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib import external_provider_governance, provider_conformance
from quwoquan_ops.cli.lib.local_env_gate_matrix.identity import (
    CANONICAL_TARGETS,
    ROOT,
    EnvRunner,
)
from quwoquan_ops.cli.lib.local_env_gate_matrix.preflight import (
    _device_binding_errors,
    _release_binding,
)


class ResearchLifecycleUnsupported(ValueError):
    """Retained import name for callers; Research is now a supported branch."""


@dataclass(frozen=True)
class MatrixInputBindings:
    """校验完成后供状态机消费的规范化输入。"""

    candidate_release: dict[str, Any]
    rollback_release: dict[str, Any]
    request_by_target: dict[str, str]
    evidence_by_target: dict[str, str]
    handoff_by_target: dict[str, str]
    compiled_provider_governance: dict[str, Any]


def _resolve_matrix_inputs(
    *,
    release_attestation: str,
    rollback_release_attestation: str,
    test_data_request: dict[str, str] | None,
    test_data_evidence: dict[str, str] | None,
    test_data_handoff: dict[str, str] | None,
    telemetry_fn: EnvRunner | None,
    provider_fn: EnvRunner | None,
    app_uat_fn: EnvRunner | None,
    ios_simulator_device: str,
    android_emulator_device: str,
    android_physical_device: str,
    ios_physical_device: str = "",
    device_profile: str,
    execution_class: str,
) -> MatrixInputBindings:
    """在任何 package/runtime 变更前解析并校验矩阵全部外部输入。"""

    candidate_release = _release_binding(release_attestation, label="candidate")
    rollback_release = _release_binding(
        rollback_release_attestation,
        label="rollback",
    )
    if candidate_release["releaseId"] == rollback_release["releaseId"]:
        raise ValueError("candidate and rollback release must be different")

    # Research and commercial are explicit release metadata branches.  The
    # matrix must not reject either class or infer it from an environment; the
    # downstream lifecycle phases consume the two exact attestation identities.
    candidate_class = str(candidate_release["releaseClass"])
    rollback_class = str(rollback_release["releaseClass"])
    if candidate_class not in {"research", "commercial"} or rollback_class not in {"research", "commercial"}:
        raise ValueError("matrix release lifecycle branch is unknown")


    request_by_target = dict(test_data_request or {})
    evidence_by_target = dict(test_data_evidence or {})
    handoff_by_target = dict(test_data_handoff or {})
    compiled_provider_governance: dict[str, Any] = {}
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
        if set(request_by_target) != set(CANONICAL_TARGETS):
            raise ValueError(
                "live matrix requires one --test-data-request for every target"
            )
        if set(handoff_by_target) != set(CANONICAL_TARGETS):
            raise ValueError(
                "live matrix requires one --test-data-handoff for every target"
            )
        for target, raw_path in sorted(request_by_target.items()):
            request_path = Path(str(raw_path or "").strip()).expanduser()
            if not request_path.is_absolute():
                request_path = ROOT / request_path
            if not request_path.is_file():
                raise ValueError(f"{target} test-data request is unavailable")
        for target, raw_path in sorted(evidence_by_target.items()):
            if target not in CANONICAL_TARGETS:
                raise ValueError(f"unknown test-data evidence target: {target}")
            evidence_path = Path(str(raw_path or "").strip()).expanduser()
            if not evidence_path.is_absolute():
                evidence_path = ROOT / evidence_path
            if not evidence_path.is_file():
                raise ValueError(f"{target} test-data evidence is unavailable")
        for target, raw_path in sorted(handoff_by_target.items()):
            handoff_path = Path(str(raw_path or "").strip()).expanduser()
            if not handoff_path.is_absolute():
                handoff_path = ROOT / handoff_path
            if not handoff_path.is_file():
                raise ValueError(f"{target} test-data handoff is unavailable")
        if telemetry_fn is None or provider_fn is None or app_uat_fn is None:
            raise ValueError(
                "live matrix requires telemetry, Provider, and App UAT runners"
            )
        device_errors = _device_binding_errors(
            device_profile=device_profile,
            ios_simulator_device=ios_simulator_device,
            android_emulator_device=android_emulator_device,
            android_physical_device=android_physical_device,
            ios_physical_device=ios_physical_device,
        )
        if device_errors:
            raise ValueError("; ".join(device_errors))

    return MatrixInputBindings(
        candidate_release=candidate_release,
        rollback_release=rollback_release,
        request_by_target=request_by_target,
        evidence_by_target=evidence_by_target,
        handoff_by_target=handoff_by_target,
        compiled_provider_governance=compiled_provider_governance,
    )
