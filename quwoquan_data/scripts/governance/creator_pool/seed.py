"""Creator pool seed handoff stage."""
from __future__ import annotations

from typing import Any, Mapping

from _common.creator_pool.batch_policy import CANONICAL_BATCH_ID
from _common.creator_pool.io import (
    artifacts_readiness_path,
    iter_creator_refs,
    read_review_gate,
    repo_seed_fixture_dir,
)
from _common.creator_pool.media_assets import materialize_batch_media
from _common.io import read_json, write_json
from _common.paths import creator_pool_shared_dir, creator_pool_stage_dir, now_iso


def run_seed(*, vertical: str, batch_id: str, env: str = "alpha", dry_run: bool = False) -> dict[str, Any]:
    planned_target = _planned_target(vertical=vertical, batch_id=batch_id)
    users = _seed_users_from_templates(vertical=vertical, batch_id=batch_id, expected_count=planned_target)
    if not users:
        users = _seed_users_from_runtime(vertical=vertical, batch_id=batch_id)
    handoff = {
        "schemaVersion": "quwoquan_data.creator_seed_handoff/1",
        "batchId": batch_id,
        "vertical": vertical,
        "environment": env,
        "userCount": len(users),
        "generatedAt": now_iso(),
    }
    shared = creator_pool_shared_dir(vertical, batch_id)
    write_json(shared / "seed_handoff.json", handoff)
    if dry_run:
        return {"seeded": len(users), "dryRun": True}
    seed_name = seed_fixture_name(vertical, batch_id, len(users))
    seed_path = repo_seed_fixture_dir() / seed_name
    seed_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        seed_path,
        {
            "schemaVersion": "creator_pool.seed/1",
            "batchId": batch_id,
            "vertical": vertical,
            "environment": env,
            "users": users,
        },
    )
    _write_relations_seed(users, batch_id)
    _merge_creator_pool_scenarios(vertical=vertical, batch_id=batch_id, seed_name=seed_name, user_count=len(users))
    _merge_environment_manifests(vertical=vertical, batch_id=batch_id)
    if not dry_run:
        materialize_batch_media(batch_id=batch_id, users=users)
    return {"seeded": len(users), "seedPath": str(seed_path), "dryRun": False}


def _seed_users_from_templates(
    *,
    vertical: str,
    batch_id: str,
    expected_count: int | None = None,
) -> list[dict[str, Any]]:
    if vertical != "travel":
        return []
    try:
        from _common.creator_pool.registry_bridge import load_travel_batch_creators
    except Exception:  # noqa: BLE001
        return []
    creators, _ = load_travel_batch_creators(batch_id)
    profiles = sorted(creators.values(), key=lambda row: str(row.get("creatorProfileId") or ""))
    if expected_count and len(profiles) != expected_count:
        return []
    return [_seed_user_from_profile(profile, vertical=vertical, batch_id=batch_id) for profile in profiles]


def _planned_target(*, vertical: str, batch_id: str) -> int | None:
    path = creator_pool_shared_dir(vertical, batch_id) / "creator_pool_plan.json"
    if not path.is_file():
        return None
    plan = read_json(path)
    try:
        return int(plan.get("targetCount") or 0) or None
    except (TypeError, ValueError):
        return None


def _seed_users_from_runtime(*, vertical: str, batch_id: str) -> list[dict[str, Any]]:
    users: list[dict[str, Any]] = []
    for creator_ref in iter_creator_refs(vertical, batch_id):
        gate = read_review_gate(vertical, batch_id, creator_ref)
        if not gate or gate.get("decision") != "passed":
            raise RuntimeError(f"review gate not passed for {creator_ref}")
        bundle_path = creator_pool_stage_dir(vertical, batch_id, creator_ref, "4.materialize") / "creator_bundle.json"
        bundle = read_json(bundle_path)
        profile = bundle.get("profile") if isinstance(bundle.get("profile"), dict) else {}
        tags = bundle.get("tags") if isinstance(bundle.get("tags"), dict) else {}
        content = bundle.get("content") if isinstance(bundle.get("content"), dict) else {}
        operations = bundle.get("operations") if isinstance(bundle.get("operations"), dict) else {}
        provenance = bundle.get("provenance") if isinstance(bundle.get("provenance"), dict) else {}
        relations = bundle.get("relations") if isinstance(bundle.get("relations"), dict) else {}
        users.append(
            _seed_user_from_profile(
                {
                    "creatorProfileId": bundle.get("creatorProfileId"),
                    "subAccountId": bundle.get("subAccountId"),
        "displayName": profile.get("displayName"),
        "userHandle": profile.get("userHandle"),
        "avatarPresetId": profile.get("avatarPresetId"),
        "coverPresetId": profile.get("coverPresetId"),
        "bio": profile.get("bio"),
        "headline": profile.get("headline"),
        "slogan": profile.get("slogan"),
                    "creatorArchetype": bundle.get("creatorArchetype"),
                    "verticalSegment": (bundle.get("classification") or {}).get("verticalSegment")
                    or (bundle.get("diversitySlots") or {}).get("verticalSegment"),
                    "verticalRefs": content.get("verticalRefs") or [vertical],
                    "interestTagRefs": tags.get("interestTagRefs") or [],
                    "publicProfileTagRefs": tags.get("publicProfileTagRefs") or [],
                    "creatorClassTagRefs": tags.get("creatorClassTagRefs") or [],
                    "carrierAffinity": content.get("carrierAffinity") or {},
                    "coverageScope": content.get("coverageScope") or {},
                    "preferredBlueprintIds": content.get("preferredBlueprintIds") or [],
                    "relations": relations,
        "envEligibility": operations.get("envEligibility"),
        "riskTier": operations.get("riskTier"),
                },
                vertical=vertical,
                batch_id=batch_id,
            )
        )
    return users


def _seed_user_from_profile(profile: Mapping[str, Any], *, vertical: str, batch_id: str) -> dict[str, Any]:
    vertical_refs = _str_list(profile.get("verticalRefs")) or [vertical]
    public_tags = _str_list(profile.get("publicProfileTagRefs"))
    recommendation_tags = _str_list(profile.get("recommendationTagRefs"))
    interest_tags = _str_list(profile.get("interestTagRefs")) or recommendation_tags or public_tags
    coverage_scope = profile.get("coverageScope") if isinstance(profile.get("coverageScope"), Mapping) else {}
    relations = profile.get("relations") if isinstance(profile.get("relations"), Mapping) else {}
    return {
        "creatorProfileId": profile.get("creatorProfileId"),
        "subAccountId": profile.get("subAccountId"),
        "displayName": profile.get("displayName"),
        "userHandle": profile.get("userHandle"),
        "avatarPresetId": profile.get("avatarPresetId"),
        "coverPresetId": profile.get("coverPresetId"),
        "bio": profile.get("bio"),
        "headline": profile.get("headline"),
        "slogan": profile.get("slogan") or _default_slogan(profile, vertical_refs),
        "creatorArchetype": profile.get("creatorArchetype"),
        "verticalSegment": profile.get("verticalSegment") or _vertical_segment(vertical_refs),
        "verticalRefs": vertical_refs,
        "interestTagRefs": interest_tags,
        "publicProfileTagRefs": public_tags,
        "creatorClassTagRefs": _str_list(profile.get("creatorClassTagRefs")),
        "carrierAffinity": profile.get("carrierAffinity") or {},
        "coverageScope": coverage_scope,
        "preferredBlueprintIds": _str_list(profile.get("preferredBlueprintIds")),
        "relations": dict(relations) if relations else _default_relations(coverage_scope, vertical_refs, interest_tags, batch_id),
        "envEligibility": _str_list(profile.get("envEligibility")) or ["alpha", "beta", "gamma", "prod"],
        "riskTier": profile.get("riskTier") or "low",
        "vertical": vertical,
        "cohortId": batch_id,
        "batchId": batch_id,
    }


def _str_list(value: Any) -> list[str]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _cover_key_for_avatar(avatar_key: str) -> str:
    if not avatar_key:
        return ""
    if avatar_key.endswith("/avatar.jpg"):
        return avatar_key[: -len("/avatar.jpg")] + "/cover.jpg"
    return avatar_key.rsplit("/", 1)[0] + "/cover.jpg"


def _vertical_segment(vertical_refs: list[str]) -> str:
    refs = set(vertical_refs)
    if {"travel", "photography"}.issubset(refs):
        return "travel_photography_cross"
    if "photography" in refs:
        return "photography_primary"
    return "travel_primary"


def _default_slogan(profile: Mapping[str, Any], vertical_refs: list[str]) -> str:
    scope = profile.get("coverageScope") if isinstance(profile.get("coverageScope"), Mapping) else {}
    regions = _str_list(scope.get("regionRefs"))
    region = regions[0] if regions else "目的地"
    if {"travel", "photography"}.issubset(set(vertical_refs)):
        return f"记录{region}旅拍里的路线、光线与取舍"
    if "photography" in vertical_refs:
        return f"整理{region}摄影题材与出片节奏"
    return f"记录{region}旅行里的真实信息与选择理由"


def _default_ip_location(scope: Mapping[str, Any]) -> dict[str, str]:
    regions = _str_list(scope.get("regionRefs"))
    region = regions[0] if regions else "中国"
    region_ref = f"Region/中国/大区/{region}" if region != "中国" else "Region/中国"
    return {
        "countryCode": "CN",
        "regionRef": region_ref,
        "displayText": f"中国 · {region}" if region != "中国" else "中国",
        "source": "derived_from_region_bucket",
    }


def _default_relations(
    scope: Mapping[str, Any],
    vertical_refs: list[str],
    interest_tags: list[str],
    batch_id: str,
) -> dict[str, Any]:
    regions = _str_list(scope.get("regionRefs"))
    region = regions[0] if regions else "global"
    topic = vertical_refs[0] if vertical_refs else "travel"
    entity_refs = [f"homepage/region/{region}", f"homepage/topic/{topic}"]
    for tag in interest_tags[:3]:
        entity_refs.append(f"homepage/tag/{_ref_token(tag)}")
    circle_refs = [f"circle/creator/{region}", f"circle/topic/{topic}"]
    return {
        "joinedCircleIds": [f"fixture_circle_creator_{batch_id}_{region}", f"fixture_circle_creator_{batch_id}_{topic}"],
        "followedHomepageCanonicalIds": entity_refs[:3],
        "entityAffinityRefs": entity_refs,
        "circleAffinityRefs": circle_refs,
        "relationSeedPolicy": "deterministic_v1",
    }


def _ref_token(value: str) -> str:
    return value.strip().replace("/", "_").replace(" ", "_")


def _seed_provenance(provenance: Mapping[str, Any], *, legacy_app_publish_allowed: bool) -> dict[str, Any]:
    commercial = provenance.get("commercialReadiness") if isinstance(provenance.get("commercialReadiness"), Mapping) else {}
    if not commercial:
        commercial = {
            "appPublishAllowed": legacy_app_publish_allowed,
            "personaPolicy": "derivative_persona_v1",
            "sourceClonePolicy": "no_real_name_no_avatar_no_bio_copy",
        }
    return {
        "sourceSiteId": provenance.get("sourceSiteId") or "legacy_creator_seed",
        "sourceKind": provenance.get("sourceKind") or "platform_seed_profile",
        "sourceRegionClass": provenance.get("sourceRegionClass") or "china",
        "rightsPolicy": provenance.get("rightsPolicy") or "platform_seed_fixture",
        "modelReleaseStatus": provenance.get("modelReleaseStatus") or "not_required",
        "validationOnly": provenance.get("validationOnly", False),
        "crawlAllowed": provenance.get("crawlAllowed", False),
        "commercialReadiness": commercial,
        "citedSourcePaths": _str_list(provenance.get("citedSourcePaths")),
    }


def seed_fixture_name(vertical: str, batch_id: str, count: int | None = None) -> str:
    if batch_id == CANONICAL_BATCH_ID:
        if vertical == "travel":
            return "creator_travel_photo_1k_v1.seed.json"
        return f"creator_{vertical}_{batch_id}.seed.json"
    if count is not None and count <= 10:
        return f"creator_{vertical}_scale10.seed.json"
    if batch_id.startswith(f"{vertical}_"):
        return f"creator_{batch_id}.seed.json"
    return f"creator_{vertical}_{batch_id}.seed.json"


def seed_refs_for_batch(vertical: str, batch_id: str) -> list[str]:
    if batch_id == CANONICAL_BATCH_ID:
        if vertical == "travel":
            return ["creator_travel_photo_1k_v1", "creator_travel_photo_1k_v1_core"]
        return [f"creator_{vertical}_{batch_id}", f"creator_{vertical}_{batch_id}_core"]
    base = f"creator_{batch_id}" if batch_id.startswith(f"{vertical}_") else f"creator_{vertical}_{batch_id}"
    return [base, f"{base}_core"]


def _write_relations_seed(users: list[dict[str, Any]], batch_id: str) -> None:
    edges: list[dict[str, Any]] = []
    for idx, user in enumerate(users):
        sub = user.get("subAccountId")
        if not sub:
            continue
        if idx > 0:
            prev = users[idx - 1].get("subAccountId")
            edges.append({"kind": "FollowEdge", "fromSubAccountId": sub, "toSubAccountId": prev})
        relations = user.get("relations") if isinstance(user.get("relations"), dict) else {}
        circle_ids = relations.get("joinedCircleIds") or [f"fixture_circle_travel_{batch_id}"]
        for circle_id in circle_ids:
            edges.append({"kind": "CircleMember", "subAccountId": sub, "circleId": circle_id})
        for entity_ref in relations.get("entityAffinityRefs") or []:
            edges.append({"kind": "EntityAffinity", "subAccountId": sub, "entityRef": entity_ref})
        for circle_ref in relations.get("circleAffinityRefs") or []:
            edges.append({"kind": "CircleAffinity", "subAccountId": sub, "circleRef": circle_ref})
    relations_name = "creator_relations.travel_photo_1k_v1.seed.json" if batch_id == CANONICAL_BATCH_ID else f"creator_relations.{batch_id}.seed.json"
    write_json(
        repo_seed_fixture_dir() / relations_name,
        {
            "schemaVersion": "creator_pool.relations/1",
            "batchId": batch_id,
            "relationSeedPolicy": "deterministic_v1",
            "edges": edges,
        },
    )


def _merge_creator_pool_scenarios(*, vertical: str, batch_id: str, seed_name: str, user_count: int) -> None:
    path = repo_seed_fixture_dir() / "creator_pool_scenarios.json"
    data = read_json(path) if path.is_file() else {
        "schemaVersion": "creator_pool.scenario-fixtures",
        "description": "creator pool 四环境 seed manifest 包装层。",
        "repositoryExpectations": {"alpha": "mock", "beta": "remote", "gamma": "remote"},
        "seedSets": {},
        "scenarios": [],
    }
    full_ref, core_ref = seed_refs_for_batch(vertical, batch_id)
    if batch_id == CANONICAL_BATCH_ID:
        data["description"] = (
            "creator pool 四环境 seed manifest 包装层，唯一指向 "
            "canonical travel_photo_1k_v1（1200 unique -> travel/photo 双 1k view）主线。"
        )
        data["seedSets"] = {}
        data["scenarios"] = []
    seed_sets = data.setdefault("seedSets", {})
    seed_sets[full_ref] = {
        "description": f"{batch_id} 全量 {user_count} 作者 seed",
        "seedFixture": seed_name,
        "userCount": user_count,
    }
    seed_sets[core_ref] = {
        "description": f"{batch_id} curated import 子集",
        "seedFixture": seed_name,
        "sampleSize": min(100, user_count),
    }
    scenario = {
        "id": core_ref,
        "title": f"Creator pool {batch_id}",
        "type": "creator_pool",
        "domainId": "creator_pool",
        "seedRefs": [full_ref, core_ref],
        "environments": {
            "alpha": {"enabled": True, "repository": "mock"},
            "beta": {"enabled": True, "repository": "remote", "requiresSeedReset": True},
            "gamma": {"enabled": True, "repository": "remote", "requiresSeedReset": True},
        },
    }
    scenarios = [s for s in data.get("scenarios") or [] if isinstance(s, dict) and s.get("id") != core_ref]
    scenarios.append(scenario)
    data["scenarios"] = scenarios
    write_json(path, data)


def _merge_environment_manifests(*, vertical: str, batch_id: str) -> None:
    from _common.paths import SERVICE_CONTRACTS_METADATA_ROOT

    refs = seed_refs_for_batch(vertical, batch_id)
    for manifest_name in (
        "app_alpha_seed_manifest.json",
        "app_beta_seed_manifest.json",
        "app_gamma_seed_manifest.json",
    ):
        path = SERVICE_CONTRACTS_METADATA_ROOT / "_shared" / "test_fixtures" / manifest_name
        if not path.is_file():
            continue
        data = read_json(path)
        entries = data.get("seedRefs") if isinstance(data, dict) else None
        if not isinstance(entries, list):
            continue
        entry = next((item for item in entries if isinstance(item, dict) and item.get("domain") == "creator_pool"), None)
        if not isinstance(entry, dict):
            continue
        entry["refs"] = refs
        write_json(path, data)


def check_scale10_prerequisite(target: int) -> bool:
    if target <= 10:
        return True
    report_path = artifacts_readiness_path("creator_scale10_readiness.json")
    if not report_path.is_file():
        return False
    report = read_json(report_path)
    return isinstance(report, dict) and report.get("decision") == "go"
