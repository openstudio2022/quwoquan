"""Run the source-owned Provider two-device Prod Remote Patrol journey.

The harness drives both physical directions: iOS→Android exercises FCM
presentation, screen-share and PiP hangup; Android→iOS exercises PushKit /
CallKit presentation. Provider-control-plane receipts are collected by the
approved hosted operator probe and supplied as a non-sensitive sidecar. Missing
devices, credentials, native observations, or operator receipts fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time
from typing import Any, Mapping
import urllib.error
import urllib.request
import uuid


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.environment_topology import (  # noqa: E402
    get_target,
    load_environment_topology,
)


_PATROL_TARGET = (
    "test/user_acceptance/service/rtc_service/rtc/call_session/"
    "provider_prod_remote_call_provider__user_acceptance_test.dart"
)
_RECEIPT_RE = re.compile(r"^receipt:[a-z0-9][a-z0-9._:-]{2,255}$")
_SHA256_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
_HOSTED_RECEIPT_REF_RE = re.compile(r"^receipt:hosted:([a-f0-9]{64})$")
_SENSITIVE_VALUE_RE = re.compile(
    r"(?:endpoint|secret|credential|token|password|https?://)",
    re.IGNORECASE,
)
_RECEIPT_REF_RE = re.compile(r"^receipt:[a-z0-9][a-z0-9._:-]{2,255}$")


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _sha256(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _device_hash(device_id: str) -> str:
    return _sha256(device_id.encode("utf-8"))


def _request_json(
    *,
    base_url: str,
    method: str,
    path: str,
    token: str,
    owner_id: str,
    persona_id: str,
    body: dict[str, Any] | None = None,
    idempotency_key: str = "",
) -> dict[str, Any]:
    payload = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "X-Client-Page-Id": "rtc.provider.prod_remote_uat",
        "X-Client-User-Id": owner_id,
        "X-Client-Persona-Id": persona_id,
        "X-Request-Id": f"ProviderUAT.{uuid.uuid4().hex}",
        "X-Trace-Id": f"ProviderUAT.{uuid.uuid4().hex}",
    }
    if body is not None:
        payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=payload,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        exc.read()
        raise ValueError(
            f"Provider two-device Prod Remote API request failed: {method} {path} HTTP {exc.code}"
        ) from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"Provider two-device Prod Remote API request failed: {method} {path}") from exc
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Provider two-device Prod Remote API response is not JSON: {method} {path}"
        ) from exc
    if not isinstance(decoded, dict):
        raise ValueError(f"Provider two-device Prod Remote API response is not an object: {path}")
    return decoded


def _find_string(value: object, keys: frozenset[str]) -> str:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if key in keys and isinstance(nested, str) and nested.strip():
                return nested.strip()
        for nested in value.values():
            found = _find_string(nested, keys)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_string(nested, keys)
            if found:
                return found
    return ""


def _require_call_digest_set(value: object, *, expected: set[str], field: str) -> None:
    if (
        not isinstance(value, list)
        or len(value) != len(expected)
        or not all(isinstance(item, str) and _SHA256_RE.fullmatch(item) for item in value)
        or set(value) != expected
    ):
        raise ValueError(f"Provider two-device operator readback {field} must bind every executed call")


def _validate_operator_evidence(
    payload: Mapping[str, Any],
    *,
    expected_call_digests: set[str],
) -> None:
    timelines = payload.get("deliveryTimelines")
    if not isinstance(timelines, list) or len(timelines) != len(expected_call_digests):
        raise ValueError("Provider two-device operator readback must include one delivery timeline per call")
    observed_timeline_calls: set[str] = set()
    for item in timelines:
        if not isinstance(item, Mapping) or set(item) != {
            "callIdDigest",
            "deviceTimelineCount",
            "ringExternalAccepted",
            "ringProviderAccepted",
            "presentationAcknowledged",
            "cancelExternalAccepted",
            "cancelProviderAccepted",
        }:
            raise ValueError("Provider two-device operator delivery timeline has an invalid shape")
        call_digest = item.get("callIdDigest")
        if (
            not isinstance(call_digest, str)
            or not _SHA256_RE.fullmatch(call_digest)
            or not isinstance(item.get("deviceTimelineCount"), int)
            or item["deviceTimelineCount"] < 1
            or any(
                item.get(field) is not True
                for field in (
                    "ringExternalAccepted",
                    "ringProviderAccepted",
                    "presentationAcknowledged",
                    "cancelExternalAccepted",
                    "cancelProviderAccepted",
                )
            )
        ):
            raise ValueError("Provider two-device operator delivery timeline is incomplete")
        observed_timeline_calls.add(call_digest)
    if observed_timeline_calls != expected_call_digests:
        raise ValueError("Provider two-device operator delivery timelines do not bind every executed call")

    realtime = payload.get("realtimeReadback")
    if not isinstance(realtime, Mapping) or set(realtime) != {
        "callIdDigests",
        "receiptRefs",
    }:
        raise ValueError("Provider two-device operator realtime readback has an invalid shape")
    _require_call_digest_set(
        realtime.get("callIdDigests"),
        expected=expected_call_digests,
        field="realtimeReadback.callIdDigests",
    )
    receipt_refs = realtime.get("receiptRefs")
    if (
        not isinstance(receipt_refs, list)
        or len(receipt_refs) != len(expected_call_digests)
        or not all(
            isinstance(value, str) and _RECEIPT_REF_RE.fullmatch(value)
            for value in receipt_refs
        )
    ):
        raise ValueError("Provider two-device operator realtime readback is incomplete")

    chat = payload.get("chatProjection")
    if not isinstance(chat, Mapping) or set(chat) != {"systemCallLogs"}:
        raise ValueError("Provider two-device operator chat projection has an invalid shape")
    logs = chat.get("systemCallLogs")
    if not isinstance(logs, list) or len(logs) != len(expected_call_digests):
        raise ValueError("Provider two-device operator chat projection must include one log per call")
    observed_chat_calls: set[str] = set()
    for item in logs:
        if (
            not isinstance(item, Mapping)
            or set(item) != {"callIdDigest", "count"}
            or not isinstance(item.get("callIdDigest"), str)
            or not _SHA256_RE.fullmatch(item["callIdDigest"])
            or item.get("count") != 1
        ):
            raise ValueError("Provider two-device operator chat system-call log is invalid")
        observed_chat_calls.add(item["callIdDigest"])
    if observed_chat_calls != expected_call_digests:
        raise ValueError("Provider two-device operator chat projection does not bind every executed call")

    qoe = payload.get("qoeReadback")
    if not isinstance(qoe, Mapping) or set(qoe) != {
        "calls",
        "effectiveSampleCount",
        "alertReceiptRef",
        "rollbackReceiptRef",
    }:
        raise ValueError("Provider two-device operator QoE readback has an invalid shape")
    if not isinstance(qoe.get("effectiveSampleCount"), int) or qoe["effectiveSampleCount"] < 50:
        raise ValueError("Provider two-device operator QoE readback requires at least 50 terminal samples")
    for field in ("alertReceiptRef", "rollbackReceiptRef"):
        if not isinstance(qoe.get(field), str) or not _RECEIPT_REF_RE.fullmatch(qoe[field]):
            raise ValueError("Provider two-device operator QoE readback requires receipt references")
    calls = qoe.get("calls")
    if not isinstance(calls, list) or len(calls) != len(expected_call_digests):
        raise ValueError("Provider two-device operator QoE readback must include one session per call")
    observed_qoe_calls: set[str] = set()
    for item in calls:
        if not isinstance(item, Mapping) or set(item) != {
            "callIdDigest",
            "sessionDigest",
            "terminalState",
            "mediaConnected",
            "connectLatencyMs",
            "reconnectCount",
        }:
            raise ValueError("Provider two-device operator QoE session readback has an invalid shape")
        if (
            not isinstance(item.get("callIdDigest"), str)
            or not _SHA256_RE.fullmatch(item["callIdDigest"])
            or not isinstance(item.get("sessionDigest"), str)
            or not _SHA256_RE.fullmatch(item["sessionDigest"])
            or item.get("terminalState") != "ended"
            or item.get("mediaConnected") is not True
            or not isinstance(item.get("connectLatencyMs"), int)
            or item["connectLatencyMs"] < 0
            or not isinstance(item.get("reconnectCount"), int)
            or item["reconnectCount"] < 0
        ):
            raise ValueError("Provider two-device operator QoE session readback is incomplete")
        observed_qoe_calls.add(item["callIdDigest"])
    if observed_qoe_calls != expected_call_digests:
        raise ValueError("Provider two-device operator QoE sessions do not bind every executed call")


def _load_operator_receipts(*, call_ids: tuple[str, ...]) -> dict[str, Any]:
    """Load signed-operator output only after Patrol observed the user journey."""
    path = Path(_required("QWQ_PROVIDER_UAT_OPERATOR_READBACK_PATH")).expanduser()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("QWQ_PROVIDER_UAT_OPERATOR_READBACK_PATH must contain valid JSON") from exc
    required = {
        "schema",
        "imageDigest",
        "configDigest",
        "contractGraphDigest",
        "adapterDigest",
        "callIdDigests",
        "providerReceipts",
        "deliveryTimelines",
        "realtimeReadback",
        "chatProjection",
        "qoeReadback",
        "assertions",
        "observabilityRefs",
        "releaseReadiness",
        "cleanupReceipt",
    }
    if (
        not isinstance(payload, dict)
        or set(payload) != required
        or payload.get("schema") != "provider-prod-operator-readback"
    ):
        raise ValueError("Provider two-device operator readback has an invalid schema")
    expected_digests = {
        "imageDigest": _required("QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST"),
        "configDigest": _required("QWQ_PROVIDER_CONFORMANCE_CONFIG_DIGEST"),
        "contractGraphDigest": _required(
            "QWQ_PROVIDER_CONFORMANCE_CONTRACT_GRAPH_DIGEST"
        ),
        "adapterDigest": _required("QWQ_PROVIDER_CONFORMANCE_ADAPTER_DIGEST"),
    }
    for field, expected in expected_digests.items():
        if not _SHA256_RE.fullmatch(expected) or payload.get(field) != expected:
            raise ValueError(
                "Provider two-device operator readback must bind the active image, config, "
                "ContractGraph and adapter digests"
            )
    expected_call_digests = {_sha256(call_id.encode("utf-8")) for call_id in call_ids}
    _require_call_digest_set(
        payload.get("callIdDigests"),
        expected=expected_call_digests,
        field="callIdDigests",
    )
    _validate_operator_evidence(
        payload,
        expected_call_digests=expected_call_digests,
    )
    _validated_operator_assertions(payload)
    _validate_hosted_release_receipts(payload)
    if _SENSITIVE_VALUE_RE.search(json.dumps(payload, sort_keys=True)):
        raise ValueError("Provider two-device operator readback contains sensitive runtime material")
    return payload


def _validated_operator_assertions(
    operator: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Accept only operator-observed scenes; metadata may not create passes."""

    try:
        assertion_ids = json.loads(
            _required("QWQ_PROVIDER_CONFORMANCE_ASSERTION_IDS")
        )
    except json.JSONDecodeError as exc:
        raise ValueError(
            "QWQ_PROVIDER_CONFORMANCE_ASSERTION_IDS must be a string list"
        ) from exc
    if (
        not isinstance(assertion_ids, list)
        or not assertion_ids
        or not all(isinstance(value, str) and value for value in assertion_ids)
        or len(set(assertion_ids)) != len(assertion_ids)
    ):
        raise ValueError(
            "QWQ_PROVIDER_CONFORMANCE_ASSERTION_IDS must be a unique string list"
        )
    observability = operator.get("observabilityRefs")
    if not isinstance(observability, Mapping) or not all(
        isinstance(observability.get(key), list) and observability[key]
        for key in ("logs", "traces", "metrics")
    ):
        raise ValueError("Provider two-device operator readback observabilityRefs are incomplete")
    allowed_logs = set(observability["logs"])
    allowed_traces = set(observability["traces"])
    allowed_metrics = set(observability["metrics"])
    assertions = operator.get("assertions")
    if not isinstance(assertions, list) or len(assertions) != len(assertion_ids):
        raise ValueError(
            "Provider two-device operator readback must provide one observed scene per assertion"
        )
    observed: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(assertions):
        if not isinstance(item, Mapping) or set(item) != {
            "assertionId",
            "status",
            "sceneReceiptRef",
            "logRef",
            "traceRef",
            "metricRefs",
        }:
            raise ValueError(
                f"Provider two-device operator assertion[{index}] has an invalid evidence shape"
            )
        assertion_id = item.get("assertionId")
        metric_refs = item.get("metricRefs")
        if (
            not isinstance(assertion_id, str)
            or assertion_id not in assertion_ids
            or assertion_id in observed
            or item.get("status") != "passed"
            or not isinstance(item.get("sceneReceiptRef"), str)
            or _RECEIPT_REF_RE.fullmatch(item["sceneReceiptRef"]) is None
            or item.get("logRef") not in allowed_logs
            or item.get("traceRef") not in allowed_traces
            or not isinstance(metric_refs, list)
            or not metric_refs
            or any(ref not in allowed_metrics for ref in metric_refs)
        ):
            raise ValueError(
                "Provider two-device operator assertion must bind one unique passed scene receipt "
                "and owned observability references"
            )
        observed[assertion_id] = {
            "assertionId": assertion_id,
            "status": "passed",
            "logRef": item["logRef"],
            "traceRef": item["traceRef"],
            "metricRefs": list(metric_refs),
        }
    if set(observed) != set(assertion_ids):
        raise ValueError(
            "Provider two-device operator assertion scenes do not match the source contract"
        )
    return [observed[assertion_id] for assertion_id in assertion_ids]


def _validate_hosted_release_receipts(payload: Mapping[str, Any]) -> None:
    """Accept release readiness only after stackctl fetches the hosted receipt."""
    readiness = payload.get("releaseReadiness")
    if not isinstance(readiness, Mapping):
        raise ValueError("Provider two-device operator readback releaseReadiness is invalid")
    candidate = {
        "imageDigest": _required("QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST"),
        "configDigest": _required("QWQ_PROVIDER_CONFORMANCE_CONFIG_DIGEST"),
        "contractGraphDigest": _required(
            "QWQ_PROVIDER_CONFORMANCE_CONTRACT_GRAPH_DIGEST"
        ),
        "adapterDigest": _required("QWQ_PROVIDER_CONFORMANCE_ADAPTER_DIGEST"),
    }
    for field, purpose in (
        ("lastGoodReceiptRef", "last-good"),
        ("rollbackReceiptRef", "rollback"),
    ):
        value = readiness.get(field)
        match = (
            _HOSTED_RECEIPT_REF_RE.fullmatch(value)
            if isinstance(value, str)
            else None
        )
        if match is None:
            raise ValueError(
                f"Provider two-device operator readback {field} must be a hosted receipt reference"
            )
        command = [
            sys.executable,
            "quwoquan_ops/cli/stackctl.py",
            "--output-format",
            "json",
            "hosted-release-receipt",
            "--service",
            "prod-stack",
            "--receipt-id",
            match.group(1),
            "--purpose",
            purpose,
            "--image-digest",
            candidate["imageDigest"],
            "--config-digest",
            candidate["configDigest"],
            "--contract-graph-digest",
            candidate["contractGraphDigest"],
            "--adapter-digest",
            candidate["adapterDigest"],
        ]
        result = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise ValueError(
                "Provider two-device hosted release receipt verification failed: "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        try:
            verified = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise ValueError("Provider two-device hosted release receipt verification was not JSON") from error
        if (
            not isinstance(verified, Mapping)
            or verified.get("receiptRef") != value
            or verified.get("candidate") != candidate
            or verified.get("purpose") != purpose
        ):
            raise ValueError("Provider two-device hosted release receipt verification is inconsistent")


@dataclass
class _CapturedProcess:
    process: subprocess.Popen[str]
    lines: list[str] = field(default_factory=list)
    output: queue.Queue[str] = field(default_factory=queue.Queue)
    reader: threading.Thread | None = None


def _start_process(command: list[str], *, environment: Mapping[str, str]) -> _CapturedProcess:
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=dict(environment),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    captured = _CapturedProcess(process=process)

    def drain() -> None:
        if process.stdout is None:
            return
        for line in process.stdout:
            captured.output.put(line)

    captured.reader = threading.Thread(target=drain, daemon=True)
    captured.reader.start()
    return captured


def _wait_for_marker(
    captured: _CapturedProcess,
    *,
    marker: str,
    role: str,
    timeout_seconds: int,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        try:
            line = captured.output.get(timeout=max(0.1, remaining))
        except queue.Empty:
            if captured.process.poll() is not None:
                break
            continue
        captured.lines.append(line)
        if marker in line:
            return
    raise ValueError(f"Provider two-device Prod Remote {role} Patrol omitted marker {marker}")


def _wait_for_exit(
    captured: _CapturedProcess,
    *,
    role: str,
    timeout_seconds: int,
) -> str:
    try:
        captured.process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        captured.process.terminate()
        try:
            captured.process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            captured.process.kill()
            captured.process.wait(timeout=15)
        raise ValueError(f"Provider two-device Prod Remote {role} Patrol timed out") from exc
    if captured.reader is not None:
        captured.reader.join(timeout=5)
    while True:
        try:
            captured.lines.append(captured.output.get_nowait())
        except queue.Empty:
            break
    if captured.process.returncode != 0:
        raise ValueError(f"Provider two-device Prod Remote {role} Patrol failed")
    return "".join(captured.lines)


def _patrol_command(platform: str, *, role: str) -> list[str]:
    command = [
        sys.executable,
        "quwoquan_ops/ci/provider_conformance/run_provider_patrol_uat.py",
        "--target",
        _PATROL_TARGET,
        "--platform",
        platform,
        "--define-key",
        "QWQ_PROVIDER_UAT_ROLE",
        "--define-key",
        "QWQ_PROVIDER_UAT_PHASE",
    ]
    if role == "caller":
        command.extend(("--define-key", "QWQ_PROVIDER_UAT_CALL_ID"))
    else:
        command.extend(
            ("--define-key", "QWQ_PROVIDER_UAT_EXPECTED_CALLER_NAME")
        )
    return command


def _role_environment(
    *,
    role: str,
    phase: str,
    call_id: str,
    device_id: str,
    auth: Mapping[str, str],
    expected_caller_name: str,
) -> dict[str, str]:
    parent_result_path = Path(_required("QWQ_PROVIDER_CONFORMANCE_RESULT_PATH"))
    patrol_result_path = parent_result_path.with_name(
        f"{parent_result_path.stem}.{phase}.{role}.patrol.json"
    )
    environment = dict(os.environ)
    environment.update(
        {
            "QWQ_PROVIDER_CONFORMANCE_DEVICE_ID": device_id,
            "QWQ_PROVIDER_CONFORMANCE_RESULT_PATH": str(patrol_result_path),
            "QWQ_PROVIDER_UAT_ROLE": role,
            "QWQ_PROVIDER_UAT_PHASE": phase,
            "QWQ_PROVIDER_UAT_CALL_ID": call_id,
            "QWQ_PROVIDER_UAT_EXPECTED_CALLER_NAME": expected_caller_name,
            "TEST_AUTH_TOKEN": auth["token"],
            "TEST_REFRESH_TOKEN": auth["refresh"],
            "APP_CURRENT_OWNER_ID": auth["owner"],
            "APP_CURRENT_PERSONA_ID": auth["persona"],
        }
    )
    return environment


def _participant(prefix: str) -> dict[str, str]:
    return {
        "token": _required(f"QWQ_PROVIDER_UAT_{prefix}_AUTH_TOKEN"),
        "refresh": _required(f"QWQ_PROVIDER_UAT_{prefix}_REFRESH_TOKEN"),
        "owner": _required(f"QWQ_PROVIDER_UAT_{prefix}_OWNER_ID"),
        "persona": _required(f"QWQ_PROVIDER_UAT_{prefix}_PERSONA_ID"),
        "display_name": _required(f"QWQ_PROVIDER_UAT_{prefix}_DISPLAY_NAME"),
    }


def _assert_markers(
    output: str,
    *,
    role: str,
    phase: str,
    required_markers: tuple[str, ...],
) -> None:
    missing = [
        marker
        for marker in required_markers
        if f"{marker}:{role}:{phase}" not in output
    ]
    if missing:
        raise ValueError(
            f"Provider two-device Prod Remote {role} Patrol omitted lifecycle evidence: {', '.join(missing)}"
        )


def _run_direction(
    *,
    api_base: str,
    phase: str,
    caller_platform: str,
    callee_platform: str,
    caller: Mapping[str, str],
    callee: Mapping[str, str],
    caller_device: str,
    callee_device: str,
    conversation_id: str,
) -> tuple[str, str]:
    callee_process: _CapturedProcess | None = None
    caller_process: _CapturedProcess | None = None
    call_id = ""
    try:
        # A callee goes offline before call creation; no direct route or UI mock
        # is used to enter the incoming-call surface.
        callee_process = _start_process(
            _patrol_command(callee_platform, role="callee"),
            environment=_role_environment(
                role="callee",
                phase=phase,
                call_id="",
                device_id=callee_device,
                auth=callee,
                expected_caller_name=caller["display_name"],
            ),
        )
        _wait_for_marker(
            callee_process,
            marker=f"QWQ_PROVIDER_UAT_REMOTE_CALLEE_READY:{phase}",
            role=f"{phase}/callee",
            timeout_seconds=120,
        )
        initiated = _request_json(
            base_url=api_base,
            method="POST",
            path="/rtc/calls",
            token=caller["token"],
            owner_id=caller["owner"],
            persona_id=caller["persona"],
            idempotency_key=f"provider-prod-{phase}-{uuid.uuid4().hex}",
            body={
                "callType": "video",
                "inviteeIds": [callee["persona"]],
                "conversationId": conversation_id,
                "maxParticipants": 2,
            },
        )
        call_id = _find_string(initiated, frozenset({"callId", "id"}))
        if not call_id:
            raise ValueError("Provider two-device Prod Remote initiation response omitted call id")
        caller_process = _start_process(
            _patrol_command(caller_platform, role="caller"),
            environment=_role_environment(
                role="caller",
                phase=phase,
                call_id=call_id,
                device_id=caller_device,
                auth=caller,
                expected_caller_name="",
            ),
        )
        caller_output = _wait_for_exit(
            caller_process,
            role=f"{phase}/caller",
            timeout_seconds=900,
        )
        callee_output = _wait_for_exit(
            callee_process,
            role=f"{phase}/callee",
            timeout_seconds=900,
        )
        _assert_markers(
            caller_output,
            role="caller",
            phase=phase,
            required_markers=(
                "QWQ_PROVIDER_UAT_REMOTE_MEDIA_CONNECTED",
                "QWQ_PROVIDER_UAT_REMOTE_CALL_ENDED",
            ),
        )
        callee_markers = (
            "QWQ_PROVIDER_UAT_REMOTE_PUSH_PRESENTED",
            "QWQ_PROVIDER_UAT_REMOTE_MEDIA_CONNECTED",
            "QWQ_PROVIDER_UAT_REMOTE_CALL_ENDED",
        )
        if phase == "ios_to_android":
            callee_markers += (
                "QWQ_PROVIDER_UAT_REMOTE_SCREEN_SHARE_COMPLETED",
                "QWQ_PROVIDER_UAT_REMOTE_PIP_HANGUP",
            )
        _assert_markers(
            callee_output,
            role="callee",
            phase=phase,
            required_markers=callee_markers,
        )
        final_call = _request_json(
            base_url=api_base,
            method="GET",
            path=f"/rtc/calls/{call_id}",
            token=caller["token"],
            owner_id=caller["owner"],
            persona_id=caller["persona"],
        )
        if _find_string(final_call, frozenset({"status"})) != "ended":
            raise ValueError("Provider two-device Prod Remote call did not reach terminal ended state")
        output_digest = _sha256(
            json.dumps(
                {
                    "phase": phase,
                    "callerOutput": _sha256(caller_output.encode("utf-8")),
                    "calleeOutput": _sha256(callee_output.encode("utf-8")),
                    "callId": _sha256(call_id.encode("utf-8")),
                },
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
        return call_id, output_digest
    finally:
        for captured in (caller_process, callee_process):
            if captured is not None and captured.process.poll() is None:
                captured.process.terminate()
                try:
                    captured.process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    captured.process.kill()
                    captured.process.wait(timeout=15)
        if call_id:
            try:
                _request_json(
                    base_url=api_base,
                    method="POST",
                    path=f"/rtc/calls/{call_id}/hangup",
                    token=caller["token"],
                    owner_id=caller["owner"],
                    persona_id=caller["persona"],
                    idempotency_key=f"provider-prod-cleanup-{call_id}",
                )
            except ValueError:
                # The operator receipt proves cleanup; do not convert a real
                # terminal race into a fabricated success.
                pass


def _build_readback(
    *,
    operator: Mapping[str, Any],
    ios_device: str,
    android_device: str,
    ios_application_digest: str,
    android_application_digest: str,
    call_ids: list[str],
    journey_digests: list[str],
) -> dict[str, Any]:
    assertions = _validated_operator_assertions(operator)
    observability = operator["observabilityRefs"]
    if not isinstance(observability, Mapping) or not all(
        isinstance(observability.get(key), list) and observability[key]
        for key in ("logs", "traces", "metrics")
    ):
        raise ValueError("Provider two-device operator readback observabilityRefs are incomplete")
    data_digest = _sha256(
        json.dumps(
            {
                "callIds": [_sha256(call_id.encode("utf-8")) for call_id in call_ids],
                "journeyDigests": journey_digests,
                "operatorDigest": _sha256(
                    json.dumps(operator, sort_keys=True, separators=(",", ":")).encode(
                        "utf-8"
                    )
                ),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    return {
        "schema": "provider-remote-uat-readback",
        "status": "passed",
        "capabilityId": _required("QWQ_PROVIDER_UAT_REMOTE_UAT_CAPABILITY_ID"),
        "adapterId": _required("QWQ_PROVIDER_UAT_REMOTE_UAT_ADAPTER_ID"),
        "imageDigest": _required("QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST"),
        "configDigest": _required("QWQ_PROVIDER_CONFORMANCE_CONFIG_DIGEST"),
        "contractGraphDigest": _required(
            "QWQ_PROVIDER_CONFORMANCE_CONTRACT_GRAPH_DIGEST"
        ),
        "adapterDigest": _required("QWQ_PROVIDER_CONFORMANCE_ADAPTER_DIGEST"),
        "deviceEvidence": [
            {
                "platform": "ios",
                "deviceHash": _device_hash(ios_device),
                "applicationDigest": ios_application_digest,
                "caseDirection": "ios_to_android",
            },
            {
                "platform": "android",
                "deviceHash": _device_hash(android_device),
                "applicationDigest": android_application_digest,
                "caseDirection": "android_to_ios",
            },
        ],
        "providerReceipts": operator["providerReceipts"],
        "deliveryTimelines": operator["deliveryTimelines"],
        "pushReadback": {
            "ios": "pushkit_callkit",
            "android": "fcm_full_screen_or_heads_up",
        },
        "callReadback": {
            "terminalState": "ended",
            "participantCount": 2,
            "mediaConnected": True,
            "screenShareCompleted": True,
            "pipHangup": True,
            "cancelRaceResolved": True,
        },
        "realtimeReadback": operator["realtimeReadback"],
        "chatProjection": operator["chatProjection"],
        "qoeReadback": operator["qoeReadback"],
        "assertions": assertions,
        "dataDigest": data_digest,
        "cleanupReceipt": operator["cleanupReceipt"],
        "observabilityRefs": operator["observabilityRefs"],
        "releaseReadiness": operator["releaseReadiness"],
    }


def main() -> int:
    if _required("QWQ_PROVIDER_CONFORMANCE_ENVIRONMENT") != "prod":
        raise ValueError("Provider two-device Prod Remote Patrol only supports prod")
    target = get_target(load_environment_topology(), "prod-hosted")
    public_bases = target.get("publicBases")
    if not isinstance(public_bases, Mapping):
        raise ValueError("prod-hosted publicBases are required")
    api_base = str(public_bases.get("api") or "").strip()
    if not api_base:
        raise ValueError("prod-hosted publicBases.api is required")
    caller = _participant("CALLER")
    callee = _participant("CALLEE")
    conversation_id = _required("QWQ_PROVIDER_UAT_CONVERSATION_ID")
    ios_device = _required("QWQ_PROVIDER_UAT_IOS_DEVICE_ID")
    android_device = _required("QWQ_PROVIDER_UAT_ANDROID_DEVICE_ID")
    if ios_device == android_device:
        raise ValueError("Provider two-device Prod Remote Patrol requires distinct iOS and Android devices")
    ios_application_digest = _required("QWQ_PROVIDER_UAT_IOS_APPLICATION_DIGEST")
    android_application_digest = _required("QWQ_PROVIDER_UAT_ANDROID_APPLICATION_DIGEST")
    if not _SHA256_RE.fullmatch(ios_application_digest) or not _SHA256_RE.fullmatch(
        android_application_digest
    ):
        raise ValueError("Provider two-device application identities must be immutable sha256 digests")

    ios_to_android_id, ios_to_android_digest = _run_direction(
        api_base=api_base,
        phase="ios_to_android",
        caller_platform="ios",
        callee_platform="android",
        caller=caller,
        callee=callee,
        caller_device=ios_device,
        callee_device=android_device,
        conversation_id=conversation_id,
    )
    android_to_ios_id, android_to_ios_digest = _run_direction(
        api_base=api_base,
        phase="android_to_ios",
        caller_platform="android",
        callee_platform="ios",
        caller=callee,
        callee=caller,
        caller_device=android_device,
        callee_device=ios_device,
        conversation_id=conversation_id,
    )
    readback = _build_readback(
        operator=_load_operator_receipts(
            call_ids=(ios_to_android_id, android_to_ios_id),
        ),
        ios_device=ios_device,
        android_device=android_device,
        ios_application_digest=ios_application_digest,
        android_application_digest=android_application_digest,
        call_ids=[ios_to_android_id, android_to_ios_id],
        journey_digests=[ios_to_android_digest, android_to_ios_digest],
    )
    output_path = Path(_required("QWQ_PROVIDER_UAT_REMOTE_UAT_READBACK_PATH"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(readback, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"[provider-prod-remote-patrol] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
