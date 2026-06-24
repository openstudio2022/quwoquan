"""Dynamic calls back to ``download.handler`` for legacy monkeypatch seams."""
from __future__ import annotations

import sys
from typing import Any


def _facade() -> Any:
    return sys.modules.get("download.handler")


def patched(name: str, fallback: Any) -> bool:
    facade = _facade()
    fn = getattr(facade, name, None) if facade is not None else None
    return callable(fn) and fn is not fallback


def call(name: str, fallback: Any, *args: Any, **kwargs: Any) -> Any:
    facade = _facade()
    fn = getattr(facade, name, None) if facade is not None else None
    if callable(fn) and fn is not fallback:
        return fn(*args, **kwargs)
    return fallback(*args, **kwargs)
