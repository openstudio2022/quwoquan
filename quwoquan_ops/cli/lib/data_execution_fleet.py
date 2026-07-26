"""Resolve the one local Mongo+Redis control plane for Data ReliableTask work."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .common import ROOT, load_json_yaml
from .environment_topology import get_target, load_environment_topology
from .port_manifest import load_port_manifest, profile_ports


CONFIG_PATH = ROOT / "quwoquan_ops" / "environments" / "data_execution_fleet.json"
LOCAL_LOOPBACK_HOST = "127.0.0.1"
MONGO_DIRECT_CONNECTION_QUERY = "?directConnection=true"


@dataclass(frozen=True, slots=True)
class DataExecutionFleetConfig:
    local_target: str
    mongo_port_role: str
    redis_port_role: str

    @classmethod
    def from_document(cls, document: object) -> "DataExecutionFleetConfig":
        if not isinstance(document, dict):
            raise ValueError("data execution fleet configuration must be an object")
        expected_keys = {"localTarget", "mongoPortRole", "redisPortRole"}
        if set(document) != expected_keys:
            raise ValueError("data execution fleet configuration has unexpected fields")
        values = {
            key: str(document.get(key) or "").strip()
            for key in expected_keys
        }
        if not all(values.values()):
            raise ValueError("data execution fleet configuration has empty fields")
        return cls(
            local_target=values["localTarget"],
            mongo_port_role=values["mongoPortRole"],
            redis_port_role=values["redisPortRole"],
        )


@dataclass(frozen=True, slots=True)
class DataExecutionFleetEndpoint:
    target: str
    mongo_uri: str
    redis_addr: str

    def document(self) -> dict[str, str]:
        return {
            "target": self.target,
            "mongoUri": self.mongo_uri,
            "redisAddr": self.redis_addr,
        }


def load_data_execution_fleet_config(
    path: Path | None = None,
) -> DataExecutionFleetConfig:
    return DataExecutionFleetConfig.from_document(load_json_yaml(path or CONFIG_PATH))


def resolve_data_execution_fleet_endpoint(
    config: DataExecutionFleetConfig | None = None,
) -> DataExecutionFleetEndpoint:
    resolved = config or load_data_execution_fleet_config()
    target = get_target(load_environment_topology(), resolved.local_target)
    if str(target.get("backend") or "").strip() != "local":
        raise ValueError("data execution fleet target must use the local backend")
    ports = profile_ports(load_port_manifest(), resolved.local_target)
    try:
        mongo_port = ports[resolved.mongo_port_role]
        redis_port = ports[resolved.redis_port_role]
    except KeyError as exc:
        raise ValueError("data execution fleet port role is not declared") from exc
    if not isinstance(mongo_port, int) or not isinstance(redis_port, int):
        raise ValueError("data execution fleet ports must be integers")
    return DataExecutionFleetEndpoint(
        target=resolved.local_target,
        mongo_uri=(
            f"mongodb://{LOCAL_LOOPBACK_HOST}:{mongo_port}/"
            f"{MONGO_DIRECT_CONNECTION_QUERY}"
        ),
        redis_addr=f"{LOCAL_LOOPBACK_HOST}:{redis_port}",
    )


__all__ = [
    "DataExecutionFleetConfig",
    "DataExecutionFleetEndpoint",
    "load_data_execution_fleet_config",
    "resolve_data_execution_fleet_endpoint",
]
