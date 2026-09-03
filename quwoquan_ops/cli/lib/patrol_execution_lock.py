"""Single-track lock for Flutter/Patrol build-workspace consumers."""

from __future__ import annotations

from pathlib import Path

from quwoquan_ops.cli.lib.host_locks import (
    DEFAULT_HOST_LOCK_ROOT,
    HostLock,
    HostLockBusyError,
    acquire_host_lock,
    host_lock_root,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PATROL_EXECUTION_LOCK_NAMESPACE = "process"
PATROL_EXECUTION_LOCK_NAME = "build-workspace.lock"
# Historical compatibility only.  Runtime acquisition resolves
# QWQ_HOST_LOCK_ROOT through patrol_execution_lock_path() on every call.
PATROL_EXECUTION_LOCK = (
    DEFAULT_HOST_LOCK_ROOT.expanduser()
    / PATROL_EXECUTION_LOCK_NAMESPACE
    / PATROL_EXECUTION_LOCK_NAME
)


def patrol_execution_lock_path() -> Path:
    """Return the canonical host-scoped Flutter build-workspace lock path."""

    return (
        host_lock_root()
        / PATROL_EXECUTION_LOCK_NAMESPACE
        / PATROL_EXECUTION_LOCK_NAME
    )


def acquire_patrol_execution_lock(
    *,
    env_name: str,
    target: str,
    lock_path: Path | None = None,
) -> HostLock:
    """Serialize Flutter builds that share the App build workspace."""

    path = Path(lock_path) if lock_path is not None else patrol_execution_lock_path()
    try:
        return acquire_host_lock(
            path,
            fields={
                "env": env_name.strip(),
                "target": target.strip(),
            },
            worktree_path=REPO_ROOT,
        )
    except HostLockBusyError as error:
        holder = str(error).partition(": ")[2]
        raise RuntimeError(
            f"Patrol build workspace is already in use: {holder or 'unknown'}",
        ) from error


__all__ = [
    "PATROL_EXECUTION_LOCK",
    "PATROL_EXECUTION_LOCK_NAME",
    "PATROL_EXECUTION_LOCK_NAMESPACE",
    "acquire_patrol_execution_lock",
    "patrol_execution_lock_path",
]
