"""Canonical local runtime published-port ownership projection."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .port_manifest import (
    compose_published_endpoint_roles,
    compose_publisher_container_role_closure,
    load_port_manifest,
    profile_ports,
    validate_port_manifest,
)


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
    return normalized_endpoints


__all__ = [
    "project_canonical_runtime_owned_ports",
    "project_compose_published_endpoints",
    "project_runtime_owned_ports",
    "require_published_endpoint_port",
]
