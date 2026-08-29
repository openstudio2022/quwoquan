"""orphan Compose teardown 的 schema、目标闭集、失败类型与规范化原语。

原单文件 ``orphan_compose_teardown.py`` 拆分出的共享常量子模块。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from uuid import uuid4

from ..environment_topology import (
    formal_release_compose_project_name,
    get_target,
    load_environment_topology,
    require_formal_release_compose_project,
)
from datetime import datetime, timezone


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


def declared_port_profile(target: str) -> str:
    """唯一判据：port profile 只从 topology 的 `portProfile` 声明位取。

    target 名与 profile 名今天恰好同形，但同形是巧合而非声明；用 target 名当
    profile 名会让身份解析绕过声明位，两者一旦分叉就无人判否。
    """
    try:
        declared = get_target(load_environment_topology(), target).get("portProfile")
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise OrphanComposeTeardownError(
            f"target {target} port profile declaration is unreadable: {exc}"
        ) from exc
    profile = str(declared or "").strip()
    if not profile:
        raise OrphanComposeTeardownError(
            f"target {target} declares no portProfile; "
            "declare it in the environment topology before orphan Compose teardown"
        )
    return profile


def canonical_project(target: str) -> str:
    try:
        return formal_release_compose_project_name(target)
    except ValueError as exc:
        raise OrphanComposeTeardownError(str(exc)) from exc


def require_canonical_project(target: str, value: object) -> str:
    try:
        return require_formal_release_compose_project(target, value)
    except ValueError as exc:
        raise OrphanComposeTeardownError(
            "orphan Compose project mismatch: formal release identity is invalid"
        ) from exc


def _normalize_published_endpoints(value: object) -> list[dict[str, object]]:
    if (
        isinstance(value, (str, bytes, bytearray, Mapping))
        or not isinstance(value, Sequence)
    ):
        raise OrphanComposeTeardownError(
            "orphan Compose published endpoints must be a list"
        )
    endpoints: list[dict[str, object]] = []
    identities: set[tuple[str, int, str]] = set()
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {
            "role",
            "hostPort",
            "protocol",
        }:
            raise OrphanComposeTeardownError(
                "orphan Compose published endpoint fields are invalid"
            )
        role = str(item.get("role") or "").strip()
        host_port = item.get("hostPort")
        protocol = str(item.get("protocol") or "").strip().lower()
        if not role or _SAFE_LABEL.fullmatch(role) is None:
            raise OrphanComposeTeardownError(
                "orphan Compose published endpoint role is invalid"
            )
        if (
            isinstance(host_port, bool)
            or not isinstance(host_port, int)
            or not 0 < host_port < 65536
        ):
            raise OrphanComposeTeardownError(
                "orphan Compose published endpoint hostPort is invalid"
            )
        if protocol not in {"tcp", "udp"}:
            raise OrphanComposeTeardownError(
                "orphan Compose published endpoint protocol is invalid"
            )
        identity = (role, host_port, protocol)
        if identity in identities:
            raise OrphanComposeTeardownError(
                "orphan Compose published endpoint identities must be distinct"
            )
        identities.add(identity)
        endpoints.append(
            {"role": role, "hostPort": host_port, "protocol": protocol}
        )
    return sorted(
        endpoints,
        key=lambda item: (
            int(item["hostPort"]),
            str(item["protocol"]),
            str(item["role"]),
        ),
    )


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _atomic_write_create_once(
    path: Path,
    payload: bytes,
    *,
    label: str,
) -> Path:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    published = False
    operation = "create temporary file"
    try:
        descriptor = os.open(temporary, flags, 0o600)
        operation = "write temporary file"
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            operation = "sync temporary file"
            os.fsync(handle.fileno())
        operation = "publish final file"
        try:
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError as exc:
            raise OrphanComposeTeardownError(
                f"orphan Compose {label} already exists"
            ) from exc
        published = True
        operation = "remove temporary file"
        temporary.unlink()
        operation = "sync parent directory"
        parent_descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
        return path
    except OrphanComposeTeardownError:
        raise
    except OSError as exc:
        rollback_error: OSError | None = None
        if published:
            try:
                path.unlink()
                parent_descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(parent_descriptor)
                finally:
                    os.close(parent_descriptor)
            except OSError as rollback_exc:
                rollback_error = rollback_exc
        detail = f"{operation} failed for {path}: [errno {exc.errno}] {exc.strerror or exc}"
        if rollback_error is not None:
            detail += (
                "; rollback failed: "
                f"[errno {rollback_error.errno}] {rollback_error.strerror or rollback_error}"
            )
        raise OrphanComposeTeardownError(
            f"orphan Compose {label} storage failure: {detail}"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


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
