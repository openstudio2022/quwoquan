"""Minimal typed boundary for untrusted JSON-like objects.

Only codec and external-adapter modules may inspect arbitrary mappings.  Domain
controllers receive values through this object so their state transitions do
not depend on ``dict.get`` or wire-format details.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


class JsonObjectDecodeError(ValueError):
    """A JSON-like value does not satisfy a required object shape."""


@dataclass(frozen=True, slots=True)
class JsonObject:
    """Validated object boundary with explicit primitive accessors."""

    _fields: Mapping[str, object]

    @classmethod
    def from_value(cls, value: object, *, label: str) -> "JsonObject":
        if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
            raise JsonObjectDecodeError(f"{label} must be an object")
        return cls(dict(value))

    def value(self, key: str) -> object:
        return self._fields.get(key)

    def string(self, key: str) -> str:
        value = self.value(key)
        if not isinstance(value, str):
            raise JsonObjectDecodeError(f"{key} must be a string")
        return value

    def string_sequence(self, key: str) -> tuple[str, ...]:
        value = self.value(key)
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
            raise JsonObjectDecodeError(f"{key} must be a non-empty string array")
        return tuple(value)

    def integer(self, key: str) -> int:
        value = self.value(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise JsonObjectDecodeError(f"{key} must be an integer")
        return value


__all__ = ["JsonObject", "JsonObjectDecodeError"]
