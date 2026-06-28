"""Select final creator cohort from scored candidate pool."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from _common.creator_pool.bundle import build_creator_ref
from _common.creator_pool.constants import COMMERCIAL_CARRIER_BUCKETS
from _common.creator_pool.diversity import build_diversity_matrix
from _common.creator_pool.io import iter_candidates, write_stage_result
from _common.io import read_json, write_json
from _common.paths import creator_pool_shared_dir, now_iso


from _common.creator_pool.candidate_pool import composite_score


def run_diversify(*, vertical: str, batch_id: str, dry_run: bool = False) -> dict[str, Any]:
    shared = creator_pool_shared_dir(vertical, batch_id)
    plan = read_json(shared / "creator_pool_plan.json")
    target = int(plan.get("targetCount") or 100)
    matrix = build_diversity_matrix(vertical, target)
    candidates = iter_candidates(vertical, batch_id)
    scored: list[dict[str, Any]] = []
    for cand in candidates:
        score_path = shared / "candidates" / str(cand["candidateRef"]).replace("/", "_") / "score.json"
        extra = read_json(score_path) if score_path.is_file() else {}
        composite = float(extra.get("compositeScore") or composite_score(cand))
        scored.append({**cand, **extra, "compositeScore": composite})
    scored.sort(key=lambda item: float(item.get("compositeScore") or 0), reverse=True)

    by_archetype: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_region: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cand in scored:
        by_archetype[str(cand.get("archetype") or "")].append(cand)
        by_region[str(cand.get("regionBucket") or "")].append(cand)

    picked: list[dict[str, Any]] = []
    picked_refs: set[str] = set()
    archetype_quota = matrix["dimensions"]["archetype"]
    region_quota = matrix["dimensions"]["region"]
    carrier_quota = matrix["dimensions"].get("carrier") or {}
    pop_quota = matrix["dimensions"].get("popularityTier") or {}
    out_quota = matrix["dimensions"].get("outputTier") or {}
    counts: dict[str, Counter[str]] = {
        "archetype": Counter(),
        "region": Counter(),
        "carrier": Counter(),
        "popularityTier": Counter(),
        "outputTier": Counter(),
    }

    def _pick_from(pool: list[dict[str, Any]], bucket: str, dim: str, quota: dict[str, int]) -> None:
        nonlocal picked
        need = int(quota.get(bucket) or 0) - counts[dim][bucket]
        for cand in pool:
            if need <= 0:
                break
            ref = str(cand.get("candidateRef") or "")
            if ref in picked_refs:
                continue
            carrier = COMMERCIAL_CARRIER_BUCKETS[len(picked) % len(COMMERCIAL_CARRIER_BUCKETS)]
            picked.append({**cand, "carrierBucket": carrier})
            picked_refs.add(ref)
            counts["archetype"][str(cand.get("archetype") or "")] += 1
            counts["region"][str(cand.get("regionBucket") or "")] += 1
            counts["carrier"][carrier] += 1
            counts["popularityTier"][str(cand.get("popularityTier") or "rising")] += 1
            counts["outputTier"][str(cand.get("outputTier") or "steady")] += 1
            need -= 1

    for arch, quota in archetype_quota.items():
        _pick_from(by_archetype.get(str(arch), []), str(arch), "archetype", {str(arch): int(quota)})

    for region, quota in region_quota.items():
        remaining = int(quota) - counts["region"][str(region)]
        if remaining > 0:
            _pick_from(by_region.get(str(region), []), str(region), "region", {str(region): int(quota)})

    for cand in scored:
        if len(picked) >= target:
            break
        ref = str(cand.get("candidateRef") or "")
        if ref in picked_refs:
            continue
        carrier = COMMERCIAL_CARRIER_BUCKETS[len(picked) % len(COMMERCIAL_CARRIER_BUCKETS)]
        picked.append({**cand, "carrierBucket": carrier})
        picked_refs.add(ref)
        counts["archetype"][str(cand.get("archetype") or "")] += 1
        counts["region"][str(cand.get("regionBucket") or "")] += 1
        counts["carrier"][carrier] += 1
        counts["popularityTier"][str(cand.get("popularityTier") or "rising")] += 1
        counts["outputTier"][str(cand.get("outputTier") or "steady")] += 1

    picked = picked[:target]
    picked = _assign_quota_buckets(picked, region_quota, "regionBucket")
    picked = _assign_quota_buckets(picked, carrier_quota, "carrierBucket")
    picked = _assign_quota_buckets(picked, pop_quota, "popularityTier")
    picked = _assign_quota_buckets(picked, out_quota, "outputTier")

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
                "archetype": sel.get("archetype"),
                "regionBucket": sel.get("regionBucket"),
                "carrierBucket": sel.get("carrierBucket"),
                "popularityTier": sel.get("popularityTier"),
                "outputTier": sel.get("outputTier"),
                "compositeScore": sel.get("compositeScore"),
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
