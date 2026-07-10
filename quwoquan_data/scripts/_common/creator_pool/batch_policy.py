"""Shared batch policy for canonical creator-pool quotas."""
from __future__ import annotations

import math
from typing import Mapping

CREATOR_VERTICAL_SEGMENTS: tuple[str, ...] = (
    "travel_primary",
    "photography_primary",
    "travel_photography_cross",
)

CANONICAL_BATCH_ID = "travel_photo_1k_v1"
CANONICAL_UNIQUE_TARGET = 1200
CANONICAL_UNIQUE_SEGMENT_COUNTS: dict[str, int] = {
    "travel_primary": 200,
    "photography_primary": 200,
    "travel_photography_cross": 800,
}
CANONICAL_SHARD_TARGET = 120
CANONICAL_SHARD_SEGMENT_COUNTS: dict[str, int] = {
    "travel_primary": 20,
    "photography_primary": 20,
    "travel_photography_cross": 80,
}

LEGACY_SEGMENT_QUOTA_RATIOS: dict[str, float] = {
    "travel_primary": 0.30,
    "photography_primary": 0.30,
    "travel_photography_cross": 0.40,
}
DUAL_VIEW_SEGMENT_QUOTA_RATIOS: dict[str, float] = {
    "travel_primary": 1 / 6,
    "photography_primary": 1 / 6,
    "travel_photography_cross": 2 / 3,
}


def uses_dual_view_policy(batch_id: str) -> bool:
    """Return whether the batch follows the 1200-unique / dual-1k contract."""
    return batch_id == CANONICAL_BATCH_ID or batch_id.startswith(f"{CANONICAL_BATCH_ID}_")


def default_target_for_batch(batch_id: str) -> int:
    return CANONICAL_UNIQUE_TARGET if uses_dual_view_policy(batch_id) else 1000


def segment_quota_ratios(batch_id: str) -> dict[str, float]:
    return dict(DUAL_VIEW_SEGMENT_QUOTA_RATIOS if uses_dual_view_policy(batch_id) else LEGACY_SEGMENT_QUOTA_RATIOS)


def segment_counts(batch_id: str, target: int) -> dict[str, int]:
    """Compute the exact per-segment creator counts for a batch target."""
    if uses_dual_view_policy(batch_id):
        if target == CANONICAL_UNIQUE_TARGET:
            return dict(CANONICAL_UNIQUE_SEGMENT_COUNTS)
        if target == CANONICAL_SHARD_TARGET:
            return dict(CANONICAL_SHARD_SEGMENT_COUNTS)
    return _weighted_split(target, segment_quota_ratios(batch_id))


def segment_cycle_counts(batch_id: str, target: int) -> dict[str, int]:
    """Return a normalized cycle that preserves the batch segment ratios."""
    counts = segment_counts(batch_id, target)
    values = [value for value in counts.values() if value > 0]
    if not values:
        return counts
    divisor = values[0]
    for value in values[1:]:
        divisor = math.gcd(divisor, value)
    divisor = max(divisor, 1)
    return {segment: max(1, value // divisor) if value > 0 else 0 for segment, value in counts.items()}


def view_counts_from_segments(segment_counts_map: Mapping[str, int]) -> dict[str, int | float]:
    travel_primary = int(segment_counts_map.get("travel_primary") or 0)
    photo_primary = int(segment_counts_map.get("photography_primary") or 0)
    cross = int(segment_counts_map.get("travel_photography_cross") or 0)
    unique_total = travel_primary + photo_primary + cross
    travel_view = travel_primary + cross
    photo_view = photo_primary + cross
    overlap_rate = cross / max(min(travel_view, photo_view), 1)
    cross_ratio = cross / max(unique_total, 1)
    return {
        "uniqueCreatorCount": unique_total,
        "travelViewCount": travel_view,
        "photographyViewCount": photo_view,
        "viewOverlapCount": cross,
        "viewOverlapRate": round(overlap_rate, 4),
        "crossSegmentRatio": round(cross_ratio, 4),
    }


def expected_view_contract(batch_id: str, target: int) -> dict[str, int | float]:
    return view_counts_from_segments(segment_counts(batch_id, target))


def is_canonical_unique_target(batch_id: str, target: int) -> bool:
    return uses_dual_view_policy(batch_id) and target == CANONICAL_UNIQUE_TARGET


def is_canonical_shard_target(batch_id: str, target: int) -> bool:
    return uses_dual_view_policy(batch_id) and target == CANONICAL_SHARD_TARGET


def _weighted_split(target: int, ratios: Mapping[str, float]) -> dict[str, int]:
    """Split a target count by ratios while keeping the sum exact."""
    raw_items = []
    allocated = 0
    for segment in CREATOR_VERTICAL_SEGMENTS:
        ratio = float(ratios.get(segment) or 0.0)
        raw = target * ratio
        base = int(math.floor(raw))
        raw_items.append((segment, base, raw - base))
        allocated += base
    remainder = max(target - allocated, 0)
    ordered = sorted(raw_items, key=lambda item: (-item[2], item[0]))
    result = {segment: base for segment, base, _ in raw_items}
    for idx in range(remainder):
        segment = ordered[idx % len(ordered)][0]
        result[segment] += 1
    return result
