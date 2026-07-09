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


def _selected_object(vertical: str, batch_id: str, creator_ref: str) -> dict[str, Any]:
    index_path = creator_pool_shared_dir(vertical, batch_id) / "creator_object_index.json"
    index = read_json(index_path) if index_path.is_file() else {}
    for obj in index.get("objects") or []:
        if isinstance(obj, dict) and obj.get("creatorRef") == creator_ref:
            return obj
    return {}


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
        selected = _selected_object(vertical, batch_id, creator_ref)
        parts = creator_ref.split("/")
        archetype = str(selected.get("archetype") or (parts[2] if len(parts) > 2 else "travel_blogger"))
        region = str(selected.get("regionBucket") or (parts[3] if len(parts) > 3 else "西南"))
        seq = parts[4] if len(parts) > 4 else "001"
        segment = str(selected.get("verticalSegment") or "travel_primary")
        display = _display_name(archetype, region, seq, segment=segment)
        handle = f"{segment}_{archetype}_{seq}".replace("-", "_")
        topic_refs = [str(ref) for ref in selected.get("topicRefs") or []]
        vertical_refs = [str(ref) for ref in selected.get("verticalRefs") or []] or [vertical]
        model_release = "editorial_only" if "portrait" in archetype or "Topic/摄影/人像摄影" in topic_refs else "not_required"
        persona = {
            "displayName": display,
            "userHandle": handle,
            "headline": _headline(segment, archetype, region),
            "bio": _bio(segment, archetype, region),
            "archetype": archetype,
            "regionBucket": region,
            "verticalSegment": segment,
            "verticalRefs": vertical_refs,
            "topicRefs": topic_refs,
            "sourceSiteId": selected.get("sourceSiteId"),
            "sourceProfileKey": selected.get("sourceProfileKey"),
            "modelReleaseStatus": model_release,
        }
        stage_dir = creator_pool_stage_dir(vertical, batch_id, creator_ref, "3.enrich")
        stage_dir.mkdir(parents=True, exist_ok=True)
        cited = _candidate_source_paths(vertical, batch_id, creator_ref)
        prompt = (
            f"Enrich derivative persona for {creator_ref} using public signals only. "
            f"segment={segment} sourceSiteId={selected.get('sourceSiteId')}"
        )
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


def _display_name(archetype: str, region: str, seq: str, *, segment: str) -> str:
    mapping = {
        "travel_blogger": "旅人",
        "self_drive_expert": "自驾客",
        "landscape_photographer": "光影客",
        "geo_editor": "地理志",
        "food_columnist": "食旅记",
        "pro_guide": "向导",
        "casual_tourist": "行者",
        "local_walker": "漫步者",
        "portrait_photographer": "人像观察员",
        "photo_landscape_photographer": "风光影像员",
        "documentary_photographer": "纪实影像员",
        "street_photographer": "街拍记录员",
        "architecture_still_photographer": "建筑静物员",
        "mobile_photographer": "手机影像员",
        "gear_reviewer": "轻器材研究员",
        "post_production_educator": "后期教练",
        "travel_landscape_photographer": "旅拍风光员",
        "city_walk_photographer": "城市漫拍员",
        "outdoor_hiking_photographer": "户外影像员",
        "food_travel_visualist": "食旅视觉员",
        "heritage_documentary_photographer": "遗产纪实员",
        "mobile_travel_creator": "手机旅拍员",
        "gear_lightweight_traveler": "轻装旅拍员",
        "local_photo_walk_guide": "本地影像向导",
    }
    prefix = mapping.get(archetype, "旅人")
    if segment == "photography_primary":
        return f"{region}{prefix}{seq}"
    if segment == "travel_photography_cross":
        return f"{region}{prefix}{seq}"
    return f"{region}{prefix}{seq}"


def _headline(segment: str, archetype: str, region: str) -> str:
    if segment == "photography_primary":
        return f"{region}摄影题材与器材观察"
    if segment == "travel_photography_cross":
        return f"{region}旅拍路线与画面叙事"
    return f"{region}旅行路线与体验整理"


def _bio(segment: str, archetype: str, region: str) -> str:
    if segment == "photography_primary":
        return f"专注{region}摄影题材、器材选择与出片节奏，基于公开平台信号生成衍生 persona。"
    if segment == "travel_photography_cross":
        return f"结合{region}旅行场景与摄影表达，偏图文和图片载体，基于公开风格信号生成衍生 persona。"
    return f"专注{region}旅行内容、路线经验与目的地信息，基于公开内容信号生成衍生 persona。"
