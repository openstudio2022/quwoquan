"""Creator pool materialize stage."""
from __future__ import annotations

from typing import Any

import yaml

from _common.creator_pool.bundle import build_creator_bundle, bundle_to_creator_yaml
from _common.creator_pool.constants import COMMERCIAL_CARRIER_BUCKETS
from _common.creator_pool.io import (
    iter_creator_refs,
    repo_creator_profiles_dir,
    stage_gate_path,
    write_gate,
    write_stage_result,
)
from _common.creator_pool.media_assets import _MIN_JPEG, ensure_creator_media
from _common.io import read_json, write_json
from _common.paths import creator_pool_shared_dir, creator_pool_stage_dir, now_iso


def run_materialize(*, vertical: str, batch_id: str, dry_run: bool = False) -> dict[str, Any]:
    plan_path = creator_pool_shared_dir(vertical, batch_id) / "creator_pool_plan.json"
    plan = read_json(plan_path) if plan_path.is_file() else {}
    fixture_mode = bool(plan.get("fixtureMode")) if isinstance(plan, dict) else False
    live_mode = bool(plan.get("liveMode"))
    out_dir = repo_creator_profiles_dir(vertical, batch_id)
    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        if live_mode:
            for stale in out_dir.glob("*.creator.yaml"):
                stale.unlink()
    index = read_json(creator_pool_shared_dir(vertical, batch_id) / "creator_object_index.json")
    by_ref = {obj.get("creatorRef"): obj for obj in (index.get("objects") or []) if isinstance(obj, dict)}
    bundles: list[dict[str, Any]] = []
    materialized = 0
    for creator_ref in iter_creator_refs(vertical, batch_id):
        enrich_path = creator_pool_stage_dir(vertical, batch_id, creator_ref, "3.enrich") / "persona_draft.json"
        enrich_meta_path = creator_pool_stage_dir(vertical, batch_id, creator_ref, "3.enrich") / "enrich_meta.json"
        persona = read_json(enrich_path) if enrich_path.is_file() else {}
        enrich_meta = read_json(enrich_meta_path) if enrich_meta_path.is_file() else {}
        score_dir = creator_pool_stage_dir(vertical, batch_id, creator_ref, "2.score")
        engagement = 0.75
        output = 0.8
        tier = "rising"
        output_tier = "steady"
        sel = by_ref.get(creator_ref) or {}
        if sel.get("compositeScore") is not None:
            engagement = float(sel.get("compositeScore") or engagement)
            output = float(sel.get("compositeScore") or output)
        if (score_dir / "engagement_metrics.json").is_file():
            engagement = float(read_json(score_dir / "engagement_metrics.json").get("score", engagement))
        if (score_dir / "output_metrics.json").is_file():
            output = float(read_json(score_dir / "output_metrics.json").get("score", output))
        if (score_dir / "popularity_tier.json").is_file():
            tier = str(read_json(score_dir / "popularity_tier.json").get("tier", tier))
        tier = str(sel.get("popularityTier") or tier)
        output_tier = str(sel.get("outputTier") or output_tier)
        parts = creator_ref.split("/")
        seq = int(parts[4]) if len(parts) > 4 else materialized + 1
        carrier = str(sel.get("carrierBucket") or COMMERCIAL_CARRIER_BUCKETS[seq % len(COMMERCIAL_CARRIER_BUCKETS)])
        bundle = build_creator_bundle(
            seq=seq,
            vertical=vertical,
            batch_id=batch_id,
            archetype=str(persona.get("archetype") or parts[2]),
            region_bucket=str(persona.get("regionBucket") or parts[3]),
            carrier_bucket=carrier,
            platform_bucket=str(sel.get("platformBucket") or "rss_blog"),
            display_name=str(persona.get("displayName") or f"旅人{seq:03d}"),
            user_handle=str(persona.get("userHandle") or f"travel_{seq:03d}"),
            headline=str(persona.get("headline") or "旅行创作者"),
            bio=str(persona.get("bio") or "旅行内容创作者"),
            engagement_score=engagement,
            output_score=output,
            popularity_tier=tier,
            output_tier=output_tier,
            fixture_mode=fixture_mode and not live_mode,
            cited_source_paths=list(enrich_meta.get("citedSourcePaths") or []),
            vertical_segment=str(sel.get("verticalSegment") or persona.get("verticalSegment") or "travel_primary"),
            vertical_refs=[str(ref) for ref in (sel.get("verticalRefs") or persona.get("verticalRefs") or [vertical])],
            topic_refs=[str(ref) for ref in (sel.get("topicRefs") or persona.get("topicRefs") or [])],
            source_kind=str(sel.get("sourceKind") or "open_web_profile"),
            source_url=str(sel.get("sourceUrl") or ""),
            source_site_id=str(sel.get("sourceSiteId") or ""),
            source_domain=str(sel.get("sourceDomain") or ""),
            source_profile_key=str(sel.get("sourceProfileKey") or persona.get("sourceProfileKey") or ""),
            source_region_class=str(sel.get("sourceRegionClass") or ""),
            china_analog_label=str(sel.get("chinaAnalogLabel") or ""),
            candidate_role=str(sel.get("candidateRole") or ""),
            crawl_allowed=bool(sel.get("crawlAllowed")),
            validation_only=bool(sel.get("validationOnly")),
            rights_policy=str(sel.get("rightsPolicy") or ""),
            model_release_status=str(persona.get("modelReleaseStatus") or ""),
        )
        stage_dir = creator_pool_stage_dir(vertical, batch_id, creator_ref, "4.materialize")
        stage_dir.mkdir(parents=True, exist_ok=True)
        write_json(stage_dir / "creator_bundle.json", bundle)
        write_json(stage_dir / "manifest.json", {"creatorRef": creator_ref, "creatorProfileId": bundle["creatorProfileId"]})
        write_json(stage_dir / "_profile.json", bundle_to_creator_yaml(bundle))
        assets = stage_dir / "assets"
        assets.mkdir(exist_ok=True)
        avatar_key = str((bundle.get("profile") or {}).get("avatarObjectKey") or "")
        cover_key = str((bundle.get("profile") or {}).get("backgroundObjectKey") or "")
        if avatar_key and not dry_run:
            ensure_creator_media(avatar_key)
        if cover_key and not dry_run:
            ensure_creator_media(cover_key)
        (assets / "avatar.jpg").write_bytes(_MIN_JPEG)
        (assets / "cover.jpg").write_bytes(_MIN_JPEG)
        yaml_path = out_dir / f"{profile_handle(bundle)}.creator.yaml"
        if not dry_run:
            with yaml_path.open("w", encoding="utf-8") as f:
                yaml.safe_dump(bundle_to_creator_yaml(bundle), f, allow_unicode=True, sort_keys=False)
        write_gate(
            stage_gate_path(vertical, batch_id, creator_ref, "4.materialize", "materialize_gate.json"),
            gate_id="materialize",
            passed=True,
        )
        write_stage_result(vertical, batch_id, creator_ref, "4.materialize", {"status": "ok"})
        bundles.append(bundle)
        materialized += 1
    manifest = {
        "schemaVersion": "quwoquan_data.batch_manifest/1",
        "batchId": batch_id,
        "vertical": vertical,
        "materializedCount": materialized,
        "generatedAt": now_iso(),
    }
    write_json(creator_pool_shared_dir(vertical, batch_id) / "batch_manifest.json", manifest)
    return {"materialized": materialized, "dryRun": dry_run, "bundles": bundles}


def profile_handle(bundle: dict[str, Any]) -> str:
    profile = bundle.get("profile") or {}
    return str(profile.get("userHandle") or bundle.get("creatorProfileId") or "creator")
