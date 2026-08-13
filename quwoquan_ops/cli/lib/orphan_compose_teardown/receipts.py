"""orphan Compose teardown 的执行日志、消费回执与收敛证据。

原单文件 ``orphan_compose_teardown.py`` 拆分出的回执/收敛子模块。
"""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .attestation import exact_removal_commands
from .constants import (
    CONSUMPTION_SCHEMA,
    CONVERGENCE_SCHEMA,
    JOURNAL_SCHEMA,
    STEP_SCHEMA,
    OrphanComposeTeardownError,
    _canonical_bytes,
    _digest,
    _utc_text,
)


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
