"""面向单个 package-bound generic substitute 的严格 HTTPS 协议客户端。"""
from __future__ import annotations

import json
import secrets
import ssl
from collections.abc import Mapping
from typing import Any
from urllib import error, parse, request

from quwoquan_ops.ci.provider_conformance.generic_protocol_substitute_lib.evidence_helpers import (
    _probe_request,
    _provider_request_digest,
    _receipt_ref,
    _sha256_text,
)
from quwoquan_ops.ci.provider_conformance.generic_protocol_substitute_lib.models import (
    ADAPTER_ID,
    ConformanceBlocked,
    HTTPResult,
    InvocationEvidence,
    RuntimeContext,
)

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
