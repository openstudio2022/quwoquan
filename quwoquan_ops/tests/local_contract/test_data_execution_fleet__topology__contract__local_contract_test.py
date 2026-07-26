"""Data ReliableTask endpoints are resolved from the Ops-owned local topology."""
from __future__ import annotations

from quwoquan_ops.cli.lib.data_execution_fleet import (
    DataExecutionFleetConfig,
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
