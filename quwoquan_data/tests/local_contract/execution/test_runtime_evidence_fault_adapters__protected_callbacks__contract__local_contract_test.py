from __future__ import annotations

import ast
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest
from content.execution.runtime_evidence_contract import (
    RuntimeEvidenceIdentity,
    canonical_digest,
    file_digest,
)
from content.execution.runtime_evidence_fault_adapters import (
    PROTECTED_OPERATION_FAULTS,
    PROVIDER_TEST_HOOK_FAULTS,
    FaultAdapterBlocker,
    GovernedFaultCallbackBinding,
    GovernedFaultInvocation,
    GovernedFaultProof,
    is_unavailable_fault_binding_document,
    protected_operation_fault_adapter,
    provider_test_hook_fault_adapter,
    unavailable_fault_adapter,
)
from content.execution.runtime_evidence_faults import FaultActionTarget

_DIGEST = "sha256:" + "a" * 64
_IDENTITY = RuntimeEvidenceIdentity(
    root_execution_id="20260805--travel-homepage--retry-001",
    run_id="runtime-fault-run-001",
    generation=3,
    fencing_token="sha256:" + "f" * 64,
)
_RESULT_CODES = {
    "lease_expiry": "DATA.RUNTIME_EVIDENCE.LEASE_EXPIRY_REQUESTED",
    "redis_restart": "DATA.RUNTIME_EVIDENCE.REDIS_RESTART_REQUESTED",
    "mongo_reconnect": "DATA.RUNTIME_EVIDENCE.MONGO_RECONNECT_REQUESTED",
    "provider_timeout": "DATA.RUNTIME_EVIDENCE.PROVIDER_TIMEOUT_ARMED",
    "provider_rate_limit": "DATA.RUNTIME_EVIDENCE.PROVIDER_RATE_LIMIT_ARMED",
}


class _ProtectedCallback:
    def __init__(self, fault_type: str, evidence_path: Path) -> None:
        self._binding = GovernedFaultCallbackBinding(
            fault_type=fault_type,
            provider_id=f"protected_{fault_type}_v1",
            configuration_digest=canonical_digest(
                {
                    "schema": "test.protected_fault_callback",
                    "faultType": fault_type,
                    "operation": f"runtime.{fault_type}",
                }
            ),
        )
        self.evidence_path = evidence_path
        self.invocations: list[GovernedFaultInvocation] = []
        self.proof_override: GovernedFaultProof | None = None

    @property
    def binding(self) -> GovernedFaultCallbackBinding:
        return self._binding

    def invoke(self, invocation: GovernedFaultInvocation) -> GovernedFaultProof:
        self.invocations.append(invocation)
        if self.proof_override is not None:
            return self.proof_override
        return GovernedFaultProof(
            invocation_digest=invocation.invocation_digest,
            callback_binding=self.binding,
            result_code=_RESULT_CODES[invocation.fault_type],
            triggered_at=datetime.now(timezone.utc).isoformat(),
            evidence_path=self.evidence_path,
            evidence_sha256=file_digest(self.evidence_path),
        )


def _target(fault_type: str) -> FaultActionTarget:
    return FaultActionTarget(
        fault_type=fault_type,
        carrier="article",
        execution_id="20260805--travel-article--retry-001",
        job_id="1234567890abcdef",
        requested_at="2026-08-05T08:00:00+00:00",
        worker_checkpoint=None,
        identity=_IDENTITY,
        request_digest="sha256:" + "b" * 64,
    )


def _proof_file(tmp_path: Path, fault_type: str) -> Path:
    path = tmp_path / f"{fault_type}.json"
    path.write_text(
        json.dumps(
            {"schema": "test.runtime_fault_proof", "faultType": fault_type},
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize("fault_type", sorted(PROTECTED_OPERATION_FAULTS))
def test_protected_operation_adapter_requires_real_bound_proof(
    tmp_path: Path, fault_type: str
) -> None:
    callback = _ProtectedCallback(fault_type, _proof_file(tmp_path, fault_type))
    adapter = protected_operation_fault_adapter(fault_type, callback=callback)

    action = adapter.trigger(_target(fault_type))

    assert action.result_code == _RESULT_CODES[fault_type]
    assert action.provider_evidence_path == callback.evidence_path
    assert adapter.binding.fault_type == fault_type
    assert adapter.binding.provider_id == callback.binding.provider_id
    assert adapter.binding.configuration_digest != callback.binding.configuration_digest
    assert callback.invocations[0].test_hook_attestation_digest is None
    assert callback.invocations[0].execution_id == _target(fault_type).execution_id
    assert callback.invocations[0].job_id == _target(fault_type).job_id
    assert callback.invocations[0].root_execution_id == _IDENTITY.root_execution_id
    assert callback.invocations[0].run_id == _IDENTITY.run_id
    assert callback.invocations[0].generation == _IDENTITY.generation
    assert callback.invocations[0].fencing_token == _IDENTITY.fencing_token
    assert callback.invocations[0].request_digest == "sha256:" + "b" * 64


@pytest.mark.parametrize("fault_type", sorted(PROVIDER_TEST_HOOK_FAULTS))
def test_provider_adapter_binds_attestation_and_exact_test_hook(
    tmp_path: Path, fault_type: str
) -> None:
    callback = _ProtectedCallback(fault_type, _proof_file(tmp_path, fault_type))
    adapter = provider_test_hook_fault_adapter(
        fault_type,
        callback=callback,
        test_hook_attestation_digest=_DIGEST,
    )

    action = adapter.trigger(_target(fault_type))

    assert action.result_code == _RESULT_CODES[fault_type]
    assert callback.invocations[0].test_hook_attestation_digest == _DIGEST
    assert adapter.binding.configuration_digest == canonical_digest(
        {
            "schema": "quwoquan_data.runtime_fault_callback_adapter",
            "version": 1,
            "faultType": fault_type,
            "callbackBinding": callback.binding.as_document(),
            "testHookAttestationDigest": _DIGEST,
        }
    )


@pytest.mark.parametrize("fault_type", sorted(PROTECTED_OPERATION_FAULTS))
def test_missing_protected_callback_is_typed_blocker(fault_type: str) -> None:
    with pytest.raises(FaultAdapterBlocker) as captured:
        protected_operation_fault_adapter(fault_type, callback=None)
    assert captured.value.code == (
        "DATA.RUNTIME_EVIDENCE.PROTECTED_OPERATION_CALLBACK_REQUIRED"
    )


@pytest.mark.parametrize("fault_type", sorted(PROVIDER_TEST_HOOK_FAULTS))
def test_provider_hook_cannot_bypass_attestation(fault_type: str) -> None:
    with pytest.raises(FaultAdapterBlocker) as captured:
        provider_test_hook_fault_adapter(
            fault_type,
            callback=None,
            test_hook_attestation_digest=None,
        )
    assert captured.value.code == (
        "DATA.RUNTIME_EVIDENCE.PROVIDER_TEST_HOOK_ATTESTATION_REQUIRED"
    )


def test_callback_drift_and_noop_proof_fail_closed(tmp_path: Path) -> None:
    fault_type = "redis_restart"
    callback = _ProtectedCallback(fault_type, _proof_file(tmp_path, fault_type))
    adapter = protected_operation_fault_adapter(fault_type, callback=callback)
    invocation = GovernedFaultInvocation.from_target(
        _target(fault_type),
        callback_binding=callback.binding,
        test_hook_attestation_digest=None,
    )
    callback.proof_override = GovernedFaultProof(
        invocation_digest=invocation.invocation_digest,
        callback_binding=callback.binding,
        result_code=_RESULT_CODES[fault_type],
        triggered_at="2026-08-05T08:00:01+00:00",
        evidence_path=callback.evidence_path,
        evidence_sha256="sha256:" + "0" * 64,
    )

    with pytest.raises(FaultAdapterBlocker) as captured:
        adapter.trigger(_target(fault_type))
    assert captured.value.code == "DATA.RUNTIME_EVIDENCE.FAULT_CALLBACK_EVIDENCE_DRIFT"

    callback.proof_override = replace(
        callback.proof_override,
        invocation_digest="sha256:" + "1" * 64,
        evidence_sha256=file_digest(callback.evidence_path),
    )
    with pytest.raises(FaultAdapterBlocker) as captured:
        adapter.trigger(_target(fault_type))
    assert captured.value.code == "DATA.RUNTIME_EVIDENCE.FAULT_CALLBACK_PROOF_MISMATCH"


def test_callback_invocation_cannot_replay_across_generation_or_request() -> None:
    callback_binding = GovernedFaultCallbackBinding(
        fault_type="lease_expiry",
        provider_id="protected_lease_expiry_v1",
        configuration_digest=_DIGEST,
    )
    first = GovernedFaultInvocation.from_target(
        _target("lease_expiry"),
        callback_binding=callback_binding,
        test_hook_attestation_digest=None,
    )
    next_generation = GovernedFaultInvocation.from_target(
        replace(
            _target("lease_expiry"),
            identity=replace(_IDENTITY, generation=_IDENTITY.generation + 1),
        ),
        callback_binding=callback_binding,
        test_hook_attestation_digest=None,
    )
    next_request = GovernedFaultInvocation.from_target(
        replace(_target("lease_expiry"), request_digest="sha256:" + "c" * 64),
        callback_binding=callback_binding,
        test_hook_attestation_digest=None,
    )

    assert len(
        {
            first.invocation_digest,
            next_generation.invocation_digest,
            next_request.invocation_digest,
        }
    ) == 3


def test_callback_invocation_requires_outer_request_identity() -> None:
    callback_binding = GovernedFaultCallbackBinding(
        fault_type="lease_expiry",
        provider_id="protected_lease_expiry_v1",
        configuration_digest=_DIGEST,
    )
    with pytest.raises(FaultAdapterBlocker) as captured:
        GovernedFaultInvocation.from_target(
            replace(_target("lease_expiry"), identity=None),
            callback_binding=callback_binding,
            test_hook_attestation_digest=None,
        )
    assert captured.value.code == "DATA.RUNTIME_EVIDENCE.FAULT_REQUEST_IDENTITY_REQUIRED"


def test_adapter_has_no_shell_endpoint_or_environment_selector_surface() -> None:
    source_path = (
        Path(__file__).parents[3]
        / "scripts/content/execution/runtime_evidence_fault_adapters.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imported.isdisjoint({"os", "subprocess", "socket", "urllib"})
    public_functions = {
        node.name: {argument.arg for argument in node.args.args + node.args.kwonlyargs}
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    }
    forbidden = {"argv", "command", "endpoint", "environment", "url"}
    assert all(not forbidden.intersection(args) for args in public_functions.values())


@pytest.mark.parametrize(
    "fault_type",
    [
        "lease_expiry",
        "redis_restart",
        "mongo_reconnect",
        "provider_timeout",
        "provider_rate_limit",
    ],
)
def test_unavailable_fault_adapter_is_explicit_and_fail_closed(
    fault_type: str,
) -> None:
    adapter = unavailable_fault_adapter(fault_type)
    assert is_unavailable_fault_binding_document(adapter.binding.as_document())
    with pytest.raises(FaultAdapterBlocker) as captured:
        adapter.trigger(_target(fault_type))
    if fault_type.startswith("provider_"):
        assert captured.value.code == (
            "DATA.RUNTIME_EVIDENCE.PROVIDER_TEST_HOOK_ATTESTATION_REQUIRED"
        )
    else:
        assert captured.value.code == (
            "DATA.RUNTIME_EVIDENCE.PROTECTED_OPERATION_CALLBACK_REQUIRED"
        )
