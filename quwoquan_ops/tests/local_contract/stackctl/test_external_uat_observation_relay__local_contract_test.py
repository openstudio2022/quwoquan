"""GWT-008 Ops launcher relay local contract；fake transport 不代表平台 runtime 已集成。"""
from __future__ import annotations

import copy
from collections.abc import Mapping

import pytest

from quwoquan_ops.cli.commands import app_preflight_uat_offline_native_contract as relay

D = lambda char: "sha256:" + char * 64


def launch(case: str = "login-success", *, attempt: str = "attempt-1", generation: int = 1, pid: int = 42):
    return {"applicationId": "app.alpha", "candidateDigest": D("a"), "artifactDigest": D("b"),
            "deviceId": "sim-1", "launchAttemptId": attempt, "canonicalProcessId": pid,
            "platform": "android", "sessionId": "session-1", "generation": generation,
            "observationBinding": D("c"), "caseId": case, "continuityDigest": D("9")}


def terminal(session: relay.RelaySession, plan: Mapping[str, object]):
    body = {"schema": "external-uat-terminal-result", "planDigest": plan["planDigest"],
            "caseId": session.admission["caseId"], "launchAttemptId": session.admission["launchAttemptId"],
            "generation": session.admission["generation"], "processId": session.admission["processId"],
            "deviceId": session.admission["deviceId"], "sessionId": session.admission["sessionId"],
            "status": "passed", "screenshotDigest": D("8")}
    return {**body, "terminalDigest": relay.digest(body), "terminalRef": "runner/terminal.json"}


def broker(session: relay.RelaySession, observations=None):
    snapshot_body = {"schema": "external-uat-sealed-snapshot", "caseId": session.admission["caseId"],
        "launchAttemptId": session.admission["launchAttemptId"], "generation": session.admission["generation"],
        "observationBinding": session.admission["observationBinding"], "processId": session.admission["processId"],
        "observations": observations or relay.expected_observation(session.admission["caseId"])["observations"],
        "sealedAtMonotonicMs": session.admission["admittedAtMonotonicMs"] + 1}
    snapshot = {**snapshot_body, "snapshotDigest": relay.digest(snapshot_body)}
    body = {"schema": "external-uat-broker-result", "status": "observed",
            "admissionDigest": session.admission["admissionDigest"], "terminalDigest": session.terminal_digest,
            "snapshot": snapshot, "snapshotDigest": snapshot["snapshotDigest"], "consumed": True,
            "revoked": True, "errorCode": ""}
    return {**body, "resultDigest": relay.digest(body)}


class FakeTransport:
    runtime_verified = True
    def __init__(self, factory=broker, error=None, close_error=None):
        self.factory, self.error, self.close_error, self.closed, self.disconnected, self.session = factory, error, close_error, False, False, None
    def arm(self, admission, verifier):
        assert verifier and "verifier" not in admission
        self.admission = admission
    @property
    def session(self):
        return self._session
    @session.setter
    def session(self, value):
        self._session = value
        if value is not None and self.runtime_verified:
            relay.arm_launcher_relay(session=value, transport=self)
    def query(self, frame, *, timeout_seconds):
        if self.error: raise self.error
        return self.factory(self.session)
    def close(self):
        self.closed = True; self.disconnected = True
        if self.close_error: raise self.close_error


def admitted(case="login-success", **kwargs):
    item = launch(case, **kwargs)
    plan = relay.build_native_case_contract(case, item)
    plan["planDigest"] = relay.digest(plan)
    session = relay.admit_launch({k: v for k, v in plan.items() if k != "planDigest"}, item,
                                 signing_digest=D("d"), lifecycle_digest=D("e"), now_ms=1, clock_ms=lambda: 2)
    return item, plan, session


# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-008
def test_observation_epoch_uses_case_budget_without_extending_query_ttl():
    for case, seconds in (("login-success", 120), ("otp-expiry", 360)):
        _, plan, session = admitted(case)
        assert session.admission["expiresAtMonotonicMs"] - session.admission["admittedAtMonotonicMs"] == seconds * 1000
        assert relay.POLICY["ttl_seconds"] == 60
        session.verify_terminal(terminal(session, plan), plan)
        value = broker(session)
        value["snapshot"]["sealedAtMonotonicMs"] = session.admission["expiresAtMonotonicMs"] + 1
        value["snapshot"]["snapshotDigest"] = relay.digest({k: v for k, v in value["snapshot"].items() if k != "snapshotDigest"})
        value["snapshotDigest"] = value["snapshot"]["snapshotDigest"]
        value["resultDigest"] = relay.digest({k: v for k, v in value.items() if k != "resultDigest"})
        with pytest.raises(ValueError, match="relay_scope_mismatch"):
            relay.validate_broker_result(session, value)
        session.revoke()


def test_catalog_binds_all_eleven_cases_and_runner_terminal_is_non_authorizing():
    assert len(relay.CASES) == 11
    for case in relay.CASES:
        assert relay.build_native_case_contract(case, launch(case))["nonPromotable"] is True
    _, plan, session = admitted()
    with pytest.raises(ValueError, match="relay_terminal_invalid"):
        session.verify_terminal({}, plan)
    session.revoke()
    with pytest.raises(ValueError, match="relay_revoked"):
        session.query_frame()


@pytest.mark.parametrize("field,value,code", [
    ("launchAttemptId", "attempt-2", "relay_scope_mismatch"), ("deviceId", "other", "relay_scope_mismatch"),
    ("generation", 2, "relay_scope_mismatch"), ("contractDigest", D("0"), "relay_contract_drift"),
])
def test_stale_cross_attempt_generation_and_contract_drift_fail_closed(field, value, code):
    item = launch(); plan = relay.build_native_case_contract("login-success", item)
    changed = {**plan, field: value}
    if field != "contractDigest": changed["contractDigest"] = relay.digest({k: v for k, v in changed.items() if k != "contractDigest"})
    with pytest.raises(ValueError, match=code):
        relay.admit_launch(changed, item, signing_digest=D("d"), lifecycle_digest=D("e"))


def test_single_query_replay_and_timeout_disconnect_are_typed_and_cleanup():
    _, plan, session = admitted(); session.verify_terminal(terminal(session, plan), plan)
    session.query_frame()
    with pytest.raises(ValueError, match="relay_consumed"): session.query_frame()
    for error, code in ((TimeoutError(), "relay_timeout"), (ConnectionError(), "relay_process_died")):
        _, plan, session = admitted(); transport = FakeTransport(error=error); transport.session = session
        with pytest.raises(ValueError, match=code):
            relay.execute_launcher_relay(session=session, plan=plan, terminal_ref=relay.TerminalReference(terminal(session, plan)),
                                         transport=transport, expected=plan["expectedObservation"])
        assert transport.closed and session.revoked and not any(session.secret)


def test_snapshot_peer_binding_digest_comparison_and_atomic_revoke():
    _, plan, session = admitted(); transport = FakeTransport(); transport.session = session
    session.verify_terminal(terminal(session, plan), plan); result = broker(session)
    comparison = relay.compare_and_report(session, result, plan["expectedObservation"])
    assert comparison["status"] == "passed" and comparison["nonPromotable"] is True
    assert session.revoked and not any(session.secret)
    _, plan, cross = admitted(); cross.verify_terminal(terminal(cross, plan), plan)
    bad = broker(cross); bad["admissionDigest"] = D("0")
    bad["resultDigest"] = relay.digest({k: v for k, v in bad.items() if k != "resultDigest"})
    with pytest.raises(ValueError, match="relay_scope_mismatch"):
        relay.compare_and_report(cross, bad, plan["expectedObservation"])


def test_partial_cleanup_failure_never_overwrites_first_failure():
    _, plan, session = admitted(); transport = FakeTransport(error=TimeoutError(), close_error=OSError()); transport.session = session
    with pytest.raises(ValueError, match="relay_timeout"):
        relay.execute_launcher_relay(session=session, plan=plan, terminal_ref=relay.TerminalReference(terminal(session, plan)),
                                     transport=transport, expected=plan["expectedObservation"])


def test_teardown_requires_consumed_predecessor_three_death_readbacks_and_disconnect():
    _, plan, session = admitted("identity-restart"); session.verify_terminal(terminal(session, plan), plan); session.query_frame()
    result = broker(session); relay.compare_and_report(session, result, plan["expectedObservation"])
    with pytest.raises(ValueError, match="teardown_pid_alive"):
        relay.build_teardown_receipt(session=session, predecessor_result_digest=D("7"), transaction_id="tx", requested_at_ms=3,
                                     terminated_at_ms=4, readbacks=[True, True, False], broker_disconnected=True)
    receipt = relay.build_teardown_receipt(session=session, predecessor_result_digest=D("7"), transaction_id="tx", requested_at_ms=3,
                                           terminated_at_ms=4, readbacks=[True, True, True], broker_disconnected=True)
    assert receipt["state"] == "terminated"


def test_restart_successor_requires_new_attempt_pid_generation_and_continuity():
    _, plan, session = admitted("identity-restart"); session.verify_terminal(terminal(session, plan), plan); session.query_frame()
    result = broker(session); relay.compare_and_report(session, result, plan["expectedObservation"])
    receipt = relay.build_teardown_receipt(session=session, predecessor_result_digest=D("7"), transaction_id="tx", requested_at_ms=3,
                                           terminated_at_ms=4, readbacks=[True, True, True], broker_disconnected=True)
    successor = launch("identity-restart", attempt="attempt-2", generation=2, pid=84)
    relay.validate_restart_successor(predecessor=receipt, successor_launch=successor, continuity_digest=D("9"))
    for field, value in (("generation", 1), ("launchAttemptId", "attempt-1"), ("canonicalProcessId", 42), ("continuityDigest", D("0"))):
        with pytest.raises(ValueError, match="restart_identity_mismatch"):
            relay.validate_restart_successor(predecessor=receipt, successor_launch={**successor, field: value}, continuity_digest=D("9"))


def test_unverified_fake_cannot_claim_platform_runtime():
    _, plan, session = admitted(); transport = FakeTransport(); transport.runtime_verified = False
    with pytest.raises(ValueError, match="relay_peer_rejected"):
        relay.execute_launcher_relay(session=session, plan=plan, terminal_ref=relay.TerminalReference(terminal(session, plan)),
                                     transport=transport, expected=plan["expectedObservation"])


def test_android_adapter_owns_forward_and_removes_only_its_forward():
    from subprocess import CompletedProcess
    from quwoquan_ops.cli.lib.external_uat_relay_transport import AndroidAdbForwardRelayTransport
    commands = []
    responses = iter(({"armed": True}, {"schema": "result"}))
    def run(command, **kwargs): commands.append(command); return CompletedProcess(command, 0, "", "")
    adapter = AndroidAdbForwardRelayTransport("adb", "sim-1", "localabstract:launcher-tx", "aut-tx", runner=run,
                                               exchange=lambda path, frame, timeout: next(responses))
    adapter.arm({"admission": "exact"}, b"memory-secret")
    assert adapter.query({"query": "sealed"}, timeout_seconds=1) == {"schema": "result"}
    adapter.close()
    assert commands == [["adb", "-s", "sim-1", "forward", "localabstract:launcher-tx", "localabstract:aut-tx"],
                        ["adb", "-s", "sim-1", "forward", "--remove", "localabstract:launcher-tx"]]
    assert "memory-secret" not in repr(commands)


@pytest.mark.parametrize("ack", [{}, {"errorCode": "APP.UAT.relay_scope_mismatch"}])
def test_ios_real_unix_socket_arms_before_ui_and_queries_without_rearm(tmp_path, ack):
    import socket
    import threading
    import tempfile
    from pathlib import Path
    from subprocess import CompletedProcess
    from quwoquan_ops.cli.lib.external_uat_relay_transport import IosSimulatorAppGroupRelayTransport
    # Darwin sockaddr_un 路径长度有限；私有临时目录不依赖 pytest 长路径。
    with tempfile.TemporaryDirectory(prefix="qwq-relay-") as directory:
        root = Path(directory).resolve()
        path = root / "aut.sock"
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(path)); server.listen(2); server.settimeout(3)
        frames = []
        errors = []
        def serve():
            import json
            try:
                for response in ([ack, {"schema": "result"}] if ack == {} else [ack]):
                    connection, _ = server.accept()
                    with connection:
                        connection.settimeout(3)
                        incoming = b""
                        while not incoming.endswith(b"\n"):
                            incoming += connection.recv(8192)
                        frames.append(json.loads(incoming))
                        connection.sendall(json.dumps(response).encode() + b"\n")
            except BaseException as error:
                errors.append(error)
        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
        adapter = IosSimulatorAppGroupRelayTransport("sim-1", "group.app.alpha.uat", "aut.sock",
            runner=lambda command, **_: CompletedProcess(command, 0, str(root), ""))
        try:
            if ack:
                with pytest.raises(ValueError, match="relay_admission_mismatch"):
                    adapter.arm({"sessionId": "native-session"}, b"x" * 32)
                with pytest.raises((ValueError, ConnectionError)):
                    adapter.query({"query": "sealed"}, timeout_seconds=1)
            else:
                adapter.arm({"sessionId": "native-session"}, b"x" * 32)
                assert [frame["operation"] for frame in frames] == ["armRelay"]
                # UI 在成功 ack 之后才允许发生。
                with pytest.raises(ValueError, match="relay_stale"):
                    adapter.arm({"sessionId": "other-session"}, b"y" * 32)
                assert adapter.query({"query": "sealed"}, timeout_seconds=1) == {"schema": "result"}
                with pytest.raises(ValueError, match="relay_consumed"):
                    adapter.query({"query": "again"}, timeout_seconds=1)
                assert len(frames) == 2 and "operation" not in frames[1]
        finally:
            adapter.close()
            server.close()
            worker.join(timeout=4)
        assert not worker.is_alive() and not errors


def test_ios_adapter_locates_exact_app_group_socket_without_secret_in_command(tmp_path):
    from subprocess import CompletedProcess
    from quwoquan_ops.cli.lib.external_uat_relay_transport import IosSimulatorAppGroupRelayTransport
    socket_path = tmp_path / "attempt.sock"; socket_path.touch()
    commands = []
    def run(command, **kwargs): commands.append(command); return CompletedProcess(command, 0, str(tmp_path) + "\n", "")
    adapter = IosSimulatorAppGroupRelayTransport("sim-1", "group.app.alpha.uat", "attempt.sock", runner=run,
                                                  exchange=lambda *_: {})
    # local_contract 无法制造 portable Unix socket inode，单独 patch Path.is_socket 只验证命令/定位边界。
    from unittest.mock import patch
    with patch("pathlib.Path.is_socket", return_value=True):
        adapter.arm({"admission": "exact"}, b"memory-secret")
    assert commands == [["xcrun", "simctl", "get_app_container", "sim-1", "group.app.alpha.uat", "group"]]
    assert "memory-secret" not in repr(commands)
    adapter.close()


def test_ios_peer_absent_uses_live_socket_and_rejects_unreadable_container(tmp_path):
    import socket
    import tempfile
    from pathlib import Path
    from subprocess import CompletedProcess
    from quwoquan_ops.cli.lib.external_uat_relay_transport import IosSimulatorAppGroupRelayTransport
    with tempfile.TemporaryDirectory(prefix="qwq-peer-") as directory:
        root = Path(directory).resolve()
        path = root / "aut.sock"
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(path)); server.listen(1)
        adapter = IosSimulatorAppGroupRelayTransport(
            "sim-1", "group.app.alpha.uat", "aut.sock",
            runner=lambda command, **_: CompletedProcess(command, 0, str(root), ""))
        try:
            assert adapter.peer_absent() is False
            server.close()
            path.unlink()
            assert adapter.peer_absent() is True
            adapter.runner = lambda command, **_: CompletedProcess(command, 1, "", "missing")
            with pytest.raises(ConnectionError, match="unreadable"):
                adapter.peer_absent()
        finally:
            server.close()

@pytest.mark.parametrize("case", relay.CASES)
def test_expected_observation_catalog_binds_each_case_without_dynamic_identity(case):
    expected = relay.expected_observation(case)
    assert expected["caseId"] == case and expected["matcher"] == "exact_ordered_rows_v1"
    assert expected["expectedObservationDigest"] == relay.digest(
        {key: value for key, value in expected.items() if key != "expectedObservationDigest"})
    forbidden = {"candidateDigest", "deviceId", "launchAttemptId", "generation", "processId", "actualObservation"}
    assert forbidden.isdisjoint(expected)
    plan = relay.build_native_case_contract(case, launch(case))
    assert plan["expectedObservation"] == expected and plan["expectedObservationDigest"] == expected["expectedObservationDigest"]


def test_expected_unknown_field_digest_drift_and_actual_mismatch_fail_closed():
    _, plan, session = admitted(); session.verify_terminal(terminal(session, plan), plan)
    result = broker(session)
    for changed in (
        {**plan["expectedObservation"], "unknown": True},
        {**plan["expectedObservation"], "expectedObservationDigest": D("0")},
    ):
        _, fresh_plan, fresh = admitted(); fresh.verify_terminal(terminal(fresh, fresh_plan), fresh_plan)
        with pytest.raises(ValueError, match="relay_contract_drift"):
            relay.compare_and_report(fresh, broker(fresh), changed)
    _, fresh_plan, fresh = admitted(); fresh.verify_terminal(terminal(fresh, fresh_plan), fresh_plan)
    mismatch = broker(fresh, observations=[{"source": "ui-control", "status": "observed", "detail": "wrong"}])
    comparison = relay.compare_and_report(fresh, mismatch, fresh_plan["expectedObservation"])
    assert comparison["status"] == "failed" and comparison["errorCode"] == "APP.UAT.relay_contract_drift"


def test_restart_supervisor_executes_exact_order_and_stops_on_failed_stage():
    events = []
    item, plan, first = admitted("identity-restart")
    first_transport = FakeTransport(); first_transport.session = first
    successor = launch("identity-restart", attempt="attempt-2", generation=2, pid=84)
    successor["continuityDigest"] = D("9")
    second_plan = relay.build_native_case_contract("identity-restart", successor)
    second_plan["planDigest"] = relay.digest(second_plan)
    second = relay.admit_launch({k: v for k, v in second_plan.items() if k != "planDigest"}, successor,
                                signing_digest=D("d"), lifecycle_digest=D("e"), now_ms=1, clock_ms=lambda: 2)
    second_transport = FakeTransport(); second_transport.session = second
    result = relay.supervise_identity_restart(
        attempt1_session=first, attempt1_plan=plan, attempt1_terminal=relay.TerminalReference(terminal(first, plan)),
        attempt1_transport=first_transport, expected_attempt1=plan["expectedObservation"],
        terminate_aut=lambda _: events.append("terminate"),
        death_readbacks=[lambda: events.append("process") or True, lambda: events.append("lifecycle") or True,
                         lambda: events.append("broker") or True],
        launch_next=lambda case, generation: events.append("launch2") or successor,
        prepare_attempt2=lambda _: events.append("prepare2") or (second_plan, second,
            relay.TerminalReference(terminal(second, second_plan)), second_transport),
        expected_attempt2=second_plan["expectedObservation"], continuity_digest=D("9"), clock_ms=lambda: 3)
    assert result["attempt1"]["status"] == result["attempt2"]["status"] == "passed"
    assert events == ["terminate", "process", "lifecycle", "broker", "launch2", "prepare2"]
    _, failed_plan, failed = admitted("identity-restart"); failed_transport = FakeTransport(); failed_transport.session = failed
    called = []
    with pytest.raises(ValueError, match="teardown_pid_alive"):
        relay.supervise_identity_restart(
            attempt1_session=failed, attempt1_plan=failed_plan,
            attempt1_terminal=relay.TerminalReference(terminal(failed, failed_plan)), attempt1_transport=failed_transport,
            expected_attempt1=failed_plan["expectedObservation"], terminate_aut=lambda _: called.append("terminate"),
            death_readbacks=[lambda: False, lambda: True, lambda: True],
            launch_next=lambda *_: called.append("launch2") or successor,
            prepare_attempt2=lambda _: (second_plan, second, relay.TerminalReference(terminal(second, second_plan)), second_transport),
            expected_attempt2=second_plan["expectedObservation"],
            continuity_digest=D("9"), clock_ms=lambda: 3)
    assert called == ["terminate"]
