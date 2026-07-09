"""Candidate pool generation for live creator batches."""
from __future__ import annotations

import hashlib
from typing import Any

from _common.creator_pool.constants import (
    CARRIER_BUCKETS,
    COMMERCIAL_CARRIER_BUCKETS,
    PHOTOGRAPHY_ARCHETYPES,
    PHOTOGRAPHY_TOPIC_REFS,
    PLATFORM_BUCKETS,
    SOURCE_REGION_CLASS_RATIOS,
    TRAVEL_ARCHETYPES,
    TRAVEL_PHOTOGRAPHY_CROSS_ARCHETYPES,
    TRAVEL_REGION_BUCKETS,
    TRAVEL_TOPIC_REFS,
)
from _common.creator_pool.batch_policy import CREATOR_VERTICAL_SEGMENTS, segment_cycle_counts
from _common.creator_pool.source_registry import sites_for_segment


def candidate_ref(*, vertical: str, seq: int) -> str:
    return f"candidate/{vertical}/{seq:04d}"


def build_candidate_pool(
    *,
    vertical: str,
    pool_size: int,
    batch_id: str = "",
    target: int = 100,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    segment_cycle = segment_cycle_counts(batch_id, target)
    for idx in range(pool_size):
        seq = idx + 1
        segment = _segment_for_index(idx, segment_cycle)
        region_class = _source_region_class_for_index(idx)
        archetype = _archetype_for_segment(segment, idx)
        region = TRAVEL_REGION_BUCKETS[idx % len(TRAVEL_REGION_BUCKETS)]
        carrier = _carrier_for_segment(segment, idx)
        platform = PLATFORM_BUCKETS[idx % len(PLATFORM_BUCKETS)]
        site = _source_site_for(segment, region_class, idx)
        domains = [str(domain) for domain in site.get("domains") or [] if str(domain).strip()]
        domain = domains[0]
        handle = f"signal_{archetype}_{seq:04d}"
        digest = hashlib.sha256(f"{vertical}:{seq}:{segment}:{archetype}:{site.get('siteId')}".encode()).hexdigest()[:12]
        vertical_refs = _vertical_refs_for_segment(segment)
        topic_refs = _topic_refs_for_segment(segment, idx)
        candidates.append(
            {
                "candidateRef": candidate_ref(vertical=vertical, seq=seq),
                "verticalSegment": segment,
                "verticalRefs": vertical_refs,
                "topicRefs": topic_refs,
                "archetype": archetype,
                "regionBucket": region,
                "carrierBucket": carrier,
                "platformBucket": platform,
                "sourceSiteId": site.get("siteId"),
                "sourceDisplayName": site.get("displayName"),
                "sourceKind": site.get("sourceKind") or "open_web_profile",
                "sourceUrl": site.get("homepageUrl"),
                "sourceDomain": domain,
                "sourceProfileKey": f"{site.get('siteId')}:public_signal:{seq:04d}",
                "chinaAnalogLabel": site.get("chinaAnalogLabel"),
                "candidateRole": site.get("candidateRole"),
                "crawlAllowed": bool(site.get("crawlAllowed")),
                "validationOnly": bool(site.get("validationOnly")),
                "rightsPolicy": site.get("rightsPolicy"),
                "sourceRegionClass": site.get("regionClass") or region_class,
                "signals": {
                    "followers": 5000 + (idx * 137) % 500000,
                    "postsPerMonth": 2 + (idx * 3) % 28,
                    "avgEngagement": round(0.02 + (idx % 17) * 0.004, 4),
                    "likes": 1000 + idx * 41,
                    "shares": 50 + idx * 7,
                    "saves": 80 + idx * 11,
                    "comments": 30 + idx * 5,
                    "topics": topic_refs,
                    "carrierPreference": carrier,
                    "publicSignalOnly": True,
                },
                "signalDigest": digest,
            }
        )
    return candidates


def tier_for_score(score: float, idx: int, total: int) -> tuple[str, str]:
    rank = idx / max(total, 1)
    if rank < 0.15:
        pop = "head"
    elif rank < 0.50:
        pop = "waist"
    elif rank < 0.80:
        pop = "rising"
    else:
        pop = "niche_expert"
    if score >= 0.75:
        out = "prolific"
    elif score >= 0.55:
        out = "steady"
    else:
        out = "seasonal"
    return pop, out


def composite_score(candidate: dict[str, Any]) -> float:
    signals = candidate.get("signals") or {}
    engagement = float(signals.get("avgEngagement") or 0.05)
    output = min(1.0, float(signals.get("postsPerMonth") or 5) / 20.0)
    followers = float(signals.get("followers") or 1000)
    reach = min(1.0, followers / 200000.0)
    return engagement * 0.45 + output * 0.35 + reach * 0.20


LIVE_BATCH_IDS: frozenset[str] = frozenset(
    {
        "travel_photo_1k_v1",
    }
)


def is_live_batch(batch_id: str, plan: dict[str, Any] | None = None) -> bool:
    if plan and plan.get("liveMode") is True:
        return True
    if batch_id in LIVE_BATCH_IDS:
        return True
    return batch_id.endswith("_live") or "_1k_" in batch_id or batch_id.startswith("travel_photo_")


def _segment_for_index(idx: int, cycle_counts: dict[str, int]) -> str:
    cycle_size = sum(int(value or 0) for value in cycle_counts.values()) or 1
    offset = idx % cycle_size
    cursor = 0
    for segment in CREATOR_VERTICAL_SEGMENTS:
        cursor += int(cycle_counts.get(segment) or 0)
        if offset < cursor:
            return segment
    return "travel_photography_cross"


def _source_region_class_for_index(idx: int) -> str:
    offset = (idx * 37) % 100
    cursor = 0
    for name, ratio in SOURCE_REGION_CLASS_RATIOS.items():
        cursor += int(ratio * 100)
        if offset < cursor:
            return name
    return "cross_region"


def _source_site_for(segment: str, region_class: str, idx: int) -> dict[str, Any]:
    sites = sites_for_segment(segment, region_class=region_class) or sites_for_segment(segment)
    if not sites:
        raise RuntimeError(f"no creator source registry sites for segment={segment} regionClass={region_class}")
    return sites[idx % len(sites)]


def _archetype_for_segment(segment: str, idx: int) -> str:
    if segment == "travel_primary":
        return TRAVEL_ARCHETYPES[idx % len(TRAVEL_ARCHETYPES)]
    if segment == "photography_primary":
        return PHOTOGRAPHY_ARCHETYPES[idx % len(PHOTOGRAPHY_ARCHETYPES)]
    return TRAVEL_PHOTOGRAPHY_CROSS_ARCHETYPES[idx % len(TRAVEL_PHOTOGRAPHY_CROSS_ARCHETYPES)]


def _vertical_refs_for_segment(segment: str) -> list[str]:
    if segment == "travel_primary":
        return ["travel"]
    if segment == "photography_primary":
        return ["photography"]
    return ["travel", "photography"]


def _topic_refs_for_segment(segment: str, idx: int) -> list[str]:
    travel_topic = TRAVEL_TOPIC_REFS[idx % len(TRAVEL_TOPIC_REFS)]
    photo_topic = PHOTOGRAPHY_TOPIC_REFS[idx % len(PHOTOGRAPHY_TOPIC_REFS)]
    if segment == "travel_primary":
        refs = [travel_topic]
        if idx % 4 == 0:
            refs.append("Topic/摄影/旅行摄影")
        return refs
    if segment == "photography_primary":
        refs = [photo_topic]
        if idx % 4 == 0:
            refs.append("Topic/旅行/玩法/摄影旅拍")
        return refs
    return [travel_topic, photo_topic]


def _carrier_for_segment(segment: str, idx: int) -> str:
    if segment == "travel_primary":
        return COMMERCIAL_CARRIER_BUCKETS[idx % len(COMMERCIAL_CARRIER_BUCKETS)]
    if segment == "photography_primary":
        return ("image", "mixed", "image", "article")[idx % 4]
    return ("image", "mixed", "image", "mixed", "article")[idx % 5]
