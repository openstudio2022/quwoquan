"""orphan Compose teardown 的只读资源盘点与快照采样。

原单文件 ``orphan_compose_teardown.py`` 拆分出的 inventory 子模块。
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from ..port_manifest import (
    compose_published_endpoint_roles,
    compose_publisher_container_role_closure,
)
from .constants import (
    LOCAL_TARGETS,
    OrphanComposeTeardownError,
    _DIGEST,
    _SAFE_LABEL,
    _canonical_bytes,
    _digest,
    _normalize_published_endpoints,
    require_canonical_project,
)


def _run_json(
    argv: list[str],
    *,
    run_command: Callable[[list[str]], Any],
    label: str,
) -> list[dict[str, Any]]:
    result = run_command(argv)
    if int(result.returncode) != 0:
        detail = str(result.stderr or result.stdout or "").strip()
        raise OrphanComposeTeardownError(
            f"{label} inspection failed" + (f": {detail}" if detail else "")
        )
    try:
        value = json.loads(str(result.stdout or "[]"))
    except json.JSONDecodeError as exc:
        raise OrphanComposeTeardownError(f"{label} inspection is unreadable") from exc
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise OrphanComposeTeardownError(f"{label} inspection is not an object list")
    return value


def _list_ids(
    argv: list[str],
    *,
    run_command: Callable[[list[str]], Any],
    label: str,
) -> list[str]:
    result = run_command(argv)
    if int(result.returncode) != 0:
        detail = str(result.stderr or result.stdout or "").strip()
        raise OrphanComposeTeardownError(
            f"{label} inventory failed" + (f": {detail}" if detail else "")
        )
    values = sorted({line.strip() for line in str(result.stdout or "").splitlines() if line.strip()})
    if any(_SAFE_LABEL.fullmatch(value) is None for value in values):
        raise OrphanComposeTeardownError(f"{label} inventory contains an unsafe identity")
    return values


def discover_exact_project(
    *,
    target: str,
    run_command: Callable[[list[str]], Any],
) -> str:
    commands = (
        [
            "docker",
            "ps",
            "--all",
            "--no-trunc",
            "--filter",
            "label=com.docker.compose.project",
            "--format",
            '{{.Label "com.docker.compose.project"}}',
        ],
        [
            "docker",
            "network",
            "ls",
            "--filter",
            "label=com.docker.compose.project",
            "--format",
            '{{.Label "com.docker.compose.project"}}',
        ],
    )
    projects: set[str] = set()
    for command in commands:
        result = run_command(command)
        if int(result.returncode) != 0:
            detail = str(result.stderr or result.stdout or "").strip()
            raise OrphanComposeTeardownError(
                "orphan Compose project discovery failed"
                + (f": {detail}" if detail else "")
            )
        for value in str(result.stdout or "").splitlines():
            candidate = value.strip()
            if not candidate:
                continue
            try:
                projects.add(require_canonical_project(target, candidate))
            except OrphanComposeTeardownError:
                continue
    if not projects:
        raise OrphanComposeTeardownError(
            f"no exact project is discoverable for orphan Compose target {target}"
        )
    if len(projects) != 1:
        raise OrphanComposeTeardownError(
            "multiple exact projects are discoverable for orphan Compose target "
            f"{target}: {', '.join(sorted(projects))}"
        )
    return next(iter(projects))


# 独立观察不复用 teardown 的唯一 project / removable admission，也不改变修复行为。
_RESOURCE_ID = re.compile(r"[0-9a-f]{64}")
_CONTAINER_OBSERVATION = (
    '{"id":{{json .Id}},"name":{{json .Name}},"state":{{json .State.Status}},'
    '"project":{{json (index .Config.Labels "com.docker.compose.project")}},'
    '"service":{{json (index .Config.Labels "com.docker.compose.service")}},'
    '"worktree":{{json (index .Config.Labels "com.docker.compose.project.working_dir")}}}'
)
_NETWORK_OBSERVATION = (
    '{"id":{{json .Id}},"name":{{json .Name}},'
    '"project":{{json (index .Labels "com.docker.compose.project")}},'
    '"network":{{json (index .Labels "com.docker.compose.network")}},'
    '"attachments":{ {{$sep := ""}}{{range $id, $_ := .Containers}}'
    '{{$sep}}{{json $id}}:null{{$sep = ","}}{{end}} }}'
)


def require_resource_observation_authority() -> None:
    from ..host_locks import require_canonical_runtime_authority

    require_canonical_runtime_authority()
    # context/config 覆盖同样能重定向 daemon，不能只检查 DOCKER_HOST。
    if os.environ.get("DOCKER_CONTEXT") or os.environ.get("DOCKER_CONFIG"):
        raise ValueError("resource observation rejects Docker context/config overrides")


def _observation_text(row: Mapping[str, Any], key: str, *, required: bool = False) -> str:
    value = row.get(key)
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value):
        raise ValueError("resource observation field is invalid")
    if len(value) > 4096 or any(ord(char) < 32 for char in value):
        raise ValueError("resource observation field is unsafe")
    return value


def _observed_resource(row: Mapping[str, Any], kind: str) -> dict[str, Any]:
    identity = _observation_text(row, "id", required=True)
    if _RESOURCE_ID.fullmatch(identity) is None:
        raise ValueError("resource identity is not exact")
    result = {"id": identity, "name": _observation_text(row, "name", required=True),
              "project": _observation_text(row, "project"), "ownerStatus": "unknown"}
    if kind == "container":
        result.update(state=_observation_text(row, "state", required=True),
                      service=_observation_text(row, "service"),
                      worktree=_observation_text(row, "worktree"))
        if result["worktree"]:
            result["ownerStatus"] = "unverified_worktree_label"
    else:
        attachments = row.get("attachments")
        if not isinstance(attachments, dict) or any(
            not isinstance(key, str) or _RESOURCE_ID.fullmatch(key) is None for key in attachments
        ):
            raise ValueError("network attachments are invalid")
        result.update(network=_observation_text(row, "network"),
                      attachedContainerIds=sorted(attachments))
    return result


def _observe_resource_kind(kind: str, *, run_command: Callable[[list[str]], Any],
                           endpoint: str) -> list[dict[str, Any]]:
    listing = (["ps", "--all", "--no-trunc", "--quiet"] if kind == "container"
               else ["network", "ls", "--no-trunc", "--quiet"])
    prefix = ["docker", "--host", endpoint]
    # 受管执行器为每次只读查询加有界 deadline；底层错误文本绝不进入报告。
    def query(argv: list[str]) -> Any:
        return run_command(argv, timeout_seconds=15)

    def identities() -> list[str]:
        values = _list_ids(prefix + listing, run_command=query, label=kind)
        if any(_RESOURCE_ID.fullmatch(value) is None for value in values):
            raise ValueError("resource listing identity is not exact")
        return values

    expected = identities()
    rows: list[dict[str, Any]] = []
    template = _CONTAINER_OBSERVATION if kind == "container" else _NETWORK_OBSERVATION
    for start in range(0, len(expected), 64):
        result = query(prefix + [kind, "inspect", "--format", template, *expected[start:start + 64]])
        if result.returncode != 0:
            raise ValueError("resource inspection failed")
        for line in str(result.stdout).splitlines():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError("resource inspection is not an object")
            rows.append(_observed_resource(value, kind))
    if sorted(row["id"] for row in rows) != expected or identities() != expected:
        raise ValueError("resource inventory changed or is partial")
    return sorted(rows, key=lambda row: row["id"])


def observe_host_resources(*, run_command: Callable[[list[str]], Any]) -> dict[str, Any]:
    """宿主全量只读观察；标签不是 owner 证明，成功也不授予接管资格。"""
    report: dict[str, Any] = {
        "schema": "stackctl-local-resource-observation", "readOnly": True,
        "admissionEligible": False, "complete": False, "status": "blocked",
        "containers": [], "networks": [], "issues": [],
        "firstBlocker": "", "inventoryScope": "host_all_containers_and_networks",
    }
    stage = "authority"
    try:
        require_resource_observation_authority()
        stage = "daemon"
        result = run_command(["docker", "context", "inspect", "--format",
                              "{{json .Endpoints.docker.Host}}"], timeout_seconds=15)
        if result.returncode != 0:
            raise ValueError("daemon context unavailable")
        endpoint = json.loads(result.stdout)
        if not isinstance(endpoint, str) or not endpoint.startswith("unix:///"):
            raise ValueError("only a local Unix daemon is admitted")
        # 固定本次 daemon endpoint，避免多次查询之间 current context 改变。
        for kind in ("container", "network"):
            stage = kind
            report[kind + "s"] = _observe_resource_kind(kind, run_command=run_command, endpoint=endpoint)
    except (OSError, RuntimeError, ValueError, TypeError, KeyError):
        # 不复制 stderr、原始 inspect 或异常内容，避免错误回显秘密。
        report["firstBlocker"] = "resource_observation_unavailable"
        report["issues"] = [f"{stage} observation failed; inventory is incomplete"]
        return report
    report.update(status="observed", complete=True)
    return report


def _labels(value: object, *, project: str, label: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise OrphanComposeTeardownError(f"{label} has no Compose labels")
    labels = {str(key): str(item) for key, item in value.items()}
    if labels.get("com.docker.compose.project") != project:
        raise OrphanComposeTeardownError(f"{label} Compose project label mismatch")
    return dict(sorted(labels.items()))


def _published_endpoints(
    container: Mapping[str, Any],
    *,
    compose_service: str,
    publisher_roles: Mapping[tuple[str, int, str, int], str],
    container_role_closure: Mapping[tuple[str, int, str], frozenset[str]],
) -> list[dict[str, object]]:
    host_config = container.get("HostConfig")
    bindings = host_config.get("PortBindings") if isinstance(host_config, Mapping) else None
    endpoints: list[dict[str, object]] = []
    if bindings is None:
        return []
    if not isinstance(bindings, Mapping):
        raise OrphanComposeTeardownError("container PortBindings is invalid")
    for container_endpoint, items in bindings.items():
        parts = str(container_endpoint or "").strip().lower().rsplit("/", 1)
        if len(parts) != 2 or not parts[0].isdigit() or parts[1] not in {"tcp", "udp"}:
            raise OrphanComposeTeardownError(
                "container PortBindings endpoint identity is invalid"
            )
        container_port = int(parts[0])
        protocol = parts[1]
        container_identity = (compose_service, container_port, protocol)
        declared_roles = container_role_closure.get(container_identity)
        if declared_roles is None:
            raise OrphanComposeTeardownError(
                "container PortBindings publisher identity is not canonical: "
                f"{compose_service}:{container_port}/{protocol}"
            )
        if items is None:
            continue
        if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
            raise OrphanComposeTeardownError("container PortBindings is invalid")
        for item in items:
            if not isinstance(item, Mapping):
                raise OrphanComposeTeardownError("container PortBindings is invalid")
            value = str(item.get("HostPort") or "")
            if not value.isdigit() or int(value) < 1 or int(value) > 65535:
                raise OrphanComposeTeardownError("container HostPort is invalid")
            host_port = int(value)
            role = publisher_roles.get((*container_identity, host_port))
            if role is None:
                # 旧栈可能把 canonical 容器口发布到非 canonical 主机端口，spec 要求这类
                # 端口一并进入清单，所以不能按 canonical 判否。容器身份只归一个 role 时
                # 归属确定；多 role 共用同一容器身份时 hostPort 是唯一区分位，非 canonical
                # 值无法归因，只能判否而不能猜。
                if len(declared_roles) != 1:
                    raise OrphanComposeTeardownError(
                        "container published host port cannot be attributed: "
                        f"{compose_service}:{container_port}/{protocol}->{host_port} "
                        f"is claimable by {','.join(sorted(declared_roles))}"
                    )
                role = next(iter(declared_roles))
            endpoints.append(
                {
                    "role": role,
                    "hostPort": host_port,
                    "protocol": protocol,
                }
            )
    return _normalize_published_endpoints(endpoints)


def _canonical_mounts(value: object) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise OrphanComposeTeardownError("container Mounts is invalid")
    mounts: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise OrphanComposeTeardownError("container Mounts is invalid")
        mounts.append(dict(item))
    return sorted(mounts, key=_canonical_bytes)


def _container_descriptor(
    value: Mapping[str, Any],
    *,
    project: str,
    publisher_roles: Mapping[tuple[str, int, str, int], str],
    container_role_closure: Mapping[tuple[str, int, str], frozenset[str]],
) -> dict[str, Any]:
    container_id = str(value.get("Id") or "").strip()
    name = str(value.get("Name") or "").strip().lstrip("/")
    config = value.get("Config")
    host_config = value.get("HostConfig")
    if (
        not container_id
        or not name
        or not isinstance(config, Mapping)
        or not isinstance(host_config, Mapping)
    ):
        raise OrphanComposeTeardownError("container identity/config is incomplete")
    labels = _labels(config.get("Labels"), project=project, label=f"container {name}")
    service = labels.get("com.docker.compose.service", "").strip()
    if not service:
        raise OrphanComposeTeardownError(f"container {name} has no Compose service label")
    image_digest = str(value.get("Image") or "").strip()
    if _DIGEST.fullmatch(image_digest) is None:
        raise OrphanComposeTeardownError(f"container {name} image digest is invalid")
    published_endpoints = _published_endpoints(
        value,
        compose_service=service,
        publisher_roles=publisher_roles,
        container_role_closure=container_role_closure,
    )
    configuration = {
        "Config": config,
        "HostConfig": host_config,
        # Docker does not guarantee inspect ordering for this set.  Preserve
        # every field while canonicalizing only its presentation order.
        "Mounts": _canonical_mounts(value.get("Mounts")),
        "NetworkSettingsPorts": (
            (value.get("NetworkSettings") or {}).get("Ports")
            if isinstance(value.get("NetworkSettings"), Mapping)
            else None
        ),
        "NetworkSettingsNetworks": (
            (value.get("NetworkSettings") or {}).get("Networks")
            if isinstance(value.get("NetworkSettings"), Mapping)
            else None
        ),
    }
    return {
        "id": container_id,
        "name": name,
        "service": service,
        "labels": labels,
        "imageRef": str(config.get("Image") or "").strip(),
        "imageDigest": image_digest,
        "configurationDigest": _digest(configuration),
        "publishedEndpoints": published_endpoints,
    }


def _network_descriptor(value: Mapping[str, Any], *, project: str) -> dict[str, Any]:
    resource_id = str(value.get("Id") or "").strip()
    name = str(value.get("Name") or "").strip()
    if not resource_id or not name:
        raise OrphanComposeTeardownError("network identity is incomplete")
    labels = _labels(value.get("Labels"), project=project, label=f"network {name}")
    if not labels.get("com.docker.compose.network", "").strip():
        raise OrphanComposeTeardownError(f"network {name} has no Compose network label")
    attached = value.get("Containers") or {}
    if not isinstance(attached, Mapping):
        raise OrphanComposeTeardownError(f"network {name} attached containers are invalid")
    attached_ids = sorted(str(item).strip() for item in attached)
    if any(not item or _SAFE_LABEL.fullmatch(item) is None for item in attached_ids):
        raise OrphanComposeTeardownError(f"network {name} attached container identity is invalid")
    configuration = {
        "Driver": value.get("Driver"),
        "EnableIPv6": value.get("EnableIPv6"),
        "IPAM": value.get("IPAM"),
        "Internal": value.get("Internal"),
        "Attachable": value.get("Attachable"),
        "Options": value.get("Options"),
        "Containers": attached,
    }
    return {
        "id": resource_id,
        "name": name,
        "labels": labels,
        "attachedContainerIds": attached_ids,
        "configurationDigest": _digest(configuration),
    }


def _volume_descriptor(value: Mapping[str, Any], *, project: str) -> dict[str, Any]:
    name = str(value.get("Name") or "").strip()
    if not name:
        raise OrphanComposeTeardownError("volume identity is incomplete")
    labels = _labels(value.get("Labels"), project=project, label=f"volume {name}")
    if not labels.get("com.docker.compose.volume", "").strip():
        raise OrphanComposeTeardownError(f"volume {name} has no Compose volume label")
    configuration = {
        "Driver": value.get("Driver"),
        "Options": value.get("Options"),
        "Scope": value.get("Scope"),
    }
    return {
        "id": name,
        "name": name,
        "labels": labels,
        "configurationDigest": _digest(configuration),
    }


def sample_snapshot(
    *,
    target: str,
    project: str,
    canonical_ports: Sequence[Mapping[str, Any]],
    port_manifest: dict[str, Any],
    port_profile: str,
    run_command: Callable[[list[str]], Any],
    require_removable: bool = True,
    other_target_port_blocks: Sequence[Mapping[str, Any]] = (),
    port_probe: Callable[[Mapping[str, object]], bool] | None = None,
) -> dict[str, Any]:
    project = require_canonical_project(target, project)
    try:
        publisher_roles = compose_published_endpoint_roles(port_manifest, port_profile)
    except ValueError as exc:
        raise OrphanComposeTeardownError(
            f"canonical Compose publisher identity is invalid: {exc}"
        ) from exc
    container_role_closure = compose_publisher_container_role_closure(publisher_roles)
    normalized_ports: list[dict[str, Any]] = []
    for item in canonical_ports:
        name = str(item.get("name") or "").strip()
        port = item.get("port")
        opened = item.get("open")
        if not name or isinstance(port, bool) or not isinstance(port, int) or not isinstance(opened, bool):
            raise OrphanComposeTeardownError("canonical target port inventory is invalid")
        normalized_ports.append({"name": name, "port": port, "open": opened})
    normalized_ports.sort(key=lambda item: (item["port"], item["name"]))
    canonical_ports_by_role = {
        str(item["name"]): int(item["port"]) for item in normalized_ports
    }
    normalized_other_blocks: list[dict[str, Any]] = []
    for item in other_target_port_blocks:
        block_target = str(item.get("target") or "").strip()
        start = item.get("blockStart")
        end = item.get("blockEnd")
        if (
            block_target not in LOCAL_TARGETS
            or block_target == target
            or isinstance(start, bool)
            or not isinstance(start, int)
            or isinstance(end, bool)
            or not isinstance(end, int)
            or start < 1
            or end > 65535
            or start > end
        ):
            raise OrphanComposeTeardownError(
                "other target canonical port block inventory is invalid"
            )
        normalized_other_blocks.append(
            {"target": block_target, "blockStart": start, "blockEnd": end}
        )
    normalized_other_blocks.sort(key=lambda item: item["target"])
    label_filter = f"label=com.docker.compose.project={project}"
    container_ids = _list_ids(
        ["docker", "ps", "--no-trunc", "-aq", "--filter", label_filter],
        run_command=run_command,
        label="container",
    )
    network_ids = _list_ids(
        [
            "docker",
            "network",
            "ls",
            "--no-trunc",
            "-q",
            "--filter",
            label_filter,
        ],
        run_command=run_command,
        label="network",
    )
    volume_names = _list_ids(
        ["docker", "volume", "ls", "-q", "--filter", label_filter],
        run_command=run_command,
        label="volume",
    )
    containers = (
        _run_json(
            ["docker", "inspect", *container_ids],
            run_command=run_command,
            label="container",
        )
        if container_ids
        else []
    )
    networks = (
        _run_json(
            ["docker", "network", "inspect", *network_ids],
            run_command=run_command,
            label="network",
        )
        if network_ids
        else []
    )
    volumes = (
        _run_json(
            ["docker", "volume", "inspect", *volume_names],
            run_command=run_command,
            label="volume",
        )
        if volume_names
        else []
    )
    if {str(item.get("Id") or "") for item in containers} != set(container_ids):
        raise OrphanComposeTeardownError("container inspection set drifted")
    if {str(item.get("Id") or "") for item in networks} != set(network_ids):
        raise OrphanComposeTeardownError("network inspection set drifted")
    if {str(item.get("Name") or "") for item in volumes} != set(volume_names):
        raise OrphanComposeTeardownError("volume inspection set drifted")
    container_descriptors = sorted(
        (
            _container_descriptor(
                item,
                project=project,
                publisher_roles=publisher_roles,
                container_role_closure=container_role_closure,
            )
            for item in containers
        ),
        key=lambda item: item["id"],
    )
    network_descriptors = sorted(
        (_network_descriptor(item, project=project) for item in networks),
        key=lambda item: item["id"],
    )
    volume_descriptors = sorted(
        (_volume_descriptor(item, project=project) for item in volumes),
        key=lambda item: item["id"],
    )
    project_container_ids = {item["id"] for item in container_descriptors}
    foreign_attachments = sorted(
        {
            attached_id
            for item in network_descriptors
            for attached_id in item["attachedContainerIds"]
            if attached_id not in project_container_ids
        }
    )
    if foreign_attachments:
        raise OrphanComposeTeardownError(
            "Compose project network has non-attested live containers: "
            + ", ".join(foreign_attachments)
        )
    project_published_endpoints = _normalize_published_endpoints(
        [
            endpoint
            for item in container_descriptors
            for endpoint in item["publishedEndpoints"]
        ]
    )
    unowned_roles = sorted(
        {
            str(endpoint["role"])
            for endpoint in project_published_endpoints
            if str(endpoint["role"]) not in canonical_ports_by_role
        }
    )
    if unowned_roles:
        raise OrphanComposeTeardownError(
            "published endpoint role has no canonical port in the target inventory: "
            + ", ".join(unowned_roles)
        )
    drifted_endpoints = [
        endpoint
        for endpoint in project_published_endpoints
        if canonical_ports_by_role[str(endpoint["role"])]
        != int(endpoint["hostPort"])
    ]
    for endpoint in drifted_endpoints:
        port = int(endpoint["hostPort"])
        protocol = str(endpoint["protocol"])
        role = str(endpoint["role"])
        conflicting_blocks = [
            item["target"]
            for item in normalized_other_blocks
            if item["blockStart"] <= port <= item["blockEnd"]
        ]
        if conflicting_blocks:
            raise OrphanComposeTeardownError(
                f"non-canonical project endpoint {role}:{port}/{protocol} "
                "belongs to another target block: "
                + ", ".join(conflicting_blocks)
            )
        if port_probe is None or not port_probe(endpoint):
            raise OrphanComposeTeardownError(
                f"non-canonical project endpoint {role}:{port}/{protocol} "
                "is not a live attested publisher"
            )
        publisher_ids = _list_ids(
            [
                "docker",
                "ps",
                "--no-trunc",
                "-q",
                "--filter",
                f"publish={port}/{protocol}",
            ],
            run_command=run_command,
            label=f"published endpoint {role}:{port}/{protocol}",
        )
        expected_publishers = sorted(
            item["id"]
            for item in container_descriptors
            if endpoint in item["publishedEndpoints"]
        )
        if publisher_ids != expected_publishers:
            raise OrphanComposeTeardownError(
                f"non-canonical project endpoint {role}:{port}/{protocol} "
                "live publisher differs from the attested containers"
            )
    if require_removable and not container_descriptors and not network_descriptors:
        raise OrphanComposeTeardownError(
            f"no removable orphan Compose resources exist for {target}"
        )
    return {
        "target": target,
        "project": project,
        "canonicalPorts": normalized_ports,
        "otherTargetPortBlocks": normalized_other_blocks,
        "publishedEndpoints": project_published_endpoints,
        "containers": container_descriptors,
        "networks": network_descriptors,
        "volumes": volume_descriptors,
    }
