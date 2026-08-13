"""generic substitute 探针请求构造、成功校验、摘要与断言证据聚合。"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib import parse

import yaml

from quwoquan_ops.cli.lib.output_paths import deployment_work_root

from quwoquan_ops.ci.provider_conformance.generic_protocol_substitute_lib.models import (
    ROLE,
    ROOT,
    _DIGEST_PREFIX,
    AssertionEvidence,
    ConformanceBlocked,
    HTTPResult,
    InvocationEvidence,
    RuntimeContext,
    SupportedRun,
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
    elif capability == "location.poi.search":
        if operation != "search":
            raise ConformanceBlocked(f"POI operation {operation} has no protocol probe")
        # Nominatim compatible wire consumed by the integration-service client.
        path = path.rstrip("/") + "/search"
        query = {
            "q": canary,
            "format": "jsonv2",
            "addressdetails": "1",
            "limit": "3",
        }
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
    elif capability == "location.poi.search":
        valid = (
            isinstance(payload, list)
            and bool(payload)
            and all(
                isinstance(row, Mapping)
                and str(row.get("lat") or "").strip()
                and str(row.get("lon") or "").strip()
                and (
                    str(row.get("name") or "").strip()
                    or str(row.get("display_name") or "").strip()
                )
                for row in payload
            )
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
