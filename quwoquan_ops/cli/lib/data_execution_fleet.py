"""Resolve the one local Mongo+Redis control plane for Data ReliableTask work."""
from __future__ import annotations

import os
import socket
import subprocess
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .common import ROOT, load_json_yaml
from .port_manifest import (
    compose_published_endpoint_roles,
    compose_publisher_container_role_closure,
    load_port_manifest,
    profile_ports,
    validate_port_manifest,
)

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
# Compose service 名必须与 fleet 自有 role 名同名。canonical port manifest 把 publisher
# 身份建模成 `(composeService, containerPort, protocol, hostPort)`，而目标 runtime 的
# backing 栈也有名为 `mongodb`/`redis`、容器口同为 27017/6379 的 service；service 名一旦
# 不是 role 名，fleet 的发布口就会被归因给目标 runtime 自有的那两个 role。
MONGO_COMPOSE_SERVICE = "data-execution-mongodb"
REDIS_COMPOSE_SERVICE = "data-execution-redis"
_RUNTIME_SERVICES = frozenset({MONGO_COMPOSE_SERVICE, REDIS_COMPOSE_SERVICE})


@dataclass(frozen=True, slots=True)
class DataExecutionFleetConfig:
    target: str
    port_profile: str
    mongo_port_role: str
    redis_port_role: str

    @classmethod
    def from_document(cls, document: object) -> "DataExecutionFleetConfig":
        if not isinstance(document, dict):
            raise ValueError("data execution fleet configuration must be an object")
        expected_keys = {
            "target",
            "portProfile",
            "mongoPortRole",
            "redisPortRole",
        }
        if set(document) != expected_keys:
            raise ValueError("data execution fleet configuration has unexpected fields")
        values = {
            key: str(document.get(key) or "").strip()
            for key in expected_keys
        }
        if not all(values.values()):
            raise ValueError("data execution fleet configuration has empty fields")
        if values["target"] != "data-local":
            raise ValueError("data execution fleet target must be data-local")
        return cls(
            target=values["target"],
            port_profile=values["portProfile"],
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
    issue_code: str | None
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
            "issueCode": self.issue_code,
            "composeProject": COMPOSE_PROJECT,
            "details": list(self.details),
        }


def load_data_execution_fleet_config(
    path: Path | None = None,
) -> DataExecutionFleetConfig:
    config = DataExecutionFleetConfig.from_document(load_json_yaml(path or CONFIG_PATH))
    # 锁住「本模块用来起停/探活的 service 名 == fleet 自有 role 名」。注意它比较的是
    # Python 常量与 config 值，**不读** compose 文件的 service key —— compose 与 manifest
    # 之间的一致性由 `verify_local_env_port_manifest` 的反向闭包承担。这里守的是「本模块
    # 自己用的名字」与「它声明拥有的 role」不分叉。
    expected = {
        MONGO_COMPOSE_SERVICE: config.mongo_port_role,
        REDIS_COMPOSE_SERVICE: config.redis_port_role,
    }
    drifted = sorted(
        f"{service}!={role}" for service, role in expected.items() if service != role
    )
    if drifted:
        raise ValueError(
            "data execution fleet Compose service names must equal their port roles: "
            + ", ".join(drifted)
        )
    return config


def project_compose_published_endpoints(
    *,
    port_profile: str,
    compose_model: Mapping[str, object],
    manifest: dict[str, Any] | None = None,
) -> list[dict[str, object]]:
    resolved_profile = str(port_profile or "").strip()
    if not resolved_profile:
        raise ValueError("runtime port profile is required")
    resolved_manifest = manifest if manifest is not None else load_port_manifest()
    manifest_issues = validate_port_manifest(resolved_manifest)
    if manifest_issues:
        raise ValueError(
            "canonical port manifest is invalid: " + "; ".join(manifest_issues)
        )
    profiles = resolved_manifest.get("profiles")
    if not isinstance(profiles, Mapping) or resolved_profile not in profiles:
        raise ValueError("runtime port profile is not declared")
    publisher_roles = compose_published_endpoint_roles(
        resolved_manifest,
        resolved_profile,
    )
    container_role_closure = compose_publisher_container_role_closure(publisher_roles)

    services = compose_model.get("services")
    if not isinstance(services, Mapping):
        raise ValueError("runtime Compose model services are required")
    endpoints: list[dict[str, object]] = []
    identities: set[tuple[str, int, str]] = set()
    for service, raw_definition in services.items():
        if not isinstance(service, str) or not service.strip():
            raise ValueError("runtime Compose service name is invalid")
        if not isinstance(raw_definition, Mapping):
            raise ValueError(f"runtime Compose service definition is invalid: {service}")
        raw_ports = raw_definition.get("ports")
        if raw_ports is None:
            continue
        if (
            isinstance(raw_ports, (str, bytes, bytearray, Mapping))
            or not isinstance(raw_ports, Sequence)
        ):
            raise ValueError(f"runtime Compose service ports are invalid: {service}")
        for raw_endpoint in raw_ports:
            if not isinstance(raw_endpoint, Mapping):
                raise ValueError(
                    f"runtime Compose published endpoint is invalid: {service}"
                )
            if "published" not in raw_endpoint:
                raise ValueError(
                    f"runtime Compose published host port is required: {service}"
                )
            raw_host_port = raw_endpoint.get("published")
            if isinstance(raw_host_port, bool):
                raise ValueError(
                    f"runtime Compose published host port must be an integer: {service}"
                )
            try:
                host_port = int(raw_host_port)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"runtime Compose published host port must be an integer: {service}"
                ) from exc
            if str(raw_host_port).strip() != str(host_port) or not 0 < host_port < 65536:
                raise ValueError(
                    f"runtime Compose published host port must be an integer: {service}"
                )
            raw_target_port = raw_endpoint.get("target")
            if isinstance(raw_target_port, bool):
                raise ValueError(
                    f"runtime Compose published target port must be an integer: {service}"
                )
            try:
                target_port = int(raw_target_port)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"runtime Compose published target port must be an integer: {service}"
                ) from exc
            if (
                str(raw_target_port).strip() != str(target_port)
                or not 0 < target_port < 65536
            ):
                raise ValueError(
                    f"runtime Compose published target port must be an integer: {service}"
                )
            protocol = str(raw_endpoint.get("protocol") or "").strip().lower()
            if protocol not in {"tcp", "udp"}:
                raise ValueError(
                    f"runtime Compose published endpoint protocol is invalid: {service}"
                )
            role = publisher_roles.get((service, target_port, protocol, host_port))
            if role is None:
                # 四元组未命中有两种根因，恢复动作不同：容器侧发布身份根本没声明，
                # 与已声明身份的主机端口发生漂移。前缀闭包用来把两者分开判否。
                if (service, target_port, protocol) in container_role_closure:
                    raise ValueError(
                        "runtime Compose published host port is not canonical: "
                        f"{resolved_profile}/{service}:{target_port}/{protocol}"
                        f"->{host_port}"
                    )
                raise ValueError(
                    "runtime Compose publisher identity is not canonical: "
                    f"{resolved_profile}/{service}:{target_port}/{protocol}"
                )
            identity = (role, host_port, protocol)
            if identity in identities:
                raise ValueError(
                    "runtime Compose published endpoint identities must be distinct"
                )
            identities.add(identity)
            endpoints.append(
                {"role": role, "hostPort": host_port, "protocol": protocol}
            )
    if not endpoints:
        raise ValueError("runtime Compose published port ownership is required")
    return sorted(
        endpoints,
        key=lambda endpoint: (
            int(endpoint["hostPort"]),
            str(endpoint["protocol"]),
            str(endpoint["role"]),
        ),
    )


def require_published_endpoint_port(
    published_ports: Sequence[Mapping[str, object]],
    *,
    role: str,
    protocol: str,
) -> int:
    resolved_role = str(role or "").strip()
    resolved_protocol = str(protocol or "").strip().lower()
    if not resolved_role:
        raise ValueError("runtime published endpoint role is required")
    if resolved_protocol not in {"tcp", "udp"}:
        raise ValueError("runtime published endpoint protocol must be tcp or udp")
    if (
        isinstance(published_ports, (str, bytes, bytearray, Mapping))
        or not isinstance(published_ports, Sequence)
    ):
        raise ValueError("runtime published endpoints must be a list")
    matches: list[int] = []
    for endpoint in published_ports:
        if not isinstance(endpoint, Mapping) or set(endpoint) != {
            "role",
            "hostPort",
            "protocol",
        }:
            raise ValueError("runtime published endpoint fields are invalid")
        endpoint_role = str(endpoint.get("role") or "").strip()
        endpoint_protocol = str(endpoint.get("protocol") or "").strip().lower()
        endpoint_port = endpoint.get("hostPort")
        if not endpoint_role:
            raise ValueError("runtime published endpoint role is required")
        if endpoint_protocol not in {"tcp", "udp"}:
            raise ValueError("runtime published endpoint protocol must be tcp or udp")
        if (
            not isinstance(endpoint_port, int)
            or isinstance(endpoint_port, bool)
            or not 0 < endpoint_port < 65536
        ):
            raise ValueError("runtime published endpoint hostPort must be an integer")
        if endpoint_role == resolved_role and endpoint_protocol == resolved_protocol:
            matches.append(endpoint_port)
    if len(matches) != 1:
        raise ValueError(
            "runtime published endpoints require exactly one "
            f"{resolved_role}/{resolved_protocol} identity"
        )
    return matches[0]


def project_canonical_runtime_owned_ports(
    *,
    port_profile: str,
    manifest: dict[str, Any] | None = None,
) -> list[dict[str, object]]:
    resolved_manifest = manifest if manifest is not None else load_port_manifest()
    canonical_ports = profile_ports(resolved_manifest, port_profile)
    endpoints = {
        (role, canonical_ports[role], protocol)
        for (
            _compose_service,
            _container_port,
            protocol,
            _host_port,
        ), role in compose_published_endpoint_roles(
            resolved_manifest,
            port_profile,
        ).items()
    }
    return project_runtime_owned_ports(
        port_profile=port_profile,
        published_ports=[
            {"role": role, "hostPort": host_port, "protocol": protocol}
            for role, host_port, protocol in sorted(
                endpoints,
                key=lambda item: (item[1], item[2], item[0]),
            )
        ],
        manifest=resolved_manifest,
    )


def project_runtime_owned_ports(
    *,
    port_profile: str,
    published_ports: Sequence[Mapping[str, object]] | None,
    manifest: dict[str, Any] | None = None,
) -> list[dict[str, object]]:
    resolved_profile = str(port_profile or "").strip()
    if not resolved_profile:
        raise ValueError("runtime port profile is required")
    resolved_manifest = manifest if manifest is not None else load_port_manifest()
    manifest_issues = validate_port_manifest(resolved_manifest)
    if manifest_issues:
        raise ValueError(
            "canonical port manifest is invalid: " + "; ".join(manifest_issues)
        )
    profiles = resolved_manifest.get("profiles")
    if not isinstance(profiles, Mapping) or resolved_profile not in profiles:
        raise ValueError("runtime port profile is not declared")
    canonical_ports = profile_ports(resolved_manifest, resolved_profile)
    fleet = load_data_execution_fleet_config()
    fleet_roles = (fleet.mongo_port_role, fleet.redis_port_role)
    if len(set(fleet_roles)) != len(fleet_roles):
        raise ValueError("data execution fleet port roles must be distinct")
    if fleet.port_profile not in profiles:
        raise ValueError("data execution fleet port profile is not declared")
    fleet_ports = profile_ports(resolved_manifest, fleet.port_profile)
    for role in fleet_roles:
        if role not in canonical_ports or role not in fleet_ports:
            raise ValueError("data execution fleet port role is not declared")
    fleet_identities = {
        (fleet.port_profile, role, fleet_ports[role]) for role in fleet_roles
    }
    if len(fleet_identities) != len(fleet_roles):
        raise ValueError("data execution fleet port ownership must be unique")

    publisher_protocols: dict[str, set[str]] = {}
    for (
        _compose_service,
        _container_port,
        protocol,
        _host_port,
    ), role in compose_published_endpoint_roles(
        resolved_manifest,
        resolved_profile,
    ).items():
        publisher_protocols.setdefault(role, set()).add(protocol)
    for role in fleet_roles:
        publisher_protocols.setdefault(role, set()).add("tcp")

    if (
        published_ports is None
        or isinstance(published_ports, (str, bytes, bytearray, Mapping))
        or not isinstance(published_ports, Sequence)
        or not published_ports
    ):
        if isinstance(published_ports, Mapping):
            raise ValueError("runtime published port ownership must be a list")
        raise ValueError("runtime published port ownership is required")
    normalized_endpoints: list[dict[str, object]] = []
    endpoint_identities: set[tuple[str, int, str]] = set()
    for raw_endpoint in published_ports:
        if not isinstance(raw_endpoint, Mapping) or set(raw_endpoint) != {
            "role",
            "hostPort",
            "protocol",
        }:
            raise ValueError("runtime published endpoint fields are invalid")
        role = str(raw_endpoint.get("role") or "").strip()
        raw_port = raw_endpoint.get("hostPort")
        protocol = str(raw_endpoint.get("protocol") or "").strip().lower()
        if not role:
            raise ValueError("runtime published endpoint role is required")
        if not isinstance(raw_port, int) or isinstance(raw_port, bool):
            raise ValueError("runtime published endpoint hostPort must be an integer")
        if protocol not in {"tcp", "udp"}:
            raise ValueError("runtime published endpoint protocol must be tcp or udp")
        if role not in canonical_ports:
            raise ValueError(f"runtime published port role is not declared: {role}")
        if protocol not in publisher_protocols.get(role, set()):
            raise ValueError(
                "runtime published endpoint publisher protocol is not canonical: "
                f"{resolved_profile}/{role}/{protocol}"
            )
        if canonical_ports[role] != raw_port:
            raise ValueError(
                f"runtime published port is not canonical: "
                f"{resolved_profile}/{role}:{raw_port}"
            )
        identity = (role, raw_port, protocol)
        if identity in endpoint_identities:
            raise ValueError("runtime published endpoint identities must be distinct")
        endpoint_identities.add(identity)
        normalized_endpoints.append(
            {"role": role, "hostPort": raw_port, "protocol": protocol}
        )

    return [
        endpoint
        for endpoint in normalized_endpoints
        if (
            resolved_profile,
            str(endpoint["role"]),
            int(endpoint["hostPort"]),
        )
        not in fleet_identities
    ]


def resolve_data_execution_fleet_endpoint(
    config: DataExecutionFleetConfig | None = None,
) -> DataExecutionFleetEndpoint:
    resolved = config or load_data_execution_fleet_config()
    ports = profile_ports(load_port_manifest(), resolved.port_profile)
    try:
        mongo_port = ports[resolved.mongo_port_role]
        redis_port = ports[resolved.redis_port_role]
    except KeyError as exc:
        raise ValueError("data execution fleet port role is not declared") from exc
    if not isinstance(mongo_port, int) or not isinstance(redis_port, int):
        raise ValueError("data execution fleet ports must be integers")
    return DataExecutionFleetEndpoint(
        target=resolved.target,
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
        MONGO_COMPOSE_SERVICE,
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
        REDIS_COMPOSE_SERVICE,
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
    ready = mongo_ready and redis_ready and owned
    return DataExecutionFleetRuntime(
        action=action,
        target=resolved.target,
        ready=ready,
        mongo=mongo_ready,
        redis=redis_ready,
        owned=owned,
        changed=changed,
        issue_code=None if ready else "DATA.POOL.DELIVERY_UNAVAILABLE",
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
    _run_compose(resolved, "up", "-d", MONGO_COMPOSE_SERVICE, REDIS_COMPOSE_SERVICE)
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
    "FLEET_ACTIONS",
    "DataExecutionFleetConfig",
    "DataExecutionFleetEndpoint",
    "DataExecutionFleetRuntime",
    "data_execution_fleet_status",
    "load_data_execution_fleet_config",
    "manage_data_execution_fleet",
    "project_canonical_runtime_owned_ports",
    "project_compose_published_endpoints",
    "project_runtime_owned_ports",
    "require_published_endpoint_port",
    "resolve_data_execution_fleet_endpoint",
]
