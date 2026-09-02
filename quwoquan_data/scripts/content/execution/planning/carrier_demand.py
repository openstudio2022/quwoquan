"""Shared identities and callback contracts for carrier-selective campaigns."""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

CAMPAIGN_CARRIERS = ("homepage", "article", "image", "video")
LaneRunner = Callable[[list[str], Path, dict[str, str], Path, float | None], int]
PhaseResultCallback = Callable[[str, tuple[int, str | None]], None]


def normalize_active_carriers(carriers: Iterable[str]) -> tuple[str, ...]:
    """Return one non-empty canonical carrier subset without hidden lanes."""

    requested = tuple(str(carrier).strip() for carrier in carriers)
    if not requested:
        raise ValueError("campaign requires at least one active carrier")
    if len(set(requested)) != len(requested):
        raise ValueError("campaign active carriers must be unique")
    unknown = sorted(set(requested) - set(CAMPAIGN_CARRIERS))
    if unknown:
        raise ValueError(f"campaign active carriers are invalid: {', '.join(unknown)}")
    return tuple(carrier for carrier in CAMPAIGN_CARRIERS if carrier in requested)


def normalize_workloads(
    workloads: Mapping[str, int],
    *,
    active_carriers: Iterable[str] | None = None,
) -> dict[str, int]:
    """Validate exact per-carrier quotas and preserve canonical ordering."""

    active = normalize_active_carriers(
        active_carriers if active_carriers is not None else workloads.keys()
    )
    if set(workloads) != set(active):
        raise ValueError("campaign workloads must exactly match active carriers")
    normalized: dict[str, int] = {}
    for carrier in active:
        quota = workloads[carrier]
        if isinstance(quota, bool) or not isinstance(quota, int) or quota < 1:
            raise ValueError(f"campaign {carrier} workload quota must be positive")
        normalized[carrier] = quota
    return normalized


__all__ = [
    "CAMPAIGN_CARRIERS",
    "LaneRunner",
    "PhaseResultCallback",
    "normalize_active_carriers",
    "normalize_workloads",
]
