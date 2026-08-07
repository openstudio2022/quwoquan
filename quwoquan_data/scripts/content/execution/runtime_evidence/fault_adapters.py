"""Governed callback adapters for non-process runtime evidence faults.

Data does not own Redis, Mongo, or semantic-provider process lifecycle.  This
module therefore deliberately has no subprocess, shell, endpoint, or
environment-variable surface.  An environment/runtime owner must provide a
typed in-process callback whose frozen binding is included in the evidence
session.  A callback invocation is accepted only when it returns a bound,
digest-verified evidence file; absence of such a callback is a typed blocker,
never a successful no-op.

Provider timeout/rate-limit hooks additionally bind an attestation digest.  The
runtime evidence injector still validates the full, current attestation before
calling these adapters, so constructing an adapter cannot bypass that gate.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from content.execution.runtime_evidence.contract import (
    FaultProviderBinding,
    RuntimeEvidenceError,
    canonical_digest,
    file_digest,
)
from content.execution.runtime_evidence.faults import (
    FaultActionResult,
    FaultActionTarget,
)

PROTECTED_OPERATION_FAULTS = frozenset(
    {"lease_expiry", "redis_restart", "mongo_reconnect"}
)
PROVIDER_TEST_HOOK_FAULTS = frozenset(
    {"provider_timeout", "provider_rate_limit"}
)
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_RESULT_CODES = {
    "lease_expiry": "DATA.RUNTIME_EVIDENCE.LEASE_EXPIRY_REQUESTED",
    "redis_restart": "DATA.RUNTIME_EVIDENCE.REDIS_RESTART_REQUESTED",
    "mongo_reconnect": "DATA.RUNTIME_EVIDENCE.MONGO_RECONNECT_REQUESTED",
    "provider_timeout": "DATA.RUNTIME_EVIDENCE.PROVIDER_TIMEOUT_ARMED",
    "provider_rate_limit": "DATA.RUNTIME_EVIDENCE.PROVIDER_RATE_LIMIT_ARMED",
}
_UNAVAILABLE_BLOCKERS = {
    "lease_expiry": "DATA.RUNTIME_EVIDENCE.PROTECTED_OPERATION_CALLBACK_REQUIRED",
    "redis_restart": "DATA.RUNTIME_EVIDENCE.PROTECTED_OPERATION_CALLBACK_REQUIRED",
    "mongo_reconnect": "DATA.RUNTIME_EVIDENCE.PROTECTED_OPERATION_CALLBACK_REQUIRED",
    "provider_timeout": "DATA.RUNTIME_EVIDENCE.PROVIDER_TEST_HOOK_ATTESTATION_REQUIRED",
    "provider_rate_limit": "DATA.RUNTIME_EVIDENCE.PROVIDER_TEST_HOOK_ATTESTATION_REQUIRED",
}


class FaultAdapterBlocker(RuntimeEvidenceError):
    """Typed fail-closed blocker for unavailable or drifting fault controls."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class GovernedFaultCallbackBinding:
    """Identity supplied by the runtime owner, without transport selectors."""

    fault_type: str
    provider_id: str
    configuration_digest: str

    def __post_init__(self) -> None:
        # Reuse the canonical fault-provider validation boundary.
        FaultProviderBinding(
            fault_type=self.fault_type,
            provider_id=self.provider_id,
            configuration_digest=self.configuration_digest,
        )

    def as_document(self) -> dict[str, str]:
        return {
            "faultType": self.fault_type,
            "providerId": self.provider_id,
            "configurationDigest": self.configuration_digest,
        }


@dataclass(frozen=True, slots=True)
class GovernedFaultInvocation:
    """Exact job-scoped request passed to one protected callback."""

    fault_type: str
    carrier: str
    execution_id: str
    job_id: str
    requested_at: str
    root_execution_id: str
    run_id: str
    generation: int
    fencing_token: str
    request_digest: str
    callback_binding: GovernedFaultCallbackBinding
    test_hook_attestation_digest: str | None
    invocation_digest: str

    @classmethod
    def from_target(
        cls,
        target: FaultActionTarget,
        *,
        callback_binding: GovernedFaultCallbackBinding,
        test_hook_attestation_digest: str | None,
    ) -> GovernedFaultInvocation:
        identity = target.identity
        if identity is None or _DIGEST.fullmatch(str(target.request_digest or "")) is None:
            raise FaultAdapterBlocker(
                "DATA.RUNTIME_EVIDENCE.FAULT_REQUEST_IDENTITY_REQUIRED",
                target.fault_type,
            )
        stable: dict[str, object] = {
            "schema": "quwoquan_data.governed_runtime_fault_invocation",
            "faultType": target.fault_type,
            "carrier": target.carrier,
            "executionId": target.execution_id,
            "jobId": target.job_id,
            "requestedAt": target.requested_at,
            **identity.as_document(),
            "requestDigest": target.request_digest,
            "callbackBinding": callback_binding.as_document(),
            "testHookAttestationDigest": test_hook_attestation_digest,
        }
        return cls(
            fault_type=target.fault_type,
            carrier=target.carrier,
            execution_id=target.execution_id,
            job_id=target.job_id,
            requested_at=target.requested_at,
            root_execution_id=identity.root_execution_id,
            run_id=identity.run_id,
            generation=identity.generation,
            fencing_token=identity.fencing_token,
            request_digest=str(target.request_digest),
            callback_binding=callback_binding,
            test_hook_attestation_digest=test_hook_attestation_digest,
            invocation_digest=canonical_digest(stable),
        )


@dataclass(frozen=True, slots=True)
class GovernedFaultProof:
    """Proof returned by the protected callback after it requested the fault."""

    invocation_digest: str
    callback_binding: GovernedFaultCallbackBinding
    result_code: str
    triggered_at: str
    evidence_path: Path
    evidence_sha256: str


class GovernedFaultCallback(Protocol):
    """Runtime-owner port; implementations live at the protected boundary."""

    @property
    def binding(self) -> GovernedFaultCallbackBinding:
        """Return the immutable callback configuration identity."""

    def invoke(self, invocation: GovernedFaultInvocation) -> GovernedFaultProof:
        """Request one typed fault and return its immutable provider proof."""


def _require_digest(value: str | None, *, blocker_code: str) -> str:
    digest = str(value or "").strip()
    if _DIGEST.fullmatch(digest) is None:
        raise FaultAdapterBlocker(blocker_code, "a sha256 attestation is required")
    return digest


def _adapter_binding(
    callback: GovernedFaultCallback,
    *,
    fault_type: str,
    attestation_digest: str | None,
) -> FaultProviderBinding:
    callback_binding = callback.binding
    if callback_binding.fault_type != fault_type:
        raise FaultAdapterBlocker(
            "DATA.RUNTIME_EVIDENCE.FAULT_CALLBACK_TYPE_MISMATCH",
            f"callback={callback_binding.fault_type} requested={fault_type}",
        )
    configuration_digest = canonical_digest(
        {
            "schema": "quwoquan_data.runtime_fault_callback_adapter",
            "version": 1,
            "faultType": fault_type,
            "callbackBinding": callback_binding.as_document(),
            "testHookAttestationDigest": attestation_digest,
        }
    )
    return FaultProviderBinding(
        fault_type=fault_type,
        provider_id=callback_binding.provider_id,
        configuration_digest=configuration_digest,
    )


class _GovernedCallbackAdapter:
    def __init__(
        self,
        *,
        fault_type: str,
        callback: GovernedFaultCallback,
        test_hook_attestation_digest: str | None,
    ) -> None:
        self._fault_type = fault_type
        self._callback = callback
        self._callback_binding = callback.binding
        self._attestation_digest = test_hook_attestation_digest
        self._binding = _adapter_binding(
            callback,
            fault_type=fault_type,
            attestation_digest=test_hook_attestation_digest,
        )

    @property
    def binding(self) -> FaultProviderBinding:
        return self._binding

    def trigger(self, target: FaultActionTarget) -> FaultActionResult:
        if target.fault_type != self._fault_type:
            raise FaultAdapterBlocker(
                "DATA.RUNTIME_EVIDENCE.FAULT_TARGET_TYPE_MISMATCH",
                f"adapter={self._fault_type} target={target.fault_type}",
            )
        if self._callback.binding != self._callback_binding:
            raise FaultAdapterBlocker(
                "DATA.RUNTIME_EVIDENCE.FAULT_CALLBACK_BINDING_DRIFT",
                self._fault_type,
            )
        invocation = GovernedFaultInvocation.from_target(
            target,
            callback_binding=self._callback_binding,
            test_hook_attestation_digest=self._attestation_digest,
        )
        proof = self._callback.invoke(invocation)
        expected_code = _RESULT_CODES[self._fault_type]
        if (
            not isinstance(proof, GovernedFaultProof)
            or proof.invocation_digest != invocation.invocation_digest
            or proof.callback_binding != self._callback_binding
            or proof.result_code != expected_code
        ):
            raise FaultAdapterBlocker(
                "DATA.RUNTIME_EVIDENCE.FAULT_CALLBACK_PROOF_MISMATCH",
                self._fault_type,
            )
        try:
            observed_digest = file_digest(proof.evidence_path)
        except RuntimeEvidenceError as exc:
            raise FaultAdapterBlocker(
                "DATA.RUNTIME_EVIDENCE.FAULT_CALLBACK_EVIDENCE_INVALID",
                self._fault_type,
            ) from exc
        if observed_digest != proof.evidence_sha256:
            raise FaultAdapterBlocker(
                "DATA.RUNTIME_EVIDENCE.FAULT_CALLBACK_EVIDENCE_DRIFT",
                self._fault_type,
            )
        return FaultActionResult(
            result_code=proof.result_code,
            triggered_at=proof.triggered_at,
            provider_evidence_path=proof.evidence_path,
        )


class _UnavailableFaultAdapter:
    """Explicit non-action adapter that terminalizes unsupported fault intent."""

    def __init__(self, fault_type: str) -> None:
        if fault_type not in _UNAVAILABLE_BLOCKERS:
            raise FaultAdapterBlocker(
                "DATA.RUNTIME_EVIDENCE.UNAVAILABLE_FAULT_TYPE_INVALID",
                fault_type,
            )
        self._fault_type = fault_type
        self._blocker_code = _UNAVAILABLE_BLOCKERS[fault_type]
        self._binding = FaultProviderBinding(
            fault_type=fault_type,
            provider_id=f"unavailable_{fault_type}_v1",
            configuration_digest=canonical_digest(
                {
                    "schema": "quwoquan_data.unavailable_runtime_fault_adapter",
                    "version": 1,
                    "faultType": fault_type,
                    "blockerCode": self._blocker_code,
                }
            ),
        )

    @property
    def binding(self) -> FaultProviderBinding:
        return self._binding

    def trigger(self, target: FaultActionTarget) -> FaultActionResult:
        if target.fault_type != self._fault_type:
            raise FaultAdapterBlocker(
                "DATA.RUNTIME_EVIDENCE.FAULT_TARGET_TYPE_MISMATCH",
                f"adapter={self._fault_type} target={target.fault_type}",
            )
        raise FaultAdapterBlocker(self._blocker_code, self._fault_type)


def unavailable_fault_adapter(fault_type: str) -> _UnavailableFaultAdapter:
    """Create the canonical fail-closed adapter for an unowned fault control."""
    return _UnavailableFaultAdapter(fault_type)


def is_unavailable_fault_binding_document(value: object) -> bool:
    if not isinstance(value, dict):
        try:
            value = dict(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
    fault_type = str(value.get("faultType") or "")
    if fault_type not in _UNAVAILABLE_BLOCKERS:
        return False
    return value == unavailable_fault_adapter(fault_type).binding.as_document()


def protected_operation_fault_adapter(
    fault_type: str,
    *,
    callback: GovernedFaultCallback | None,
) -> _GovernedCallbackAdapter:
    """Bind an Ops/runtime-owned lease, Redis, or Mongo callback.

    There is intentionally no built-in local implementation: the current Data
    repository exposes no protected control-plane API for these destructive
    operations.  Missing ownership therefore remains a precise blocker.
    """
    if fault_type not in PROTECTED_OPERATION_FAULTS:
        raise FaultAdapterBlocker(
            "DATA.RUNTIME_EVIDENCE.PROTECTED_OPERATION_TYPE_INVALID",
            fault_type,
        )
    if callback is None:
        raise FaultAdapterBlocker(
            "DATA.RUNTIME_EVIDENCE.PROTECTED_OPERATION_CALLBACK_REQUIRED",
            fault_type,
        )
    return _GovernedCallbackAdapter(
        fault_type=fault_type,
        callback=callback,
        test_hook_attestation_digest=None,
    )


def provider_test_hook_fault_adapter(
    fault_type: str,
    *,
    callback: GovernedFaultCallback | None,
    test_hook_attestation_digest: str | None,
) -> _GovernedCallbackAdapter:
    """Bind an explicitly attested provider timeout or rate-limit test hook."""
    if fault_type not in PROVIDER_TEST_HOOK_FAULTS:
        raise FaultAdapterBlocker(
            "DATA.RUNTIME_EVIDENCE.PROVIDER_TEST_HOOK_TYPE_INVALID",
            fault_type,
        )
    attestation_digest = _require_digest(
        test_hook_attestation_digest,
        blocker_code="DATA.RUNTIME_EVIDENCE.PROVIDER_TEST_HOOK_ATTESTATION_REQUIRED",
    )
    if callback is None:
        raise FaultAdapterBlocker(
            "DATA.RUNTIME_EVIDENCE.PROVIDER_TEST_HOOK_CALLBACK_REQUIRED",
            fault_type,
        )
    return _GovernedCallbackAdapter(
        fault_type=fault_type,
        callback=callback,
        test_hook_attestation_digest=attestation_digest,
    )


__all__ = [
    "PROTECTED_OPERATION_FAULTS",
    "PROVIDER_TEST_HOOK_FAULTS",
    "FaultAdapterBlocker",
    "GovernedFaultCallback",
    "GovernedFaultCallbackBinding",
    "GovernedFaultInvocation",
    "GovernedFaultProof",
    "is_unavailable_fault_binding_document",
    "protected_operation_fault_adapter",
    "provider_test_hook_fault_adapter",
    "unavailable_fault_adapter",
]
