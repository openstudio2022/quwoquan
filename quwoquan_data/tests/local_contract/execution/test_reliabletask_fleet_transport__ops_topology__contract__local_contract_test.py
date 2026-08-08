"""Data resolves fleet transport from stackctl rather than caller environment."""
from __future__ import annotations

import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
for path in (DATA_ROOT.parent, DATA_ROOT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from content.execution.queue.reliabletask import transport as reliabletask_transport
from content.execution.queue.reliabletask.fleet import (
    resolve_reliabletask_fleet_transport,
)


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


def test_campaign_lane__uses_plan_bound_fleet_without_stackctl__local_contract(
    monkeypatch,
    tmp_path,
) -> None:
    capsule_root = tmp_path / "capsule"
    capsule_root.mkdir()
    capsule_stackctl = capsule_root / "quwoquan_ops" / "cli" / "stackctl.py"
    stackctl_calls: list[tuple[object, ...]] = []

    def reject_stackctl(*args, **_kwargs):
        stackctl_calls.append(args)
        raise AssertionError("frozen campaign lane must not invoke stackctl")

    transport = reliabletask_transport.ReliableTaskFleetTransport(
        target="data-execution-local",
        mongo_uri="mongodb://127.0.0.1:27117/quwoquan",
        redis_addr="127.0.0.1:6389",
    )
    binding = reliabletask_transport.FrozenReliableTaskFleetBinding.create(
        root_execution_id="20260805--travel-homepage-m3--china--scale-016",
        plan_digest="sha256:" + "a" * 64,
        transport=transport,
    )
    monkeypatch.setenv(
        reliabletask_transport.CAMPAIGN_ROOT_ENV,
        binding.root_execution_id,
    )
    for name, value in binding.environment().items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(reliabletask_transport, "REPO_ROOT", capsule_root)
    monkeypatch.setattr(reliabletask_transport, "_STACKCTL_PATH", capsule_stackctl)
    monkeypatch.setattr(
        reliabletask_transport.subprocess,
        "run",
        reject_stackctl,
    )

    assert not capsule_stackctl.exists()
    assert reliabletask_transport.resolve_reliabletask_fleet_transport() == transport
    assert reliabletask_transport.reliabletask_fleet_preflight() == {
        "checked": True,
        "ready": True,
        "target": "data-execution-local",
        "mongo": True,
        "redis": True,
        "owned": True,
        "issues": [],
    }
    assert stackctl_calls == []


def test_campaign_lane__rejects_incomplete_or_drifted_fleet_binding__local_contract(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        reliabletask_transport.CAMPAIGN_ROOT_ENV,
        "20260805--travel-homepage-m3--china--scale-016",
    )
    with pytest.raises(RuntimeError, match="binding is incomplete"):
        reliabletask_transport.resolve_reliabletask_fleet_transport()

    transport = reliabletask_transport.ReliableTaskFleetTransport(
        target="data-execution-local",
        mongo_uri="mongodb://127.0.0.1:27117/quwoquan",
        redis_addr="127.0.0.1:6389",
    )
    binding = reliabletask_transport.FrozenReliableTaskFleetBinding.create(
        root_execution_id=os.environ[reliabletask_transport.CAMPAIGN_ROOT_ENV],
        plan_digest="sha256:" + "b" * 64,
        transport=transport,
    )
    for name, value in binding.environment().items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv(
        reliabletask_transport.FLEET_BINDING_DIGEST_ENV,
        "sha256:" + "c" * 64,
    )
    with pytest.raises(ValueError, match="binding digest drift"):
        reliabletask_transport.resolve_reliabletask_fleet_transport()


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
    monkeypatch.setattr(reliabletask_transport.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(reliabletask_transport.time, "sleep", sleeps.append)

    recovered = reliabletask_transport._wait_for_fleet_transport(
        transport,
        timeout_seconds=10,
        retry_delay_seconds=3,
        socket_timeout_seconds=1,
    )

    assert recovered is True
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
    assert sleeps == [1, 1, 1, 1]


def test_reliabletask_fleet_preflight__serializes_read_only_status__local_contract(
    monkeypatch,
    tmp_path,
) -> None:
    transport = reliabletask_transport.ReliableTaskFleetTransport(
        target="test",
        mongo_uri="mongodb://127.0.0.1:27017/quwoquan",
        redis_addr="127.0.0.1:6379",
    )
    status_started = threading.Event()
    release_status = threading.Event()
    active = 0
    max_active = 0
    state_lock = threading.Lock()
    start_barrier = threading.Barrier(2)

    def status(*_args):
        nonlocal active, max_active
        with state_lock:
            active += 1
            max_active = max(max_active, active)
        status_started.set()
        assert release_status.wait(timeout=2)
        with state_lock:
            active -= 1
        return {
            "exitCode": 0,
            "fleet": reliabletask_transport.transport_document(transport),
            "evidence": {
                "ready": True,
                "mongo": True,
                "redis": True,
                "owned": True,
            },
        }

    def invoke():
        start_barrier.wait(timeout=2)
        return reliabletask_transport.reliabletask_fleet_preflight()

    monkeypatch.setattr(reliabletask_transport, "DATA_LOCAL_ROOT", tmp_path)
    monkeypatch.setattr(
        reliabletask_transport,
        "_stackctl_fleet_document",
        status,
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(invoke) for _ in range(2)]
        assert status_started.wait(timeout=2)
        release_status.set()
        reports = [future.result(timeout=2) for future in futures]

    assert max_active == 1
    assert all(report["ready"] is True for report in reports)
    assert all(report["owned"] is True for report in reports)
