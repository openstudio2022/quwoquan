"""orphan Compose teardown 的一次性 attestation 封版、加载与精确删除指令。

原单文件 ``orphan_compose_teardown.py`` 拆分出的 attestation 子模块。
"""

from __future__ import annotations

import json
import stat
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..port_manifest import (
    compose_published_endpoint_roles,
    compose_publisher_container_role_closure,
    load_port_manifest,
)
from .constants import (
    ATTESTATION_TTL_SECONDS,
    SCHEMA,
    OrphanComposeTeardownError,
    _atomic_write_create_once,
    _canonical_bytes,
    _digest,
    _normalize_published_endpoints,
    _timestamp,
    _utc_text,
    declared_port_profile,
    require_canonical_project,
)


def seal_attestation(
    snapshot: Mapping[str, Any],
    *,
    sampled_at: datetime | None = None,
) -> dict[str, Any]:
    now = (sampled_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "target": snapshot.get("target"),
        "project": snapshot.get("project"),
        "sampledAt": _utc_text(now),
        "expiresAt": _utc_text(now + timedelta(seconds=ATTESTATION_TTL_SECONDS)),
        "snapshot": dict(snapshot),
        "snapshotDigest": _digest(snapshot),
    }
    payload["attestationDigest"] = _digest(payload)
    return validate_attestation(payload, now=now)


def validate_attestation(
    value: object,
    *,
    expected_target: str = "",
    now: datetime | None = None,
    allow_expired: bool = False,
) -> dict[str, Any]:
    fields = {
        "schema",
        "target",
        "project",
        "sampledAt",
        "expiresAt",
        "snapshot",
        "snapshotDigest",
        "attestationDigest",
    }
    if not isinstance(value, dict) or set(value) != fields or value.get("schema") != SCHEMA:
        raise OrphanComposeTeardownError("orphan Compose attestation fields/schema mismatch")
    target = str(value.get("target") or "")
    if expected_target and target != expected_target:
        raise OrphanComposeTeardownError("orphan Compose attestation target mismatch")
    project = require_canonical_project(target, value.get("project"))
    snapshot = value.get("snapshot")
    if (
        not isinstance(snapshot, dict)
        or snapshot.get("target") != target
        or snapshot.get("project") != project
    ):
        raise OrphanComposeTeardownError("orphan Compose attestation snapshot identity mismatch")
    snapshot_fields = {
        "target",
        "project",
        "canonicalPorts",
        "otherTargetPortBlocks",
        "publishedEndpoints",
        "containers",
        "networks",
        "volumes",
    }
    if set(snapshot) != snapshot_fields:
        raise OrphanComposeTeardownError(
            "orphan Compose attestation snapshot fields mismatch"
        )
    canonical_ports = snapshot.get("canonicalPorts")
    if not isinstance(canonical_ports, list):
        raise OrphanComposeTeardownError(
            "orphan Compose attestation canonical port inventory is invalid"
        )
    canonical_roles: set[str] = set()
    for item in canonical_ports:
        if not isinstance(item, Mapping) or set(item) != {"name", "port", "open"}:
            raise OrphanComposeTeardownError(
                "orphan Compose attestation canonical port fields are invalid"
            )
        role = str(item.get("name") or "").strip()
        port = item.get("port")
        opened = item.get("open")
        if (
            not role
            or role in canonical_roles
            or isinstance(port, bool)
            or not isinstance(port, int)
            or not 0 < port < 65536
            or not isinstance(opened, bool)
        ):
            raise OrphanComposeTeardownError(
                "orphan Compose attestation canonical port identity is invalid"
            )
        canonical_roles.add(role)
    published_endpoints = _normalize_published_endpoints(
        snapshot.get("publishedEndpoints")
    )
    if any(str(item["role"]) not in canonical_roles for item in published_endpoints):
        raise OrphanComposeTeardownError(
            "orphan Compose published endpoint role is not canonical"
        )
    containers = snapshot.get("containers")
    if not isinstance(containers, list):
        raise OrphanComposeTeardownError(
            "orphan Compose attestation container inventory is invalid"
        )
    container_fields = {
        "id",
        "name",
        "service",
        "labels",
        "imageRef",
        "imageDigest",
        "configurationDigest",
        "publishedEndpoints",
    }
    port_profile = declared_port_profile(target)
    try:
        publisher_roles = compose_published_endpoint_roles(
            load_port_manifest(),
            port_profile,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise OrphanComposeTeardownError(
            "orphan Compose attestation publisher manifest is invalid"
        ) from exc
    # 白名单必须恰好覆盖 inventory 能合法产出的集合，否则封存会把刚采到的事实判否。
    # inventory 有两条归因路径：四元组精确命中 canonical hostPort；以及旧栈发布的非
    # canonical hostPort —— 那条只在容器发布口仅归一个 role 时成立。这里按同一判据
    # 分成精确集与「独占容器发布口」集，两者都从 publisher_roles 派生，不另立判据。
    container_role_closure = compose_publisher_container_role_closure(publisher_roles)
    canonical_identities: set[tuple[str, str, str, int]] = set()
    sole_owner_identities: set[tuple[str, str, str]] = set()
    # `sole_owner_identities` 的键丢掉了 containerPort，它与 inventory 的归因等价只在
    # 「同一 role 在同一 composeService+protocol 下只有一个容器口」时成立。该前提今天由
    # port manifest 的两条校验联合保证，但那是跨文件不变量：放宽任一条，白名单就会比
    # inventory 宽，本该判否的非 canonical hostPort 会被放行。故就地显式断言，不外借。
    role_container_ports: dict[tuple[str, str, str], set[int]] = {}
    for (
        compose_service,
        container_port,
        protocol,
        host_port,
    ), role in publisher_roles.items():
        canonical_identities.add((compose_service, role, protocol, host_port))
        role_container_ports.setdefault(
            (compose_service, role, protocol), set()
        ).add(container_port)
        if len(container_role_closure[(compose_service, container_port, protocol)]) == 1:
            sole_owner_identities.add((compose_service, role, protocol))
    ambiguous = sorted(
        f"{compose_service}/{role}/{protocol}"
        for (compose_service, role, protocol), ports in role_container_ports.items()
        if len(ports) != 1
    )
    if ambiguous:
        raise OrphanComposeTeardownError(
            "orphan Compose publisher role owns multiple container ports under one "
            "service/protocol; attestation cannot bound the whitelist: "
            + ", ".join(ambiguous)
        )
    container_endpoints: list[dict[str, object]] = []
    for container in containers:
        if not isinstance(container, Mapping) or set(container) != container_fields:
            raise OrphanComposeTeardownError(
                "orphan Compose attestation container fields mismatch"
            )
        service = str(container.get("service") or "").strip()
        endpoints = _normalize_published_endpoints(
            container.get("publishedEndpoints")
        )
        for endpoint in endpoints:
            role = str(endpoint["role"])
            protocol = str(endpoint["protocol"])
            if (service, role, protocol, int(endpoint["hostPort"])) in (
                canonical_identities
            ):
                continue
            if (service, role, protocol) in sole_owner_identities:
                continue
            raise OrphanComposeTeardownError(
                "orphan Compose published endpoint publisher identity is not canonical: "
                f"{service}/{role}:{endpoint['hostPort']}/{protocol}"
            )
        container_endpoints.extend(endpoints)
    if published_endpoints != _normalize_published_endpoints(container_endpoints):
        raise OrphanComposeTeardownError(
            "orphan Compose attestation published endpoint inventory mismatch"
        )
    if value.get("snapshotDigest") != _digest(snapshot):
        raise OrphanComposeTeardownError("orphan Compose attestation snapshot digest mismatch")
    unsigned = dict(value)
    declared = unsigned.pop("attestationDigest", None)
    if declared != _digest(unsigned):
        raise OrphanComposeTeardownError("orphan Compose attestation digest mismatch")
    sampled = _timestamp(str(value.get("sampledAt") or ""))
    expires = _timestamp(str(value.get("expiresAt") or ""))
    if expires - sampled != timedelta(seconds=ATTESTATION_TTL_SECONDS):
        raise OrphanComposeTeardownError("orphan Compose attestation lifetime mismatch")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if sampled > current + timedelta(seconds=5) or (
        current > expires and not allow_expired
    ):
        raise OrphanComposeTeardownError("orphan Compose attestation is stale")
    return value


def _safe_attestation_path(path: Path, *, allowed_root: Path) -> Path:
    root = allowed_root.expanduser().resolve()
    candidate = path.expanduser().absolute()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise OrphanComposeTeardownError(
            "orphan Compose attestation must stay under the environment runs root"
        ) from exc
    if candidate.name != "orphaned-compose-teardown-attestation.json":
        raise OrphanComposeTeardownError("orphan Compose attestation filename is not canonical")
    if not candidate.parent.is_dir() or candidate.parent.resolve() != candidate.parent:
        raise OrphanComposeTeardownError("orphan Compose attestation parent is unsafe")
    return candidate


def write_attestation_create_once(
    path: Path,
    value: Mapping[str, Any],
    *,
    allowed_root: Path,
) -> Path:
    candidate = _safe_attestation_path(path, allowed_root=allowed_root)
    return _atomic_write_create_once(
        candidate,
        _canonical_bytes(value) + b"\n",
        label="attestation",
    )


def load_attestation(
    path: Path,
    *,
    allowed_root: Path,
    expected_target: str,
    now: datetime | None = None,
    allow_expired: bool = False,
) -> dict[str, Any]:
    candidate = _safe_attestation_path(path, allowed_root=allowed_root)
    try:
        info = candidate.lstat()
        if not stat.S_ISREG(info.st_mode) or candidate.is_symlink():
            raise OSError("not a regular no-follow file")
        value = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OrphanComposeTeardownError("orphan Compose attestation is unreadable or unsafe") from exc
    return validate_attestation(
        value,
        expected_target=expected_target,
        now=now,
        allow_expired=allow_expired,
    )


def assert_snapshot_unchanged(
    attestation: Mapping[str, Any],
    current_snapshot: Mapping[str, Any],
) -> None:
    if attestation.get("snapshot") != dict(current_snapshot):
        raise OrphanComposeTeardownError(
            "orphan Compose live resources changed after attestation"
        )


def exact_removal_commands(attestation: Mapping[str, Any]) -> list[list[str]]:
    snapshot = attestation.get("snapshot")
    if not isinstance(snapshot, Mapping):
        raise OrphanComposeTeardownError("orphan Compose attestation snapshot is missing")
    commands: list[list[str]] = []
    containers = snapshot.get("containers")
    networks = snapshot.get("networks")
    if not isinstance(containers, list) or not isinstance(networks, list):
        raise OrphanComposeTeardownError("orphan Compose resource lists are invalid")
    container_ids = [str(item.get("id") or "") for item in containers if isinstance(item, Mapping)]
    network_ids = [str(item.get("id") or "") for item in networks if isinstance(item, Mapping)]
    if len(container_ids) != len(containers) or len(network_ids) != len(networks) or any(not value for value in (*container_ids, *network_ids)):
        raise OrphanComposeTeardownError("orphan Compose resource identity is incomplete")
    commands.extend(["docker", "rm", "--force", item] for item in container_ids)
    commands.extend(["docker", "network", "rm", item] for item in network_ids)
    return commands
