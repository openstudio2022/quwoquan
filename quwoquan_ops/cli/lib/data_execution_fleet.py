"""Resolve the one local Mongo+Redis control plane for Data ReliableTask work."""
from __future__ import annotations

import os
import socket
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .common import ROOT, load_json_yaml
from .environment_topology import get_target, load_environment_topology
from .port_manifest import load_port_manifest, profile_ports


CONFIG_PATH = ROOT / "quwoquan_ops" / "environments" / "data_execution_fleet.json"
LOCAL_LOOPBACK_HOST = "127.0.0.1"
MONGO_DIRECT_CONNECTION_QUERY = "?directConnection=true"
COMPOSE_PATH = (
    ROOT
    / "quwoquan_ops"
    / "environments"
    / "compose"
    / "docker-compose.data-execution-fleet.yaml"
)
COMPOSE_PROJECT = "quwoquan-data-execution-fleet"
FLEET_ACTIONS = ("resolve", "up", "status", "down")
_RUNTIME_SERVICES = frozenset({"mongodb", "redis"})


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


@dataclass(frozen=True, slots=True)
class DataExecutionFleetRuntime:
    action: str
    target: str
    ready: bool
    mongo: bool
    redis: bool
    owned: bool
    changed: bool
    details: tuple[str, ...]

    def document(self) -> dict[str, object]:
        return {
            "action": self.action,
            "target": self.target,
            "ready": self.ready,
            "mongo": self.mongo,
            "redis": self.redis,
            "owned": self.owned,
            "changed": self.changed,
            "composeProject": COMPOSE_PROJECT,
            "details": list(self.details),
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


def _endpoint_ports(endpoint: DataExecutionFleetEndpoint) -> tuple[int, int]:
    mongo = urlparse(endpoint.mongo_uri)
    _redis_host, separator, redis_port = endpoint.redis_addr.rpartition(":")
    if mongo.hostname != LOCAL_LOOPBACK_HOST or mongo.port is None or not separator:
        raise ValueError("data execution fleet endpoint contract is invalid")
    return mongo.port, int(redis_port)


def _compose_command(*args: str) -> list[str]:
    return [
        "docker",
        "compose",
        "-p",
        COMPOSE_PROJECT,
        "-f",
        str(COMPOSE_PATH),
        *args,
    ]


def _compose_environment(endpoint: DataExecutionFleetEndpoint) -> dict[str, str]:
    mongo_port, redis_port = _endpoint_ports(endpoint)
    environment = os.environ.copy()
    environment.update(
        {
            "QWQ_DATA_FLEET_MONGO_PORT": str(mongo_port),
            "QWQ_DATA_FLEET_REDIS_PORT": str(redis_port),
        }
    )
    return environment


def _socket_ready(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def _compose_running_services(
    endpoint: DataExecutionFleetEndpoint,
) -> frozenset[str]:
    completed = subprocess.run(
        _compose_command("ps", "--status", "running", "--services"),
        cwd=ROOT,
        env=_compose_environment(endpoint),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return frozenset()
    return frozenset(line.strip() for line in completed.stdout.splitlines() if line.strip())


def _compose_service_probe(
    endpoint: DataExecutionFleetEndpoint,
    service: str,
    *command: str,
    expected_stdout: str | None = None,
) -> bool:
    completed = subprocess.run(
        _compose_command("exec", "-T", service, *command),
        cwd=ROOT,
        env=_compose_environment(endpoint),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return False
    if expected_stdout is None:
        return True
    return completed.stdout.strip() == expected_stdout and not completed.stderr.strip()


def _mongo_writable(endpoint: DataExecutionFleetEndpoint) -> bool:
    probe_id = f"stackctl-{uuid.uuid4().hex}"
    script = (
        'const d=db.getSiblingDB("admin");'
        'const h=d.runCommand({hello:1});'
        'if(h.ok!==1||h.setName!=="rs0"||h.isWritablePrimary!==true){quit(10)};'
        'const c=d.getCollection("__qwq_data_execution_fleet_probe");'
        f'const id="{probe_id}";'
        'c.insertOne({_id:id,expiresAt:new Date(Date.now()+60000)});'
        'if(c.findOne({_id:id})===null){quit(11)};'
        'c.deleteOne({_id:id});'
    )
    return _compose_service_probe(
        endpoint,
        "mongodb",
        "mongosh",
        "--quiet",
        "--eval",
        script,
    )


def _redis_writable(endpoint: DataExecutionFleetEndpoint) -> bool:
    key = f"__qwq_data_execution_fleet_probe:{uuid.uuid4().hex}"
    script = (
        "redis.call('SET',KEYS[1],'ok','EX',10);"
        "local v=redis.call('GET',KEYS[1]);"
        "redis.call('DEL',KEYS[1]);return v"
    )
    return _compose_service_probe(
        endpoint,
        "redis",
        "redis-cli",
        "--raw",
        "EVAL",
        script,
        "1",
        key,
        expected_stdout="ok",
    )


def data_execution_fleet_status(
    endpoint: DataExecutionFleetEndpoint | None = None,
    *,
    action: str = "status",
    changed: bool = False,
    details: tuple[str, ...] = (),
) -> DataExecutionFleetRuntime:
    resolved = endpoint or resolve_data_execution_fleet_endpoint()
    mongo_port, redis_port = _endpoint_ports(resolved)
    owned = _RUNTIME_SERVICES.issubset(_compose_running_services(resolved))
    mongo_ready = bool(
        owned
        and _socket_ready(LOCAL_LOOPBACK_HOST, mongo_port)
        and _mongo_writable(resolved)
    )
    redis_ready = bool(
        owned
        and _socket_ready(LOCAL_LOOPBACK_HOST, redis_port)
        and _redis_writable(resolved)
    )
    return DataExecutionFleetRuntime(
        action=action,
        target=resolved.target,
        ready=mongo_ready and redis_ready and owned,
        mongo=mongo_ready,
        redis=redis_ready,
        owned=owned,
        changed=changed,
        details=details,
    )


def _wait_for_fleet_ports(
    endpoint: DataExecutionFleetEndpoint,
    *,
    timeout_seconds: float = 120.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    mongo_port, redis_port = _endpoint_ports(endpoint)
    while time.monotonic() < deadline:
        if _socket_ready(LOCAL_LOOPBACK_HOST, mongo_port) and _socket_ready(
            LOCAL_LOOPBACK_HOST, redis_port
        ):
            return
        time.sleep(1.0)
    raise RuntimeError("data execution fleet Mongo/Redis startup timed out")


def _run_compose(
    endpoint: DataExecutionFleetEndpoint,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        _compose_command(*args),
        cwd=ROOT,
        env=_compose_environment(endpoint),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        raise RuntimeError(
            f"data execution fleet compose failed rc={completed.returncode}: "
            + (detail[-1] if detail else "no diagnostic output")
        )
    return completed


def manage_data_execution_fleet(
    action: str,
    endpoint: DataExecutionFleetEndpoint | None = None,
) -> DataExecutionFleetRuntime:
    normalized = str(action or "").strip()
    if normalized not in FLEET_ACTIONS or normalized == "resolve":
        raise ValueError("data execution fleet action must be up, status, or down")
    resolved = endpoint or resolve_data_execution_fleet_endpoint()
    before = data_execution_fleet_status(resolved, action=normalized)
    if normalized == "status":
        return before
    if normalized == "down":
        _run_compose(resolved, "down", "--remove-orphans")
        return data_execution_fleet_status(
            resolved,
            action=normalized,
            changed=before.mongo or before.redis or before.owned,
            details=("dedicated fleet stopped; persistent volumes preserved",),
        )
    if before.ready:
        return data_execution_fleet_status(
            resolved,
            action=normalized,
            details=("dedicated fleet already ready",),
        )
    mongo_port, redis_port = _endpoint_ports(resolved)
    ports_occupied = _socket_ready(
        LOCAL_LOOPBACK_HOST, mongo_port
    ) or _socket_ready(LOCAL_LOOPBACK_HOST, redis_port)
    if ports_occupied and not before.owned:
        raise RuntimeError(
            "data execution fleet ports are occupied outside the dedicated compose project"
        )
    _run_compose(resolved, "up", "-d", "mongodb", "redis")
    _wait_for_fleet_ports(resolved)
    _run_compose(resolved, "run", "--rm", "mongo-init")
    after = data_execution_fleet_status(
        resolved,
        action=normalized,
        changed=True,
        details=("dedicated Mongo/Redis fleet started through stackctl",),
    )
    if not after.ready:
        raise RuntimeError("data execution fleet failed ownership/readiness verification")
    return after


__all__ = [
    "DataExecutionFleetConfig",
    "DataExecutionFleetEndpoint",
    "DataExecutionFleetRuntime",
    "FLEET_ACTIONS",
    "data_execution_fleet_status",
    "load_data_execution_fleet_config",
    "manage_data_execution_fleet",
    "resolve_data_execution_fleet_endpoint",
]
