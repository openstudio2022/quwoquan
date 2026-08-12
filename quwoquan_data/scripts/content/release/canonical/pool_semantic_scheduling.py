"""Deterministic four-slot semantic scheduling projection for pool inspection."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

_CARRIERS = ("homepage", "article", "image", "video")
_WAVE_SIZE = 12
_INITIAL_SLOTS = {
    "M100": {"homepage": 2, "article": 1, "image": 1, "video": 0},
    "M1000": {"homepage": 1, "article": 1, "image": 1, "video": 1},
    # This projection is one local wave only. Governed M10000 campaigns bind
    # the horizontally scalable host set/capacity plan at execution dispatch.
    "M10000": {"homepage": 1, "article": 1, "image": 1, "video": 1},
}


def _nonnegative_int(value: object) -> int:
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value > 0
        else 0
    )


def _positive_rate(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return float(value)
    return None


def _select_distinct_entity_candidates(
    rows: list[Mapping[str, Any]], *, limit: int
) -> list[dict[str, Any]]:
    """Select one candidate per canonical entity for a single semantic wave."""
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in rows:
        entity_ref = str(raw.get("entityRef") or "").strip()
        if not entity_ref or entity_ref in seen:
            continue
        selected.append(dict(raw))
        seen.add(entity_ref)
        if len(selected) == limit:
            break
    return selected


def semantic_scheduling_projection(
    *,
    milestone: str,
    supply: Mapping[str, Mapping[str, Any]],
    source_ready_backlog: Mapping[str, int] | None = None,
    p10_per_slot_throughput: Mapping[str, float] | None = None,
    source_ready_candidates: Mapping[str, list[Mapping[str, Any]]] | None = None,
    source_ready_input: Mapping[str, Any] | None = None,
    throughput_input: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Allocate only slots backed by physical source-ready inputs."""

    initial = dict(_INITIAL_SLOTS[milestone])
    backlog_input = source_ready_backlog or {}
    rate_input = p10_per_slot_throughput or {}
    backlog = {
        carrier: _nonnegative_int(backlog_input.get(carrier))
        for carrier in _CARRIERS
    }
    rates = {
        carrier: _positive_rate(rate_input.get(carrier))
        for carrier in _CARRIERS
    }
    gaps = {
        carrier: _nonnegative_int(supply[carrier].get("gap"))
        for carrier in _CARRIERS
    }
    launchable = {
        carrier
        for carrier in _CARRIERS
        if gaps[carrier] > 0 and backlog[carrier] > 0
    }
    slot_capacity = {
        carrier: (
            (min(gaps[carrier], backlog[carrier]) + _WAVE_SIZE - 1) // _WAVE_SIZE
            if carrier in launchable
            else 0
        )
        for carrier in _CARRIERS
    }
    assigned = {
        carrier: (
            min(initial[carrier], slot_capacity[carrier])
            if carrier in launchable
            else 0
        )
        for carrier in _CARRIERS
    }
    remaining_hours = {
        carrier: (
            round(gaps[carrier] / (rates[carrier] * 3600), 6)
            if rates[carrier] is not None
            else None
        )
        for carrier in _CARRIERS
    }
    while sum(assigned.values()) < 4:
        reallocatable = {
            carrier
            for carrier in launchable
            if assigned[carrier] < min(4, slot_capacity[carrier])
        }
        if not reallocatable:
            break
        carrier = max(
            reallocatable,
            key=lambda item: (
                remaining_hours[item]
                if remaining_hours[item] is not None
                else float(gaps[item]),
                gaps[item],
                -_CARRIERS.index(item),
            ),
        )
        assigned[carrier] += 1
    inventory = source_ready_candidates or {}
    distinct_capacity = {
        carrier: len(
            {
                str(row.get("entityRef") or "").strip()
                for row in inventory.get(carrier, [])
                if str(row.get("entityRef") or "").strip()
            }
        )
        for carrier in _CARRIERS
    }
    rows = [
        {
            "carrier": carrier,
            "gap": gaps[carrier],
            "sourceReadyBacklog": backlog[carrier],
            "p10PerSlotThroughput": rates[carrier],
            "remainingSemanticHours": remaining_hours[carrier],
            "assignedSlots": assigned[carrier],
            "sourceReadyHighWater": (
                max(initial[carrier], assigned[carrier]) * _WAVE_SIZE * 2
            ),
            "dispatchCandidateCount": min(
                gaps[carrier],
                backlog[carrier],
                distinct_capacity[carrier],
                assigned[carrier] * _WAVE_SIZE,
            ),
        }
        for carrier in _CARRIERS
    ]
    candidates = [row for row in rows if row["assignedSlots"] > 0]
    next_carrier = (
        max(
            candidates,
            key=lambda row: (
                row["remainingSemanticHours"]
                if row["remainingSemanticHours"] is not None
                else float(row["gap"]),
                row["gap"],
                -_CARRIERS.index(str(row["carrier"])),
            ),
        )["carrier"]
        if candidates
        else None
    )
    selected_candidates = [
        dict(candidate)
        for row in rows
        for candidate in _select_distinct_entity_candidates(
            list(inventory.get(str(row["carrier"]), [])),
            limit=int(row["dispatchCandidateCount"]),
        )
    ]
    wave_stable = {
        "schema": "quwoquan_data.pool_semantic_wave_input",
        "milestone": milestone,
        "sourcePoolRef": (source_ready_input or {}).get("sourcePoolRef"),
        "sourcePoolDigest": (source_ready_input or {}).get("sourcePoolDigest"),
        "sourcePoolEvidenceRootRef": (source_ready_input or {}).get(
            "sourcePoolEvidenceRootRef"
        ),
        "candidates": selected_candidates,
    }
    wave_digest = "sha256:" + hashlib.sha256(
        json.dumps(
            wave_stable,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "totalSemanticSlots": 4,
        "researchWaveSize": _WAVE_SIZE,
        "initialSlots": initial,
        "idleSlots": 4 - sum(assigned.values()),
        "nextReallocationCarrier": next_carrier,
        "dispatchBlockedWithoutPhysicalBacklog": not bool(launchable),
        "carriers": rows,
        "sourceReadyInput": dict(
            source_ready_input
            or {
                "status": "not_provided",
                "sourcePoolRef": None,
                "sourcePoolFileSha256": None,
                "sourcePoolDigest": None,
                "sourcePoolEvidenceRootRef": None,
                "evidenceBindingCount": 0,
            }
        ),
        "throughputInput": dict(
            throughput_input
            or {
                "throughputPromotionRef": None,
                "throughputPromotionFileSha256": None,
            }
        ),
        "waveInput": {**wave_stable, "waveInputDigest": wave_digest},
    }


__all__ = ["semantic_scheduling_projection"]
