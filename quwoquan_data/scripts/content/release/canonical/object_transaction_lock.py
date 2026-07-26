"""Process-safe serialization for canonical publish tree replacement."""
from __future__ import annotations

import fcntl
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import Callable, Iterator, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


@contextmanager
def canonical_publish_lock() -> Iterator[None]:
    """Fence the whole-root audit/apply sequence across workers and executions."""
    from core.paths import OUTPUT_ROOT

    lock_path = (
        Path(OUTPUT_ROOT)
        / "data/local/workspace/object-transactions"
        / ".canonical-publish.lock"
    )
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def canonical_publish_serialized(function: Callable[P, R]) -> Callable[P, R]:
    """Decorate one complete object transaction with the global publish fence."""

    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        with canonical_publish_lock():
            return function(*args, **kwargs)

    return wrapped


__all__ = ["canonical_publish_lock", "canonical_publish_serialized"]
