"""Candidate pool generation for live creator batches."""
from __future__ import annotations

import hashlib
from typing import Any

from _common.creator_pool.constants import (
    ACQUIRE_ALLOWLIST_DOMAINS,
    TRAVEL_ARCHETYPES,
    TRAVEL_REGION_BUCKETS,
    CARRIER_BUCKETS,
    PLATFORM_BUCKETS,
)


def candidate_ref(*, vertical: str, seq: int) -> str:
    return f"candidate/{vertical}/{seq:04d}"


def build_candidate_pool(*, vertical: str, pool_size: int) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for idx in range(pool_size):
        seq = idx + 1
        archetype = TRAVEL_ARCHETYPES[idx % len(TRAVEL_ARCHETYPES)]
        region = TRAVEL_REGION_BUCKETS[idx % len(TRAVEL_REGION_BUCKETS)]
        carrier = CARRIER_BUCKETS[idx % len(CARRIER_BUCKETS)]
        platform = PLATFORM_BUCKETS[idx % len(PLATFORM_BUCKETS)]
        domain = ACQUIRE_ALLOWLIST_DOMAINS[idx % len(ACQUIRE_ALLOWLIST_DOMAINS)]
        handle = f"signal_{archetype}_{seq:04d}"
        digest = hashlib.sha256(f"{vertical}:{seq}:{archetype}".encode()).hexdigest()[:12]
        candidates.append(
            {
                "candidateRef": candidate_ref(vertical=vertical, seq=seq),
                "archetype": archetype,
                "regionBucket": region,
                "carrierBucket": carrier,
                "platformBucket": platform,
                "sourceKind": "open_web_profile",
                "sourceUrl": f"https://{domain}/authors/{handle}",
                "sourceDomain": domain,
                "signals": {
                    "followers": 5000 + (idx * 137) % 500000,
                    "postsPerMonth": 2 + (idx * 3) % 28,
                    "avgEngagement": round(0.02 + (idx % 17) * 0.004, 4),
                    "likes": 1000 + idx * 41,
                    "shares": 50 + idx * 7,
                    "saves": 80 + idx * 11,
                    "comments": 30 + idx * 5,
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
        pop = "niche"
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
        "travel_batch_100_v1",
    }
)


def is_live_batch(batch_id: str, plan: dict[str, Any] | None = None) -> bool:
    if plan and plan.get("liveMode") is True:
        return True
    if batch_id in LIVE_BATCH_IDS:
        return True
    return batch_id.endswith("_live")
