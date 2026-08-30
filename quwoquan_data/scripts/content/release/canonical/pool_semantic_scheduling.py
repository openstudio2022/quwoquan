"""Deterministic workload-backed semantic scheduling for pool inspection."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from content.execution.campaign.lane import normalize_workloads

_CARRIERS = ("homepage", "article", "image", "video")
_WAVE_SIZE = 12


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
    rows: list[Mapping[str, Any]],
    *,
    limit: int,
    claimed_entity_refs: set[str],
) -> list[dict[str, Any]]:
    """Select one mutation per canonical entity across the current wave."""

    selected: list[dict[str, Any]] = []
    for raw in rows:
        entity_ref = str(raw.get("entityRef") or "").strip()
        if not entity_ref or entity_ref in claimed_entity_refs:
            continue
        selected.append(dict(raw))
        claimed_entity_refs.add(entity_ref)
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
    workload_targets: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Allocate only slots backed by physical source-ready inputs."""

    if milestone not in {"WORKLOAD", "M100", "M1000", "M10000"}:
        raise ValueError(f"unsupported semantic milestone: {milestone}")
    workloads = (
        normalize_workloads(workload_targets)
        if workload_targets is not None
        else normalize_workloads(
            {
                carrier: max(
                    1,
                    _nonnegative_int(row.get("target"))
                    or _nonnegative_int(row.get("gap")),
                )
                for carrier, row in supply.items()
            }
        )
    )
    active = tuple(workloads)
    backlog_input = source_ready_backlog or {}
    rate_input = p10_per_slot_throughput or {}
    backlog = {
        carrier: _nonnegative_int(backlog_input.get(carrier))
        for carrier in active
    }
    rates = {
        carrier: _positive_rate(rate_input.get(carrier))
        for carrier in active
    }
    gaps = (
        dict(workloads)
        if workload_targets is not None
        else {
            carrier: _nonnegative_int(supply[carrier].get("gap"))
            for carrier in active
        }
    )
    launchable = {
        carrier
        for carrier in active
        if gaps[carrier] > 0 and backlog[carrier] > 0
    }
    slot_capacity = {
        carrier: (
            (min(gaps[carrier], backlog[carrier]) + _WAVE_SIZE - 1) // _WAVE_SIZE
            if carrier in launchable
            else 0
        )
        for carrier in active
    }
    # slot 只隔离失败域，不声明 Provider、主机或 carrier 容量；所有有物理
    # 来源的 work unit 都进入本次可调度集合。
    assigned = dict(slot_capacity)
    remaining_hours = {
        carrier: (
            round(gaps[carrier] / (rates[carrier] * 3600), 6)
            if rates[carrier] is not None
            else None
        )
        for carrier in active
    }
    inventory = source_ready_candidates or {}
    physical_capacity = {
        carrier: len(inventory.get(carrier, []))
        for carrier in active
    }
    rows: list[dict[str, Any]] = [
        {
            "carrier": carrier,
            "gap": gaps[carrier],
            "sourceReadyBacklog": backlog[carrier],
            "p10PerSlotThroughput": rates[carrier],
            "remainingSemanticHours": remaining_hours[carrier],
            "assignedSlots": assigned[carrier],
            "sourceReadyHighWater": min(gaps[carrier], backlog[carrier]),
            "dispatchCandidateCount": 0,
        }
        for carrier in active
    ]
    selected_candidates: list[dict[str, Any]] = []
    claimed_entity_refs: set[str] = set()
    for row in rows:
        selected = _select_distinct_entity_candidates(
            list(inventory.get(str(row["carrier"]), [])),
            limit=min(
                int(row["gap"]),
                int(row["sourceReadyBacklog"]),
                physical_capacity[str(row["carrier"])],
            ),
            claimed_entity_refs=claimed_entity_refs,
        )
        row["dispatchCandidateCount"] = len(selected)
        selected_candidates.extend(selected)
    wave_stable = {
        "schema": "quwoquan_data.pool_semantic_wave_input",
        "milestone": milestone,
        "activeCarriers": list(active),
        "workloadTargets": workloads,
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
        "totalSemanticSlots": sum(assigned.values()),
        "researchWaveSize": _WAVE_SIZE,
        "dispatchBlockedWithoutPhysicalBacklog": not bool(launchable),
        "carriers": rows,
        "sourceReadyInput": dict(
            source_ready_input
            or {
                "status": "not_provided",
                "targetScale": milestone,
                "workloadMode": (
                    "explicit" if milestone == "WORKLOAD" else "milestone_preset"
                ),
                "activeCarriers": list(active),
                "workloadTargets": workloads,
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
