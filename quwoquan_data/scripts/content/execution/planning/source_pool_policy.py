"""Execution projection of the source-pool policy frozen by campaign workload."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.schema import assert_valid

_MILESTONE_SCALES = frozenset({"M100", "M1000", "M10000"})


def _policy(*, workload_mode: str, scale: str) -> tuple[bool, str]:
    if workload_mode == "explicit":
        if not scale:
            raise ValueError("DATA.SOURCE.POOL_SHORTFALL: workload scale is missing")
        return False, "WORKLOAD"
    if workload_mode != "milestone_preset" or scale not in _MILESTONE_SCALES:
        raise ValueError("DATA.SOURCE.POOL_SHORTFALL: frozen workload policy is invalid")
    return scale == "M10000", scale


def requires_scale_source_pool(*, workload_mode: str, scale: str) -> bool:
    """Return the requirement explicitly frozen by workload mode and scale."""

    required, _target_scale = _policy(workload_mode=workload_mode, scale=scale)
    return required


def allows_scale_source_pool(*, workload_mode: str, scale: str) -> bool:
    """Validate a workload policy that may bind a complete source pool."""

    _policy(workload_mode=workload_mode, scale=scale)
    return True


def source_pool_policy_fields(
    *,
    binding: Mapping[str, Any] | None,
    evidence_root_ref: str | None,
    selection: Mapping[str, Any] | None,
) -> dict[str, Any]:
    values = (binding, evidence_root_ref, selection)
    if any(value is not None for value in values) and not all(
        value is not None for value in values
    ):
        raise ValueError("DATA.SOURCE.POOL_SHORTFALL: incomplete source pool binding")
    if binding is None:
        return {}
    assert_valid(
        dict(binding),
        "execution",
        "scale_source_pool_binding",
        label="frozen workload source pool",
    )
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
