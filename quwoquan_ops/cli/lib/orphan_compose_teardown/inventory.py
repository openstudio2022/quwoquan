"""orphan Compose teardown 的只读资源盘点与快照采样。

原单文件 ``orphan_compose_teardown.py`` 拆分出的 inventory 子模块。
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from .constants import (
    LOCAL_TARGETS,
    OrphanComposeTeardownError,
    _DIGEST,
    _SAFE_LABEL,
    _canonical_bytes,
    _digest,
    canonical_project,
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


def _labels(value: object, *, project: str, label: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise OrphanComposeTeardownError(f"{label} has no Compose labels")
    labels = {str(key): str(item) for key, item in value.items()}
    if labels.get("com.docker.compose.project") != project:
        raise OrphanComposeTeardownError(f"{label} Compose project label mismatch")
    return dict(sorted(labels.items()))


def _published_ports(container: Mapping[str, Any]) -> list[int]:
    host_config = container.get("HostConfig")
    bindings = host_config.get("PortBindings") if isinstance(host_config, Mapping) else None
    ports: set[int] = set()
    if bindings is None:
        return []
    if not isinstance(bindings, Mapping):
        raise OrphanComposeTeardownError("container PortBindings is invalid")
    for items in bindings.values():
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
            ports.add(int(value))
    return sorted(ports)


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
    canonical_ports: set[int],
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
    published_ports = _published_ports(value)
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
        "publishedHostPorts": published_ports,
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
    canonical_ports: Sequence[Mapping[str, Any]],
    run_command: Callable[[list[str]], Any],
    require_removable: bool = True,
    other_target_port_blocks: Sequence[Mapping[str, Any]] = (),
    port_probe: Callable[[int], bool] | None = None,
) -> dict[str, Any]:
    project = canonical_project(target)
    normalized_ports: list[dict[str, Any]] = []
    for item in canonical_ports:
        name = str(item.get("name") or "").strip()
        port = item.get("port")
        opened = item.get("open")
        if not name or isinstance(port, bool) or not isinstance(port, int) or not isinstance(opened, bool):
            raise OrphanComposeTeardownError("canonical target port inventory is invalid")
        normalized_ports.append({"name": name, "port": port, "open": opened})
    normalized_ports.sort(key=lambda item: (item["port"], item["name"]))
    port_numbers = {item["port"] for item in normalized_ports}
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
            _container_descriptor(item, project=project, canonical_ports=port_numbers)
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
    project_published_ports = sorted(
        {
            port
            for item in container_descriptors
            for port in item["publishedHostPorts"]
        }
    )
    noncanonical_ports = sorted(set(project_published_ports) - port_numbers)
    for port in noncanonical_ports:
        conflicting_blocks = [
            item["target"]
            for item in normalized_other_blocks
            if item["blockStart"] <= port <= item["blockEnd"]
        ]
        if conflicting_blocks:
            raise OrphanComposeTeardownError(
                f"non-canonical project port {port} belongs to another target block: "
                + ", ".join(conflicting_blocks)
            )
        if port_probe is None or not port_probe(port):
            raise OrphanComposeTeardownError(
                f"non-canonical project port {port} is not a live attested publisher"
            )
        publisher_ids = _list_ids(
            [
                "docker",
                "ps",
                "--no-trunc",
                "-q",
                "--filter",
                f"publish={port}",
            ],
            run_command=run_command,
            label=f"published port {port}",
        )
        expected_publishers = sorted(
            item["id"]
            for item in container_descriptors
            if port in item["publishedHostPorts"]
        )
        if publisher_ids != expected_publishers:
            raise OrphanComposeTeardownError(
                f"non-canonical project port {port} live publisher differs from the attested containers"
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
        "projectPublishedHostPorts": project_published_ports,
        "nonCanonicalPublishedHostPorts": noncanonical_ports,
        "containers": container_descriptors,
        "networks": network_descriptors,
        "volumes": volume_descriptors,
    }
