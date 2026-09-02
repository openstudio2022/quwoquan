from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .common import ROOT
from .service_core_composition import (
    SERVICE_CORE_WORKLOAD,
    service_core_composition_issues,
    service_core_module_target_ports,
)


DEFAULT_PATH = ROOT / "quwoquan_ops" / "environments" / "local_env_port_manifest.yaml"
REQUIRED_PROFILES = ("alpha-local", "beta-local", "gamma-local", "prod-sim")
REQUIRED_PLANES = ("edge", "media", "service", "dataDebug")
PROFILE_CANONICAL_CONTAINER_PORT = "profileCanonical"
HOST_PORT_VARIABLES_KEY = "composeHostPortVariables"
UNOWNED_COMPOSE_SOURCES_KEY = "unownedComposeSources"
RETIRED_COMPOSE_SOURCES_KEY = "retiredComposeSources"
_ENVIRONMENT_VARIABLE_NAME = re.compile(r"[A-Z_][A-Z0-9_]*")


def _is_declared_container_port(value: object) -> bool:
    """唯一判据：containerPort 只能是字面端口号或 `profileCanonical` 指代。

    校验与投影两侧共用同一判据，避免两份等价谓词漂移后放行畸形 publisher。
    """
    if value == PROFILE_CANONICAL_CONTAINER_PORT:
        return True
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return 0 < value < 65536


def load_port_manifest(path: Path | None = None) -> dict[str, Any]:
    manifest_path = path or DEFAULT_PATH

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        loaded_object: dict[str, Any] = {}
        for key, value in pairs:
            if key in loaded_object:
                raise RuntimeError(
                    f"local env port manifest contains duplicate key: {key}"
                )
            loaded_object[key] = value
        return loaded_object

    try:
        loaded = json.loads(
            manifest_path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"local env port manifest must use strict JSON syntax: {manifest_path}"
        ) from exc
    if not isinstance(loaded, dict):
        raise RuntimeError("local env port manifest must be a mapping")
    return loaded


def _host_port_variable_issues(
    manifest: dict[str, Any],
    roles: dict[str, Any],
) -> list[str]:
    """`composeHostPortVariables` 是 Compose 主机端口变量到 role 的唯一声明位。

    走 `${VAR:?msg}` 必填形态的发布口在字面上判定不出主机端口，注入值由各启动面提供。
    没有这个声明位时，门禁只能对这些声明「不判定」，等于整片逃出 canonical 断言；而注入面
    本身分散在 profile 导出、fleet compose 环境、content-backing 等多处，不能作单一真相源。
    """
    declared = manifest.get(HOST_PORT_VARIABLES_KEY)
    if declared is None:
        return [f"{HOST_PORT_VARIABLES_KEY} must be declared"]
    if not isinstance(declared, dict) or not declared:
        return [f"{HOST_PORT_VARIABLES_KEY} must be a non-empty mapping"]
    issues: list[str] = []
    for name, role_name in sorted(declared.items()):
        if not isinstance(name, str) or _ENVIRONMENT_VARIABLE_NAME.fullmatch(name) is None:
            issues.append(
                f"{HOST_PORT_VARIABLES_KEY}: variable name is invalid: {name!r}"
            )
            continue
        if not isinstance(role_name, str) or role_name not in roles:
            issues.append(
                f"{HOST_PORT_VARIABLES_KEY}[{name}]: role is not declared: {role_name!r}"
            )
    return issues


def _compose_source_adjudication_issues(
    manifest: dict[str, Any],
    *,
    key: str,
) -> list[str]:
    declared = manifest.get(key)
    if declared is None:
        return [f"{key} must be declared"]
    if not isinstance(declared, dict):
        return [f"{key} must be a mapping"]
    issues: list[str] = []
    for name, reason in sorted(declared.items()):
        if not isinstance(name, str) or not name.strip():
            issues.append(f"{key}: file name is invalid")
            continue
        if not isinstance(reason, str) or not reason.strip():
            issues.append(f"{key}[{name}]: reason is required")
    return issues


def _unowned_compose_source_issues(manifest: dict[str, Any]) -> list[str]:
    """不受端口所有权模型管辖的 Compose 源，必须带理由声明在 manifest 里。"""
    return _compose_source_adjudication_issues(
        manifest,
        key=UNOWNED_COMPOSE_SOURCES_KEY,
    )


def _retired_compose_source_issues(manifest: dict[str, Any]) -> list[str]:
    """已从现役拓扑断开的 Compose 源必须单独声明，禁止混入永久豁免。"""
    return _compose_source_adjudication_issues(
        manifest,
        key=RETIRED_COMPOSE_SOURCES_KEY,
    )


def validate_port_manifest(manifest: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if manifest.get("schema") != "local-env-port-manifest":
        issues.append("schema must be local-env-port-manifest")

    planes = manifest.get("planes")
    roles = manifest.get("roles")
    profiles = manifest.get("profiles")
    if not isinstance(planes, dict):
        issues.append("planes must be a mapping")
        return issues
    if not isinstance(roles, dict):
        issues.append("roles must be a mapping")
        return issues
    if not isinstance(profiles, dict):
        issues.append("profiles must be a mapping")
        return issues
    issues.extend(_host_port_variable_issues(manifest, roles))
    issues.extend(_unowned_compose_source_issues(manifest))
    issues.extend(_retired_compose_source_issues(manifest))
    unowned_sources = manifest.get(UNOWNED_COMPOSE_SOURCES_KEY)
    retired_sources = manifest.get(RETIRED_COMPOSE_SOURCES_KEY)
    if isinstance(unowned_sources, dict) and isinstance(retired_sources, dict):
        overlap = sorted(set(unowned_sources) & set(retired_sources))
        if overlap:
            issues.append(
                "Compose sources cannot be both unowned and retired: "
                + ", ".join(overlap)
            )

    for plane_name in REQUIRED_PLANES:
        plane = planes.get(plane_name)
        if not isinstance(plane, dict):
            issues.append(f"missing plane definition: {plane_name}")
            continue
        if not isinstance(plane.get("offsetStart"), int):
            issues.append(f"{plane_name}: offsetStart must be int")
        if not isinstance(plane.get("offsetEnd"), int):
            issues.append(f"{plane_name}: offsetEnd must be int")

    compose_publishers: list[tuple[str, str, int | str, str]] = []
    # composition 装载失败要作为一条 issue 判否，而不是让异常穿透门禁：service-core
    # publisher 的交叉校验依赖它，拿不到就等于这段校验没跑，必须显式说出来。
    composition_issues = service_core_composition_issues()
    if composition_issues:
        issues.extend(composition_issues)
        return issues
    service_core_targets = service_core_module_target_ports()
    for role_name, role in roles.items():
        if not isinstance(role, dict):
            issues.append(f"{role_name}: role definition must be a mapping")
            continue
        plane = str(role.get("plane", "")).strip()
        slot = role.get("slotOffset")
        if plane not in planes:
            issues.append(f"{role_name}: plane must be one of {', '.join(planes)}")
            continue
        if not isinstance(slot, int):
            issues.append(f"{role_name}: slotOffset must be int")
            continue
        plane_range = planes[plane]
        start = int(plane_range["offsetStart"])
        end = int(plane_range["offsetEnd"])
        if slot < start or slot > end:
            issues.append(
                f"{role_name}: slotOffset {slot} must stay within plane {plane} range {start}-{end}"
            )
        if slot % 10 != 0:
            issues.append(f"{role_name}: slotOffset must end with 0")
        endpoint_values = {
            "serviceHost": role.get("serviceHost"),
            "containerPort": role.get("containerPort"),
            "scheme": role.get("scheme"),
        }
        if any(value is not None for value in endpoint_values.values()):
            missing = [
                key
                for key, value in endpoint_values.items()
                if value is None or (isinstance(value, str) and not value.strip())
            ]
            if missing:
                issues.append(
                    f"{role_name}: internal endpoint metadata is incomplete: {missing}"
                )
            if (
                not isinstance(endpoint_values["containerPort"], int)
                or not 0 < endpoint_values["containerPort"] < 65536
            ):
                issues.append(
                    f"{role_name}: containerPort must be an integer in 1..65535"
                )
            if endpoint_values["scheme"] not in {"http", "https"}:
                issues.append(f"{role_name}: scheme must be http or https")

        published_endpoints = role.get("composePublishedEndpoints")
        if published_endpoints is not None:
            if (
                not isinstance(published_endpoints, list)
                or not published_endpoints
            ):
                issues.append(
                    f"{role_name}: composePublishedEndpoints must be a non-empty list"
                )
            else:
                role_identities: set[tuple[str, int | str, str]] = set()
                for index, endpoint in enumerate(published_endpoints):
                    if not isinstance(endpoint, dict) or set(endpoint) != {
                        "composeService",
                        "containerPort",
                        "protocol",
                    }:
                        issues.append(
                            f"{role_name}: composePublishedEndpoints[{index}] fields are invalid"
                        )
                        continue
                    compose_service = str(endpoint.get("composeService") or "").strip()
                    container_port = endpoint.get("containerPort")
                    protocol = str(endpoint.get("protocol") or "").strip().lower()
                    if not compose_service:
                        issues.append(
                            f"{role_name}: composePublishedEndpoints[{index}] composeService is required"
                        )
                    if not _is_declared_container_port(container_port):
                        issues.append(
                            f"{role_name}: composePublishedEndpoints[{index}] containerPort is invalid"
                        )
                    if protocol not in {"tcp", "udp"}:
                        issues.append(
                            f"{role_name}: composePublishedEndpoints[{index}] protocol must be tcp or udp"
                        )
                    if (
                        compose_service
                        and _is_declared_container_port(container_port)
                        and protocol in {"tcp", "udp"}
                    ):
                        if compose_service == SERVICE_CORE_WORKLOAD:
                            expected_target = service_core_targets.get(role_name)
                            if expected_target is None:
                                issues.append(
                                    f"{role_name}: service-core publisher has no composition module"
                                )
                            elif container_port != expected_target:
                                issues.append(
                                    f"{role_name}: service-core publisher containerPort must match "
                                    f"composition target {expected_target}"
                                )
                        identity = (compose_service, container_port, protocol)
                        if identity in role_identities:
                            issues.append(
                                f"{role_name}: composePublishedEndpoints identities must be distinct"
                            )
                        else:
                            role_identities.add(identity)
                            compose_publishers.append((role_name, *identity))

    for profile_name in REQUIRED_PROFILES:
        profile = profiles.get(profile_name)
        if not isinstance(profile, dict):
            issues.append(f"missing profile definition: {profile_name}")
            continue
        start = profile.get("blockStart")
        end = profile.get("blockEnd")
        if not isinstance(start, int) or not isinstance(end, int):
            issues.append(f"{profile_name}: blockStart/blockEnd must be int")
            continue
        if start % 1000 != 0:
            issues.append(f"{profile_name}: blockStart must align to 1000-port block")
        if end - start != 999:
            issues.append(f"{profile_name}: blockEnd must close a 1000-port block")

    seen_ports: dict[int, str] = {}
    for profile_name, profile in profiles.items():
        if not isinstance(profile, dict):
            continue
        start = profile.get("blockStart")
        end = profile.get("blockEnd")
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        for role_name, role in roles.items():
            if not isinstance(role, dict):
                continue
            slot = role.get("slotOffset")
            if not isinstance(slot, int):
                continue
            canonical = start + slot
            if canonical % 10 != 0:
                issues.append(f"{profile_name}/{role_name}: canonical port must end with 0")
            if canonical < start or canonical > end:
                issues.append(
                    f"{profile_name}/{role_name}: canonical port {canonical} escapes block {start}-{end}"
                )
            owner = seen_ports.setdefault(canonical, f"{profile_name}/{role_name}")
            if owner != f"{profile_name}/{role_name}":
                issues.append(
                    f"duplicate canonical port {canonical}: {owner} and {profile_name}/{role_name}"
                )

        publisher_owners: dict[tuple[str, int, str, int], str] = {}
        container_claims: dict[tuple[str, int, str], set[str]] = {}
        for role_name, compose_service, container_port, protocol in compose_publishers:
            resolved_container_port = (
                canonical_port(manifest, profile_name, role_name)
                if container_port == PROFILE_CANONICAL_CONTAINER_PORT
                else int(container_port)
            )
            host_port = canonical_port(manifest, profile_name, role_name)
            identity = (compose_service, resolved_container_port, protocol, host_port)
            previous_owner = publisher_owners.setdefault(identity, role_name)
            if previous_owner != role_name:
                issues.append(
                    "compose publisher identity maps to multiple roles: "
                    f"{profile_name}/{compose_service}:{resolved_container_port}/{protocol}"
                    f"->{host_port} ({previous_owner},{role_name})"
                )
            container_claims.setdefault(
                (compose_service, resolved_container_port, protocol), set()
            ).add(role_name)

        for (
            compose_service,
            container_port,
            protocol,
        ), claimants in container_claims.items():
            if len(claimants) < 2:
                continue
            # 多个 role 共用一个容器发布口，只有 service-core 合法，且必须与
            # composition 声明同源：每个声明方都得是容器口正是该值的 composition 模块。
            # 否则就是两个 role 抢同一个容器端点，hostPort 之外无判据，teardown 无法归因。
            if compose_service != SERVICE_CORE_WORKLOAD or any(
                service_core_targets.get(role) != container_port for role in claimants
            ):
                issues.append(
                    "compose publisher container endpoint maps to multiple roles: "
                    f"{profile_name}/{compose_service}:{container_port}/{protocol} "
                    f"({','.join(sorted(claimants))})"
                )

    return issues


def canonical_port(manifest: dict[str, Any], profile_name: str, role_name: str) -> int:
    profile = manifest["profiles"][profile_name]
    role = manifest["roles"][role_name]
    return int(profile["blockStart"]) + int(role["slotOffset"])


def profile_ports(manifest: dict[str, Any], profile_name: str) -> dict[str, int]:
    return {
        role_name: canonical_port(manifest, profile_name, role_name)
        for role_name in manifest.get("roles", {})
    }


def compose_published_endpoint_roles(
    manifest: dict[str, Any],
    profile_name: str,
) -> dict[tuple[str, int, str, int], str]:
    """publisher 身份键是 `(composeService, containerPort, protocol, hostPort)`。

    三元组不足以定位 role：service-core 把多个模块并进同一个 Compose service，
    user/chat 共用容器口 18081、assistant/notification 共用 18087，只有 canonical
    hostPort 能把它们分开。hostPort 同时是 role 的 canonical 端口，查表命中即等于
    「发布身份与 canonical 端口双向吻合」，调用方不需再做一次后验。
    """
    issues = validate_port_manifest(manifest)
    if issues:
        raise ValueError("canonical port manifest is invalid: " + "; ".join(issues))
    profiles = manifest.get("profiles")
    if not isinstance(profiles, dict) or profile_name not in profiles:
        raise ValueError(f"local port profile is unavailable: {profile_name}")

    identities: dict[tuple[str, int, str, int], str] = {}
    roles = manifest["roles"]
    for role_name, role in roles.items():
        published_endpoints = role.get("composePublishedEndpoints")
        if published_endpoints is None:
            continue
        host_port = canonical_port(manifest, profile_name, role_name)
        for endpoint in published_endpoints:
            raw_container_port = endpoint["containerPort"]
            container_port = (
                host_port
                if raw_container_port == PROFILE_CANONICAL_CONTAINER_PORT
                else int(raw_container_port)
            )
            identities[
                (
                    str(endpoint["composeService"]),
                    container_port,
                    str(endpoint["protocol"]),
                    host_port,
                )
            ] = role_name
    return identities


def compose_publisher_container_role_closure(
    publisher_roles: dict[tuple[str, int, str, int], str],
) -> dict[tuple[str, int, str], frozenset[str]]:
    """容器侧发布身份 `(composeService, containerPort, protocol)` 的 role 闭包。

    四元组是定位 role 的唯一判据，但有两处只有容器侧信息可用：容器口已声明却没绑主机
    端口；以及旧栈发布的非 canonical host port —— spec 要求它们一并进入清单并逐端口
    证明释放，所以这里不能用 canonical hostPort 把它们判否。

    闭包大小决定这些场景能否归因：只有一个 role 声明过该容器身份时归属确定；service-core
    把多个模块并进同一 Compose service（user/chat 同 18081、assistant/notification 同
    18087），闭包大于一，此时 hostPort 是唯一区分位，非 canonical 值无法归因，只能判否。
    """
    closure: dict[tuple[str, int, str], set[str]] = {}
    for identity, role in publisher_roles.items():
        closure.setdefault(identity[:3], set()).add(role)
    return {identity: frozenset(roles) for identity, roles in closure.items()}


def internal_role_base_url(manifest: dict[str, Any], role_name: str) -> str:
    role = manifest.get("roles", {}).get(role_name)
    if not isinstance(role, dict):
        raise ValueError(f"local topology role is unavailable: {role_name}")
    host = str(role.get("serviceHost") or "").strip()
    scheme = str(role.get("scheme") or "").strip()
    port = role.get("containerPort")
    if not host or scheme not in {"http", "https"} or not isinstance(port, int):
        raise ValueError(
            f"local topology role has no complete internal endpoint: {role_name}"
        )
    return f"{scheme}://{host}:{port}"
