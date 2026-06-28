"""Creator pool score stage."""
from __future__ import annotations

from typing import Any

from _common.creator_pool.candidate_pool import composite_score, is_live_batch, tier_for_score as _tier_for_score
from _common.creator_pool.io import (
    iter_candidates,
    iter_creator_refs,
    stage_gate_path,
    write_gate,
    write_stage_result,
)
from _common.io import read_json, write_json
from _common.paths import creator_pool_shared_dir, creator_pool_stage_dir


def run_score(*, vertical: str, batch_id: str, dry_run: bool = False) -> dict[str, Any]:
    plan_path = creator_pool_shared_dir(vertical, batch_id) / "creator_pool_plan.json"
    plan = read_json(plan_path) if plan_path.is_file() else {}
    live_mode = bool(plan.get("liveMode")) or is_live_batch(batch_id, plan)
    scored = 0
    if live_mode:
        ranked: list[tuple[float, dict[str, Any]]] = []
        for idx, cand in enumerate(iter_candidates(vertical, batch_id)):
            signals = cand.get("signals") or {}
            composite = composite_score(cand)
            pop, out = _tier_for_score(composite, idx, len(iter_candidates(vertical, batch_id)))
            stage_dir = creator_pool_shared_dir(vertical, batch_id) / "candidates" / str(cand["candidateRef"]).replace("/", "_")
            stage_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "compositeScore": round(composite, 4),
                "engagementScore": float(signals.get("avgEngagement") or 0.05),
                "outputScore": min(1.0, float(signals.get("postsPerMonth") or 5) / 20.0),
                "popularityTier": pop,
                "outputTier": out,
            }
            write_json(stage_dir / "score.json", payload)
            ranked.append((composite, {**cand, **payload}))
            scored += 1
        ranked.sort(key=lambda item: item[0], reverse=True)
        write_json(
            creator_pool_shared_dir(vertical, batch_id) / "candidate_rankings.json",
            {"rankedCount": len(ranked), "topScore": ranked[0][0] if ranked else 0.0},
        )
        return {"scored": scored, "mode": "live_candidate_pool", "dryRun": dry_run}

    for idx, creator_ref in enumerate(iter_creator_refs(vertical, batch_id)):
        acquire = creator_pool_stage_dir(vertical, batch_id, creator_ref, "1.acquire") / "source_profile.json"
        signals = {}
        if acquire.is_file():
            data = read_json(acquire)
            signals = (data.get("signals") if isinstance(data, dict) else {}) or {}
        engagement = min(0.99, 0.55 + (idx % 5) * 0.08)
        output = min(0.99, 0.6 + (signals.get("postsPerMonth", 5) / 20))
        tier = "head" if engagement > 0.85 else "waist" if engagement > 0.7 else "rising"
        stage_dir = creator_pool_stage_dir(vertical, batch_id, creator_ref, "2.score")
        stage_dir.mkdir(parents=True, exist_ok=True)
        write_json(stage_dir / "engagement_metrics.json", {"score": engagement, "normalized": engagement})
        write_json(stage_dir / "output_metrics.json", {"score": output, "postsPerMonth": signals.get("postsPerMonth", 6)})
        write_json(stage_dir / "popularity_tier.json", {"tier": tier})
        write_gate(stage_gate_path(vertical, batch_id, creator_ref, "2.score", "score_gate.json"), gate_id="score", passed=True)
        write_stage_result(vertical, batch_id, creator_ref, "2.score", {"status": "ok", "tier": tier})
        scored += 1
    return {"scored": scored, "dryRun": dry_run}
