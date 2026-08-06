"""Data ReliableTask endpoints are resolved from the Ops-owned local topology.

spec_ref: specs/feature-tree/platform-ops-governance/config-and-reliability-governance/config-source-governance/spec.md#gwt-001
"""
from __future__ import annotations

from quwoquan_ops.cli.lib.data_execution_fleet import (
    COMPOSE_PATH,
    DataExecutionFleetConfig,
    _redis_writable,
    data_execution_fleet_status,
    load_data_execution_fleet_config,
    resolve_data_execution_fleet_endpoint,
)
from quwoquan_ops.cli.lib.port_manifest import load_port_manifest, profile_ports


def test_data_execution_fleet__uses_one_declared_local_target__contract__local_contract() -> None:
    config = load_data_execution_fleet_config()
    endpoint = resolve_data_execution_fleet_endpoint(config)
    ports = profile_ports(load_port_manifest(), config.local_target)

    assert endpoint.target == config.local_target
    assert endpoint.mongo_uri.endswith(f":{ports[config.mongo_port_role]}/?directConnection=true")
    assert endpoint.redis_addr.endswith(f":{ports[config.redis_port_role]}")
    assert config.mongo_port_role == "data-execution-mongodb"
    assert config.redis_port_role == "data-execution-redis"
    assert ports[config.mongo_port_role] != ports["mongodb"]
    assert ports[config.redis_port_role] != ports["redis"]


def test_data_execution_fleet__rejects_implicit_or_extra_configuration__contract__local_contract() -> None:
    try:
        DataExecutionFleetConfig.from_document(
            {
                "localTarget": "gamma-local",
                "mongoPortRole": "mongodb",
                "redisPortRole": "redis",
                "fallbackTarget": "beta-local",
            }
        )
    except ValueError as exc:
        assert "unexpected fields" in str(exc)
    else:
        raise AssertionError("fleet topology must not accept a fallback target")


def test_data_execution_fleet__dedicated_compose_owns_both_endpoints__contract__local_contract(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.data_execution_fleet._socket_ready",
        lambda _host, _port: True,
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.data_execution_fleet._compose_running_services",
        lambda _endpoint: frozenset({"mongodb", "redis"}),
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.data_execution_fleet._mongo_writable",
        lambda _endpoint: True,
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.data_execution_fleet._redis_writable",
        lambda _endpoint: True,
    )

    status = data_execution_fleet_status()

    assert status.ready is True
    assert status.owned is True
    compose = COMPOSE_PATH.read_text(encoding="utf-8")
    assert "QWQ_DATA_FLEET_MONGO_PORT" in compose
    assert "QWQ_DATA_FLEET_REDIS_PORT" in compose
    assert "postgres" not in compose
    assert "object-storage" not in compose


def test_data_execution_fleet__tcp_without_writable_backends_is_not_ready__contract__local_contract(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.data_execution_fleet._socket_ready",
        lambda _host, _port: True,
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.data_execution_fleet._compose_running_services",
        lambda _endpoint: frozenset({"mongodb", "redis"}),
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.data_execution_fleet._mongo_writable",
        lambda _endpoint: True,
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.data_execution_fleet._redis_writable",
        lambda _endpoint: False,
    )

    status = data_execution_fleet_status()

    assert status.ready is False
    assert status.mongo is True
    assert status.redis is False


def test_data_execution_fleet__redis_probe_requires_exact_write_read_delete_result__contract__local_contract(
    monkeypatch,
) -> None:
    endpoint = resolve_data_execution_fleet_endpoint()

    class Result:
        returncode = 0
        stdout = "LOADING Redis is loading the dataset in memory\n"
        stderr = ""

    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.data_execution_fleet.subprocess.run",
        lambda *_args, **_kwargs: Result(),
    )

    assert _redis_writable(endpoint) is False
