"""Diversity matrix planning for creator pools."""
from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from _common.creator_pool.bundle import build_creator_ref
from _common.creator_pool.batch_policy import (
    CREATOR_VERTICAL_SEGMENTS,
    expected_view_contract,
    segment_counts,
    view_counts_from_segments,
)
from _common.creator_pool.constants import (
    CARRIER_BUCKETS,
    COMMERCIAL_CARRIER_BUCKETS,
    OUTPUT_TIERS,
    PHOTOGRAPHY_ARCHETYPES,
    PHOTOGRAPHY_TOPIC_REFS,
    PLATFORM_BUCKETS,
    POPULARITY_TIERS,
    SOURCE_REGION_CLASS_RATIOS,
    TRAVEL_ARCHETYPES,
    TRAVEL_PHOTOGRAPHY_CROSS_ARCHETYPES,
    TRAVEL_REGION_BUCKETS,
    TRAVEL_TOPIC_REFS,
)
from _common.paths import creator_pool_shared_dir


def build_diversity_matrix(vertical: str, target: int, *, batch_id: str = "") -> dict[str, Any]:
    segment = segment_counts(batch_id, target)
    view_contract = expected_view_contract(batch_id, target)
    archetype = _combined_archetype_quota(segment) if target >= 100 else _even_split(TRAVEL_ARCHETYPES, target)
    region = _even_split(TRAVEL_REGION_BUCKETS, target)
    carrier = _even_split(COMMERCIAL_CARRIER_BUCKETS if target >= 100 else CARRIER_BUCKETS, target)
    platform = _even_split(PLATFORM_BUCKETS, target)
    popularity = _tier_split(POPULARITY_TIERS, target, (0.15, 0.35, 0.30, 0.20))
    output = _tier_split(OUTPUT_TIERS, target, (0.40, 0.45, 0.15))
    source_region = _tier_split(tuple(SOURCE_REGION_CLASS_RATIOS.keys()), target, tuple(SOURCE_REGION_CLASS_RATIOS.values()))
    return {
        "schemaVersion": "quwoquan_data.diversity_matrix/1",
        "vertical": vertical,
        "dimensions": {
            "verticalSegment": segment,
            "archetype": archetype,
            "region": region,
            "carrier": carrier,
            "platform": platform,
            "popularityTier": popularity,
            "outputTier": output,
            "sourceRegionClass": source_region,
        },
        "topicCoverageMin": 12 if target >= 100 else 4,
        "topicRefs": list(TRAVEL_TOPIC_REFS) + list(PHOTOGRAPHY_TOPIC_REFS),
        "minBucketFillRate": 1.0 if target >= 100 else 0.5,
        "targetEntropy": 0.85 if target >= 100 else 0.6,
        "crossSegmentRatioTarget": view_contract["crossSegmentRatio"],
        "travelViewCountTarget": view_contract["travelViewCount"],
        "photographyViewCountTarget": view_contract["photographyViewCount"],
        "viewOverlapCountTarget": view_contract["viewOverlapCount"],
        "viewOverlapRateTarget": view_contract["viewOverlapRate"],
        "singlePlatformMaxShare": 0.15,
    }


def assign_creator_slots(vertical: str, target: int, *, batch_id: str = "") -> list[dict[str, str]]:
    matrix = build_diversity_matrix(vertical, target, batch_id=batch_id)
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
        "verticalSegment": Counter(),
        "archetype": Counter(),
        "region": Counter(),
        "carrier": Counter(),
        "platform": Counter(),
        "popularityTier": Counter(),
        "outputTier": Counter(),
        "sourceRegionClass": Counter(),
    }
    topic_refs: set[str] = set()
    cross_total = 0
    cross_dual = 0
    source_profiles: Counter[str] = Counter()
    source_sites: Counter[str] = Counter()
    for bundle in bundles:
        slots = bundle.get("diversitySlots") or {}
        metrics = bundle.get("sourceMetrics") or {}
        provenance = bundle.get("provenance") or {}
        extracted = provenance.get("extractedSignals") or {}
        archetype = str(slots.get("archetypeBucket") or "")
        region = str(slots.get("regionBucket") or "")
        carrier = str(slots.get("carrierBucket") or "")
        segment = str(slots.get("verticalSegment") or "")
        platform = str(slots.get("platformBucket") or metrics.get("platformStyle") or "")
        source_region = str(slots.get("sourceRegionClass") or extracted.get("sourceRegionClass") or "")
        key = f"{segment}|{archetype}|{region}"
        buckets[key] += 1
        for name, value in (
            ("verticalSegment", segment),
            ("archetype", archetype),
            ("region", region),
            ("carrier", carrier),
            ("platform", platform),
            ("popularityTier", str(metrics.get("popularityTier") or "")),
            ("outputTier", str(metrics.get("outputTier") or "")),
            ("sourceRegionClass", source_region),
        ):
            if value:
                counters[name][value] += 1
        tags = bundle.get("tags") or {}
        tag_refs = [str(ref) for ref in tags.get("interestTagRefs") or []]
        for ref in tag_refs:
            if ref.startswith("Topic/旅行") or ref.startswith("Topic/摄影"):
                topic_refs.add(ref)
        if segment == "travel_photography_cross":
            cross_total += 1
            vertical_refs = set((bundle.get("content") or {}).get("verticalRefs") or [])
            has_travel_topic = any(ref.startswith("Topic/旅行/") for ref in tag_refs)
            has_photo_topic = any(ref.startswith("Topic/摄影/") for ref in tag_refs)
            if {"travel", "photography"}.issubset(vertical_refs) and has_travel_topic and has_photo_topic:
                cross_dual += 1
        source_profile = str(extracted.get("sourceProfileKey") or "")
        if source_profile:
            source_profiles[source_profile] += 1
        source_site = str(extracted.get("sourceSiteId") or "")
        if source_site:
            source_sites[source_site] += 1
    total = max(len(bundles), 1)
    probs = [count / total for count in buckets.values()]
    entropy = -sum(p * math.log(p, 2) for p in probs if p > 0)
    max_entropy = math.log(max(len(buckets), 1), 2) or 1.0
    normalized = entropy / max_entropy if max_entropy else 0.0
    min_fill = min(buckets.values()) / total if buckets else 0.0
    quota_fill = _quota_fill_rate(vertical, batch_id, counters)
    platform_max = max(counters["platform"].values() or [0]) / total
    source_site_max = max(source_sites.values() or [0]) / total
    source_profile_max = max(source_profiles.values() or [0])
    view_counts = view_counts_from_segments(dict(counters["verticalSegment"]))
    cross_ratio = counters["verticalSegment"]["travel_photography_cross"] / total
    china_ratio = counters["sourceRegionClass"]["china"] / total
    non_china_ratio = counters["sourceRegionClass"]["non_china"] / total
    cross_region_ratio = counters["sourceRegionClass"]["cross_region"] / total
    return {
        "entropy": round(normalized, 4),
        "rawEntropy": round(entropy, 4),
        "minBucketFillRate": round(min_fill, 4),
        "quotaFillRate": round(quota_fill, 4),
        "bucketFill": dict(buckets),
        "archetypeFill": dict(counters["archetype"]),
        "regionFill": dict(counters["region"]),
        "carrierFill": dict(counters["carrier"]),
        "platformFill": dict(counters["platform"]),
        "popularityTierFill": dict(counters["popularityTier"]),
        "outputTierFill": dict(counters["outputTier"]),
        "verticalSegmentFill": dict(counters["verticalSegment"]),
        "sourceRegionClassFill": dict(counters["sourceRegionClass"]),
        "sourceSiteFill": dict(source_sites),
        "topicCoverageCount": len(topic_refs),
        "quotaFillByDimension": {k: dict(v) for k, v in counters.items()},
        "bucketCount": len(buckets),
        "crossSegmentRatio": round(cross_ratio, 4),
        "crossDualTagCoverageRate": round(cross_dual / max(cross_total, 1), 4) if cross_total else 0.0,
        "travelViewCount": int(view_counts["travelViewCount"]),
        "photographyViewCount": int(view_counts["photographyViewCount"]),
        "viewOverlapCount": int(view_counts["viewOverlapCount"]),
        "viewOverlapRate": float(view_counts["viewOverlapRate"]),
        "platformMaxShare": round(platform_max, 4),
        "sourceSiteMaxShare": round(source_site_max, 4),
        "sourceProfileMaxCount": source_profile_max,
        "chinaSourceRatio": round(china_ratio, 4),
        "nonChinaSourceRatio": round(non_china_ratio, 4),
        "crossRegionSourceRatio": round(cross_region_ratio, 4),
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
def _combined_archetype_quota(segment_quota: dict[str, int]) -> dict[str, int]:
    out: dict[str, int] = {}
    out.update(_even_split(TRAVEL_ARCHETYPES, int(segment_quota.get("travel_primary") or 0)))
    out.update(_even_split(PHOTOGRAPHY_ARCHETYPES, int(segment_quota.get("photography_primary") or 0)))
    out.update(
        _even_split(
            TRAVEL_PHOTOGRAPHY_CROSS_ARCHETYPES,
            int(segment_quota.get("travel_photography_cross") or 0),
        )
    )
    return out


def _even_split(keys: tuple[str, ...], target: int) -> dict[str, int]:
    if not keys:
        return {}
    base = target // len(keys)
    rem = target % len(keys)
    out: dict[str, int] = {}
    for idx, key in enumerate(keys):
        out[key] = base + (1 if idx < rem else 0)
    return out
