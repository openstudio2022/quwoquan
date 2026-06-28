"""Diversity matrix planning for creator pools."""
from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from _common.creator_pool.bundle import build_creator_ref
from _common.creator_pool.constants import (
    CARRIER_BUCKETS,
    COMMERCIAL_CARRIER_BUCKETS,
    OUTPUT_TIERS,
    PLATFORM_BUCKETS,
    POPULARITY_TIERS,
    TRAVEL_ARCHETYPES,
    TRAVEL_REGION_BUCKETS,
    TRAVEL_TOPIC_REFS,
)
from _common.paths import creator_pool_shared_dir


def build_diversity_matrix(vertical: str, target: int) -> dict[str, Any]:
    archetype = _travel_archetype_quota(target) if vertical == "travel" and target >= 100 else _even_split(
        TRAVEL_ARCHETYPES, target
    )
    region = _even_split(TRAVEL_REGION_BUCKETS, target)
    carrier = _even_split(COMMERCIAL_CARRIER_BUCKETS if target >= 100 else CARRIER_BUCKETS, target)
    platform = _even_split(PLATFORM_BUCKETS, target)
    popularity = _tier_split(POPULARITY_TIERS, target, (0.15, 0.35, 0.30, 0.20))
    output = _tier_split(OUTPUT_TIERS, target, (0.40, 0.45, 0.15))
    return {
        "schemaVersion": "quwoquan_data.diversity_matrix/1",
        "vertical": vertical,
        "dimensions": {
            "archetype": archetype,
            "region": region,
            "carrier": carrier,
            "platform": platform,
            "popularityTier": popularity,
            "outputTier": output,
        },
        "topicCoverageMin": 12 if target >= 100 else 4,
        "topicRefs": list(TRAVEL_TOPIC_REFS),
        "minBucketFillRate": 1.0 if target >= 100 else 0.5,
        "targetEntropy": 0.85 if target >= 100 else 0.6,
    }


def assign_creator_slots(vertical: str, target: int) -> list[dict[str, str]]:
    matrix = build_diversity_matrix(vertical, target)
    slots: list[dict[str, str]] = []
    for idx in range(target):
        archetype = TRAVEL_ARCHETYPES[idx % len(TRAVEL_ARCHETYPES)]
        region = TRAVEL_REGION_BUCKETS[idx % len(TRAVEL_REGION_BUCKETS)]
        carrier = CARRIER_BUCKETS[idx % len(CARRIER_BUCKETS)]
        platform = PLATFORM_BUCKETS[idx % len(PLATFORM_BUCKETS)]
        seq = idx + 1
        slots.append(
            {
                "creatorRef": build_creator_ref(
                    vertical=vertical,
                    archetype=archetype,
                    region=region,
                    seq=seq,
                ),
                "archetype": archetype,
                "regionBucket": region,
                "carrierBucket": carrier,
                "platformBucket": platform,
            }
        )
    return slots


def diversity_report(bundles: list[dict[str, Any]], *, vertical: str = "", batch_id: str = "") -> dict[str, Any]:
    buckets: Counter[str] = Counter()
    counters: dict[str, Counter[str]] = {
        "archetype": Counter(),
        "region": Counter(),
        "carrier": Counter(),
        "popularityTier": Counter(),
        "outputTier": Counter(),
    }
    topic_refs: set[str] = set()
    for bundle in bundles:
        slots = bundle.get("diversitySlots") or {}
        metrics = bundle.get("sourceMetrics") or {}
        archetype = str(slots.get("archetypeBucket") or "")
        region = str(slots.get("regionBucket") or "")
        carrier = str(slots.get("carrierBucket") or "")
        key = f"{archetype}|{region}"
        buckets[key] += 1
        for name, value in (
            ("archetype", archetype),
            ("region", region),
            ("carrier", carrier),
            ("popularityTier", str(metrics.get("popularityTier") or "")),
            ("outputTier", str(metrics.get("outputTier") or "")),
        ):
            if value:
                counters[name][value] += 1
        tags = bundle.get("tags") or {}
        for ref in tags.get("interestTagRefs") or []:
            if str(ref).startswith("Topic/旅行"):
                topic_refs.add(str(ref))
    total = max(len(bundles), 1)
    probs = [count / total for count in buckets.values()]
    entropy = -sum(p * math.log(p, 2) for p in probs if p > 0)
    max_entropy = math.log(max(len(buckets), 1), 2) or 1.0
    normalized = entropy / max_entropy if max_entropy else 0.0
    min_fill = min(buckets.values()) / total if buckets else 0.0
    quota_fill = _quota_fill_rate(vertical, batch_id, counters)
    return {
        "entropy": round(normalized, 4),
        "rawEntropy": round(entropy, 4),
        "minBucketFillRate": round(min_fill, 4),
        "quotaFillRate": round(quota_fill, 4),
        "bucketFill": dict(buckets),
        "archetypeFill": dict(counters["archetype"]),
        "regionFill": dict(counters["region"]),
        "carrierFill": dict(counters["carrier"]),
        "popularityTierFill": dict(counters["popularityTier"]),
        "outputTierFill": dict(counters["outputTier"]),
        "topicCoverageCount": len(topic_refs),
        "quotaFillByDimension": {k: dict(v) for k, v in counters.items()},
        "bucketCount": len(buckets),
    }


def _quota_fill_rate(
    vertical: str,
    batch_id: str,
    counters: dict[str, Counter[str]],
) -> float:
    if not vertical or not batch_id:
        return 1.0 if counters.get("archetype") else 0.0
    matrix_path = creator_pool_shared_dir(vertical, batch_id) / "diversity_matrix.yaml"
    if not matrix_path.is_file():
        return 1.0 if counters.get("archetype") else 0.0
    with matrix_path.open(encoding="utf-8") as f:
        matrix = yaml.safe_load(f) or {}
    dims = matrix.get("dimensions") if isinstance(matrix, dict) else {}
    rates: list[float] = []
    if not isinstance(dims, dict):
        return 1.0
    for dim_name, counter in counters.items():
        quotas = dims.get(dim_name) or {}
        if not isinstance(quotas, dict):
            continue
        for bucket, quota in quotas.items():
            quota_i = int(quota or 0)
            if quota_i <= 0:
                continue
            actual = int(counter.get(str(bucket), 0))
            rates.append(min(actual / quota_i, 1.0))
    return min(rates) if rates else 1.0


def _tier_split(keys: tuple[str, ...], target: int, ratios: tuple[float, ...]) -> dict[str, int]:
    if len(keys) != len(ratios):
        return _even_split(keys, target)
    raw = [int(target * r) for r in ratios]
    while sum(raw) < target:
        for i in range(len(raw)):
            raw[i] += 1
            if sum(raw) >= target:
                break
    while sum(raw) > target:
        for i in range(len(raw) - 1, -1, -1):
            if raw[i] > 0:
                raw[i] -= 1
            if sum(raw) <= target:
                break
    return {key: raw[idx] for idx, key in enumerate(keys)}


def _travel_archetype_quota(target: int) -> dict[str, int]:
    """Batch-100 commercial archetype quotas (plan §5.1)."""
    if target != 100:
        return _even_split(TRAVEL_ARCHETYPES, target)
    quotas = {
        "casual_tourist": 15,
        "local_walker": 5,
        "travel_blogger": 14,
        "self_drive_expert": 14,
        "landscape_photographer": 13,
        "geo_editor": 13,
        "food_columnist": 13,
        "pro_guide": 13,
    }
    assert sum(quotas.values()) == target
    return quotas


def _even_split(keys: tuple[str, ...], target: int) -> dict[str, int]:
    if not keys:
        return {}
    base = target // len(keys)
    rem = target % len(keys)
    out: dict[str, int] = {}
    for idx, key in enumerate(keys):
        out[key] = base + (1 if idx < rem else 0)
    return out
