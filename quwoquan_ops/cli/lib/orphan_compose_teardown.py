"""Candidate-independent, exact-resource recovery for orphaned local Compose stacks.

This module deliberately does not accept a Compose project from argv.  The only
eligible project is derived from the canonical Alpha/Beta/Gamma target.  A
read-only inventory is sealed once, expires quickly, and must match a complete
second inventory before any exact resource ID is removed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SCHEMA = "stackctl-orphan-compose-teardown-attestation"
CONSUMPTION_SCHEMA = "stackctl-orphan-compose-teardown-consumption"
JOURNAL_SCHEMA = "stackctl-orphan-compose-teardown-journal"
STEP_SCHEMA = "stackctl-orphan-compose-teardown-step"
CONVERGENCE_SCHEMA = "stackctl-orphan-compose-teardown-convergence"
LOCAL_TARGETS = frozenset({"alpha-local", "beta-local", "gamma-local"})
ATTESTATION_TTL_SECONDS = 300
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_SAFE_LABEL = re.compile(r"[a-zA-Z0-9_.:/@+,-]+")


class OrphanComposeTeardownError(RuntimeError):
    """Fail-closed contract error; callers must surface it as GATE_BLOCK."""


def canonical_project(target: str) -> str:
    if target not in LOCAL_TARGETS:
        raise OrphanComposeTeardownError(
            "orphan Compose teardown supports only Alpha/Beta/Gamma local targets"
        )
    return f"quwoquan_{target.removesuffix('-local')}_release"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OrphanComposeTeardownError(
            "orphan Compose attestation timestamp is invalid"
        ) from exc
    if parsed.tzinfo is None:
        raise OrphanComposeTeardownError(
            "orphan Compose attestation timestamp has no timezone"
        )
    return parsed.astimezone(timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


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
    project = canonical_project(target)
    if value.get("project") != project:
        raise OrphanComposeTeardownError("orphan Compose attestation project mismatch")
    snapshot = value.get("snapshot")
    if not isinstance(snapshot, dict) or snapshot.get("target") != target or snapshot.get("project") != project:
        raise OrphanComposeTeardownError("orphan Compose attestation snapshot identity mismatch")
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
    payload = _canonical_bytes(value) + b"\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(candidate, flags, 0o600)
    except OSError as exc:
        raise OrphanComposeTeardownError(
            "orphan Compose attestation already exists or is unsafe"
        ) from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return candidate


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


def _write_create_once(path: Path, payload: Mapping[str, Any], *, label: str) -> Path:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise OrphanComposeTeardownError(
            f"orphan Compose {label} already exists or path is unsafe"
        ) from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(_canonical_bytes(payload) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return path


def write_execution_journal_create_once(
    attestation_path: Path,
    *,
    attestation: Mapping[str, Any],
    commands: Sequence[Sequence[str]],
) -> Path:
    path = attestation_path.with_name("orphaned-compose-teardown-journal.json")
    steps: list[dict[str, Any]] = []
    for index, command_value in enumerate(commands, start=1):
        command = list(command_value)
        if len(command) == 4 and command[:3] == ["docker", "rm", "--force"]:
            kind = "container"
        elif len(command) == 4 and command[:3] == ["docker", "network", "rm"]:
            kind = "network"
        else:
            raise OrphanComposeTeardownError(
                "orphan Compose execution journal contains a non-exact command"
            )
        steps.append(
            {
                "index": index,
                "resourceKind": kind,
                "resourceId": command[-1],
                "argv": command,
            }
        )
    payload: dict[str, Any] = {
        "schema": JOURNAL_SCHEMA,
        "target": attestation.get("target"),
        "project": attestation.get("project"),
        "attestationDigest": attestation.get("attestationDigest"),
        "startedAt": _utc_text(datetime.now(timezone.utc)),
        "steps": steps,
    }
    payload["journalDigest"] = _digest(payload)
    return _write_create_once(path, payload, label="execution journal")


def write_step_receipt_create_once(
    attestation_path: Path,
    *,
    attestation: Mapping[str, Any],
    index: int,
    command: Sequence[str],
) -> Path:
    command_value = list(command)
    if len(command_value) != 4:
        raise OrphanComposeTeardownError("orphan Compose completed step is invalid")
    if command_value[:3] == ["docker", "rm", "--force"]:
        kind = "container"
    elif command_value[:3] == ["docker", "network", "rm"]:
        kind = "network"
    else:
        raise OrphanComposeTeardownError("orphan Compose completed step is invalid")
    path = attestation_path.with_name(
        f"orphaned-compose-teardown-step-{index:03d}.json"
    )
    payload: dict[str, Any] = {
        "schema": STEP_SCHEMA,
        "target": attestation.get("target"),
        "project": attestation.get("project"),
        "attestationDigest": attestation.get("attestationDigest"),
        "index": index,
        "resourceKind": kind,
        "resourceId": command_value[-1],
        "argv": command_value,
        "status": "removed",
        "completedAt": _utc_text(datetime.now(timezone.utc)),
    }
    payload["stepDigest"] = _digest(payload)
    return _write_create_once(path, payload, label="step receipt")


def write_consumption_create_once(
    attestation_path: Path,
    *,
    attestation: Mapping[str, Any],
    removed_containers: Sequence[str],
    removed_networks: Sequence[str],
    status: str = "passed",
    failed_command: Sequence[str] = (),
    removal_outcome: str = "complete",
) -> Path:
    if status not in {"passed", "partial_failure"}:
        raise OrphanComposeTeardownError(
            "orphan Compose consumption status is invalid"
        )
    path = attestation_path.with_name("orphaned-compose-teardown-consumption.json")
    payload: dict[str, Any] = {
        "schema": CONSUMPTION_SCHEMA,
        "target": attestation.get("target"),
        "project": attestation.get("project"),
        "attestationDigest": attestation.get("attestationDigest"),
        "consumedAt": _utc_text(datetime.now(timezone.utc)),
        "status": status,
        "removalOutcome": removal_outcome,
        "failedCommand": list(failed_command),
        "removedContainerIds": list(removed_containers),
        "removedNetworkIds": list(removed_networks),
        "preservedVolumeNames": [
            str(item.get("name") or "")
            for item in (attestation.get("snapshot") or {}).get("volumes", [])
        ],
    }
    payload["consumptionDigest"] = _digest(payload)
    return _write_create_once(path, payload, label="consumption receipt")


def assert_not_consumed(attestation_path: Path) -> None:
    """Reject replay before a destructive command is attempted."""

    path = attestation_path.with_name("orphaned-compose-teardown-consumption.json")
    if path.exists() or path.is_symlink():
        raise OrphanComposeTeardownError(
            "orphan Compose attestation was already consumed"
        )


def load_partial_consumption_for_convergence(
    attestation_path: Path,
    *,
    attestation: Mapping[str, Any],
) -> dict[str, Any]:
    path = attestation_path.with_name("orphaned-compose-teardown-consumption.json")
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or path.is_symlink():
            raise OSError("not a regular no-follow file")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OrphanComposeTeardownError(
            "orphan Compose consumption receipt is unreadable or unsafe"
        ) from exc
    fields = {
        "schema",
        "target",
        "project",
        "attestationDigest",
        "consumedAt",
        "status",
        "removalOutcome",
        "failedCommand",
        "removedContainerIds",
        "removedNetworkIds",
        "preservedVolumeNames",
        "consumptionDigest",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise OrphanComposeTeardownError(
            "orphan Compose consumption receipt fields mismatch"
        )
    unsigned = dict(value)
    declared_digest = unsigned.pop("consumptionDigest", None)
    if declared_digest != _digest(unsigned):
        raise OrphanComposeTeardownError(
            "orphan Compose consumption receipt digest mismatch"
        )
    if (
        value.get("schema") != CONSUMPTION_SCHEMA
        or value.get("target") != attestation.get("target")
        or value.get("project") != attestation.get("project")
        or value.get("attestationDigest") != attestation.get("attestationDigest")
    ):
        raise OrphanComposeTeardownError(
            "orphan Compose consumption receipt identity mismatch"
        )
    snapshot = attestation.get("snapshot")
    if not isinstance(snapshot, Mapping):
        raise OrphanComposeTeardownError(
            "orphan Compose attestation snapshot is missing"
        )
    expected_containers = [item.get("id") for item in snapshot.get("containers", [])]
    expected_networks = [item.get("id") for item in snapshot.get("networks", [])]
    expected_volumes = [item.get("name") for item in snapshot.get("volumes", [])]
    if (
        value.get("status") != "partial_failure"
        or value.get("removalOutcome") != "partial_failure"
        or value.get("failedCommand") != []
        or value.get("removedContainerIds") != expected_containers
        or value.get("removedNetworkIds") != expected_networks
        or value.get("preservedVolumeNames") != expected_volumes
    ):
        raise OrphanComposeTeardownError(
            "partial consumption is not eligible for audit-only convergence"
        )
    return value


def validate_execution_evidence_for_convergence(
    attestation_path: Path,
    *,
    attestation: Mapping[str, Any],
) -> None:
    expected_commands = exact_removal_commands(attestation)
    journal_path = attestation_path.with_name(
        "orphaned-compose-teardown-journal.json"
    )
    try:
        journal_info = journal_path.lstat()
        if not stat.S_ISREG(journal_info.st_mode) or journal_path.is_symlink():
            raise OSError("not a regular no-follow file")
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OrphanComposeTeardownError(
            "orphan Compose convergence journal is unreadable"
        ) from exc
    if not isinstance(journal, dict) or journal.get("schema") != JOURNAL_SCHEMA:
        raise OrphanComposeTeardownError(
            "orphan Compose convergence journal schema mismatch"
        )
    unsigned_journal = dict(journal)
    journal_digest = unsigned_journal.pop("journalDigest", None)
    if journal_digest != _digest(unsigned_journal):
        raise OrphanComposeTeardownError(
            "orphan Compose convergence journal digest mismatch"
        )
    steps = journal.get("steps")
    if (
        journal.get("target") != attestation.get("target")
        or journal.get("project") != attestation.get("project")
        or journal.get("attestationDigest") != attestation.get("attestationDigest")
        or not isinstance(steps, list)
        or [item.get("argv") for item in steps if isinstance(item, Mapping)]
        != expected_commands
        or len(steps) != len(expected_commands)
    ):
        raise OrphanComposeTeardownError(
            "orphan Compose convergence journal does not cover every exact resource"
        )
    for index, command in enumerate(expected_commands, start=1):
        step_path = attestation_path.with_name(
            f"orphaned-compose-teardown-step-{index:03d}.json"
        )
        try:
            step_info = step_path.lstat()
            if not stat.S_ISREG(step_info.st_mode) or step_path.is_symlink():
                raise OSError("not a regular no-follow file")
            step = json.loads(step_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise OrphanComposeTeardownError(
                f"orphan Compose convergence step {index} is unreadable"
            ) from exc
        if not isinstance(step, dict) or step.get("schema") != STEP_SCHEMA:
            raise OrphanComposeTeardownError(
                f"orphan Compose convergence step {index} schema mismatch"
            )
        unsigned_step = dict(step)
        step_digest = unsigned_step.pop("stepDigest", None)
        if step_digest != _digest(unsigned_step):
            raise OrphanComposeTeardownError(
                f"orphan Compose convergence step {index} digest mismatch"
            )
        if (
            step.get("target") != attestation.get("target")
            or step.get("project") != attestation.get("project")
            or step.get("attestationDigest")
            != attestation.get("attestationDigest")
            or step.get("index") != index
            or step.get("argv") != command
            or step.get("resourceId") != command[-1]
            or step.get("status") != "removed"
        ):
            raise OrphanComposeTeardownError(
                f"orphan Compose convergence step {index} identity mismatch"
            )


def write_convergence_create_once(
    attestation_path: Path,
    *,
    attestation: Mapping[str, Any],
    consumption: Mapping[str, Any],
    current_snapshot: Mapping[str, Any],
) -> Path:
    path = attestation_path.with_name("orphaned-compose-teardown-convergence.json")
    payload: dict[str, Any] = {
        "schema": CONVERGENCE_SCHEMA,
        "target": attestation.get("target"),
        "project": attestation.get("project"),
        "attestationDigest": attestation.get("attestationDigest"),
        "consumptionDigest": consumption.get("consumptionDigest"),
        "verifiedAt": _utc_text(datetime.now(timezone.utc)),
        "status": "passed",
        "currentSnapshotDigest": _digest(current_snapshot),
        "verifiedReleasedPorts": list(
            (attestation.get("snapshot") or {}).get(
                "projectPublishedHostPorts", []
            )
        ),
        "preservedVolumeNames": [
            str(item.get("name") or "")
            for item in current_snapshot.get("volumes", [])
        ],
    }
    payload["convergenceDigest"] = _digest(payload)
    return _write_create_once(path, payload, label="convergence receipt")


def assert_post_teardown_state(
    attestation: Mapping[str, Any],
    current_snapshot: Mapping[str, Any],
    *,
    port_probe: Callable[[int], bool],
) -> None:
    """Prove that only attested containers/networks were removed.

    Volumes are intentionally retained.  Their full descriptors must still
    match the attested inventory after the destructive commands complete.
    """

    expected = attestation.get("snapshot")
    if not isinstance(expected, Mapping):
        raise OrphanComposeTeardownError(
            "orphan Compose attestation snapshot is missing"
        )
    expected_ports = expected.get("canonicalPorts")
    current_ports = current_snapshot.get("canonicalPorts")
    if not isinstance(expected_ports, list) or not isinstance(current_ports, list):
        raise OrphanComposeTeardownError(
            "orphan Compose post-teardown canonical port inventory is invalid"
        )
    expected_identities = [
        {"name": item.get("name"), "port": item.get("port")}
        for item in expected_ports
        if isinstance(item, Mapping)
    ]
    current_identities = [
        {"name": item.get("name"), "port": item.get("port")}
        for item in current_ports
        if isinstance(item, Mapping)
    ]
    if (
        current_snapshot.get("target") != expected.get("target")
        or current_snapshot.get("project") != expected.get("project")
        or current_identities != expected_identities
        or current_snapshot.get("otherTargetPortBlocks")
        != expected.get("otherTargetPortBlocks")
    ):
        raise OrphanComposeTeardownError(
            "orphan Compose post-teardown target identity changed"
        )
    if any(bool(item.get("open")) for item in current_ports if isinstance(item, Mapping)):
        raise OrphanComposeTeardownError(
            "canonical target ports remain occupied after orphan Compose teardown"
        )
    project_ports = expected.get("projectPublishedHostPorts")
    if not isinstance(project_ports, list) or any(
        isinstance(item, bool) or not isinstance(item, int) for item in project_ports
    ):
        raise OrphanComposeTeardownError(
            "attested project published port inventory is invalid"
        )
    still_open = [item for item in project_ports if port_probe(item)]
    if still_open:
        raise OrphanComposeTeardownError(
            "attested project TCP ports remain occupied after teardown: "
            + ", ".join(str(item) for item in still_open)
        )
    if current_snapshot.get("containers") or current_snapshot.get("networks"):
        raise OrphanComposeTeardownError(
            "attested orphan Compose containers or networks remain live"
        )
    if current_snapshot.get("volumes") != expected.get("volumes"):
        raise OrphanComposeTeardownError(
            "orphan Compose volume inventory changed; volumes must be preserved"
        )
