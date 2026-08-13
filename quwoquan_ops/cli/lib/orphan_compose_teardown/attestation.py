"""orphan Compose teardown 的一次性 attestation 封版、加载与精确删除指令。

原单文件 ``orphan_compose_teardown.py`` 拆分出的 attestation 子模块。
"""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .constants import (
    ATTESTATION_TTL_SECONDS,
    SCHEMA,
    OrphanComposeTeardownError,
    _canonical_bytes,
    _digest,
    _timestamp,
    _utc_text,
    canonical_project,
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
