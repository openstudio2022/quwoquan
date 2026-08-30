"""Stable four-carrier normalization shared by host-only inputs."""
from __future__ import annotations

from collections.abc import Iterable, Mapping

CARRIERS = ("homepage", "article", "image", "video")


def normalize_active_carriers(carriers: Iterable[str]) -> tuple[str, ...]:
    requested = tuple(str(carrier).strip() for carrier in carriers)
    if not requested:
        raise ValueError("at least one active carrier is required")
    if len(set(requested)) != len(requested):
        raise ValueError("active carriers must be unique")
    unknown = sorted(set(requested) - set(CARRIERS))
    if unknown:
        raise ValueError("unsupported carriers: " + ", ".join(unknown))
    return tuple(carrier for carrier in CARRIERS if carrier in requested)


def normalize_workloads(
    values: Mapping[str, int],
    *,
    active_carriers: Iterable[str] | None = None,
) -> dict[str, int]:
    active = normalize_active_carriers(
        active_carriers if active_carriers is not None else values.keys()
    )
    if set(values) != set(active):
        raise ValueError("workloads must exactly match active carriers")
    result: dict[str, int] = {}
    for carrier in active:
        value = values[carrier]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{carrier} workload must be a positive integer")
        result[carrier] = value
    return result


__all__ = ["CARRIERS", "normalize_active_carriers", "normalize_workloads"]
