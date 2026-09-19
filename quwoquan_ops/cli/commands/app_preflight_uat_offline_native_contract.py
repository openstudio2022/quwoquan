"""DEC-008 launcher-only external AUT observation relay and restart supervisor.

本模块只消费 canonical generated contract。runner terminal result/ref 不携带查询能力；
bootstrap verifier 与 relay secret 只存在于 launcher/AUT 内存。平台 socket 实现通过
``RelayTransport`` 注入，测试 fake 只能证明 Ops local contract，不能冒充设备 runtime。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from quwoquan_ops.cli.lib.generated.app_launch_contract import (
    APP_LAUNCH_MANIFEST,
    EXTERNAL_UAT_BROKER_RESULT_REQUIRED_FIELDS,
    EXTERNAL_UAT_SEALED_SNAPSHOT_REQUIRED_FIELDS,
    EXTERNAL_UAT_TEARDOWN_RECEIPT_REQUIRED_FIELDS,
    EXTERNAL_UAT_TERMINAL_RESULT_REQUIRED_FIELDS,
)

SPEC = "specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-008"
POLICY = APP_LAUNCH_MANIFEST["external_uat_observation_relay"]
CASES = tuple(POLICY["case_catalog"])
FAILURES = frozenset(POLICY["failure_codes"])
SENSITIVE = frozenset({"phone", "otp", "identity", "account", "challenge", "payload", "secret", "mac", "capability"})
DIGEST_RE = __import__("re").compile(r"sha256:[0-9a-f]{64}")

EXPECTED_SCHEMA = str(POLICY["expected_observation_schema"])
EXPECTED_MATCHER = str(POLICY["expected_matcher"])
EXPECTED_CATALOG = POLICY["expected_observations"]


def expected_observation(case_id: str) -> dict[str, Any]:
    if case_id not in CASES or case_id not in EXPECTED_CATALOG:
        raise _fail("APP.UAT.relay_contract_drift", "expected case is missing")
    configured = EXPECTED_CATALOG[case_id]
    if not isinstance(configured, Mapping) or set(configured) != {"observations"}:
        raise _fail("APP.UAT.relay_contract_drift", "expected case fields drifted")
    rows = configured["observations"]
    if not isinstance(rows, list) or not rows:
        raise _fail("APP.UAT.relay_contract_drift", "expected observations are empty")
    allowed = {"source", "status", "detail", "attemptCount"}
    for row in rows:
        if (not isinstance(row, Mapping) or not {"source", "status", "detail"} <= set(row)
                or set(row) - allowed or row.get("status") != "observed"
                or any(str(key).lower() in SENSITIVE for key in row)):
            raise _fail("APP.UAT.relay_contract_drift", "expected row fields drifted")
    value = {"schema": EXPECTED_SCHEMA, "caseId": case_id, "matcher": EXPECTED_MATCHER,
             "observations": [dict(row) for row in rows]}
    value["expectedObservationDigest"] = digest(value)
    return value



def digest(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


_digest = digest


def _fail(code: str, detail: str = "") -> ValueError:
    if code not in FAILURES:
        raise AssertionError(f"undeclared relay failure: {code}")
    return ValueError(code + (": " + detail if detail else ""))


def _require_digest(value: object, code: str) -> str:
    if not isinstance(value, str) or DIGEST_RE.fullmatch(value) is None:
        raise _fail(code)
    return value


def build_native_case_contract(case_id: str, launch: Mapping[str, Any]) -> dict[str, Any]:
    if case_id not in CASES:
        raise _fail("APP.UAT.relay_scope_mismatch")
    required = ("applicationId", "candidateDigest", "artifactDigest", "deviceId", "launchAttemptId", "canonicalProcessId")
    if any(key not in launch for key in required):
        raise _fail("APP.UAT.relay_contract_drift")
    generation = int(launch.get("generation", 1))
    value: dict[str, Any] = {
        "schema": "external-uat-case-plan",
        "specRef": SPEC,
        "caseId": case_id,
        **{key: launch[key] for key in required},
        "generation": generation,
        "sessionId": str(launch.get("sessionId") or launch["deviceId"]),
        "observationBinding": str(launch.get("observationBinding") or digest({"case": case_id, "attempt": launch["launchAttemptId"]})),
        "expectedObservation": expected_observation(case_id),
        "expectedObservationDigest": expected_observation(case_id)["expectedObservationDigest"],
        "observationSources": [row["source"] for row in expected_observation(case_id)["observations"]],
        "runnerTimeoutSeconds": 360 if case_id == "otp-expiry" else 120,
        "minimumObservedWaitSeconds": 300 if case_id == "otp-expiry" else 0,
        "restartPolicy": "cold-restart-new-launch-attempt-and-pid" if case_id == "identity-restart" else "same-attempt-same-pid",
        "nonPromotable": True,
    }
    value["contractDigest"] = digest(value)
    return value


def validate_native_case_contract(value: Mapping[str, Any], *, launch: Mapping[str, Any]) -> None:
    try:
        canonical = build_native_case_contract(str(value.get("caseId") or ""), launch)
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ValueError) and "APP.UAT." in str(error):
            raise
        raise _fail("APP.UAT.relay_contract_drift") from error
    if set(value) != set(canonical) or value.get("contractDigest") != digest({key: item for key, item in value.items() if key != "contractDigest"}):
        raise _fail("APP.UAT.relay_contract_drift", "native case contract drifted")
    identity = ("candidateDigest", "artifactDigest", "deviceId", "launchAttemptId", "applicationId", "canonicalProcessId", "generation", "sessionId", "observationBinding")
    if any(value.get(key) != canonical.get(key) for key in identity):
        raise _fail("APP.UAT.relay_scope_mismatch", "cross AUT/attempt identity")
    if value != canonical:
        detail = "wait budget drifted" if value.get("minimumObservedWaitSeconds") != canonical.get("minimumObservedWaitSeconds") else "case policy drifted"
        raise _fail("APP.UAT.relay_contract_drift", detail)


@dataclass(frozen=True)
class TerminalReference:
    """Runner 只发布这一闭集值；它不是 relay capability。"""

    terminal: Mapping[str, Any]


class RelayTransport(Protocol):
    """由 launcher 拥有的 Android forward / iOS App Group socket adapter。"""

    runtime_verified: bool

    def arm(self, admission: Mapping[str, Any], verifier: bytes) -> None: ...
    def query(self, frame: Mapping[str, Any], *, timeout_seconds: float) -> Mapping[str, Any]: ...
    def close(self) -> None: ...


@dataclass
class RelaySession:
    admission: dict[str, Any]
    clock_ms: Callable[[], int] = lambda: time.monotonic_ns() // 1_000_000
    secret: bytearray = field(default_factory=lambda: bytearray(secrets.token_bytes(32)))
    consumed: bool = False
    revoked: bool = False
    terminal_digest: str = ""
    armed: bool = False

    def arm_frame(self) -> dict[str, Any]:
        if self.revoked:
            raise _fail("APP.UAT.relay_revoked")
        return {"operation": "armRelay", "admission": self.admission, "verifier": self.secret.hex()}

    def verify_terminal(self, terminal: Mapping[str, Any], plan: Mapping[str, Any]) -> None:
        if set(terminal) != set(EXTERNAL_UAT_TERMINAL_RESULT_REQUIRED_FIELDS) or terminal.get("schema") != "external-uat-terminal-result":
            raise _fail("APP.UAT.relay_terminal_invalid")
        if terminal.get("status") != "passed" or not terminal.get("terminalRef"):
            raise _fail("APP.UAT.relay_terminal_invalid")
        if any(key.lower() in SENSITIVE or "actual" in key.lower() for key in terminal):
            raise _fail("APP.UAT.relay_terminal_invalid")
        expected = {
            "planDigest": plan["planDigest"], "caseId": self.admission["caseId"],
            "launchAttemptId": self.admission["launchAttemptId"], "generation": self.admission["generation"],
            "processId": self.admission["processId"], "deviceId": self.admission["deviceId"],
            "sessionId": self.admission["sessionId"],
        }
        if any(terminal.get(key) != value for key, value in expected.items()):
            raise _fail("APP.UAT.relay_scope_mismatch")
        body = {key: value for key, value in terminal.items() if key not in {"terminalDigest", "terminalRef"}}
        if terminal.get("terminalDigest") != digest(body):
            raise _fail("APP.UAT.relay_terminal_invalid")
        if self.terminal_digest:
            raise _fail("APP.UAT.relay_terminal_replayed")
        self.terminal_digest = str(terminal["terminalDigest"])

    def query_frame(self) -> dict[str, Any]:
        if self.revoked:
            raise _fail("APP.UAT.relay_revoked")
        if self.consumed:
            raise _fail("APP.UAT.relay_consumed")
        if not self.terminal_digest:
            raise _fail("APP.UAT.relay_terminal_invalid")
        # Host 只施加观察截止+短查询窗的外界；实际seal时点由native单独核验。
        if self.clock_ms() >= self.admission["expiresAtMonotonicMs"] + int(POLICY["ttl_seconds"]) * 1000:
            raise _fail("APP.UAT.relay_expired")
        frame = {
            "schema": "external-uat-broker-query", "contractDigest": self.admission["contractDigest"],
            "admissionDigest": self.admission["admissionDigest"], "terminalDigest": self.terminal_digest,
            "caseId": self.admission["caseId"], "launchAttemptId": self.admission["launchAttemptId"],
            "generation": self.admission["generation"], "observationBinding": self.admission["observationBinding"],
            "processId": self.admission["processId"], "deviceId": self.admission["deviceId"],
            "sessionId": self.admission["sessionId"], "sequence": 1, "challenge": secrets.token_hex(32),
        }
        frame["mac"] = hmac.new(bytes(self.secret), json.dumps(frame, sort_keys=True, separators=(",", ":")).encode(), hashlib.sha256).hexdigest()
        self.consumed = True
        return frame

    def revoke(self) -> None:
        self.revoked = True
        for index in range(len(self.secret)):
            self.secret[index] = 0


def admit_launch(plan: Mapping[str, Any], launch: Mapping[str, Any], *, signing_digest: str,
                 lifecycle_digest: str, now_ms: int | None = None,
                 clock_ms: Callable[[], int] | None = None) -> RelaySession:
    validate_native_case_contract(plan, launch=launch)
    _require_digest(signing_digest, "APP.UAT.relay_admission_mismatch")
    _require_digest(lifecycle_digest, "APP.UAT.relay_admission_mismatch")
    now = time.monotonic_ns() // 1_000_000 if now_ms is None else now_ms
    platform = "android-emulator" if launch.get("platform") == "android" else "ios-simulator" if launch.get("platform") in {"ios", "ios-simulator"} else ""
    if platform not in POLICY["enabled_targets"] or int(plan["generation"]) <= 0 or int(plan["canonicalProcessId"]) <= 0:
        raise _fail("APP.UAT.relay_admission_mismatch")
    admission = {
        "schema": "external-uat-managed-launch-admission", "contractDigest": plan["contractDigest"],
        "candidateDigest": plan["candidateDigest"], "artifactDigest": plan["artifactDigest"],
        "packageIdentity": plan["applicationId"], "signingDigest": signing_digest, "platform": platform,
        "deviceId": plan["deviceId"], "sessionId": plan["sessionId"], "caseId": plan["caseId"],
        "launchAttemptId": plan["launchAttemptId"], "generation": plan["generation"],
        "observationBinding": plan["observationBinding"], "processId": int(plan["canonicalProcessId"]),
        "lifecycleReceiptDigest": lifecycle_digest, "admittedAtMonotonicMs": now,
        "expiresAtMonotonicMs": now + int(POLICY["observation_lifetime_seconds"].get(
            plan["caseId"], POLICY["observation_lifetime_seconds"]["default"])) * 1000,
    }
    admission["admissionDigest"] = digest(admission)
    return RelaySession(admission=admission, clock_ms=clock_ms or (lambda: time.monotonic_ns() // 1_000_000))


def _validate_snapshot(snapshot: object, session: RelaySession) -> Mapping[str, Any]:
    if not isinstance(snapshot, Mapping) or set(snapshot) != set(EXTERNAL_UAT_SEALED_SNAPSHOT_REQUIRED_FIELDS):
        raise _fail("APP.UAT.relay_contract_drift")
    expected = {
        "schema": "external-uat-sealed-snapshot", "caseId": session.admission["caseId"],
        "launchAttemptId": session.admission["launchAttemptId"], "generation": session.admission["generation"],
        "observationBinding": session.admission["observationBinding"], "processId": session.admission["processId"],
    }
    if any(snapshot.get(key) != value for key, value in expected.items()):
        raise _fail("APP.UAT.relay_scope_mismatch")
    if any(key.lower() in SENSITIVE for key in snapshot):
        raise _fail("APP.UAT.relay_sensitive_field")
    sealed_at = snapshot.get("sealedAtMonotonicMs")
    if (type(sealed_at) is not int or sealed_at < session.admission["admittedAtMonotonicMs"]
            or sealed_at > session.admission["expiresAtMonotonicMs"]):
        raise _fail("APP.UAT.relay_scope_mismatch", "snapshot lifecycle time is outside admission")
    body = {key: value for key, value in snapshot.items() if key != "snapshotDigest"}
    if snapshot.get("snapshotDigest") != digest(body):
        raise _fail("APP.UAT.relay_contract_drift")
    return snapshot


def validate_broker_result(session: RelaySession, broker: Mapping[str, Any]) -> Mapping[str, Any]:
    if set(broker) != set(EXTERNAL_UAT_BROKER_RESULT_REQUIRED_FIELDS) or broker.get("schema") != "external-uat-broker-result":
        raise _fail("APP.UAT.relay_contract_drift")
    if broker.get("status") != "observed" or broker.get("consumed") is not True or broker.get("revoked") is not True or broker.get("errorCode") != "":
        raise _fail("APP.UAT.relay_not_sealed")
    if broker.get("admissionDigest") != session.admission["admissionDigest"] or broker.get("terminalDigest") != session.terminal_digest:
        raise _fail("APP.UAT.relay_scope_mismatch")
    snapshot = _validate_snapshot(broker.get("snapshot"), session)
    if broker.get("snapshotDigest") != snapshot["snapshotDigest"]:
        raise _fail("APP.UAT.relay_contract_drift")
    if broker.get("resultDigest") != digest({key: value for key, value in broker.items() if key != "resultDigest"}):
        raise _fail("APP.UAT.relay_contract_drift")
    return snapshot


def compare_and_report(session: RelaySession, broker: Mapping[str, Any], expected: Mapping[str, Any]) -> dict[str, Any]:
    try:
        snapshot = validate_broker_result(session, broker)
        canonical = expected_observation(session.admission["caseId"])
        if dict(expected) != canonical or expected.get("expectedObservationDigest") != digest(
                {key: value for key, value in expected.items() if key != "expectedObservationDigest"}):
            raise _fail("APP.UAT.relay_contract_drift", "expected binding drifted")
        actual_rows = snapshot.get("observations")
        status = "passed" if actual_rows == expected.get("observations") else "failed"
        body = {
            "schema": "external-uat-comparison-result", "caseId": session.admission["caseId"],
            "admissionDigest": session.admission["admissionDigest"], "terminalDigest": session.terminal_digest,
            "brokerResultDigest": broker["resultDigest"], "expectedDigest": expected["expectedObservationDigest"],
            "status": status, "nonPromotable": True,
            "errorCode": "" if status == "passed" else "APP.UAT.relay_contract_drift",
        }
        body["comparisonDigest"] = digest(body)
        return body
    finally:
        session.revoke()


def arm_launcher_relay(*, session: RelaySession, transport: RelayTransport) -> None:
    """成功 ACK 是启动 UI 的前置；失败不得重签或继续执行。"""
    if session.armed or session.revoked:
        raise _fail("APP.UAT.relay_stale")
    if transport.runtime_verified is not True:
        raise _fail("APP.UAT.relay_peer_rejected")
    try:
        transport.arm(session.admission, bytes(session.secret))
        session.armed = True
    except BaseException:
        session.revoke()
        transport.close()
        raise


def execute_launcher_relay(*, session: RelaySession, plan: Mapping[str, Any], terminal_ref: TerminalReference,
                           transport: RelayTransport, expected: Mapping[str, Any], timeout_seconds: float = 60) -> dict[str, Any]:
    """Launcher 唯一查询、comparison 与 cleanup owner；所有失败 fail-closed。"""
    if transport.runtime_verified is not True:
        raise _fail("APP.UAT.relay_peer_rejected", "platform runtime adapter is not verified")
    first_error: BaseException | None = None
    try:
        if not session.armed:
            raise _fail("APP.UAT.relay_admission_mismatch", "UI terminal arrived before arm acknowledgement")
        session.verify_terminal(terminal_ref.terminal, plan)
        broker = transport.query(session.query_frame(), timeout_seconds=timeout_seconds)
        comparison = compare_and_report(session, broker, expected)
        return {**comparison, "admission": dict(session.admission), "brokerResult": dict(broker)}
    except TimeoutError as error:
        first_error = _fail("APP.UAT.relay_timeout")
        raise first_error from error
    except (BrokenPipeError, ConnectionError, EOFError) as error:
        first_error = _fail("APP.UAT.relay_process_died")
        raise first_error from error
    except BaseException as error:
        first_error = error
        raise
    finally:
        session.revoke()
        try:
            transport.close()
        except (OSError, RuntimeError, ValueError):
            if first_error is None:
                raise _fail("APP.UAT.relay_revoked", "transport cleanup failed")


def validate_actual_observation(actual: Mapping[str, Any], *, contract: Mapping[str, Any]) -> None:
    """兼容父级 consumer：验证已转成明文 local-contract observation 的闭集。"""
    expected = {"schema", "caseId", "contractDigest", "applicationId", "deviceId", "candidateDigest", "artifactDigest",
                "launchAttemptBefore", "processIdBefore", "launchAttemptAfter", "processIdAfter", "observations", "logSummary"}
    if set(actual) != expected or actual.get("schema") != "quwoquan_ops.alpha_gwt008_native_observation.v1":
        raise _fail("APP.UAT.relay_contract_drift")
    pairs = (("caseId", "caseId"), ("contractDigest", "contractDigest"), ("applicationId", "applicationId"),
             ("deviceId", "deviceId"), ("candidateDigest", "candidateDigest"), ("artifactDigest", "artifactDigest"),
             ("launchAttemptBefore", "launchAttemptId"), ("processIdBefore", "canonicalProcessId"))
    if any(actual.get(left) != contract.get(right) for left, right in pairs):
        raise _fail("APP.UAT.relay_scope_mismatch", "cross AUT/attempt identity")
    observations = actual.get("observations")
    if not isinstance(observations, list) or [row.get("source") for row in observations if isinstance(row, Mapping)] != contract.get("observationSources"):
        raise _fail("APP.UAT.relay_contract_drift")
    if any(not isinstance(row, Mapping) or row.get("status") != "observed" for row in observations):
        raise _fail("APP.UAT.relay_not_sealed")
    if actual.get("logSummary") != "input-redacted":
        raise _fail("APP.UAT.relay_sensitive_field", "terminal is not redacted")
    restart = contract["caseId"] == "identity-restart"
    if restart == (actual.get("launchAttemptAfter") == actual.get("launchAttemptBefore") or actual.get("processIdAfter") == actual.get("processIdBefore")):
        raise _fail("APP.UAT.restart_identity_mismatch")


def build_teardown_receipt(*, session: RelaySession, predecessor_result_digest: str, transaction_id: str,
                           requested_at_ms: int, terminated_at_ms: int, readbacks: Sequence[bool],
                           broker_disconnected: bool) -> dict[str, Any]:
    """至少三项现役 readback 均确认 PID1 死亡后，才能签 terminated receipt。"""
    _require_digest(predecessor_result_digest, "APP.UAT.teardown_predecessor_invalid")
    if not session.consumed or not session.revoked or not session.terminal_digest:
        raise _fail("APP.UAT.teardown_predecessor_invalid")
    if len(readbacks) < 3 or not all(value is True for value in readbacks):
        raise _fail("APP.UAT.teardown_pid_alive")
    if not broker_disconnected:
        raise _fail("APP.UAT.relay_process_died")
    receipt = {
        "schema": "external-uat-teardown-receipt", "transactionId": transaction_id,
        "admissionDigest": session.admission["admissionDigest"], "launchAttemptId": session.admission["launchAttemptId"],
        "generation": session.admission["generation"], "processId": session.admission["processId"], "state": "terminated",
        "predecessorResultDigest": predecessor_result_digest, "requestedAtMonotonicMs": requested_at_ms,
        "terminatedAtMonotonicMs": terminated_at_ms, "processTableConfirmed": True, "lifecycleConfirmed": True,
        "brokerDisconnected": True, "errorCode": "",
    }
    receipt["receiptDigest"] = digest(receipt)
    return receipt


def validate_restart_successor(*, predecessor: Mapping[str, Any], successor_launch: Mapping[str, Any],
                               continuity_digest: str) -> None:
    if set(predecessor) != set(EXTERNAL_UAT_TEARDOWN_RECEIPT_REQUIRED_FIELDS) or predecessor.get("state") != "terminated":
        raise _fail("APP.UAT.teardown_predecessor_invalid")
    if predecessor.get("receiptDigest") != digest({key: value for key, value in predecessor.items() if key != "receiptDigest"}):
        raise _fail("APP.UAT.teardown_predecessor_invalid")
    if (successor_launch.get("generation") != int(predecessor["generation"]) + 1
            or successor_launch.get("launchAttemptId") == predecessor.get("launchAttemptId")
            or successor_launch.get("canonicalProcessId") == predecessor.get("processId")
            or successor_launch.get("caseId") != "identity-restart"
            or successor_launch.get("continuityDigest") != continuity_digest):
        raise _fail("APP.UAT.restart_identity_mismatch")


def supervise_identity_restart(*, attempt1_session: RelaySession, attempt1_plan: Mapping[str, Any],
                                attempt1_terminal: TerminalReference, attempt1_transport: RelayTransport,
                                expected_attempt1: Mapping[str, Any], terminate_aut: Callable[[Mapping[str, Any]], None],
                                death_readbacks: Sequence[Callable[[], bool]], launch_next: Callable[[str, int], Mapping[str, Any]],
                                prepare_attempt2: Callable[[Mapping[str, Any]], tuple[Mapping[str, Any], RelaySession, TerminalReference, RelayTransport]],
                                expected_attempt2: Mapping[str, Any], continuity_digest: str,
                                clock_ms: Callable[[], int] = lambda: time.monotonic_ns() // 1_000_000) -> dict[str, Any]:
    """Launcher-owned identity restart：consume attempt1，停 AUT，验死，再 canonical launch generation2。"""
    if attempt1_plan.get("caseId") != "identity-restart" or attempt1_session.admission.get("generation") != 1:
        raise _fail("APP.UAT.restart_identity_mismatch")
    first = execute_launcher_relay(session=attempt1_session, plan=attempt1_plan, terminal_ref=attempt1_terminal,
                                   transport=attempt1_transport, expected=expected_attempt1)
    if first.get("status") != "passed":
        raise _fail("APP.UAT.teardown_predecessor_invalid")
    requested = clock_ms()
    terminate_aut(attempt1_session.admission)
    readbacks = [probe() for probe in death_readbacks]
    teardown = build_teardown_receipt(
        session=attempt1_session, predecessor_result_digest=first["comparisonDigest"],
        transaction_id=digest({"attempt": attempt1_session.admission["launchAttemptId"], "requested": requested}),
        requested_at_ms=requested, terminated_at_ms=clock_ms(), readbacks=readbacks,
        broker_disconnected=bool(getattr(attempt1_transport, "disconnected", False)),
    )
    successor = dict(launch_next("identity-restart", 2))
    successor.setdefault("caseId", "identity-restart")
    validate_restart_successor(predecessor=teardown, successor_launch=successor, continuity_digest=continuity_digest)
    second_plan, second_session, second_terminal, second_transport = prepare_attempt2(successor)
    if (second_plan.get("caseId") != "identity-restart"
            or second_session.admission.get("generation") != 2
            or second_session.admission.get("processId") != successor.get("canonicalProcessId")):
        raise _fail("APP.UAT.restart_identity_mismatch")
    second = execute_launcher_relay(session=second_session, plan=second_plan,
                                    terminal_ref=second_terminal, transport=second_transport,
                                    expected=expected_attempt2)
    if second.get("status") != "passed":
        raise _fail("APP.UAT.restart_identity_mismatch", "successor observation did not pass")
    return {"schema": "external-uat-identity-restart-supervision", "attempt1": first, "teardown": teardown,
            "attempt2": second, "continuityDigest": continuity_digest, "nonPromotable": True}
