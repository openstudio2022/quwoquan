"""Frozen ReliableTask job-set targets for the runtime evidence facade."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from content.execution.runtime_evidence.reliabletask_contract import (
    JobSetTarget,
    job_set_targets,
)
from content.execution.runtime_evidence.reliabletask_process import observer_error


def load_job_set_targets(
    carrier: str,
    execution_id: str,
    backend_envelope: Mapping[str, Any],
    *,
    load_envelopes: Callable[[str], tuple[dict[str, Any], ...]],
) -> tuple[JobSetTarget, ...]:
    """Load and validate immutable job-set envelopes for one execution."""
    try:
        envelopes = load_envelopes(execution_id)
        return job_set_targets(
            carrier,
            execution_id,
            backend_envelope,
            envelopes,
        )
    except (OSError, TypeError, ValueError) as exc:
        raise observer_error(
            "FROZEN_TARGET_INVALID",
            f"{carrier}/{execution_id} immutable job-set invalid",
        ) from exc


__all__ = ["load_job_set_targets"]
