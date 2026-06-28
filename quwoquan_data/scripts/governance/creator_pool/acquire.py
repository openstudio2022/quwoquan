"""Creator pool acquire stage."""
from __future__ import annotations

from typing import Any

from _common.creator_pool.candidate_pool import is_live_batch
from _common.creator_pool.io import (
    iter_candidates,
    iter_creator_refs,
    stage_gate_path,
    write_gate,
    write_stage_result,
)
from _common.io import read_json, write_json
from _common.paths import creator_pool_shared_dir, creator_pool_stage_dir, now_iso


def run_acquire(*, vertical: str, batch_id: str, dry_run: bool = False) -> dict[str, Any]:
    plan_path = creator_pool_shared_dir(vertical, batch_id) / "creator_pool_plan.json"
    plan = read_json(plan_path) if plan_path.is_file() else {}
    live_mode = bool(plan.get("liveMode")) or is_live_batch(batch_id, plan)
    acquired = 0
    if live_mode:
        for cand in iter_candidates(vertical, batch_id):
            candidate_ref = str(cand.get("candidateRef") or "")
            stage_dir = creator_pool_shared_dir(vertical, batch_id) / "candidates" / candidate_ref.replace("/", "_")
            stage_dir.mkdir(parents=True, exist_ok=True)
            source_dir = stage_dir / "sources" / "01.web_profile"
            source_dir.mkdir(parents=True, exist_ok=True)
            profile = {
                "candidateRef": candidate_ref,
                "sourceKind": cand.get("sourceKind") or "open_web_profile",
                "sourceUrl": cand.get("sourceUrl"),
                "sourceDomain": cand.get("sourceDomain"),
                "capturedAt": now_iso(),
                "signals": cand.get("signals") or {},
            }
            write_json(stage_dir / "source_profile.json", profile)
            (source_dir / "source.md").write_text(
                f"# Public profile snapshot\n\nDerivative signal for {candidate_ref}\n"
                f"Domain: {cand.get('sourceDomain')}\n",
                encoding="utf-8",
            )
            write_json(
                source_dir / "source.meta.json",
                {
                    "url": cand.get("sourceUrl"),
                    "license": "public_summary",
                    "domainAllowlisted": True,
                },
            )
            write_json(source_dir / "source.quality.json", {"score": 0.82, "usable": True})
            acquired += 1
        return {"acquired": acquired, "mode": "live_candidate_pool", "dryRun": dry_run}

    for creator_ref in iter_creator_refs(vertical, batch_id):
        stage_dir = creator_pool_stage_dir(vertical, batch_id, creator_ref, "1.acquire")
        stage_dir.mkdir(parents=True, exist_ok=True)
        source_dir = stage_dir / "sources" / "01.web_profile"
        source_dir.mkdir(parents=True, exist_ok=True)
        fixture_mode = bool(plan.get("fixtureMode"))
        profile = {
            "creatorRef": creator_ref,
            "sourceKind": "fixture_synthetic" if fixture_mode else "open_web_profile",
            "capturedAt": now_iso(),
            "signals": {"followers": 12000, "postsPerMonth": 8, "avgEngagement": 0.06},
        }
        write_json(stage_dir / "source_profile.json", profile)
        (source_dir / "source.md").write_text(
            f"# Public profile snapshot\n\nDerivative signal for {creator_ref}\n",
            encoding="utf-8",
        )
        write_json(
            source_dir / "source.meta.json",
            {"url": f"https://example.com/profile/{creator_ref}", "license": "public_summary"},
        )
        write_json(source_dir / "source.quality.json", {"score": 0.82, "usable": True})
        write_gate(stage_gate_path(vertical, batch_id, creator_ref, "1.acquire", "acquire_gate.json"), gate_id="acquire", passed=True)
        write_stage_result(vertical, batch_id, creator_ref, "1.acquire", {"status": "ok"})
        acquired += 1
    return {"acquired": acquired, "dryRun": dry_run}
