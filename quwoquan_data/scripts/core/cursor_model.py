"""Typed Cursor SDK model selection shared by policy and content execution."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True, slots=True, order=True)
class CursorModelParameter:
    id: str
    value: str

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.value.strip():
            raise ValueError("Cursor model parameter id and value are required")

    def to_document(self) -> dict[str, str]:
        return {"id": self.id, "value": self.value}


@dataclass(frozen=True, slots=True)
class CursorModelSelection:
    model_id: str
    parameters: tuple[CursorModelParameter, ...] = ()

    def __post_init__(self) -> None:
        if not self.model_id.strip():
            raise ValueError("Cursor model id is required")
        ids = tuple(parameter.id for parameter in self.parameters)
        if len(ids) != len(set(ids)):
            raise ValueError("Cursor model parameters must not contain duplicate ids")

    @classmethod
    def from_value(
        cls,
        value: str | "CursorModelSelection",
    ) -> "CursorModelSelection":
        if isinstance(value, cls):
            return value
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Cursor model selection must be a model id or typed selection")
        return cls(model_id=value.strip())

    @classmethod
    def from_config(
        cls,
        model_id: object,
        raw_parameters: object,
        *,
        label: str,
    ) -> "CursorModelSelection":
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError(f"{label}.model must be a non-empty string")
        if not isinstance(raw_parameters, Sequence) or isinstance(
            raw_parameters,
            (str, bytes),
        ):
            raise ValueError(f"{label}.modelParameters must be an array")
        parameters: list[CursorModelParameter] = []
        for index, raw in enumerate(raw_parameters):
            if not isinstance(raw, Mapping):
                raise ValueError(
                    f"{label}.modelParameters[{index}] must be an object"
                )
            if set(raw) != {"id", "value"}:
                raise ValueError(
                    f"{label}.modelParameters[{index}] must contain id and value only"
                )
            parameters.append(
                CursorModelParameter(
                    id=str(raw.get("id") or "").strip(),
                    value=str(raw.get("value") or "").strip(),
                )
            )
        return cls(model_id=model_id.strip(), parameters=tuple(parameters))

    def parameters_document(self) -> list[dict[str, str]]:
        return [parameter.to_document() for parameter in self.parameters]

    def to_sdk_document(self) -> dict[str, object]:
        return {
            "id": self.model_id,
            "params": self.parameters_document(),
        }

    def cache_key(self) -> str:
        return json.dumps(
            self.to_sdk_document(),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )


__all__ = ["CursorModelParameter", "CursorModelSelection"]
