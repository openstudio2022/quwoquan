"""Data resolves fleet transport from stackctl rather than caller environment."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
import sys
import threading
from pathlib import Path
from types import SimpleNamespace


DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
for path in (DATA_ROOT.parent, DATA_ROOT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from content.execution import reliabletask_transport  # noqa: E402
from content.execution.reliabletask_fleet import resolve_reliabletask_fleet_transport  # noqa: E402


def test_reliabletask_fleet_transport__ignores_caller_endpoint_variables__contract__local_contract(
    monkeypatch,
) -> None:
    monkeypatch.setenv("QWQ_DATA_FLEET_MONGO_URI", "mongodb://caller.invalid:27017")
    monkeypatch.setenv("QWQ_DATA_FLEET_REDIS_ADDR", "caller.invalid:6379")

    transport = resolve_reliabletask_fleet_transport()
    policy = json.loads(
        (DATA_ROOT.parent / "quwoquan_ops/environments/data_execution_fleet.json").read_text(
            encoding="utf-8"
        )
    )

    assert transport.target == policy["localTarget"]
    assert "caller.invalid" not in transport.mongo_uri
    assert "caller.invalid" not in transport.redis_addr
    assert os.environ["QWQ_DATA_FLEET_MONGO_URI"] == "mongodb://caller.invalid:27017"


def test_reliabletask_fleet_transport__waits_until_both_backends_recover__local_contract(
    monkeypatch,
) -> None:
    probes = iter((False, False, False, True))
    ticks = iter((0.0, 1.0, 2.0, 3.0))
    sleeps: list[float] = []
    transport = reliabletask_transport.ReliableTaskFleetTransport(
        target="test",
        mongo_uri="mongodb://127.0.0.1:27017/quwoquan",
        redis_addr="127.0.0.1:6379",
    )
    monkeypatch.setattr(
        reliabletask_transport,
        "_fleet_transport_ready",
        lambda _transport, **_kwargs: next(probes),
    )
    reconciled: list[str] = []
    monkeypatch.setattr(
        reliabletask_transport,
        "_ensure_reliabletask_fleet_transport",
        lambda current: reconciled.append(current.target),
    )
    monkeypatch.setattr(reliabletask_transport.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(reliabletask_transport.time, "sleep", sleeps.append)

    recovered = reliabletask_transport._wait_for_fleet_transport(
        transport,
        timeout_seconds=10,
        retry_delay_seconds=3,
        socket_timeout_seconds=1,
    )

    assert recovered is True
    assert reconciled == ["test"]
    assert sleeps == [3, 3, 3]


def test_reliabletask_fleet_transport__requires_stable_ready_window__local_contract(
    monkeypatch,
) -> None:
    probes = iter((True, False, True, True, True))
    ticks = iter((0.0, 1.0, 2.0, 3.0, 4.0))
    sleeps: list[float] = []
    transport = reliabletask_transport.ReliableTaskFleetTransport(
        target="test",
        mongo_uri="mongodb://127.0.0.1:27017/quwoquan",
        redis_addr="127.0.0.1:6379",
    )
    monkeypatch.setattr(
        reliabletask_transport,
        "_fleet_transport_ready",
        lambda _transport, **_kwargs: next(probes),
    )
    reconciled: list[str] = []
    monkeypatch.setattr(
        reliabletask_transport,
        "_ensure_reliabletask_fleet_transport",
        lambda current: reconciled.append(current.target),
    )
    monkeypatch.setattr(reliabletask_transport.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(reliabletask_transport.time, "sleep", sleeps.append)

    recovered = reliabletask_transport._wait_for_fleet_transport(
        transport,
        timeout_seconds=10,
        retry_delay_seconds=1,
        socket_timeout_seconds=1,
        required_ready_probes=3,
    )

    assert recovered is True
    assert reconciled == ["test"]
    assert sleeps == [1, 1, 1, 1]


def test_reliabletask_fleet_preflight__serializes_cold_start_reconcile__local_contract(
    monkeypatch,
    tmp_path,
) -> None:
    transport = reliabletask_transport.ReliableTaskFleetTransport(
        target="test",
        mongo_uri="mongodb://127.0.0.1:27017/quwoquan",
        redis_addr="127.0.0.1:6379",
    )
    state = {"ready": False}
    reconcile_started = threading.Event()
    release_reconcile = threading.Event()
    reconcile_calls: list[str] = []
    start_barrier = threading.Barrier(2)

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def reconcile(current):
        reconcile_calls.append(current.target)
        reconcile_started.set()
        assert release_reconcile.wait(timeout=2)
        state["ready"] = True

    def invoke():
        start_barrier.wait(timeout=2)
        return reliabletask_transport.reliabletask_fleet_preflight()

    monkeypatch.setattr(reliabletask_transport, "DATA_LOCAL_ROOT", tmp_path)
    monkeypatch.setattr(
        reliabletask_transport,
        "resolve_reliabletask_fleet_transport",
        lambda: transport,
    )
    monkeypatch.setattr(
        reliabletask_transport,
        "_fleet_transport_ready",
        lambda *_args, **_kwargs: state["ready"],
    )
    monkeypatch.setattr(
        reliabletask_transport,
        "_ensure_reliabletask_fleet_transport",
        reconcile,
    )
    monkeypatch.setattr(
        "core.runtime_policy.active_runtime_policy",
        lambda: SimpleNamespace(preflight_network_timeout_seconds=1),
    )
    monkeypatch.setattr(
        reliabletask_transport.socket,
        "create_connection",
        lambda *_args, **_kwargs: Connection(),
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(invoke) for _ in range(2)]
        assert reconcile_started.wait(timeout=2)
        release_reconcile.set()
        reports = [future.result(timeout=2) for future in futures]

    assert reconcile_calls == ["test"]
    assert all(report["ready"] is True for report in reports)
