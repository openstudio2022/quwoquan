"""Host-scoped non-blocking locks for resources shared by worktrees."""

from __future__ import annotations

import contextlib
import fcntl
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TextIO
from urllib.parse import unquote

from quwoquan_ops.cli.lib.common import utc_now
from quwoquan_ops.cli.lib.worktree_identity import (
    WorktreeIdentity,
    WorktreeIdentityError,
    resolve_worktree_identity,
)

HOST_LOCK_ROOT_ENV = "QWQ_HOST_LOCK_ROOT"
DEFAULT_HOST_LOCK_ROOT = Path("~/.cache/quwoquan/host-locks")
_HOLDER_PID = re.compile(r"\bpid=(?P<pid>[1-9][0-9]*)\b")
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


class HostLockBusyError(RuntimeError):
    """A live process owns a requested host-scoped resource."""


@dataclass(frozen=True)
class HostLockOwner:
    pid: int
    worktree: str
    lane: str
    head_sha: str
    started_at: str

    def record(self, *, fields: dict[str, str] | None = None) -> str:
        values = {
            "pid": str(self.pid),
            **(fields or {}),
            "startedAt": self.started_at,
            "worktree": self.worktree,
            "lane": self.lane,
            "headSha": self.head_sha,
        }
        return " ".join(f"{key}={_quote(value)}" for key, value in values.items())


class HostLock:
    """A held flock descriptor. Closing it releases the host resource."""

    def __init__(self, path: Path, handle: TextIO, record: str) -> None:
        self.path = path
        self._handle = handle
        self.record = record
        self._closed = False

    def fileno(self) -> int:
        return self._handle.fileno()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._handle.seek(0)
            self._handle.truncate()
            self._handle.flush()
            os.fsync(self._handle.fileno())
        finally:
            with contextlib.suppress(OSError, ValueError):
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()

    def __enter__(self) -> HostLock:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _quote(value: str) -> str:
    return value.replace("%", "%25").replace(" ", "%20").replace("\n", "%0A")


def _safe_segment(value: str, *, name: str) -> str:
    normalized = str(value).strip()
    if not _SAFE_SEGMENT.fullmatch(normalized) or normalized in {".", ".."}:
        raise ValueError(f"invalid {name} lock identity: {value!r}")
    return normalized


def host_lock_root() -> Path:
    override = str(os.environ.get(HOST_LOCK_ROOT_ENV) or "").strip()
    return Path(override or DEFAULT_HOST_LOCK_ROOT).expanduser().resolve()


def device_lock_path(device: str, app: str) -> Path:
    return (
        host_lock_root()
        / "device"
        / _safe_segment(device, name="device")
        / f"{_safe_segment(app, name='app')}.lock"
    )


def local_runtime_lock_path(target: str) -> Path:
    return (
        host_lock_root()
        / "local-runtime"
        / f"{_safe_segment(target, name='local runtime target')}.lock"
    )


def named_host_lock_path(namespace: str, resource: str) -> Path:
    """Return a safe host-scoped path for a named shared resource."""

    return (
        host_lock_root()
        / _safe_segment(namespace, name="host lock namespace")
        / f"{_safe_segment(resource, name='host lock resource')}.lock"
    )


def app_dependency_sync_lock_path() -> Path:
    """Return the host-wide Flutter/CocoaPods/Gradle sync lock."""

    return named_host_lock_path("app-dependency-sync", "toolchain")


def _pid_is_live(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (OSError, OverflowError, ValueError):
        return True
    return True


def holder_record_is_live(record: str) -> bool:
    matched = _HOLDER_PID.search(record)
    if matched is None:
        return True
    return _pid_is_live(int(matched.group("pid")))


def parse_holder_record(record: str) -> dict[str, str]:
    """Parse a lock record without treating its fields as authority."""
    parsed: dict[str, str] = {}
    for field in record.split():
        key, separator, value = field.partition("=")
        if separator and key:
            parsed[key] = unquote(value)
    return parsed


def read_lock_holder(path: Path) -> str | None:
    """Read a live holder record, ignoring stale dead-pid metadata."""
    try:
        record = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except OSError:
        return None
    return record if record and holder_record_is_live(record) else None


def current_lock_owner(
    *,
    worktree_path: Path | str | None = None,
    identity: WorktreeIdentity | None = None,
) -> HostLockOwner:
    resolved = identity or resolve_worktree_identity(worktree_path)
    if resolved.worktree_root is None:
        raise WorktreeIdentityError("bare repository cannot own a host resource")
    return HostLockOwner(
        pid=os.getpid(),
        worktree=resolved.worktree_root,
        lane=resolved.lane,
        head_sha=resolved.head_sha,
        started_at=utc_now(),
    )


def acquire_host_lock(
    path: Path,
    *,
    fields: dict[str, str] | None = None,
    worktree_path: Path | str | None = None,
    identity: WorktreeIdentity | None = None,
) -> HostLock:
    """Acquire ``path`` exclusively and non-blockingly.

    flock releases automatically when an owner dies.  A stale record left by
    that process is overwritten after the new descriptor obtains the lock.
    """
    owner = current_lock_owner(worktree_path=worktree_path, identity=identity)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        handle.seek(0)
        holder = handle.read().strip()
        if not holder or not holder_record_is_live(holder):
            holder = "unknown live holder"
        handle.close()
        raise HostLockBusyError(f"host resource is already locked: {holder}") from error

    record = owner.record(fields=fields)
    handle.seek(0)
    handle.truncate()
    handle.write(record + "\n")
    handle.flush()
    os.fsync(handle.fileno())
    return HostLock(path, handle, record)


def acquire_host_lock_bounded(
    path: Path,
    *,
    timeout_seconds: float,
    poll_seconds: float = 0.1,
    fields: dict[str, str] | None = None,
    worktree_path: Path | str | None = None,
    identity: WorktreeIdentity | None = None,
    on_wait: Callable[[str, float], None] | None = None,
) -> HostLock:
    """Acquire a host resource within a wall-clock bound, reporting its holder."""

    if timeout_seconds < 0 or poll_seconds <= 0:
        raise ValueError("host lock timeout and poll interval are invalid")
    resolved_identity = identity or resolve_worktree_identity(worktree_path)
    deadline = time.monotonic() + timeout_seconds
    last_holder = "unknown live holder"
    while True:
        try:
            return acquire_host_lock(
                path,
                fields=fields,
                identity=resolved_identity,
            )
        except HostLockBusyError as error:
            last_holder = str(error).partition(": ")[2] or last_holder
            remaining = max(0.0, deadline - time.monotonic())
            if on_wait is not None:
                on_wait(last_holder, remaining)
            if remaining <= 0:
                raise HostLockBusyError(
                    f"host resource wait timed out: {last_holder}"
                ) from error
            time.sleep(min(poll_seconds, remaining))


def acquire_device_lock(
    *,
    device: str,
    app: str,
    worktree_path: Path | str | None = None,
    identity: WorktreeIdentity | None = None,
) -> HostLock:
    return acquire_host_lock(
        device_lock_path(device, app),
        fields={"device": device.strip(), "app": app.strip()},
        worktree_path=worktree_path,
        identity=identity,
    )


def acquire_local_runtime_lock(
    *,
    target: str,
    worktree_path: Path | str | None = None,
    identity: WorktreeIdentity | None = None,
) -> HostLock:
    return acquire_host_lock(
        local_runtime_lock_path(target),
        fields={"target": target.strip()},
        worktree_path=worktree_path,
        identity=identity,
    )


def local_runtime_holders(target: str) -> list[dict[str, str]]:
    """Return live holder records for status/read-only diagnostics."""
    path = local_runtime_lock_path(target)
    try:
        records = path.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, OSError):
        return []
    return [
        {"path": str(path), "record": record, **parse_holder_record(record)}
        for record in records
        if record.strip() and holder_record_is_live(record)
    ]


__all__ = [
    "DEFAULT_HOST_LOCK_ROOT",
    "HOST_LOCK_ROOT_ENV",
    "HostLock",
    "HostLockBusyError",
    "HostLockOwner",
    "WorktreeIdentityError",
    "acquire_device_lock",
    "app_dependency_sync_lock_path",
    "acquire_host_lock",
    "acquire_host_lock_bounded",
    "acquire_local_runtime_lock",
    "device_lock_path",
    "holder_record_is_live",
    "host_lock_root",
    "local_runtime_holders",
    "local_runtime_lock_path",
    "named_host_lock_path",
    "parse_holder_record",
    "read_lock_holder",
]
