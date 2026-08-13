"""generic substitute 一致性探针的常量、异常与证据数据模型。"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
ROLE = "provider-protocol-substitute"
ADAPTER_ID = "ops.provider_protocol_substitute"
SUPPORTED_PUBLIC_ASSERTIONS = frozenset(
    {
        "provider.success",
        "provider.validation",
        "provider.auth",
        "provider.network_dns",
        "provider.timeout",
        "provider.throttle",
        "provider.retry",
        "provider.idempotency",
        "provider.callback_ordering",
        "provider.redaction",
        "provider.observability",
    }
)
_DIGEST_PREFIX = "sha256:"


class ConformanceBlocked(RuntimeError):
    """A required assertion cannot be proven by the active implementation."""


@dataclass(frozen=True)
class RuntimeContext:
    environment: str
    target: str
    baseline_id: str
    attempt_id: str
    runtime_config_digest: str
    runtime_composition_digest: str
    capability_id: str
    adapter_id: str
    typed_port: str
    operations: tuple[str, ...]
    endpoint_values: Mapping[str, str]
    host_origin: str
    ca_path: Path
    operator_token: str = field(repr=False)


@dataclass(frozen=True)
class HTTPResult:
    status: int
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True)
class InvocationEvidence:
    operation: str
    outcome: str
    status: int
    request_digest: str
    trace_digest: str
    lease_id: str
    receipt_ref: str
    call_ordinal: int = 0
    effect_ordinal: int = 0
    idempotency_key_digest: str = ""
    idempotency_state: str = "none"
    network_host_digest: str = ""
    tls_server_name_digest: str = ""
    tls_version: str = ""


@dataclass(frozen=True)
class AssertionEvidence:
    assertion_id: str
    scene_receipt_ref: str
    log_ref: str
    trace_ref: str
    metric_refs: tuple[str, ...]

    def marker(self) -> dict[str, Any]:
        return {
            "assertionId": self.assertion_id,
            "status": "passed",
            "sceneReceiptRef": self.scene_receipt_ref,
            "logRef": self.log_ref,
            "traceRef": self.trace_ref,
            "metricRefs": list(self.metric_refs),
        }


@dataclass(frozen=True)
class SupportedRun:
    assertions: Mapping[str, AssertionEvidence]
    cleanup_receipt: str
    supported_assertion_ids: tuple[str, ...]
    blocked_assertion_ids: tuple[str, ...]
    readback_digest: str
