"""Runtime bridge for legacy task.object_queue monkeypatch seams."""
from __future__ import annotations

import sys
from typing import Any, Callable, TypeVar

_T = TypeVar("_T")


def patched(name: str, default: _T) -> _T:
    facade = sys.modules.get("task.object_queue")
    if facade is None:
        return default
    return getattr(facade, name, default)  # type: ignore[return-value]


def call(name: str, default: Callable[..., _T], *args: Any, **kwargs: Any) -> _T:
    return patched(name, default)(*args, **kwargs)
