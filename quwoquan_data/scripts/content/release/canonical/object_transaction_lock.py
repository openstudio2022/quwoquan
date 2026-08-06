"""Process-safe serialization for canonical publish tree replacement."""
from __future__ import annotations

import fcntl
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

_ACTIVE_LOCK_IDENTITIES: ContextVar[frozenset[str]] = ContextVar(
    "canonical_publish_lock_identities",
    default=frozenset(),
)


@contextmanager
def canonical_publish_lock(publish_root: Path | None = None) -> Iterator[None]:
    """Fence the whole-root audit/apply sequence across workers and executions."""
    from core.paths import publish_lock_path

    lock_path = publish_lock_path(publish_root)
    identity = str(lock_path)
    active = _ACTIVE_LOCK_IDENTITIES.get()
    if identity in active:
        yield
        return
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        token = _ACTIVE_LOCK_IDENTITIES.set(active | {identity})
        try:
            yield
        finally:
            _ACTIVE_LOCK_IDENTITIES.reset(token)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def canonical_publish_serialized(function: Callable[P, R]) -> Callable[P, R]:
    """Decorate one complete object transaction with the global publish fence."""

    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        raw_publish_root = kwargs.get("publish_root")
        publish_root = (
            raw_publish_root if isinstance(raw_publish_root, Path) else None
        )
        with canonical_publish_lock(publish_root):
            return function(*args, **kwargs)

    return wrapped


__all__ = ["canonical_publish_lock", "canonical_publish_serialized"]
