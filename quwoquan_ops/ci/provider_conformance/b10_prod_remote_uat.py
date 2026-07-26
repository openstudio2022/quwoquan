"""Validate B10 two-device Prod Remote UAT and emit Provider CaseResults.

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


READBACK_SCHEMA = "b10-remote-uat-readback"
READBACK_VERSION = 1
SENSITIVE_VALUE_RE = re.compile(
    r"(?:endpoint|secret|credential|token|password|https?://)",
    re.IGNORECASE,
)
RECEIPT_RE = re.compile(r"^receipt:[a-z0-9][a-z0-9._:-]{2,255}$")
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


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _device_hash(device_id: str) -> str:
    return f"sha256:{hashlib.sha256(device_id.encode('utf-8')).hexdigest()}"


def _load_command() -> list[str]:
    raw = _required_env("QWQ_B10_REMOTE_UAT_COMMAND_JSON")
    try:
        command = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("QWQ_B10_REMOTE_UAT_COMMAND_JSON must be a JSON argv") from exc
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(item, str) and item for item in command)
    ):
        raise ValueError("QWQ_B10_REMOTE_UAT_COMMAND_JSON must contain a non-empty argv")
    return command


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
    expected_hashes = {
        _device_hash(_required_env("QWQ_B10_IOS_DEVICE_ID")),
        _device_hash(_required_env("QWQ_B10_ANDROID_DEVICE_ID")),
    }
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("deviceEvidence must contain exactly the iOS and Android devices")
    observed_hashes: set[str] = set()
    platforms: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {
            "platform",
            "deviceHash",
            "appVersion",
            "caseDirection",
        }:
            raise ValueError("deviceEvidence items have an invalid shape")
        platform = item.get("platform")
        device_hash = item.get("deviceHash")
        if platform not in {"ios", "android"} or not isinstance(device_hash, str):
            raise ValueError("deviceEvidence must identify iOS and Android with hashes only")
        if not SHA256_RE.fullmatch(device_hash):
            raise ValueError("deviceEvidence.deviceHash must be a sha256 digest")
        if not isinstance(item.get("appVersion"), str) or not item["appVersion"]:
            raise ValueError("deviceEvidence.appVersion is required")
        if item.get("caseDirection") not in {
            "ios_to_android",
            "android_to_ios",
        }:
            raise ValueError("deviceEvidence.caseDirection is invalid")
        observed_hashes.add(device_hash)
        platforms.add(platform)
    if platforms != {"ios", "android"} or observed_hashes != expected_hashes:
        raise ValueError("deviceEvidence must match the configured physical device pair")


def _validate_provider_receipts(capability_id: str, value: object) -> None:
    required_kinds = CAPABILITY_PROVIDER_KINDS.get(capability_id)
    if required_kinds is None:
        raise ValueError(f"unsupported B10 capability: {capability_id}")
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
        raise ValueError("providerReceipts omit required B10 provider readback")


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
        "version",
        "status",
        "capabilityId",
        "adapterId",
        "imageDigest",
        "configDigest",
        "deviceEvidence",
        "providerReceipts",
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
        or payload.get("version") != READBACK_VERSION
        or payload.get("status") != "passed"
        or payload.get("capabilityId") != capability_id
        or payload.get("adapterId") != adapter_id
    ):
        raise ValueError("native-device patrol readback does not identify the requested B10 case")
    if payload.get("imageDigest") != _required_env(
        "QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST"
    ):
        raise ValueError("native-device patrol readback does not bind the active image")
    if payload.get("configDigest") != config_digest:
        raise ValueError("native-device patrol readback does not bind the selected config")
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
    if not isinstance(realtime_readback, Mapping) or not RECEIPT_RE.fullmatch(
        str(realtime_readback.get("receiptRef"))
    ):
        raise ValueError("realtimeReadback must contain a non-sensitive receipt")
    chat_projection = payload.get("chatProjection")
    if not isinstance(chat_projection, Mapping) or chat_projection != {
        "systemCallLogCount": 1
    }:
        raise ValueError("chatProjection must prove exactly one system call log")
    qoe = payload.get("qoeReadback")
    if not isinstance(qoe, Mapping) or set(qoe) != {
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


def run(capability_id: str, adapter_id: str) -> int:
    result_path = Path(_required_env("QWQ_PROVIDER_CONFORMANCE_RESULT_PATH"))
    environment = _required_env("QWQ_PROVIDER_CONFORMANCE_ENVIRONMENT")
    if environment != "prod":
        raise ValueError("B10 Remote UAT only supports Prod")
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
            "Provider Conformance source assertions are invalid for B10 Remote"
        )
    result_path.parent.mkdir(parents=True, exist_ok=True)
    readback_path = result_path.with_name(
        f"{result_path.stem}.native-device-readback.json"
    )
    command_environment = {
        **os.environ,
        "QWQ_B10_REMOTE_UAT_READBACK_PATH": str(readback_path),
        "QWQ_B10_REMOTE_UAT_CAPABILITY_ID": capability_id,
        "QWQ_B10_REMOTE_UAT_ADAPTER_ID": adapter_id,
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
        "version": 1,
        "status": "passed",
        "adapterId": adapter_id,
        "capabilityId": capability_id,
        "environment": environment,
        "testLayer": "user_acceptance",
        "typedPort": _required_env("QWQ_PROVIDER_CONFORMANCE_TYPED_PORT"),
        "contractRef": _required_env("QWQ_PROVIDER_CONFORMANCE_CONTRACT_REF"),
        "networkBoundary": "user_journey",
        "testTarget": f"b10-remote-{capability_id}",
        "configDigest": _required_env("QWQ_PROVIDER_CONFORMANCE_CONFIG_DIGEST"),
        "assertionIds": assertion_ids,
        "caseResults": assertion_results,
        "dataDigest": data_digest,
        "cleanupReceipt": cleanup_receipt,
        "observabilityRefs": observability_refs,
        "releaseReadiness": release_readiness,
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
        raise SystemExit("usage: b10_remote_uat.py <capability-id> <adapter-id>")
    try:
        return run(argv[0], argv[1])
    except ValueError as exc:
        print(f"[b10-remote-uat] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
