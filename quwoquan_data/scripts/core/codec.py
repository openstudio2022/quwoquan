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

    def to_document(self) -> dict[str, object]:
        """Return a copy only for a schema-validation boundary."""
        return dict(self._fields)

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

    def boolean(self, key: str) -> bool:
        value = self.value(key)
        if not isinstance(value, bool):
            raise JsonObjectDecodeError(f"{key} must be a boolean")
        return value

    def optional_string(self, key: str) -> str | None:
        value = self.value(key)
        if value is None:
            return None
        if not isinstance(value, str):
            raise JsonObjectDecodeError(f"{key} must be a string or null")
        return value

    def object(self, key: str) -> "JsonObject":
        return self.from_value(self.value(key), label=key)

    def object_sequence(self, key: str) -> tuple["JsonObject", ...]:
        value = self.value(key)
        if not isinstance(value, list):
            raise JsonObjectDecodeError(f"{key} must be an array")
        return tuple(self.from_value(item, label=f"{key} item") for item in value)

    def string_mapping(self, key: str) -> tuple[tuple[str, str], ...]:
        value = self.value(key)
        if not isinstance(value, Mapping):
            raise JsonObjectDecodeError(f"{key} must be an object")
        rows: list[tuple[str, str]] = []
        for raw_key, raw_value in value.items():
            if (
                not isinstance(raw_key, str)
                or not raw_key.strip()
                or not isinstance(raw_value, str)
                or not raw_value.strip()
            ):
                raise JsonObjectDecodeError(f"{key} must map non-empty strings")
            rows.append((raw_key, raw_value))
        return tuple(rows)


__all__ = ["JsonObject", "JsonObjectDecodeError"]
