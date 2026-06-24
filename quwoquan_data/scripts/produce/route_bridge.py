"""Runtime bridge for legacy produce.route_workflow monkeypatch seams."""
from __future__ import annotations

import sys
from typing import Any, Callable, TypeVar

_T = TypeVar("_T")


def patched(name: str, default: _T) -> _T:
    facade = sys.modules.get("produce.route_workflow")
    if facade is None:
        return default
    value = getattr(facade, name, default)
    return value  # type: ignore[return-value]


def call(name: str, default: Callable[..., _T], *args: Any, **kwargs: Any) -> _T:
    return patched(name, default)(*args, **kwargs)
