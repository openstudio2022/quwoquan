"""Single-track lock for Flutter/Patrol build-workspace consumers."""

from __future__ import annotations

from pathlib import Path

from quwoquan_ops.cli.lib.host_locks import (
    DEFAULT_HOST_LOCK_ROOT,
    HostLock,
    HostLockBusyError,
    acquire_host_lock,
    app_dependency_sync_lock_path,
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


class PatrolExecutionLock:
    """Workspace lock retaining dependency-sync exclusion until close."""

    def __init__(self, workspace_lock: HostLock, dependency_guard: HostLock | None) -> None:
        self._workspace_lock = workspace_lock
        self._dependency_guard = dependency_guard

    @property
    def path(self) -> Path:
        return self._workspace_lock.path

    @property
    def record(self) -> str:
        return self._workspace_lock.record

    def fileno(self) -> int:
        return self._workspace_lock.fileno()

    def close(self) -> None:
        try:
            self._workspace_lock.close()
        finally:
            if self._dependency_guard is not None:
                self._dependency_guard.close()
                self._dependency_guard = None

    def __enter__(self) -> "PatrolExecutionLock":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def acquire_patrol_execution_lock(
    *,
    env_name: str,
    target: str,
    lock_path: Path | None = None,
) -> PatrolExecutionLock:
    """Serialize Flutter builds that share the App build workspace."""

    path = Path(lock_path) if lock_path is not None else patrol_execution_lock_path()
    dependency_guard: HostLock | None = None
    if lock_path is None:
        try:
            dependency_guard = acquire_host_lock(
                app_dependency_sync_lock_path(),
                fields={"resource": "patrol-build-workspace-admission"},
                worktree_path=REPO_ROOT,
            )
        except HostLockBusyError as error:
            holder = str(error).partition(": ")[2]
            raise RuntimeError(
                "Patrol build workspace is already in use: "
                f"dependency-sync {holder or 'unknown'}",
            ) from error
    try:
        workspace_lock = acquire_host_lock(
            path,
            fields={
                "env": env_name.strip(),
                "target": target.strip(),
            },
            worktree_path=REPO_ROOT,
        )
    except HostLockBusyError as error:
        if dependency_guard is not None:
            dependency_guard.close()
        holder = str(error).partition(": ")[2]
        raise RuntimeError(
            f"Patrol build workspace is already in use: {holder or 'unknown'}",
        ) from error
    except BaseException:
        if dependency_guard is not None:
            dependency_guard.close()
        raise
    return PatrolExecutionLock(workspace_lock, dependency_guard)


__all__ = [
    "PATROL_EXECUTION_LOCK",
    "PATROL_EXECUTION_LOCK_NAME",
    "PATROL_EXECUTION_LOCK_NAMESPACE",
    "PatrolExecutionLock",
    "acquire_patrol_execution_lock",
    "patrol_execution_lock_path",
]
