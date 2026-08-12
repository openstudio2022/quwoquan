"""Execution-policy projection for a frozen scale source pool."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from content.execution.identity import parse_execution_id

_OPTIONAL_SOURCE_POOL_SCALE_INTENTS = frozenset({"m100", "m1000"})
_REQUIRED_SOURCE_POOL_SCALE_INTENTS = frozenset({"m10000"})


def requires_scale_source_pool(execution_id: str) -> bool:
    """Derive pool admission from the canonical execution identity."""
    return parse_execution_id(execution_id).intent in _REQUIRED_SOURCE_POOL_SCALE_INTENTS


def allows_scale_source_pool(execution_id: str) -> bool:
    """Return whether the current wave may bind a physical source-pool capsule."""

    intent = parse_execution_id(execution_id).intent
    return intent in (
        _OPTIONAL_SOURCE_POOL_SCALE_INTENTS | _REQUIRED_SOURCE_POOL_SCALE_INTENTS
    )


def source_pool_policy_fields(
    execution_id: str,
    *,
    binding: Mapping[str, Any] | None,
    evidence_root_ref: str | None,
    selection: Mapping[str, Any] | None,
) -> dict[str, Any]:
    required = requires_scale_source_pool(execution_id)
    allowed = allows_scale_source_pool(execution_id)
    values = (binding, evidence_root_ref, selection)
    if any(value is not None for value in values) and not all(
        value is not None for value in values
    ):
        raise ValueError("DATA.SOURCE.POOL_SHORTFALL: incomplete source pool binding")
    if required and not all(value is not None for value in values):
        raise ValueError("DATA.SOURCE.POOL_SHORTFALL: M10000 execution requires source pool")
    if not allowed and any(value is not None for value in values):
        raise ValueError(
            "DATA.SOURCE.POOL_SHORTFALL: below-M100 execution forbids source pool"
        )
    if binding is None:
        return {}
    return {
        "scaleSourcePool": dict(binding),
        "sourcePoolEvidenceRootRef": evidence_root_ref,
        "sourcePoolSelection": dict(selection or {}),
    }


__all__ = [
    "allows_scale_source_pool",
    "requires_scale_source_pool",
    "source_pool_policy_fields",
]
