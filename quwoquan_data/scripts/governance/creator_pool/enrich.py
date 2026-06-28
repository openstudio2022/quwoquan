"""Creator pool enrich stage (Agent semantic with structured artifacts)."""
from __future__ import annotations

import hashlib
from typing import Any

from _common.creator_pool.io import (
    iter_creator_refs,
    stage_gate_path,
    write_gate,
    write_stage_result,
)
from _common.io import read_json, write_json
from _common.paths import creator_pool_shared_dir, creator_pool_stage_dir, now_iso


def _candidate_source_paths(vertical: str, batch_id: str, creator_ref: str) -> list[str]:
    index_path = creator_pool_shared_dir(vertical, batch_id) / "creator_object_index.json"
    index = read_json(index_path) if index_path.is_file() else {}
    candidate_ref = ""
    for obj in index.get("objects") or []:
        if isinstance(obj, dict) and obj.get("creatorRef") == creator_ref:
            candidate_ref = str(obj.get("candidateRef") or "")
            break
    if not candidate_ref:
        acquire_dir = creator_pool_stage_dir(vertical, batch_id, creator_ref, "1.acquire")
        return [str(acquire_dir / "sources" / "01.web_profile" / "source.md")]
    cand_dir = creator_pool_shared_dir(vertical, batch_id) / "candidates" / candidate_ref.replace("/", "_")
    return [
        str(cand_dir / "sources" / "01.web_profile" / "source.md"),
        str(cand_dir / "sources" / "01.web_profile" / "source.meta.json"),
    ]


def run_enrich(*, vertical: str, batch_id: str, dry_run: bool = False) -> dict[str, Any]:
    plan_path = creator_pool_shared_dir(vertical, batch_id) / "creator_pool_plan.json"
    plan = read_json(plan_path) if plan_path.is_file() else {}
    fixture_mode = bool(plan.get("fixtureMode")) if isinstance(plan, dict) else False
    live_mode = bool(plan.get("liveMode"))
    enriched = 0
    for creator_ref in iter_creator_refs(vertical, batch_id):
        parts = creator_ref.split("/")
        archetype = parts[2] if len(parts) > 2 else "travel_blogger"
        region = parts[3] if len(parts) > 3 else "西南"
        seq = parts[4] if len(parts) > 4 else "001"
        display = _display_name(archetype, region, seq)
        handle = f"travel_{archetype}_{seq}"
        persona = {
            "displayName": display,
            "userHandle": handle,
            "headline": f"{region}旅行{archetype}视角",
            "bio": f"专注{region}旅行内容，风格参考公开高互动作者信号，输出衍生 persona。",
            "archetype": archetype,
            "regionBucket": region,
        }
        stage_dir = creator_pool_stage_dir(vertical, batch_id, creator_ref, "3.enrich")
        stage_dir.mkdir(parents=True, exist_ok=True)
        cited = _candidate_source_paths(vertical, batch_id, creator_ref)
        prompt = f"Enrich derivative persona for {creator_ref} using public signals only."
        (stage_dir / "enrich_prompt.md").write_text(prompt, encoding="utf-8")
        digest = hashlib.sha256(prompt.encode()).hexdigest()
        write_json(stage_dir / "persona_draft.json", persona)
        write_json(
            stage_dir / "enrich_meta.json",
            {
                "generator": "agent",
                "fixtureMode": fixture_mode,
                "liveMode": live_mode,
                "promptHash": digest,
                "citedSourcePaths": cited,
                "generatedAt": now_iso(),
            },
        )
        write_gate(stage_gate_path(vertical, batch_id, creator_ref, "3.enrich", "enrich_gate.json"), gate_id="enrich", passed=True)
        write_stage_result(vertical, batch_id, creator_ref, "3.enrich", {"status": "ok"})
        enriched += 1
    return {"enriched": enriched, "dryRun": dry_run}


def _display_name(archetype: str, region: str, seq: str) -> str:
    mapping = {
        "travel_blogger": "旅人",
        "self_drive_expert": "自驾客",
        "landscape_photographer": "光影客",
        "geo_editor": "地理志",
        "food_columnist": "食旅记",
        "pro_guide": "向导",
        "casual_tourist": "行者",
        "local_walker": "漫步者",
    }
    prefix = mapping.get(archetype, "旅人")
    return f"{region}{prefix}{seq}"
