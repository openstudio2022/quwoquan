"""Dynamic accessors for monkeypatch-compatible research-plan IO."""
from __future__ import annotations

import sys
import time as _time
from typing import Any


def _facade() -> Any:
    return sys.modules.get("download.research_plan")


def curl_json(url: str, *, timeout: int = 25) -> dict[str, Any]:
    facade = _facade()
    fn = getattr(facade, "_curl_json", None) if facade is not None else None
    if callable(fn) and fn is not curl_json:
        return fn(url, timeout=timeout)
    return {}


def wiki_api(host: str, params: dict[str, str | int]) -> dict[str, Any]:
    facade = _facade()
    fn = getattr(facade, "_wiki_api", None) if facade is not None else None
    if callable(fn) and fn is not wiki_api:
        return fn(host, params)
    return {}


def sleep(seconds: float) -> None:
    facade = _facade()
    time_module = getattr(facade, "time", _time) if facade is not None else _time
    time_module.sleep(seconds)


def call(name: str, fallback: Any, *args: Any, **kwargs: Any) -> Any:
    facade = _facade()
    fn = getattr(facade, name, None) if facade is not None else None
    if callable(fn) and fn is not fallback:
        return fn(*args, **kwargs)
    return fallback(*args, **kwargs)
