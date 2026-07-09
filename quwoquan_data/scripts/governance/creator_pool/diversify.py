"""Select final creator cohort from scored candidate pool."""
from __future__ import annotations

from collections import Counter
from typing import Any

from _common.creator_pool.bundle import build_creator_ref
from _common.creator_pool.constants import (
    PHOTOGRAPHY_ARCHETYPES,
    TRAVEL_ARCHETYPES,
    TRAVEL_PHOTOGRAPHY_CROSS_ARCHETYPES,
)
from _common.creator_pool.diversity import build_diversity_matrix
from _common.creator_pool.io import iter_candidates, write_stage_result
from _common.io import read_json, write_json
from _common.paths import creator_pool_shared_dir, now_iso


from _common.creator_pool.candidate_pool import composite_score


def run_diversify(*, vertical: str, batch_id: str, dry_run: bool = False) -> dict[str, Any]:
    shared = creator_pool_shared_dir(vertical, batch_id)
    plan = read_json(shared / "creator_pool_plan.json")
    target = int(plan.get("targetCount") or 100)
    matrix = build_diversity_matrix(vertical, target, batch_id=batch_id)
    candidates = iter_candidates(vertical, batch_id)
    scored: list[dict[str, Any]] = []
    for cand in candidates:
        score_path = shared / "candidates" / str(cand["candidateRef"]).replace("/", "_") / "score.json"
        extra = read_json(score_path) if score_path.is_file() else {}
        composite = float(extra.get("compositeScore") or composite_score(cand))
        scored.append({**cand, **extra, "compositeScore": composite})
    scored.sort(key=lambda item: float(item.get("compositeScore") or 0), reverse=True)

    picked: list[dict[str, Any]] = []
    picked_refs: set[str] = set()
    segment_quota = matrix["dimensions"].get("verticalSegment") or {}
    region_quota = matrix["dimensions"]["region"]
    carrier_quota = matrix["dimensions"].get("carrier") or {}
    platform_quota = matrix["dimensions"].get("platform") or {}
    pop_quota = matrix["dimensions"].get("popularityTier") or {}
    out_quota = matrix["dimensions"].get("outputTier") or {}
    source_region_quota = matrix["dimensions"].get("sourceRegionClass") or {}

    segment_sequence = _expand_quota(segment_quota, target)
    source_region_sequence = _expand_quota(source_region_quota, target)

    def _pick_one(segment: str | None = None, source_region: str | None = None) -> dict[str, Any] | None:
        for cand in scored:
            ref = str(cand.get("candidateRef") or "")
            if ref in picked_refs:
                continue
            if segment and str(cand.get("verticalSegment") or "") != segment:
                continue
            if source_region and str(cand.get("sourceRegionClass") or "") != source_region:
                continue
            picked_refs.add(ref)
            return dict(cand)
        return None

    for idx in range(target):
        segment = segment_sequence[idx] if idx < len(segment_sequence) else ""
        source_region = source_region_sequence[idx] if idx < len(source_region_sequence) else ""
        cand = (
            _pick_one(segment=segment, source_region=source_region)
            or _pick_one(segment=segment)
            or _pick_one(source_region=source_region)
            or _pick_one()
        )
        if cand:
            picked.append(cand)

    for cand in scored:
        if len(picked) >= target:
            break
        ref = str(cand.get("candidateRef") or "")
        if ref in picked_refs:
            continue
        picked.append(dict(cand))
        picked_refs.add(ref)

    picked = picked[:target]
    picked = _assign_segment_archetypes(picked)
    picked = _assign_quota_buckets(picked, region_quota, "regionBucket")
    picked = _assign_quota_buckets(picked, carrier_quota, "carrierBucket")
    picked = _assign_quota_buckets(picked, platform_quota, "platformBucket")
    picked = _assign_quota_buckets(picked, pop_quota, "popularityTier")
    picked = _assign_quota_buckets(picked, out_quota, "outputTier")
    counts = _count_picked(picked)

    creator_refs: list[str] = []
    objects: list[dict[str, Any]] = []
    for idx, sel in enumerate(picked[:target], start=1):
        ref = build_creator_ref(
            vertical=vertical,
            archetype=str(sel.get("archetype") or "travel_blogger"),
            region=str(sel.get("regionBucket") or "西南"),
            seq=idx,
        )
        creator_refs.append(ref)
        objects.append(
            {
                "creatorRef": ref,
                "candidateRef": sel.get("candidateRef"),
                "stage": "selected",
                "verticalSegment": sel.get("verticalSegment"),
                "verticalRefs": sel.get("verticalRefs") or [],
                "topicRefs": sel.get("topicRefs") or [],
                "archetype": sel.get("archetype"),
                "regionBucket": sel.get("regionBucket"),
                "carrierBucket": sel.get("carrierBucket"),
                "platformBucket": sel.get("platformBucket"),
                "popularityTier": sel.get("popularityTier"),
                "outputTier": sel.get("outputTier"),
                "compositeScore": sel.get("compositeScore"),
                "sourceSiteId": sel.get("sourceSiteId"),
                "sourceDisplayName": sel.get("sourceDisplayName"),
                "sourceKind": sel.get("sourceKind"),
                "sourceUrl": sel.get("sourceUrl"),
                "sourceDomain": sel.get("sourceDomain"),
                "sourceProfileKey": sel.get("sourceProfileKey"),
                "sourceRegionClass": sel.get("sourceRegionClass"),
                "chinaAnalogLabel": sel.get("chinaAnalogLabel"),
                "candidateRole": sel.get("candidateRole"),
                "crawlAllowed": sel.get("crawlAllowed"),
                "validationOnly": sel.get("validationOnly"),
                "rightsPolicy": sel.get("rightsPolicy"),
            }
        )
        write_stage_result(
            vertical,
            batch_id,
            ref,
            "2.score",
            {
                "status": "selected",
                "candidateRef": sel.get("candidateRef"),
                "verticalSegment": sel.get("verticalSegment"),
                "popularityTier": sel.get("popularityTier"),
                "outputTier": sel.get("outputTier"),
            },
            filename="diversify_selection.json",
        )

    plan["creatorRefs"] = creator_refs
    plan["diversifiedAt"] = now_iso()
    write_json(shared / "creator_pool_plan.json", plan)
    write_json(
        shared / "creator_object_index.json",
        {"schemaVersion": "quwoquan_data.creator_object_index/1", "batchId": batch_id, "objects": objects},
    )
    write_json(
        shared / "diversify_report.json",
        {
            "selectedCount": len(creator_refs),
            "candidatePoolSize": len(candidates),
            "quotaFillByDimension": {k: dict(v) for k, v in counts.items()},
            "generatedAt": now_iso(),
        },
    )
    return {"selected": len(creator_refs), "candidatePoolSize": len(candidates), "dryRun": dry_run}


def _assign_quota_buckets(
    picked: list[dict[str, Any]],
    quota: dict[str, int],
    field: str,
) -> list[dict[str, Any]]:
    if not picked or not quota:
        return picked
    expanded: list[str] = []
    for bucket, count in quota.items():
        expanded.extend([str(bucket)] * int(count or 0))
    while len(expanded) < len(picked):
        expanded.extend(list(quota.keys()))
    for idx, item in enumerate(picked):
        item[field] = expanded[idx % len(expanded)]
    return picked


def _assign_segment_archetypes(picked: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_segment: dict[str, list[int]] = {}
    for idx, item in enumerate(picked):
        by_segment.setdefault(str(item.get("verticalSegment") or "travel_primary"), []).append(idx)
    archetypes_by_segment = {
        "travel_primary": TRAVEL_ARCHETYPES,
        "photography_primary": PHOTOGRAPHY_ARCHETYPES,
        "travel_photography_cross": TRAVEL_PHOTOGRAPHY_CROSS_ARCHETYPES,
    }
    for segment, indices in by_segment.items():
        archetypes = archetypes_by_segment.get(segment, TRAVEL_ARCHETYPES)
        expanded = _expand_even(archetypes, len(indices))
        for pos, item_idx in enumerate(indices):
            picked[item_idx]["archetype"] = expanded[pos]
    return picked


def _expand_quota(quota: dict[str, int], target: int) -> list[str]:
    expanded: list[str] = []
    for bucket, count in quota.items():
        expanded.extend([str(bucket)] * int(count or 0))
    while len(expanded) < target and quota:
        expanded.extend(str(bucket) for bucket in quota)
    return expanded[:target]


def _expand_even(keys: tuple[str, ...], target: int) -> list[str]:
    if not keys:
        return []
    expanded: list[str] = []
    base = target // len(keys)
    rem = target % len(keys)
    for idx, key in enumerate(keys):
        expanded.extend([key] * (base + (1 if idx < rem else 0)))
    return expanded[:target]


def _count_picked(picked: list[dict[str, Any]]) -> dict[str, Counter[str]]:
    counts: dict[str, Counter[str]] = {
        "verticalSegment": Counter(),
        "archetype": Counter(),
        "region": Counter(),
        "carrier": Counter(),
        "platform": Counter(),
        "popularityTier": Counter(),
        "outputTier": Counter(),
        "sourceRegionClass": Counter(),
    }
    for cand in picked:
        counts["verticalSegment"][str(cand.get("verticalSegment") or "")] += 1
        counts["archetype"][str(cand.get("archetype") or "")] += 1
        counts["region"][str(cand.get("regionBucket") or "")] += 1
        counts["carrier"][str(cand.get("carrierBucket") or "")] += 1
        counts["platform"][str(cand.get("platformBucket") or "")] += 1
        counts["popularityTier"][str(cand.get("popularityTier") or "rising")] += 1
        counts["outputTier"][str(cand.get("outputTier") or "steady")] += 1
        counts["sourceRegionClass"][str(cand.get("sourceRegionClass") or "")] += 1
    for counter in counts.values():
        counter.pop("", None)
    return counts
