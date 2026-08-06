"""Execute package-bound conformance probes against the generic substitute.

This module does not select an Adapter or maintain a Provider registry.  The
selected Adapter, operations and endpoint material keys come from the source
metadata, the object-owned ``operations.yaml`` and the active candidate's
packaged Provider composition.  Target-specific endpoint and operator values
remain in the protected deployment workspace and are never returned by this
module.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import ssl
import stat
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib import error, parse, request

import yaml

from quwoquan_ops.ci.provider_conformance.native_case_result import (
    _ASSERTION_MARKER,
    _CLEANUP_MARKER,
)
from quwoquan_ops.ci.provider_conformance.run_provider_patrol_uat import (
    _load_nonprod_runtime_identity,
)
from quwoquan_ops.cli.lib.deployment_candidate_manifest import load_candidate_manifest
from quwoquan_ops.cli.lib.environment_topology import (
    get_target,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.external_provider_governance import load_and_compile
from quwoquan_ops.cli.lib.local_environment_auth import load_local_environment_auth
from quwoquan_ops.cli.lib.output_paths import (
    active_deployment_candidate,
    deployment_work_root,
)
from quwoquan_ops.cli.lib.port_manifest import canonical_port, load_port_manifest
from quwoquan_ops.cli.lib.public_domain_tls import root_certificate_path

ROOT = Path(__file__).resolve().parents[3]
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


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ConformanceBlocked("Provider protocol probe forbids redirects")


class ProtocolClient:
    """Strict HTTPS client for one already-running package-bound substitute."""

    def __init__(self, context: RuntimeContext, *, timeout_seconds: float = 5.0):
        self._context = context
        self._timeout_seconds = timeout_seconds
        tls = ssl.create_default_context(cafile=str(context.ca_path))
        tls.minimum_version = ssl.TLSVersion.TLSv1_3
        self._opener = request.build_opener(
            request.HTTPSHandler(context=tls),
            _NoRedirect(),
        )
        self._active_leases: dict[str, str] = {}
        self._active_callback_channels: dict[str, str] = {}
        self._cleanup_receipts: list[str] = []

    @property
    def cleanup_receipts(self) -> tuple[str, ...]:
        return tuple(self._cleanup_receipts)

    def health(self) -> Mapping[str, Any]:
        payload = self._json_request("GET", "/healthz")
        if (
            payload.get("status") != "ready"
            or payload.get("adapterId") != ADAPTER_ID
            or payload.get("environment") != self._context.environment
            or payload.get("target") != self._context.target
            or payload.get("configurationDigest")
            != self._context.runtime_config_digest
            or payload.get("runtimeCompositionDigest")
            != self._context.runtime_composition_digest
            or payload.get("nonPromotable") is not True
            or payload.get("conformanceMechanisms")
            != [
                "tls_dns_authority",
                "idempotency_ledger",
                "callback_channel_ordering",
            ]
            or payload.get("activeFaultLeases") != []
        ):
            raise ConformanceBlocked(
                "generic substitute health is not bound to the active candidate"
            )
        return payload

    def readback(self) -> Mapping[str, Any]:
        payload = self._json_request(
            "GET",
            "/control/readback",
            operator=True,
        )
        if (
            payload.get("adapterId") != ADAPTER_ID
            or payload.get("environment") != self._context.environment
            or payload.get("target") != self._context.target
            or payload.get("configurationDigest")
            != self._context.runtime_config_digest
            or payload.get("runtimeCompositionDigest")
            != self._context.runtime_composition_digest
            or payload.get("nonPromotable") is not True
            or not isinstance(payload.get("invocations"), list)
            or not isinstance(payload.get("faultLeases"), list)
            or not isinstance(payload.get("callbackChannels"), list)
            or not isinstance(payload.get("effects"), Mapping)
        ):
            raise ConformanceBlocked("generic substitute readback identity mismatch")
        return payload

    def acquire(
        self,
        *,
        operation: str,
        scenario: str,
        parameters: Mapping[str, int],
        max_matches: int,
    ) -> Mapping[str, Any]:
        owner = "attempt:" + _sha256_text(self._context.attempt_id)[7:31]
        payload = self._json_request(
            "POST",
            "/control/fault-leases",
            operator=True,
            body={
                "environment": self._context.environment,
                "target": self._context.target,
                "configurationDigest": self._context.runtime_config_digest,
                "runtimeCompositionDigest": self._context.runtime_composition_digest,
                "capabilityId": self._context.capability_id,
                "operation": operation,
                "scenario": scenario,
                "parameters": dict(parameters),
                "owner": owner,
                "ttlSeconds": 30,
                "maxMatches": max_matches,
            },
            expected_status=201,
        )
        lease_id = str(payload.get("leaseId") or "")
        if (
            not lease_id.startswith("fault-")
            or payload.get("state") != "active"
            or payload.get("owner") != owner
            or payload.get("capabilityId") != self._context.capability_id
            or payload.get("operation") != operation
            or payload.get("scenario") != scenario
            or payload.get("version") != 1
        ):
            raise ConformanceBlocked("fault lease acquire receipt is malformed")
        self._active_leases[lease_id] = owner
        return payload

    def read_lease(self, lease_id: str) -> Mapping[str, Any]:
        payload = self._json_request(
            "GET",
            f"/control/fault-leases/{lease_id}",
            operator=True,
        )
        if payload.get("leaseId") != lease_id:
            raise ConformanceBlocked("fault lease readback identity mismatch")
        cleanup = payload.get("cleanupReceipt")
        if isinstance(cleanup, Mapping) and cleanup.get("status") == "restored":
            receipt_ref = str(cleanup.get("receiptRef") or "")
            if receipt_ref and receipt_ref not in self._cleanup_receipts:
                self._cleanup_receipts.append(receipt_ref)
            self._active_leases.pop(lease_id, None)
        return payload

    def release_all(self) -> None:
        errors: list[str] = []
        for lease_id, owner in list(self._active_leases.items()):
            try:
                state = self.read_lease(lease_id)
                if state.get("state") != "active":
                    continue
                released = self._json_request(
                    "DELETE",
                    f"/control/fault-leases/{lease_id}",
                    operator=True,
                    body={
                        "owner": owner,
                        "expectedVersion": state.get("version"),
                    },
                )
                cleanup = released.get("cleanupReceipt")
                if (
                    released.get("state") != "released"
                    or not isinstance(cleanup, Mapping)
                    or cleanup.get("status") != "restored"
                ):
                    raise ConformanceBlocked("fault lease release did not restore scope")
                receipt_ref = str(cleanup.get("receiptRef") or "")
                self._cleanup_receipts.append(receipt_ref)
                self._active_leases.pop(lease_id, None)
            except (ConformanceBlocked, OSError, ValueError) as exc:
                errors.append(f"{lease_id}:{exc}")
        for channel_id, owner in list(self._active_callback_channels.items()):
            try:
                state = self.read_callback_channel(channel_id)
                if state.get("state") != "active":
                    continue
                released = self._json_request(
                    "DELETE",
                    f"/control/callback-channels/{channel_id}",
                    operator=True,
                    body={
                        "owner": owner,
                        "expectedVersion": state.get("version"),
                    },
                )
                cleanup = released.get("cleanupReceipt")
                if (
                    released.get("state") != "released"
                    or not isinstance(cleanup, Mapping)
                    or cleanup.get("status") != "restored"
                ):
                    raise ConformanceBlocked(
                        "callback channel release did not restore scope"
                    )
                receipt_ref = str(cleanup.get("receiptRef") or "")
                self._cleanup_receipts.append(receipt_ref)
                self._active_callback_channels.pop(channel_id, None)
            except (ConformanceBlocked, OSError, ValueError) as exc:
                errors.append(f"{channel_id}:{exc}")
        if errors:
            raise ConformanceBlocked(
                "generic substitute cleanup failed: " + "; ".join(errors)
            )

    def invoke(self, operation: str, *, canary: str) -> InvocationEvidence:
        method, url, body = _probe_request(self._context, operation, canary=canary)
        request_id = "pc-" + secrets.token_hex(12)
        trace_id = secrets.token_hex(16)
        span_id = secrets.token_hex(8)
        traceparent = f"00-{trace_id}-{span_id}-01"
        headers = {
            "X-Request-ID": request_id,
            "traceparent": traceparent,
        }
        result = self._request(method, url, body=body, headers=headers)
        request_digest = _provider_request_digest(method, url, request_id)
        trace_digest = _sha256_text("trace\n" + traceparent)
        readback = self.readback()
        matches = [
            item
            for item in readback["invocations"]
            if isinstance(item, Mapping)
            and item.get("capabilityId") == self._context.capability_id
            and item.get("operation") == operation
            and item.get("requestDigest") == request_digest
            and item.get("traceDigest") == trace_digest
        ]
        if len(matches) != 1:
            raise ConformanceBlocked(
                "sanitized invocation ledger does not uniquely bind the protocol request"
            )
        item = matches[0]
        if item.get("status") != result.status or not isinstance(
            item.get("callOrdinal"), int
        ):
            raise ConformanceBlocked("invocation ledger status/ordinal mismatch")
        outcome = str(item.get("outcome") or "")
        receipt_ref = _receipt_ref(
            "provider-protocol-invocation",
            {
                "runtime": self._context.runtime_composition_digest,
                "request": request_digest,
                "trace": trace_digest,
                "outcome": outcome,
                "status": result.status,
                "ordinal": item["callOrdinal"],
            },
        )
        return InvocationEvidence(
            operation=operation,
            outcome=outcome,
            status=result.status,
            request_digest=request_digest,
            trace_digest=trace_digest,
            lease_id=str(item.get("leaseId") or ""),
            receipt_ref=receipt_ref,
        )

    def acquire_callback_channel(
        self,
        *,
        operation: str,
        max_callbacks: int,
    ) -> Mapping[str, Any]:
        owner = "attempt:" + _sha256_text(
            self._context.attempt_id + ":callback"
        )[7:31]
        payload = self._json_request(
            "POST",
            "/control/callback-channels",
            operator=True,
            body={
                "environment": self._context.environment,
                "target": self._context.target,
                "configurationDigest": self._context.runtime_config_digest,
                "runtimeCompositionDigest": self._context.runtime_composition_digest,
                "capabilityId": self._context.capability_id,
                "operation": operation,
                "owner": owner,
                "ttlSeconds": 30,
                "maxCallbacks": max_callbacks,
            },
            expected_status=201,
        )
        channel_id = str(payload.get("channelId") or "")
        if (
            not channel_id.startswith("callback-")
            or payload.get("state") != "active"
            or payload.get("owner") != owner
            or payload.get("capabilityId") != self._context.capability_id
            or payload.get("operation") != operation
            or payload.get("version") != 1
        ):
            raise ConformanceBlocked("callback channel acquire receipt is malformed")
        self._active_callback_channels[channel_id] = owner
        return payload

    def read_callback_channel(self, channel_id: str) -> Mapping[str, Any]:
        payload = self._json_request(
            "GET",
            f"/control/callback-channels/{channel_id}",
            operator=True,
        )
        if payload.get("channelId") != channel_id:
            raise ConformanceBlocked("callback channel readback identity mismatch")
        cleanup = payload.get("cleanupReceipt")
        if isinstance(cleanup, Mapping) and cleanup.get("status") == "restored":
            receipt_ref = str(cleanup.get("receiptRef") or "")
            if receipt_ref and receipt_ref not in self._cleanup_receipts:
                self._cleanup_receipts.append(receipt_ref)
            self._active_callback_channels.pop(channel_id, None)
        return payload

    def invoke_raw(
        self,
        operation: str,
        *,
        canary: str,
        idempotency_key: str = "",
        callback_channel: str = "",
        extra_query: str = "",
    ) -> tuple[InvocationEvidence, HTTPResult]:
        method, url, body = _probe_request(self._context, operation, canary=canary)
        if extra_query:
            parsed_url = parse.urlsplit(url)
            url = parse.urlunsplit(
                (
                    parsed_url.scheme,
                    parsed_url.netloc,
                    parsed_url.path,
                    "&".join(filter(None, (parsed_url.query, extra_query))),
                    "",
                )
            )
        request_id = "pc-" + secrets.token_hex(12)
        trace_id = secrets.token_hex(16)
        span_id = secrets.token_hex(8)
        traceparent = f"00-{trace_id}-{span_id}-01"
        headers = {"X-Request-ID": request_id, "traceparent": traceparent}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        if callback_channel:
            headers["X-Provider-Callback-Channel"] = callback_channel
        result = self._request(method, url, body=body, headers=headers)
        request_digest = _provider_request_digest(method, url, request_id)
        trace_digest = _sha256_text("trace\n" + traceparent)
        readback = self.readback()
        matches = [
            item
            for item in readback["invocations"]
            if isinstance(item, Mapping)
            and item.get("capabilityId") == self._context.capability_id
            and item.get("operation") == operation
            and item.get("requestDigest") == request_digest
            and item.get("traceDigest") == trace_digest
        ]
        if len(matches) != 1:
            raise ConformanceBlocked("invocation ledger linkage is missing")
        item = matches[0]
        call_ordinal = item.get("callOrdinal")
        if (
            item.get("status") != result.status
            or not isinstance(call_ordinal, int)
            or isinstance(call_ordinal, bool)
            or call_ordinal <= 0
        ):
            raise ConformanceBlocked("invocation ledger status/ordinal mismatch")
        evidence = InvocationEvidence(
            operation=operation,
            outcome=str(item.get("outcome") or ""),
            status=result.status,
            request_digest=request_digest,
            trace_digest=trace_digest,
            lease_id=str(item.get("leaseId") or ""),
            receipt_ref=_receipt_ref("provider-protocol-invocation", dict(item)),
            call_ordinal=call_ordinal,
            effect_ordinal=int(item.get("effectOrdinal") or 0),
            idempotency_key_digest=str(item.get("idempotencyKeyDigest") or ""),
            idempotency_state=str(item.get("idempotencyState") or ""),
            network_host_digest=str(item.get("networkHostDigest") or ""),
            tls_server_name_digest=str(item.get("tlsServerNameDigest") or ""),
            tls_version=str(item.get("tlsVersion") or ""),
        )
        return evidence, result

    def _json_request(
        self,
        method: str,
        path: str,
        *,
        operator: bool = False,
        body: Mapping[str, Any] | None = None,
        expected_status: int = 200,
    ) -> Mapping[str, Any]:
        headers = {"Authorization": "Bearer " + self._context.operator_token} if operator else {}
        result = self._request(
            method,
            self._context.host_origin + path,
            body=body,
            headers=headers,
        )
        if result.status != expected_status:
            raise ConformanceBlocked(
                f"generic substitute control request returned HTTP {result.status}"
            )
        try:
            payload = json.loads(result.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ConformanceBlocked("generic substitute returned invalid JSON") from exc
        if not isinstance(payload, Mapping):
            raise ConformanceBlocked("generic substitute JSON response is not an object")
        return payload

    def _request(
        self,
        method: str,
        url: str,
        *,
        body: Mapping[str, Any] | None,
        headers: Mapping[str, str],
    ) -> HTTPResult:
        parsed = parse.urlsplit(url)
        origin = parse.urlsplit(self._context.host_origin)
        if (
            parsed.scheme != "https"
            or parsed.hostname != origin.hostname
            or parsed.port != origin.port
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise ConformanceBlocked("Provider probe URL escapes the target-local HTTPS origin")
        encoded = None
        request_headers = dict(headers)
        if body is not None:
            encoded = json.dumps(body, separators=(",", ":")).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        outbound = request.Request(
            url,
            data=encoded,
            headers=request_headers,
            method=method,
        )
        try:
            with self._opener.open(outbound, timeout=self._timeout_seconds) as response:
                return HTTPResult(
                    status=int(response.status),
                    headers=dict(response.headers.items()),
                    body=response.read(4 << 20),
                )
        except error.HTTPError as exc:
            return HTTPResult(
                status=int(exc.code),
                headers=dict(exc.headers.items()),
                body=exc.read(4 << 20),
            )
        except (error.URLError, TimeoutError, ssl.SSLError, OSError) as exc:
            raise ConformanceBlocked(
                "generic substitute HTTPS request failed before protocol readback"
            ) from exc


def execute_offline_local_contract(*, process_runner=subprocess.run) -> None:
    """Relay exact markers emitted by the workload-owned Go native harness."""

    environment = _required_environment("QWQ_PROVIDER_CONFORMANCE_ENVIRONMENT")
    capability_id = _required_environment("QWQ_PROVIDER_CONFORMANCE_CAPABILITY_ID")
    adapter_id = _required_environment("QWQ_PROVIDER_CONFORMANCE_ADAPTER_ID")
    typed_port = _required_environment("QWQ_PROVIDER_CONFORMANCE_TYPED_PORT")
    contract_ref = _required_environment("QWQ_PROVIDER_CONFORMANCE_CONTRACT_REF")
    if environment not in {"alpha", "beta", "gamma"}:
        raise ConformanceBlocked("generic substitute is limited to Alpha/Beta/Gamma")
    compiled, issues = load_and_compile()
    if issues:
        raise ConformanceBlocked(
            "compiled Provider Bindings are invalid: "
            + "; ".join(issue.render() for issue in issues)
        )
    selected = compiled.get("selectedBindings")
    scope = selected.get(environment) if isinstance(selected, Mapping) else None
    binding = scope.get(capability_id) if isinstance(scope, Mapping) else None
    if (
        not isinstance(binding, Mapping)
        or binding.get("state") != "enabled"
        or binding.get("adapter_id") != adapter_id
        or binding.get("endpoint_ref") != f"local_topology:{ROLE}"
    ):
        raise ConformanceBlocked("source Binding does not select the generic substitute")
    _owner_dependency(
        contract_ref=contract_ref,
        capability_id=capability_id,
        adapter_id=adapter_id,
        typed_port=typed_port,
    )
    cache_root = ROOT / ".qwq_output/env/repo/local"
    go_cache = cache_root / "go-build/generic-provider-conformance"
    go_tmp = cache_root / "go-tmp/generic-provider-conformance"
    go_cache.mkdir(parents=True, exist_ok=True)
    go_tmp.mkdir(parents=True, exist_ok=True)
    command = (
        "go",
        "-C",
        "quwoquan_ops/external/provider-protocol-substitute",
        "run",
        "./cmd/provider-protocol-conformance",
    )
    forwarded_names = (
        "QWQ_PROVIDER_CONFORMANCE_ENVIRONMENT",
        "QWQ_PROVIDER_CONFORMANCE_CAPABILITY_ID",
        "QWQ_PROVIDER_CONFORMANCE_ASSERTION_IDS",
    )
    execution_environment = {
        key: value
        for key in ("PATH", "HOME", "TMPDIR", "GOROOT", "GOPATH", "GOENV")
        if (value := os.environ.get(key, ""))
    }
    execution_environment.update(
        {
            "GOCACHE": str(go_cache),
            "GOTMPDIR": str(go_tmp),
            **{name: _required_environment(name) for name in forwarded_names},
        }
    )
    completed = process_runner(
        command,
        cwd=ROOT,
        env=execution_environment,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ConformanceBlocked(
            "generic substitute offline native suite failed; no CaseResult was emitted"
        )
    marker_lines = _validated_native_marker_lines(
        completed.stdout,
        expected_assertions=_required_assertion_ids(),
    )
    for line in marker_lines:
        print(line)


def _validated_native_marker_lines(
    stdout: bytes,
    *,
    expected_assertions: Sequence[str],
) -> tuple[str, ...]:
    """Validate coverage while preserving the exact native marker payload bytes."""

    if not isinstance(stdout, bytes):
        raise ConformanceBlocked("offline native harness stdout must be bytes")
    assertion_ids: list[str] = []
    cleanup_count = 0
    marker_lines: list[str] = []
    for raw_line in stdout.decode("utf-8", errors="strict").splitlines():
        line = raw_line.strip()
        if line.startswith(_ASSERTION_MARKER):
            try:
                payload = json.loads(line.removeprefix(_ASSERTION_MARKER))
            except json.JSONDecodeError as exc:
                raise ConformanceBlocked(
                    "offline native harness emitted malformed assertion marker"
                ) from exc
            if not isinstance(payload, Mapping) or not isinstance(
                payload.get("assertionId"), str
            ):
                raise ConformanceBlocked(
                    "offline native harness emitted malformed assertion receipt"
                )
            assertion_ids.append(payload["assertionId"])
            marker_lines.append(line)
        elif line.startswith(_CLEANUP_MARKER):
            cleanup_count += 1
            marker_lines.append(line)
    if tuple(assertion_ids) != tuple(expected_assertions) or cleanup_count != 1:
        raise ConformanceBlocked(
            "offline native harness markers do not exactly cover source assertions"
        )
    return tuple(marker_lines)


def load_runtime_context() -> RuntimeContext:
    environment = _required_environment("QWQ_PROVIDER_CONFORMANCE_ENVIRONMENT")
    layer = _required_environment("QWQ_PROVIDER_CONFORMANCE_LAYER")
    capability_id = _required_environment("QWQ_PROVIDER_CONFORMANCE_CAPABILITY_ID")
    adapter_id = _required_environment("QWQ_PROVIDER_CONFORMANCE_ADAPTER_ID")
    typed_port = _required_environment("QWQ_PROVIDER_CONFORMANCE_TYPED_PORT")
    contract_ref = _required_environment("QWQ_PROVIDER_CONFORMANCE_CONTRACT_REF")
    if environment not in {"alpha", "beta", "gamma"}:
        raise ConformanceBlocked("generic substitute is limited to Alpha/Beta/Gamma")
    if layer not in {"local_contract", "api_integration"}:
        raise ConformanceBlocked("generic substitute runner only owns local/API layers")
    target = f"{environment}-local"
    runtime_identity = _load_nonprod_runtime_identity(environment, target)
    active = active_deployment_candidate(target)
    if not isinstance(active, Mapping):
        raise ConformanceBlocked("active immutable candidate is unavailable")
    manifest = load_candidate_manifest(
        environment,
        target,
        runtime_identity.baseline_id,
        require_full=True,
    )
    provider_runtime = manifest.get("providerRuntime")
    composition = (
        provider_runtime.get("composition")
        if isinstance(provider_runtime, Mapping)
        else None
    )
    if not isinstance(composition, Mapping):
        raise ConformanceBlocked("packaged Provider composition is unavailable")
    binding = _packaged_binding(composition, capability_id)
    if (
        binding.get("state") != "enabled"
        or binding.get("adapterId") != adapter_id
        or binding.get("endpointRef") != f"local_topology:{ROLE}"
    ):
        raise ConformanceBlocked("selected Binding is not the packaged generic substitute")

    dependency = _owner_dependency(
        contract_ref=contract_ref,
        capability_id=capability_id,
        adapter_id=adapter_id,
        typed_port=typed_port,
    )
    if binding.get("endpointEnvironmentKeys") != dependency["endpointEnvs"]:
        raise ConformanceBlocked("packaged Binding endpoint roles drifted from owner contract")
    operations = tuple(dependency["operations"])
    workload = _provider_workload(composition)
    if (
        capability_id not in workload.get("capabilityIds", [])
        or adapter_id not in workload.get("adapterIds", [])
    ):
        raise ConformanceBlocked("packaged generic workload does not own the selected Binding")

    active_config, material = _load_provider_material(target)
    if (
        active_config.get("schema") != "stackctl-provider-config"
        or active_config.get("environment") != environment
        or active_config.get("target") != target
        or active_config.get("runtimeCompositionDigest")
        != composition.get("runtimeCompositionDigest")
        or active_config.get("missingKeys") != []
        or active_config.get("invalidKeys") != []
    ):
        raise ConformanceBlocked("rendered Provider config is not bound to the active runtime")
    endpoint_values = {
        alias: str(material.get(key) or "").strip()
        for alias, key in dependency["endpointEnvs"].items()
    }
    if any(not value for value in endpoint_values.values()):
        raise ConformanceBlocked("selected generic Binding endpoint material is missing")

    topology_target = get_target(load_environment_topology(), target)
    profile_name = str(topology_target.get("portProfile") or "")
    port_manifest = load_port_manifest()
    role = port_manifest.get("roles", {}).get(ROLE)
    if not isinstance(role, Mapping) or role.get("scheme") != "https":
        raise ConformanceBlocked("generic substitute role is not canonical HTTPS")
    port = canonical_port(port_manifest, profile_name, ROLE)
    host_origin = parse.urlunsplit(("https", f"localhost:{port}", "", "", ""))
    ca_path = root_certificate_path(target)
    auth = load_local_environment_auth(environment, target)
    operator_token = auth.environment.get("PROVIDER_SUBSTITUTE_OPERATOR_TOKEN", "")
    if len(operator_token) < 24:
        raise ConformanceBlocked("target-managed generic substitute operator material is missing")
    return RuntimeContext(
        environment=environment,
        target=target,
        baseline_id=runtime_identity.baseline_id,
        attempt_id=runtime_identity.attempt_id,
        runtime_config_digest=runtime_identity.runtime_config_digest,
        runtime_composition_digest=runtime_identity.provider_runtime_digest,
        capability_id=capability_id,
        adapter_id=adapter_id,
        typed_port=typed_port,
        operations=operations,
        endpoint_values=endpoint_values,
        host_origin=host_origin,
        ca_path=ca_path,
        operator_token=operator_token,
    )


def execute_supported_scenes(
    context: RuntimeContext,
    *,
    client_factory=ProtocolClient,
) -> SupportedRun:
    expected_assertions = _required_assertion_ids()
    capability_assertions = tuple(
        assertion_id
        for assertion_id in expected_assertions
        if assertion_id not in SUPPORTED_PUBLIC_ASSERTIONS
    )
    if len(capability_assertions) != 1:
        raise ConformanceBlocked("source must declare exactly one capability assertion")
    client = client_factory(context)
    evidence_by_assertion: dict[str, list[InvocationEvidence]] = {
        assertion_id: []
        for assertion_id in (*SUPPORTED_PUBLIC_ASSERTIONS, *capability_assertions)
    }
    canary = "redaction-canary-" + secrets.token_hex(12)
    primary_failure: BaseException | None = None
    try:
        client.health()
        for operation in context.operations:
            success, result = client.invoke_raw(operation, canary=canary)
            _validate_success(context.capability_id, operation, result)
            if success.outcome != "success" or success.status not in {200, 202}:
                raise ConformanceBlocked("generic substitute success scene failed")
            evidence_by_assertion["provider.success"].append(success)
            evidence_by_assertion[capability_assertions[0]].append(success)
            expected_dns_digest = _sha256_text("dns\nlocalhost")
            if (
                success.network_host_digest != expected_dns_digest
                or success.tls_server_name_digest != expected_dns_digest
                or success.tls_version != "TLSv1.3"
            ):
                raise ConformanceBlocked(
                    "generic substitute network/DNS scene lacks TLS authority readback"
                )
            evidence_by_assertion["provider.network_dns"].append(success)

            for assertion_id, scenario, parameters, expected_status, expected_outcome in (
                ("provider.validation", "validation", {}, 400, "validation_rejected"),
                ("provider.auth", "auth", {}, 401, "auth_rejected"),
                (
                    "provider.timeout",
                    "delay_timeout",
                    {"delayMillis": 10},
                    504,
                    "timeout",
                ),
                (
                    "provider.throttle",
                    "throttle",
                    {"retryAfterSeconds": 1},
                    429,
                    "throttled",
                ),
            ):
                lease = client.acquire(
                    operation=operation,
                    scenario=scenario,
                    parameters=parameters,
                    max_matches=1,
                )
                invocation, fault_result = client.invoke_raw(operation, canary=canary)
                state = client.read_lease(str(lease["leaseId"]))
                cleanup = state.get("cleanupReceipt")
                if (
                    fault_result.status != expected_status
                    or invocation.outcome != expected_outcome
                    or invocation.lease_id != lease["leaseId"]
                    or state.get("state") != "exhausted"
                    or not isinstance(cleanup, Mapping)
                    or cleanup.get("status") != "restored"
                ):
                    raise ConformanceBlocked(
                        f"generic substitute {scenario} scene did not restore"
                    )
                evidence_by_assertion[assertion_id].append(invocation)

            retry_lease = client.acquire(
                operation=operation,
                scenario="transient_then_success",
                parameters={"remainingFailures": 1},
                max_matches=2,
            )
            first_retry, first_result = client.invoke_raw(operation, canary=canary)
            second_retry, second_result = client.invoke_raw(operation, canary=canary)
            _validate_success(context.capability_id, operation, second_result)
            retry_state = client.read_lease(str(retry_lease["leaseId"]))
            if (
                first_result.status != 503
                or first_retry.outcome != "transient_unavailable"
                or second_result.status not in {200, 202}
                or second_retry.outcome != "success"
                or retry_state.get("state") != "exhausted"
                or not isinstance(retry_state.get("cleanupReceipt"), Mapping)
            ):
                raise ConformanceBlocked("generic substitute retry/recovery scene failed")
            evidence_by_assertion["provider.retry"].extend(
                (first_retry, second_retry)
            )

            before_idempotency = client.readback()
            scope = f"{context.capability_id}/{operation}"
            before_effects = int(
                (before_idempotency.get("effects") or {}).get(scope, 0)
            )
            idempotency_key = "pc-idempotency-" + secrets.token_hex(12)
            first_idempotent, first_idempotent_result = client.invoke_raw(
                operation,
                canary=canary,
                idempotency_key=idempotency_key,
            )
            replay_idempotent, replay_idempotent_result = client.invoke_raw(
                operation,
                canary=canary,
                idempotency_key=idempotency_key,
            )
            conflict_idempotent, conflict_idempotent_result = client.invoke_raw(
                operation,
                canary=canary,
                idempotency_key=idempotency_key,
                extra_query="conformanceConflict=1",
            )
            after_idempotency = client.readback()
            after_effects = int(
                (after_idempotency.get("effects") or {}).get(scope, 0)
            )
            if (
                first_idempotent_result.status not in {200, 202}
                or replay_idempotent_result.status != first_idempotent_result.status
                or replay_idempotent_result.body != first_idempotent_result.body
                or conflict_idempotent_result.status != 409
                or first_idempotent.idempotency_state != "new"
                or replay_idempotent.idempotency_state != "replay"
                or conflict_idempotent.idempotency_state != "conflict"
                or first_idempotent.effect_ordinal <= 0
                or replay_idempotent.effect_ordinal
                != first_idempotent.effect_ordinal
                or conflict_idempotent.effect_ordinal
                != first_idempotent.effect_ordinal
                or after_effects - before_effects != 1
            ):
                raise ConformanceBlocked(
                    "generic substitute idempotency scene did not prove one effect"
                )
            evidence_by_assertion["provider.idempotency"].extend(
                (
                    first_idempotent,
                    replay_idempotent,
                    conflict_idempotent,
                )
            )

            channel = client.acquire_callback_channel(
                operation=operation,
                max_callbacks=2,
            )
            channel_id = str(channel["channelId"])
            callback_first, callback_first_result = client.invoke_raw(
                operation,
                canary=canary + "-callback-1",
                callback_channel=channel_id,
            )
            callback_second, callback_second_result = client.invoke_raw(
                operation,
                canary=canary + "-callback-2",
                callback_channel=channel_id,
            )
            callback_state = client.read_callback_channel(channel_id)
            callback_events = callback_state.get("events")
            if (
                callback_first_result.status not in {200, 202}
                or callback_second_result.status not in {200, 202}
                or callback_state.get("state") != "exhausted"
                or not isinstance(callback_events, list)
                or len(callback_events) != 2
                or not all(isinstance(item, Mapping) for item in callback_events)
                or [item.get("sequence") for item in callback_events] != [1, 2]
                or not isinstance(callback_events[0].get("callOrdinal"), int)
                or not isinstance(callback_events[1].get("callOrdinal"), int)
                or callback_events[0]["callOrdinal"]
                >= callback_events[1]["callOrdinal"]
                or callback_events[0].get("effectOrdinal")
                != callback_first.effect_ordinal
                or callback_events[1].get("effectOrdinal")
                != callback_second.effect_ordinal
                or callback_events[0].get("requestDigest")
                != callback_first.request_digest
                or callback_events[1].get("requestDigest")
                != callback_second.request_digest
                or callback_events[0].get("traceDigest")
                != callback_first.trace_digest
                or callback_events[1].get("traceDigest")
                != callback_second.trace_digest
                or not isinstance(callback_state.get("cleanupReceipt"), Mapping)
                or callback_state["cleanupReceipt"].get("status") != "restored"
            ):
                raise ConformanceBlocked(
                    "generic substitute callback ordering scene is incomplete"
                )
            evidence_by_assertion["provider.callback_ordering"].extend(
                (callback_first, callback_second)
            )

        readback = client.readback()
        encoded_readback = json.dumps(
            readback,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        if context.operator_token in encoded_readback or canary in encoded_readback:
            raise ConformanceBlocked("generic substitute readback leaked protected material")
        all_invocations = [
            item
            for values in evidence_by_assertion.values()
            for item in values
        ]
        if not all_invocations:
            raise ConformanceBlocked("generic substitute produced no invocation evidence")
        evidence_by_assertion["provider.redaction"] = list(all_invocations)
        evidence_by_assertion["provider.observability"] = list(all_invocations)
        readback_digest = _sha256_text(encoded_readback)
    except BaseException as exc:  # cleanup must also run for interrupts/failures
        primary_failure = exc
        raise
    finally:
        try:
            client.release_all()
            final = client.readback()
            active = [
                item
                for item in final.get("faultLeases", [])
                if isinstance(item, Mapping) and item.get("state") == "active"
            ]
            if active:
                raise ConformanceBlocked("generic substitute retained active fault leases")
        except BaseException as cleanup_error:
            if primary_failure is None:
                raise
            raise ConformanceBlocked(
                f"generic substitute cleanup failed after scene error: {cleanup_error}"
            ) from primary_failure

    assertions = {
        assertion_id: _aggregate_assertion(assertion_id, invocations)
        for assertion_id, invocations in evidence_by_assertion.items()
        if invocations
    }
    blocked = tuple(
        assertion_id
        for assertion_id in expected_assertions
        if assertion_id not in assertions
    )
    cleanup_receipts = tuple(sorted(set(client.cleanup_receipts)))
    expected_cleanup_count = len(context.operations) * 6
    if (
        len(cleanup_receipts) != expected_cleanup_count
        or any(
            not receipt.startswith(
                (
                    "receipt:provider-fault-cleanup:",
                    "receipt:provider-callback-cleanup:",
                )
            )
            or len(receipt.rsplit(":", 1)[-1]) != 24
            for receipt in cleanup_receipts
        )
    ):
        raise ConformanceBlocked(
            "generic substitute cleanup receipts do not cover every fault lease"
        )
    cleanup_receipt = _receipt_ref(
        "provider-protocol-cleanup",
        {
            "target": context.target,
            "attemptId": context.attempt_id,
            "runtime": context.runtime_composition_digest,
            "receipts": list(cleanup_receipts),
        },
    )
    return SupportedRun(
        assertions=assertions,
        cleanup_receipt=cleanup_receipt,
        supported_assertion_ids=tuple(
            assertion_id for assertion_id in expected_assertions if assertion_id in assertions
        ),
        blocked_assertion_ids=blocked,
        readback_digest=readback_digest,
    )


def emit_markers(run: SupportedRun, *, expected_assertions: Sequence[str]) -> None:
    missing = [
        assertion_id
        for assertion_id in expected_assertions
        if assertion_id not in run.assertions
    ]
    if missing:
        raise ConformanceBlocked(
            "required generic Provider assertions have no real mechanism: "
            + ",".join(missing)
        )
    for assertion_id in expected_assertions:
        print(
            _ASSERTION_MARKER
            + json.dumps(
                run.assertions[assertion_id].marker(),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
    print(
        _CLEANUP_MARKER
        + json.dumps(
            {"status": "restored", "receiptRef": run.cleanup_receipt},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def _owner_dependency(
    *,
    contract_ref: str,
    capability_id: str,
    adapter_id: str,
    typed_port: str,
) -> dict[str, Any]:
    path = (ROOT / contract_ref).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file() or path.is_symlink():
        raise ConformanceBlocked("Provider owner contract reference is unsafe")
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ConformanceBlocked("Provider owner contract is unreadable") from exc
    dependencies = payload.get("externalDependencies") if isinstance(payload, Mapping) else None
    matches = [
        item
        for item in dependencies or []
        if isinstance(item, Mapping) and item.get("capability") == capability_id
    ]
    if len(matches) != 1:
        raise ConformanceBlocked("Provider owner contract capability is not unique")
    dependency = matches[0]
    contracts = dependency.get("adapterContracts")
    adapter = contracts.get(adapter_id) if isinstance(contracts, Mapping) else None
    endpoint_envs = adapter.get("endpointEnvs") if isinstance(adapter, Mapping) else None
    operations = dependency.get("operations")
    if (
        dependency.get("port") != typed_port
        or not isinstance(endpoint_envs, Mapping)
        or not endpoint_envs
        or not isinstance(operations, list)
        or not operations
        or any(not isinstance(item, str) or not item for item in operations)
        or len(set(operations)) != len(operations)
    ):
        raise ConformanceBlocked("Provider owner contract probe metadata is invalid")
    return {
        "operations": list(operations),
        "endpointEnvs": {str(key): str(value) for key, value in endpoint_envs.items()},
    }


def _packaged_binding(composition: Mapping[str, Any], capability_id: str) -> Mapping[str, Any]:
    matches = [
        item
        for item in composition.get("bindings", [])
        if isinstance(item, Mapping) and item.get("capabilityId") == capability_id
    ]
    if len(matches) != 1:
        raise ConformanceBlocked("packaged Provider Binding is not unique")
    return matches[0]


def _provider_workload(composition: Mapping[str, Any]) -> Mapping[str, Any]:
    matches = [
        item
        for item in composition.get("workloads", [])
        if isinstance(item, Mapping) and item.get("role") == ROLE
    ]
    if len(matches) != 1:
        raise ConformanceBlocked("packaged generic Provider workload is not unique")
    return matches[0]


def _load_provider_material(target: str) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    root = deployment_work_root(target) / "provider-config"
    active = _read_protected_json(root / "active.json")
    material = _read_protected_json(root / "material.json")
    return active, material


def _read_protected_json(path: Path) -> Mapping[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ConformanceBlocked(f"protected Provider material is unavailable: {path.name}")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise ConformanceBlocked(f"protected Provider material mode is unsafe: {path.name}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConformanceBlocked(f"protected Provider material is unreadable: {path.name}") from exc
    if not isinstance(payload, Mapping):
        raise ConformanceBlocked(f"protected Provider material is malformed: {path.name}")
    return payload


def _probe_request(
    context: RuntimeContext,
    operation: str,
    *,
    canary: str,
) -> tuple[str, str, Mapping[str, Any] | None]:
    internal = _endpoint_for_operation(context, operation)
    parsed = parse.urlsplit(internal)
    path = parsed.path
    query: Mapping[str, str] = {}
    body: Mapping[str, Any] | None = None
    method = "GET"
    capability = context.capability_id
    if capability == "assistant.model.generation":
        method = "POST"
        body = {
            "messages": [{"role": "user", "content": canary}],
            "stream": operation == "stream",
        }
    elif capability == "assistant.public.search":
        query = {"q": canary}
    elif capability == "assistant.weather.forecast":
        query = {"latitude": "30.2741", "longitude": "120.1551"}
    elif capability == "assistant.finance.quote":
        path = path.rstrip("/") + "/000001.SS"
    elif capability == "content.embedding.generation":
        method = "POST"
        body = {"input": [canary]}
    elif capability == "integration.location.lookup":
        if operation == "nearby":
            path = path.rstrip("/") + "/reverse_geocoding/v3/"
            query = {"location": "30.2741,120.1551"}
        elif operation == "search":
            path = path.rstrip("/") + "/place/v2/search"
            query = {"query": canary, "location": "30.2741,120.1551"}
        else:
            raise ConformanceBlocked(f"location operation {operation} has no protocol probe")
    elif capability == "identity.carrier.one_tap":
        method = "POST"
        body = {"token": canary}
    elif capability == "identity.social.login":
        method = "POST"
        if operation == "authorize":
            body = {"action": "authorize", "provider": "alipay"}
        elif operation == "resolveIdentity":
            body = {
                "action": "resolveIdentity",
                "provider": "wechat",
                "code": canary,
            }
        else:
            raise ConformanceBlocked(
                f"social operation {operation} has no substitute protocol mechanism"
            )
    elif capability == "integration.push.delivery":
        method = "POST"
        body = {"requestId": canary, "title": "conformance", "body": "conformance"}
    else:
        raise ConformanceBlocked(f"capability {capability} is not owned by the generic substitute")
    encoded_query = parse.urlencode(query)
    url = parse.urlunsplit(
        ("https", parse.urlsplit(context.host_origin).netloc, path, encoded_query, "")
    )
    return method, url, body


def _endpoint_for_operation(context: RuntimeContext, operation: str) -> str:
    if operation in context.endpoint_values:
        return context.endpoint_values[operation]
    aliases = {
        "assistant.model.generation": "completion",
        "assistant.finance.quote": "chart",
    }
    alias = aliases.get(context.capability_id)
    if alias is not None and alias in context.endpoint_values:
        return context.endpoint_values[alias]
    if len(context.endpoint_values) == 1:
        return next(iter(context.endpoint_values.values()))
    raise ConformanceBlocked(
        f"operation {operation} cannot be resolved from the selected Binding endpoint roles"
    )


def _validate_success(capability: str, operation: str, result: HTTPResult) -> None:
    if result.status not in {200, 202}:
        raise ConformanceBlocked(f"{capability}/{operation} success returned HTTP {result.status}")
    text = result.body.decode("utf-8", errors="replace")
    if capability == "assistant.public.search":
        if "result__a" not in text:
            raise ConformanceBlocked("public search success payload is malformed")
        return
    if capability == "assistant.model.generation" and operation == "stream":
        if "data: [DONE]" not in text:
            raise ConformanceBlocked("model stream success payload is malformed")
        return
    try:
        payload = json.loads(result.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConformanceBlocked(f"{capability} success payload is not JSON") from exc
    if capability == "assistant.model.generation":
        valid = isinstance(payload.get("choices"), list)
    elif capability == "assistant.weather.forecast":
        valid = isinstance(payload.get("current"), Mapping)
    elif capability == "assistant.finance.quote":
        valid = isinstance(payload.get("chart"), Mapping)
    elif capability == "content.embedding.generation":
        valid = isinstance(payload.get("data"), list) and bool(payload["data"])
    elif capability == "integration.location.lookup":
        valid = payload.get("status") == 0 and (
            isinstance(payload.get("result"), Mapping)
            or isinstance(payload.get("results"), list)
        )
    elif capability == "identity.carrier.one_tap":
        valid = str(payload.get("phone") or "").startswith("+")
    elif capability == "identity.social.login":
        if operation == "authorize":
            valid = bool(str(payload.get("payload") or "")) and bool(
                str(payload.get("expiresAt") or "")
            )
        else:
            valid = bool(str(payload.get("credentialKey") or ""))
    elif capability == "integration.push.delivery":
        valid = bool(str(payload.get("providerRequestId") or ""))
    else:
        valid = False
    if not valid:
        raise ConformanceBlocked(f"{capability}/{operation} success payload is malformed")


def _aggregate_assertion(
    assertion_id: str,
    invocations: Sequence[InvocationEvidence],
) -> AssertionEvidence:
    if not invocations:
        raise ConformanceBlocked(f"{assertion_id} has no invocation evidence")
    material = [
        {
            "operation": item.operation,
            "outcome": item.outcome,
            "status": item.status,
            "requestDigest": item.request_digest,
            "traceDigest": item.trace_digest,
            "receiptRef": item.receipt_ref,
            "callOrdinal": item.call_ordinal,
            "effectOrdinal": item.effect_ordinal,
            "idempotencyKeyDigest": item.idempotency_key_digest,
            "idempotencyState": item.idempotency_state,
            "networkHostDigest": item.network_host_digest,
            "tlsServerNameDigest": item.tls_server_name_digest,
            "tlsVersion": item.tls_version,
        }
        for item in invocations
    ]
    digest = _sha256_json({"assertionId": assertion_id, "invocations": material})
    normalized_capability = assertion_id.replace(".", "_")
    return AssertionEvidence(
        assertion_id=assertion_id,
        scene_receipt_ref="receipt:provider-protocol-scene:" + digest[7:31],
        log_ref="log:provider-protocol-substitute:" + digest[7:31],
        trace_ref="trace:provider-protocol-substitute:" + digest[31:55],
        metric_refs=("metric:provider-protocol-substitute:" + normalized_capability,),
    )


def _provider_request_digest(method: str, url: str, request_id: str) -> str:
    parsed = parse.urlsplit(url)
    material = f"{method}\n{parsed.path}\n{parsed.query}\n{request_id}"
    return _sha256_text("request\n" + material)


def _receipt_ref(kind: str, value: object) -> str:
    return "receipt:" + kind + ":" + _sha256_json(value)[7:31]


def _sha256_json(value: object) -> str:
    return _sha256_text(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def _sha256_text(value: str) -> str:
    return _DIGEST_PREFIX + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _required_assertion_ids() -> tuple[str, ...]:
    raw = _required_environment("QWQ_PROVIDER_CONFORMANCE_ASSERTION_IDS")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConformanceBlocked("source assertion IDs are not valid JSON") from exc
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item for item in value)
        or len(set(value)) != len(value)
    ):
        raise ConformanceBlocked("source assertion IDs are invalid")
    return tuple(value)


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConformanceBlocked(f"{name} is required")
    return value


def diagnostic_payload(context: RuntimeContext, run: SupportedRun) -> dict[str, Any]:
    """Return a secret-free blocked-run diagnostic; it is never CaseResult evidence."""

    return {
        "schema": "generic-provider-protocol-conformance-diagnostic",
        "status": "GATE_BLOCK" if run.blocked_assertion_ids else "ready",
        "environment": context.environment,
        "target": context.target,
        "baselineId": context.baseline_id,
        "attemptId": context.attempt_id,
        "runtimeConfigDigest": context.runtime_config_digest,
        "runtimeCompositionDigest": context.runtime_composition_digest,
        "capabilityId": context.capability_id,
        "adapterId": context.adapter_id,
        "operations": list(context.operations),
        "supportedAssertionIds": list(run.supported_assertion_ids),
        "blockedAssertionIds": list(run.blocked_assertion_ids),
        "readbackDigest": run.readback_digest,
        "cleanupReceipt": run.cleanup_receipt,
    }
