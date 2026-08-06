"""Validate the Provider two-device Prod Remote UAT and emit Provider CaseResults.

This runner does not drive provider APIs itself.  CI supplies an immutable argv
for the native-device patrol, and the patrol owns every observed assertion.
Only a passed, non-sensitive readback from that patrol can be converted into a
Provider Conformance CaseResult.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Mapping


READBACK_SCHEMA = "provider-remote-uat-readback"
SENSITIVE_VALUE_RE = re.compile(
    r"(?:endpoint|secret|credential|token|password|https?://)",
    re.IGNORECASE,
)
RECEIPT_RE = re.compile(r"^receipt:[a-z0-9][a-z0-9._:-]{2,255}$")
HOSTED_RECEIPT_RE = re.compile(r"^receipt:hosted:[a-f0-9]{64}$")
SHA256_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
RELEASE_ASSERTIONS = frozenset(
    {
        "provider.adapter_health",
        "provider.adapter_switch",
        "provider.adapter_rollback",
    }
)
CAPABILITY_PROVIDER_KINDS = {
    "rtc.room.transport": frozenset({"livekit"}),
    "integration.push.delivery": frozenset({"apns_voip", "fcm"}),
    "runtime.message.transport": frozenset({"redis_stream"}),
}
CAPABILITY_ASSERTIONS = {
    "rtc.room.transport": "provider.rtc_transport",
    "integration.push.delivery": "provider.push_delivery",
    "runtime.message.transport": "provider.redis_message_transport",
}
SOURCE_OWNED_PATROL_COMMAND = (
    "python3",
    "quwoquan_ops/ci/provider_conformance/run_prod_remote_patrol_uat.py",
)


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _device_hash(device_id: str) -> str:
    return f"sha256:{hashlib.sha256(device_id.encode('utf-8')).hexdigest()}"


def _load_command() -> list[str]:
    """Return the only source-owned Provider two-device production harness."""
    if os.environ.get("QWQ_PROVIDER_UAT_REMOTE_UAT_COMMAND_JSON", "").strip():
        raise ValueError(
            "QWQ_PROVIDER_UAT_REMOTE_UAT_COMMAND_JSON is forbidden; "
            "Provider two-device Remote UAT must run the source-owned Patrol harness"
        )
    return list(SOURCE_OWNED_PATROL_COMMAND)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("native-device patrol did not write a valid readback") from exc
    if not isinstance(payload, dict):
        raise ValueError("native-device patrol readback root must be an object")
    return payload


def _string_list(value: object, *, name: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
    ):
        raise ValueError(f"{name} must be a non-empty string list")
    return list(value)


def _validate_observability(value: object) -> dict[str, list[str]]:
    if not isinstance(value, Mapping) or set(value) != {"logs", "traces", "metrics"}:
        raise ValueError("observabilityRefs must contain logs, traces and metrics")
    return {
        key: _string_list(value.get(key), name=f"observabilityRefs.{key}")
        for key in ("logs", "traces", "metrics")
    }


def _validate_device_evidence(value: object) -> None:
    ios_device_id = _required_env("QWQ_PROVIDER_UAT_IOS_DEVICE_ID")
    android_device_id = _required_env("QWQ_PROVIDER_UAT_ANDROID_DEVICE_ID")
    if ios_device_id == android_device_id:
        raise ValueError("Provider two-device Remote UAT requires distinct iOS and Android physical devices")
    expected_hashes = {
        _device_hash(ios_device_id),
        _device_hash(android_device_id),
    }
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("deviceEvidence must contain exactly the iOS and Android devices")
    observed_hashes: set[str] = set()
    platforms: set[str] = set()
    directions: set[str] = set()
    expected_application_digests = {
        "ios": _required_env("QWQ_PROVIDER_UAT_IOS_APPLICATION_DIGEST"),
        "android": _required_env("QWQ_PROVIDER_UAT_ANDROID_APPLICATION_DIGEST"),
    }
    if not all(SHA256_RE.fullmatch(value) for value in expected_application_digests.values()):
        raise ValueError("Provider two-device application identities must be immutable sha256 digests")
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {
            "platform",
            "deviceHash",
            "applicationDigest",
            "caseDirection",
        }:
            raise ValueError("deviceEvidence items have an invalid shape")
        platform = item.get("platform")
        device_hash = item.get("deviceHash")
        if platform not in {"ios", "android"} or not isinstance(device_hash, str):
            raise ValueError("deviceEvidence must identify iOS and Android with hashes only")
        if not SHA256_RE.fullmatch(device_hash):
            raise ValueError("deviceEvidence.deviceHash must be a sha256 digest")
        if item.get("applicationDigest") != expected_application_digests[platform]:
            raise ValueError(
                "deviceEvidence.applicationDigest must bind the exact platform package"
            )
        if item.get("caseDirection") not in {
            "ios_to_android",
            "android_to_ios",
        }:
            raise ValueError("deviceEvidence.caseDirection is invalid")
        observed_hashes.add(device_hash)
        platforms.add(platform)
        directions.add(str(item["caseDirection"]))
    if platforms != {"ios", "android"} or observed_hashes != expected_hashes:
        raise ValueError("deviceEvidence must match the configured physical device pair")
    if directions != {"ios_to_android", "android_to_ios"}:
        raise ValueError(
            "deviceEvidence must prove both iOS-to-Android and Android-to-iOS call directions"
        )


def _validate_provider_receipts(capability_id: str, value: object) -> None:
    required_kinds = CAPABILITY_PROVIDER_KINDS.get(capability_id)
    if required_kinds is None:
        raise ValueError(f"unsupported Provider two-device capability: {capability_id}")
    if not isinstance(value, list) or not value:
        raise ValueError("providerReceipts must be non-empty")
    observed_kinds: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {"providerKind", "receiptRef"}:
            raise ValueError("providerReceipts items have an invalid shape")
        provider_kind = item.get("providerKind")
        receipt_ref = item.get("receiptRef")
        if not isinstance(provider_kind, str) or not RECEIPT_RE.fullmatch(str(receipt_ref)):
            raise ValueError("providerReceipts contain an invalid receipt")
        observed_kinds.add(provider_kind)
    if not required_kinds.issubset(observed_kinds):
        raise ValueError("providerReceipts omit required Provider two-device provider readback")


def _validate_readback(
    payload: Mapping[str, Any],
    *,
    capability_id: str,
    adapter_id: str,
    assertion_ids: list[str],
    config_digest: str,
) -> tuple[list[dict[str, Any]], str, str, dict[str, list[str]], dict[str, str]]:
    required = {
        "schema",
        "status",
        "capabilityId",
        "adapterId",
        "imageDigest",
        "configDigest",
        "contractGraphDigest",
        "adapterDigest",
        "deviceEvidence",
        "providerReceipts",
        "deliveryTimelines",
        "pushReadback",
        "callReadback",
        "realtimeReadback",
        "chatProjection",
        "qoeReadback",
        "assertions",
        "dataDigest",
        "cleanupReceipt",
        "observabilityRefs",
        "releaseReadiness",
    }
    if set(payload) != required:
        raise ValueError("native-device patrol readback has missing or unsupported fields")
    if (
        payload.get("schema") != READBACK_SCHEMA
        or payload.get("status") != "passed"
        or payload.get("capabilityId") != capability_id
        or payload.get("adapterId") != adapter_id
    ):
        raise ValueError("native-device patrol readback does not identify the requested Provider two-device case")
    if payload.get("imageDigest") != _required_env(
        "QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST"
    ):
        raise ValueError("native-device patrol readback does not bind the active image")
    if payload.get("configDigest") != config_digest:
        raise ValueError("native-device patrol readback does not bind the selected config")
    if payload.get("contractGraphDigest") != _required_env(
        "QWQ_PROVIDER_CONFORMANCE_CONTRACT_GRAPH_DIGEST"
    ):
        raise ValueError("native-device patrol readback does not bind the ContractGraph")
    if payload.get("adapterDigest") != _required_env(
        "QWQ_PROVIDER_CONFORMANCE_ADAPTER_DIGEST"
    ):
        raise ValueError("native-device patrol readback does not bind the selected adapter")
    _validate_device_evidence(payload.get("deviceEvidence"))
    _validate_provider_receipts(capability_id, payload.get("providerReceipts"))
    push_readback = payload.get("pushReadback")
    if not isinstance(push_readback, Mapping) or push_readback != {
        "ios": "pushkit_callkit",
        "android": "fcm_full_screen_or_heads_up",
    }:
        raise ValueError("pushReadback must prove the iOS and Android offline call paths")
    call_readback = payload.get("callReadback")
    if not isinstance(call_readback, Mapping) or call_readback != {
        "terminalState": "ended",
        "participantCount": 2,
        "mediaConnected": True,
        "screenShareCompleted": True,
        "pipHangup": True,
        "cancelRaceResolved": True,
    }:
        raise ValueError(
            "callReadback must prove media, screen share, PiP hangup and cancel-race closure"
        )
    realtime_readback = payload.get("realtimeReadback")
    if (
        not isinstance(realtime_readback, Mapping)
        or set(realtime_readback) != {"callIdDigests", "receiptRefs"}
        or not isinstance(realtime_readback.get("callIdDigests"), list)
        or len(realtime_readback["callIdDigests"]) != 2
        or not all(
            isinstance(value, str) and SHA256_RE.fullmatch(value)
            for value in realtime_readback["callIdDigests"]
        )
        or not isinstance(realtime_readback.get("receiptRefs"), list)
        or len(realtime_readback["receiptRefs"]) != 2
        or not all(
            isinstance(value, str) and RECEIPT_RE.fullmatch(value)
            for value in realtime_readback["receiptRefs"]
        )
    ):
        raise ValueError("realtimeReadback must bind both calls to receipt references")
    chat_projection = payload.get("chatProjection")
    chat_logs = (
        chat_projection.get("systemCallLogs")
        if isinstance(chat_projection, Mapping)
        else None
    )
    if (
        not isinstance(chat_projection, Mapping)
        or set(chat_projection) != {"systemCallLogs"}
        or not isinstance(chat_logs, list)
        or len(chat_logs) != 2
        or not all(
            isinstance(item, Mapping)
            and set(item) == {"callIdDigest", "count"}
            and isinstance(item.get("callIdDigest"), str)
            and SHA256_RE.fullmatch(item["callIdDigest"])
            and item.get("count") == 1
            for item in chat_logs
        )
    ):
        raise ValueError("chatProjection must prove exactly one system call log per call")
    qoe = payload.get("qoeReadback")
    if not isinstance(qoe, Mapping) or set(qoe) != {
        "calls",
        "effectiveSampleCount",
        "alertReceiptRef",
        "rollbackReceiptRef",
    }:
        raise ValueError("qoeReadback has an invalid shape")
    if not isinstance(qoe.get("effectiveSampleCount"), int) or qoe["effectiveSampleCount"] < 50:
        raise ValueError("qoeReadback requires at least 50 real terminal samples")
    if not RECEIPT_RE.fullmatch(str(qoe.get("alertReceiptRef"))) or not RECEIPT_RE.fullmatch(
        str(qoe.get("rollbackReceiptRef"))
    ):
        raise ValueError("qoeReadback requires alert and rollback receipts")
    qoe_calls = qoe.get("calls")
    if (
        not isinstance(qoe_calls, list)
        or len(qoe_calls) != 2
        or not all(
            isinstance(item, Mapping)
            and set(item)
            == {
                "callIdDigest",
                "sessionDigest",
                "terminalState",
                "mediaConnected",
                "connectLatencyMs",
                "reconnectCount",
            }
            and isinstance(item.get("callIdDigest"), str)
            and SHA256_RE.fullmatch(item["callIdDigest"])
            and isinstance(item.get("sessionDigest"), str)
            and SHA256_RE.fullmatch(item["sessionDigest"])
            and item.get("terminalState") == "ended"
            and item.get("mediaConnected") is True
            and isinstance(item.get("connectLatencyMs"), int)
            and item["connectLatencyMs"] >= 0
            and isinstance(item.get("reconnectCount"), int)
            and item["reconnectCount"] >= 0
            for item in qoe_calls
        )
    ):
        raise ValueError("qoeReadback must bind terminal QoE to both calls")
    delivery_timelines = payload.get("deliveryTimelines")
    if (
        not isinstance(delivery_timelines, list)
        or len(delivery_timelines) != 2
        or not all(
            isinstance(item, Mapping)
            and set(item)
            == {
                "callIdDigest",
                "deviceTimelineCount",
                "ringExternalAccepted",
                "ringProviderAccepted",
                "presentationAcknowledged",
                "cancelExternalAccepted",
                "cancelProviderAccepted",
            }
            and isinstance(item.get("callIdDigest"), str)
            and SHA256_RE.fullmatch(item["callIdDigest"])
            and isinstance(item.get("deviceTimelineCount"), int)
            and item["deviceTimelineCount"] >= 1
            and all(
                item.get(field) is True
                for field in (
                    "ringExternalAccepted",
                    "ringProviderAccepted",
                    "presentationAcknowledged",
                    "cancelExternalAccepted",
                    "cancelProviderAccepted",
                )
            )
            for item in delivery_timelines
        )
    ):
        raise ValueError("deliveryTimelines must prove per-device ring and cancel receipts")
    delivery_call_digests = {str(item["callIdDigest"]) for item in delivery_timelines}
    if len(delivery_call_digests) != 2:
        raise ValueError("deliveryTimelines must contain distinct call digests")
    if (
        set(realtime_readback["callIdDigests"]) != delivery_call_digests
        or {str(item["callIdDigest"]) for item in chat_logs} != delivery_call_digests
        or {str(item["callIdDigest"]) for item in qoe_calls} != delivery_call_digests
    ):
        raise ValueError(
            "delivery, realtime, chat, and QoE readback must bind the same calls"
        )
    assertions = payload.get("assertions")
    if not isinstance(assertions, list) or len(assertions) != len(assertion_ids):
        raise ValueError("native-device patrol must report every source assertion")
    assertion_results: list[dict[str, Any]] = []
    observed_assertions: set[str] = set()
    observability_refs = _validate_observability(payload.get("observabilityRefs"))
    for item in assertions:
        if not isinstance(item, Mapping) or set(item) != {
            "assertionId",
            "status",
            "logRef",
            "traceRef",
            "metricRefs",
        }:
            raise ValueError("native-device patrol assertion has an invalid shape")
        assertion_id = item.get("assertionId")
        metric_refs = _string_list(item.get("metricRefs"), name="assertion.metricRefs")
        if (
            assertion_id not in assertion_ids
            or item.get("status") != "passed"
            or not isinstance(item.get("logRef"), str)
            or not item["logRef"]
            or not isinstance(item.get("traceRef"), str)
            or not item["traceRef"]
        ):
            raise ValueError("native-device patrol assertion is incomplete")
        if (
            item["logRef"] not in observability_refs["logs"]
            or item["traceRef"] not in observability_refs["traces"]
            or not set(metric_refs).issubset(observability_refs["metrics"])
        ):
            raise ValueError("assertion observability references are not declared")
        observed_assertions.add(assertion_id)
        assertion_results.append(
            {
                "assertionId": assertion_id,
                "status": "passed",
                "logRef": item["logRef"],
                "traceRef": item["traceRef"],
                "metricRefs": metric_refs,
            }
        )
    if observed_assertions != set(assertion_ids):
        raise ValueError("native-device patrol assertions do not match the source contract")
    data_digest = payload.get("dataDigest")
    cleanup_receipt = payload.get("cleanupReceipt")
    if not isinstance(data_digest, str) or not SHA256_RE.fullmatch(data_digest):
        raise ValueError("native-device patrol dataDigest must be sha256")
    if not isinstance(cleanup_receipt, str) or not RECEIPT_RE.fullmatch(cleanup_receipt):
        raise ValueError("native-device patrol cleanupReceipt is invalid")
    release_readiness = payload.get("releaseReadiness")
    if not isinstance(release_readiness, Mapping) or set(release_readiness) != {
        "bindingPreflightReceiptRef",
        "adapterHealthReceiptRef",
        "switchCompatibilityReceiptRef",
        "callbackDrainReceiptRef",
        "lastGoodReceiptRef",
        "rollbackReceiptRef",
    } or not all(
        isinstance(value, str) and RECEIPT_RE.fullmatch(value)
        for value in release_readiness.values()
    ) or any(
        HOSTED_RECEIPT_RE.fullmatch(str(release_readiness[field])) is None
        for field in ("lastGoodReceiptRef", "rollbackReceiptRef")
    ):
        raise ValueError("native-device patrol releaseReadiness is invalid")
    raw = json.dumps(payload, sort_keys=True)
    if SENSITIVE_VALUE_RE.search(raw):
        raise ValueError("native-device patrol readback contains sensitive runtime material")
    return (
        assertion_results,
        data_digest,
        cleanup_receipt,
        observability_refs,
        dict(release_readiness),
    )


def _readback_digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def run(capability_id: str, adapter_id: str) -> int:
    result_path = Path(_required_env("QWQ_PROVIDER_CONFORMANCE_RESULT_PATH"))
    environment = _required_env("QWQ_PROVIDER_CONFORMANCE_ENVIRONMENT")
    if environment != "prod":
        raise ValueError("Provider two-device Remote UAT only supports Prod")
    try:
        assertion_ids = json.loads(
            _required_env("QWQ_PROVIDER_CONFORMANCE_ASSERTION_IDS")
        )
    except json.JSONDecodeError as exc:
        raise ValueError(
            "QWQ_PROVIDER_CONFORMANCE_ASSERTION_IDS must be a JSON list"
        ) from exc
    required_capability_assertion = CAPABILITY_ASSERTIONS.get(capability_id)
    if (
        not isinstance(assertion_ids, list)
        or not all(isinstance(item, str) for item in assertion_ids)
        or not RELEASE_ASSERTIONS.issubset(set(assertion_ids))
        or required_capability_assertion not in assertion_ids
    ):
        raise ValueError(
            "Provider Conformance source assertions are invalid for Provider two-device Remote"
        )
    result_path.parent.mkdir(parents=True, exist_ok=True)
    readback_path = result_path.with_name(
        f"{result_path.stem}.native-device-readback.json"
    )
    command_environment = {
        **os.environ,
        "QWQ_PROVIDER_UAT_REMOTE_UAT_READBACK_PATH": str(readback_path),
        "QWQ_PROVIDER_UAT_REMOTE_UAT_CAPABILITY_ID": capability_id,
        "QWQ_PROVIDER_UAT_REMOTE_UAT_ADAPTER_ID": adapter_id,
    }
    completed = subprocess.run(
        _load_command(),
        check=False,
        env=command_environment,
    )
    if completed.returncode != 0:
        raise ValueError("native-device patrol did not complete successfully")
    (
        assertion_results,
        data_digest,
        cleanup_receipt,
        observability_refs,
        release_readiness,
    ) = _validate_readback(
        _load_json(readback_path),
        capability_id=capability_id,
        adapter_id=adapter_id,
        assertion_ids=assertion_ids,
        config_digest=_required_env("QWQ_PROVIDER_CONFORMANCE_CONFIG_DIGEST"),
    )
    case_result = {
        "schema": "provider-conformance-case-results",
        "status": "passed",
        "adapterId": adapter_id,
        "capabilityId": capability_id,
        "environment": environment,
        "testLayer": "user_acceptance",
        "typedPort": _required_env("QWQ_PROVIDER_CONFORMANCE_TYPED_PORT"),
        "contractRef": _required_env("QWQ_PROVIDER_CONFORMANCE_CONTRACT_REF"),
        "networkBoundary": "user_journey",
        "testTarget": f"provider-remote-{capability_id}",
        "configDigest": _required_env("QWQ_PROVIDER_CONFORMANCE_CONFIG_DIGEST"),
        "assertionIds": assertion_ids,
        "caseResults": assertion_results,
        "dataDigest": data_digest,
        "cleanupReceipt": cleanup_receipt,
        "observabilityRefs": observability_refs,
        "releaseReadiness": release_readiness,
        "nativeReadback": {
            "schema": READBACK_SCHEMA,
            "artifactName": readback_path.name,
            "artifactDigest": _readback_digest(readback_path),
        },
    }
    result_path.write_text(
        json.dumps(case_result, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if len(argv) != 2:
        raise SystemExit("usage: run_prod_remote_uat.py <capability-id> <adapter-id>")
    try:
        return run(argv[0], argv[1])
    except ValueError as exc:
        print(f"[provider-remote-uat] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
