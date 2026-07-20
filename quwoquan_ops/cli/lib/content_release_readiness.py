"""Typed, phase-scoped readiness policy for content releases.

The policy intentionally names logical capabilities and topology targets only.
URLs, ports, credentials, legal facts and deployment configuration remain in
their existing source-owned contracts.  Receipts are derived run evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping

from .common import ROOT, load_json_yaml
from .environment_topology import ENVIRONMENTS, get_target, load_environment_topology


POLICY_PATH = ROOT / "quwoquan_ops" / "environments" / "content_release_readiness.yaml"
POLICY_SCHEMA = "content-release-readiness"


class ReadinessPhase(StrEnum):
    IMPORT = "import"
    CONSUMER = "consumer"
    COMMERCIAL = "commercial"


class VerificationProfile(StrEnum):
    """The only execution contracts for repository and environment verification."""

    BASELINE = "baseline"
    SMOKE = "smoke"
    INTEGRATION = "integration"
    RELEASE = "release"

    @property
    def requires_environment(self) -> bool:
        return self is not VerificationProfile.BASELINE

    @property
    def readiness_phase(self) -> ReadinessPhase | None:
        if self is VerificationProfile.INTEGRATION:
            return ReadinessPhase.IMPORT
        if self is VerificationProfile.RELEASE:
            return ReadinessPhase.COMMERCIAL
        return None


class ReadinessCapability(StrEnum):
    CONTENT_API = "content_api"
    CONTENT_MEDIA = "content_media"
    CONTENT_SERVICES = "content_services"
    APP_CONSUMER = "app_consumer"
    TELEMETRY_SLS = "telemetry_sls"
    TRACE_QUERY = "trace_query"
    SLO_QUERY = "slo_query"
    LEGAL_APPROVAL = "legal_approval"


class ProbeOutcome(StrEnum):
    PASS = "PASS"
    GATE_BLOCK = "GATE_BLOCK"
    FAIL = "FAIL"


class ProbeSource(StrEnum):
    """Where a capability's mandatory probe evidence comes from."""

    HEALTH_SCOPE = "healthScope"
    COMMERCIAL_DOCTOR = "doctor"


@dataclass(frozen=True, slots=True)
class CapabilityProbeBinding:
    capability: ReadinessCapability
    source: ProbeSource
    health_scope: str | None


@dataclass(frozen=True, slots=True)
class ReadinessRequirement:
    phase: ReadinessPhase
    environment: str
    target: str
    workload: str
    health_scope: str
    capabilities: tuple[ReadinessCapability, ...]


@dataclass(frozen=True, slots=True)
class ContentReleaseReadinessPolicy:
    policy_id: str
    requirements: tuple[ReadinessRequirement, ...]
    probe_bindings: Mapping[ReadinessCapability, CapabilityProbeBinding]

    def requirement_for(
        self,
        *,
        phase: ReadinessPhase,
        environment: str,
    ) -> ReadinessRequirement:
        for requirement in self.requirements:
            if requirement.phase is phase and requirement.environment == environment:
                return requirement
        raise ValueError(
            f"content readiness policy does not define {phase.value} for {environment}"
        )

    def probe_binding_for(self, capability: ReadinessCapability) -> CapabilityProbeBinding:
        binding = self.probe_bindings.get(capability)
        if binding is None:
            raise ValueError(
                f"content readiness policy does not bind a probe for {capability.value}"
            )
        return binding


@dataclass(frozen=True, slots=True)
class ShipReadinessReceipt:
    policy_id: str
    phase: ReadinessPhase
    environment: str
    target: str
    workload: str
    outcome: ProbeOutcome
    capabilities: tuple[ReadinessCapability, ...]
    probes: tuple[str, ...]
    report_dir: str


def _mapping(value: object, *, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _parse_probe_bindings(
    payload: Mapping[str, object],
) -> dict[ReadinessCapability, CapabilityProbeBinding]:
    raw_bindings = _mapping(
        payload.get("capabilityProbes"),
        label="content readiness policy capabilityProbes",
    )
    bindings: dict[ReadinessCapability, CapabilityProbeBinding] = {}
    for raw_capability, raw_binding in raw_bindings.items():
        try:
            capability = ReadinessCapability(_text(raw_capability, label="capabilityProbes key"))
        except ValueError as exc:
            raise ValueError(f"capabilityProbes has unknown capability {raw_capability!r}") from exc
        binding = _mapping(raw_binding, label=f"capabilityProbes.{capability.value}")
        health_scope = binding.get("healthScope")
        doctor = binding.get("doctor")
        if isinstance(health_scope, str) and health_scope.strip() and doctor is None:
            bindings[capability] = CapabilityProbeBinding(
                capability=capability,
                source=ProbeSource.HEALTH_SCOPE,
                health_scope=health_scope.strip(),
            )
        elif doctor is True and health_scope is None:
            bindings[capability] = CapabilityProbeBinding(
                capability=capability,
                source=ProbeSource.COMMERCIAL_DOCTOR,
                health_scope=None,
            )
        else:
            raise ValueError(
                f"capabilityProbes.{capability.value} must declare exactly one of "
                "healthScope: <scope> or doctor: true"
            )
    missing = [capability.value for capability in ReadinessCapability if capability not in bindings]
    if missing:
        raise ValueError(f"capabilityProbes must bind every capability; missing: {missing}")
    return bindings


def load_content_release_readiness_policy(
    *,
    policy_path: Path = POLICY_PATH,
) -> ContentReleaseReadinessPolicy:
    payload = _mapping(load_json_yaml(policy_path), label="content readiness policy")
    if payload.get("schema") != POLICY_SCHEMA:
        raise ValueError(f"content readiness policy schema must be {POLICY_SCHEMA}")
    policy_id = _text(payload.get("policyId"), label="content readiness policy policyId")
    probe_bindings = _parse_probe_bindings(payload)
    raw_phases = _mapping(payload.get("phases"), label="content readiness policy phases")
    topology = load_environment_topology()
    requirements: list[ReadinessRequirement] = []
    seen: set[tuple[ReadinessPhase, str]] = set()
    for phase in ReadinessPhase:
        raw_phase = _mapping(raw_phases.get(phase.value), label=f"phase {phase.value}")
        for environment, raw_requirement in raw_phase.items():
            if environment not in ENVIRONMENTS:
                raise ValueError(f"phase {phase.value} has invalid environment {environment!r}")
            requirement = _mapping(raw_requirement, label=f"phase {phase.value}/{environment}")
            target_name = _text(requirement.get("target"), label=f"{phase.value}/{environment}.target")
            target = get_target(topology, target_name)
            if target.get("env") != environment:
                raise ValueError(f"{phase.value}/{environment} target must belong to {environment}")
            workload = _text(requirement.get("workload"), label=f"{phase.value}/{environment}.workload")
            if workload not in {"content-release", "full"}:
                raise ValueError(f"{phase.value}/{environment}.workload is invalid")
            health_scope = _text(requirement.get("healthScope"), label=f"{phase.value}/{environment}.healthScope")
            raw_capabilities = requirement.get("capabilities")
            if not isinstance(raw_capabilities, list) or not raw_capabilities:
                raise ValueError(f"{phase.value}/{environment}.capabilities must be non-empty")
            try:
                capabilities = tuple(ReadinessCapability(_text(item, label="capability")) for item in raw_capabilities)
            except ValueError as exc:
                raise ValueError(f"{phase.value}/{environment} has invalid capability") from exc
            for capability in capabilities:
                binding = probe_bindings[capability]
                if (
                    binding.source is ProbeSource.COMMERCIAL_DOCTOR
                    and phase is not ReadinessPhase.COMMERCIAL
                ):
                    raise ValueError(
                        f"{phase.value}/{environment} requires {capability.value}, "
                        "but doctor-bound capabilities are commercial-only"
                    )
            key = (phase, environment)
            if key in seen:
                raise ValueError(f"duplicate content readiness requirement {phase.value}/{environment}")
            seen.add(key)
            requirements.append(
                ReadinessRequirement(
                    phase=phase,
                    environment=environment,
                    target=target_name,
                    workload=workload,
                    health_scope=health_scope,
                    capabilities=capabilities,
                )
            )
    return ContentReleaseReadinessPolicy(
        policy_id=policy_id,
        requirements=tuple(requirements),
        probe_bindings=probe_bindings,
    )


__all__ = [
    "CapabilityProbeBinding",
    "ContentReleaseReadinessPolicy",
    "POLICY_PATH",
    "ProbeOutcome",
    "ProbeSource",
    "ReadinessCapability",
    "ReadinessPhase",
    "ReadinessRequirement",
    "ShipReadinessReceipt",
    "VerificationProfile",
    "load_content_release_readiness_policy",
]
