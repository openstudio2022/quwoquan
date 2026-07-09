"""Cursor SDK usage extraction helpers.

The Cursor SDK result surface is not fully stable across versions. We therefore
probe a conservative set of common usage fields and fall back cleanly when a
given runtime does not expose them.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_TOKEN_TOTAL_KEYS = (
    "used_tokens",
    "usedTokens",
    "total_tokens",
    "totalTokens",
    "token_count",
    "tokenCount",
)
_TOKEN_INPUT_KEYS = (
    "input_tokens",
    "inputTokens",
    "prompt_tokens",
    "promptTokens",
)
_TOKEN_OUTPUT_KEYS = (
    "output_tokens",
    "outputTokens",
    "completion_tokens",
    "completionTokens",
)
_COST_KEYS = (
    "cost_usd",
    "costUsd",
    "total_cost_usd",
    "totalCostUsd",
    "cost",
)
_USAGE_CONTAINERS = ("usage", "billing", "metrics", "stats")


def _as_mapping(obj: Any) -> Mapping[str, Any] | None:
    if isinstance(obj, Mapping):
        return obj
    for attr in ("model_dump", "dict"):
        func = getattr(obj, attr, None)
        if callable(func):
            try:
                payload = func()
            except TypeError:
                continue
            except Exception:  # noqa: BLE001
                continue
            if isinstance(payload, Mapping):
                return payload
    return None


def _numeric_value(container: Any, keys: tuple[str, ...], *, integer: bool) -> int | float | None:
    mapping = _as_mapping(container)
    for key in keys:
        value: Any
        if mapping is not None and key in mapping:
            value = mapping.get(key)
        else:
            value = getattr(container, key, None)
        if value is None:
            continue
        try:
            return int(value) if integer else float(value)
        except (TypeError, ValueError):
            continue
    return None


def extract_cursor_usage(result: Any) -> dict[str, Any]:
    """Best-effort usage extraction from a Cursor SDK result object.

    Returns a stable dict with:
    - `available`: whether any authoritative usage field was discovered
    - `usedTokens`: total tokens consumed (0 when only cost is known)
    - `costUsd`: billed USD if exposed
    - `source`: which container exposed the fields
    """
    containers: list[tuple[str, Any]] = [("result", result)]
    for name in _USAGE_CONTAINERS:
        nested = getattr(result, name, None)
        if nested is not None:
            containers.append((name, nested))
        mapping = _as_mapping(result)
        if mapping is not None and mapping.get(name) is not None:
            containers.append((f"result.{name}", mapping.get(name)))

    for source, container in containers:
        total = _numeric_value(container, _TOKEN_TOTAL_KEYS, integer=True)
        input_tokens = _numeric_value(container, _TOKEN_INPUT_KEYS, integer=True)
        output_tokens = _numeric_value(container, _TOKEN_OUTPUT_KEYS, integer=True)
        cost = _numeric_value(container, _COST_KEYS, integer=False)
        if total is None and input_tokens is not None and output_tokens is not None:
            total = int(input_tokens) + int(output_tokens)
        elif total is None and input_tokens is not None:
            total = int(input_tokens)
        elif total is None and output_tokens is not None:
            total = int(output_tokens)
        if total is None and cost is None:
            continue
        return {
            "available": True,
            "usedTokens": int(total or 0),
            "costUsd": float(cost or 0.0),
            "source": source,
        }
    return {
        "available": False,
        "usedTokens": 0,
        "costUsd": 0.0,
        "source": "",
    }


def aggregate_turn_usage(turn_usages: Any) -> dict[str, Any]:
    """Aggregate authoritative usage from streamed `turn-ended` events.

    The local bridge does not copy usage onto the terminal ``RunResult``; the
    only authoritative source is the per-turn ``usage`` payload on
    ``turn-ended`` interaction updates. Token口径与 ``extract_cursor_usage``
    保持一致：优先 total 字段，否则 input+output（cache 读写不计入总量）。
    """
    total_tokens = 0
    total_cost = 0.0
    found = False
    for usage in turn_usages or ():
        if usage is None:
            continue
        total = _numeric_value(usage, _TOKEN_TOTAL_KEYS, integer=True)
        input_tokens = _numeric_value(usage, _TOKEN_INPUT_KEYS, integer=True)
        output_tokens = _numeric_value(usage, _TOKEN_OUTPUT_KEYS, integer=True)
        cost = _numeric_value(usage, _COST_KEYS, integer=False)
        if total is None:
            parts = [x for x in (input_tokens, output_tokens) if x is not None]
            total = sum(parts) if parts else None
        if total is None and cost is None:
            continue
        found = True
        total_tokens += int(total or 0)
        total_cost += float(cost or 0.0)
    if not found:
        return {"available": False, "usedTokens": 0, "costUsd": 0.0, "source": ""}
    return {
        "available": True,
        "usedTokens": total_tokens,
        "costUsd": total_cost,
        "source": "stream_turn_ended",
    }


__all__ = ["extract_cursor_usage", "aggregate_turn_usage"]
