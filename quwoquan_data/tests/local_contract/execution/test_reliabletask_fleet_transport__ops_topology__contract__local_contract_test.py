"""Data resolves fleet transport from stackctl rather than caller environment."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


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
    ticks = iter((0.0, 1.0, 2.0))
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
    assert sleeps == [3, 3]
