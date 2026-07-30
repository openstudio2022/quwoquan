"""Process-safe coordination for immutable release operations.

Lock files are disposable runtime coordination under ``.qwq_output``.  They do
not contain release state and are never used as a source of truth.  A global
lock protects canonical reset, while release and environment resource locks let
each caller declare its conflict domain.  Ship and acceptance workflows acquire
both resources exclusively: a release cannot be mutated concurrently, and one
environment cannot switch releases while UAT acceptance is active.
"""

from __future__ import annotations

import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class ReleaseOperationConflict(RuntimeError):
    """Another process owns a conflicting release operation."""


def release_operation_lock_root(release_root: Path) -> Path:
    """Derive a disposable lock root beside ``data/releases``.

    The canonical layout is ``<output>/data/releases``.  Custom roots used by
    contract tests retain the same relative ``local/workspace`` isolation.
    """

    return release_root.parent / "local" / "workspace" / "release-operations"


def _safe_lock_name(release_id: str) -> str:
    if not release_id or release_id in {".", ".."} or "/" in release_id or "\\" in release_id:
        raise ValueError("releaseId is unsafe for release operation lock")
    return release_id


def _safe_environment_name(environment: str) -> str:
    if (
        not environment
        or environment in {".", ".."}
        or "/" in environment
        or "\\" in environment
    ):
        raise ValueError("environment is unsafe for release operation lock")
    return environment


@contextmanager
def release_operation_guard(
    *,
    lock_root: Path,
    release_ids: tuple[str, ...] = (),
    exclusive_releases: bool = False,
    environments: tuple[str, ...] = (),
    exclusive_environments: bool = False,
    global_exclusive: bool = False,
) -> Iterator[None]:
    """Acquire non-blocking global, environment and release resource locks.

    Locks are always acquired in global -> environment -> release order.  This
    deterministic hierarchy prevents deadlocks for multi-resource callers.
    Aggregate/baseline/discard take an exclusive per-release lock.  Ship and
    acceptance additionally take an exclusive per-environment lock, while
    operations targeting different environments retain independent resources.
    Canonical reset takes the global exclusive lock and therefore cannot overlap
    any class of operation.
    """

    normalized_ids = tuple(sorted({_safe_lock_name(item) for item in release_ids}))
    normalized_environments = tuple(
        sorted({_safe_environment_name(item) for item in environments})
    )
    lock_root.mkdir(parents=True, exist_ok=True)
    acquired: list[object] = []
    try:
        requests = [
            (
                lock_root / "global.lock",
                fcntl.LOCK_EX if global_exclusive else fcntl.LOCK_SH,
                "canonical release operations",
            )
        ]
        requests.extend(
            (
                lock_root / f"environment-{environment}.lock",
                fcntl.LOCK_EX if exclusive_environments else fcntl.LOCK_SH,
                f"environment={environment}",
            )
            for environment in normalized_environments
        )
        requests.extend(
            (
                lock_root / f"release-{release_id}.lock",
                fcntl.LOCK_EX if exclusive_releases else fcntl.LOCK_SH,
                f"releaseId={release_id}",
            )
            for release_id in normalized_ids
        )
        for path, mode, label in requests:
            handle = path.open("a+b")
            try:
                fcntl.flock(handle.fileno(), mode | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                handle.close()
                raise ReleaseOperationConflict(
                    f"GATE_BLOCK conflicting active release operation owns {label}"
                ) from exc
            acquired.append(handle)
        yield
    finally:
        for handle in reversed(acquired):
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()


__all__ = [
    "ReleaseOperationConflict",
    "release_operation_guard",
    "release_operation_lock_root",
]
