"""Environment-neutral field inspection for immutable release payloads."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

FORBIDDEN_RELEASE_KEYS = frozenset(
    {
        "env",
        "environment",
        "sampleRatio",
        "activatedAt",
        "importRun",
    }
)


def iter_forbidden_release_keys(value: Any) -> Iterable[str]:
    """Yield mutable environment keys found anywhere in one JSON value."""

    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, Mapping):
            for key, child in current.items():
                if key in FORBIDDEN_RELEASE_KEYS:
                    yield key
                stack.append(child)
        elif isinstance(current, list):
            stack.extend(current)


__all__ = ["FORBIDDEN_RELEASE_KEYS", "iter_forbidden_release_keys"]
