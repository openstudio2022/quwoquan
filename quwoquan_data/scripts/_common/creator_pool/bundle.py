"""Build CreatorBundle records and creator.yaml projections."""
from __future__ import annotations

from typing import Any

from _common.creator_pool.constants import CLAIM_POLICY, DISCLOSURE, PHOTOGRAPHY_TOPIC_REFS, TRAVEL_TOPIC_REFS


def build_creator_ref(*, vertical: str, archetype: str, region: str, seq: int) -> str:
    return f"creator/{vertical}/{archetype}/{region}/{seq:03d}"


def build_creator_bundle(
    *,
    seq: int,
    vertical: str,
    batch_id: str,
    archetype: str,
    region_bucket: str,
    carrier_bucket: str,
    platform_bucket: str,
    display_name: str,
    user_handle: str,
    headline: str,
    bio: str,
    engagement_score: float,
    output_score: float,
    popularity_tier: str,
    output_tier: str = "steady",
    fixture_mode: bool = False,
    cited_source_paths: list[str] | None = None,
    vertical_segment: str | None = None,
    vertical_refs: list[str] | None = None,
    topic_refs: list[str] | None = None,
    source_kind: str | None = None,
    source_url: str | None = None,
    source_site_id: str | None = None,
    source_domain: str | None = None,
    source_profile_key: str | None = None,
    source_region_class: str | None = None,
    china_analog_label: str | None = None,
    candidate_role: str | None = None,
    crawl_allowed: bool | None = None,
    validation_only: bool | None = None,
    rights_policy: str | None = None,
    model_release_status: str | None = None,
) -> dict[str, Any]:
    suffix = f"{seq:03d}"
    vertical_segment = vertical_segment or "travel_primary"
    vertical_refs = _dedupe(vertical_refs or [vertical])
    topic_refs = _dedupe(topic_refs or [])
    primary_vertical = vertical_refs[0] if vertical_refs else vertical
    profile_id = _creator_profile_id(
        primary_vertical=primary_vertical,
        batch_id=batch_id,
        archetype=archetype,
        suffix=suffix,
    )
    sub_account = f"agent_sub_account_{primary_vertical}_{batch_id}_{suffix}"
    author_id = f"agent_author_{primary_vertical}_{batch_id}_{suffix}"
    carrier = _carrier_affinity(carrier_bucket)
    source_kind_value = "fixture_synthetic" if fixture_mode else (source_kind or "open_web_profile")
    source_url_value = source_url or f"https://example.com/travel-signal/{user_handle}"
    model_release_status = model_release_status or _model_release_status(archetype, topic_refs)
    slogan = _slogan(vertical_segment, archetype, region_bucket)
    ip_location = _ip_location(region_bucket)
    public_tags = _public_tags(archetype, region_bucket, vertical_refs=vertical_refs, segment=vertical_segment)
    interest_tags = _interest_tags(
        archetype,
        region_bucket,
        seq,
        vertical_refs=vertical_refs,
        segment=vertical_segment,
        topic_refs=topic_refs,
    )
    class_tags = [_popularity_tag(popularity_tier)]
    preferred_blueprints = _preferred_blueprints(archetype)
    coverage_scope = _coverage_scope(
        region_bucket=region_bucket,
        vertical_refs=vertical_refs,
        topic_refs=interest_tags,
    )
    relation_refs = _relation_refs(
        batch_id=batch_id,
        region_bucket=region_bucket,
        vertical_refs=vertical_refs,
        topic_refs=interest_tags,
    )
    rights = {
        "rightsPolicy": rights_policy or ("fixture" if fixture_mode else "public_signal_reference"),
        "modelReleaseStatus": model_release_status,
        "appPublishAllowed": not bool(validation_only) and model_release_status != "editorial_only",
    }
    commercial_readiness = {
        "appPublishAllowed": rights["appPublishAllowed"],
        "personaPolicy": "derivative_persona_v1",
        "sourceClonePolicy": "no_real_name_no_avatar_no_bio_copy",
    }
    return {
        "schemaVersion": "quwoquan_data.creator_bundle/1",
        "creatorProfileId": profile_id,
        "subAccountId": sub_account,
        "authorId": author_id,
        "creatorArchetype": archetype,
        "identity": {
            "creatorProfileId": profile_id,
            "subAccountId": sub_account,
            "authorId": author_id,
            "userHandle": user_handle,
            "personaVersion": "derivative_persona_v1",
            "sourceClonePolicy": "no_real_name_no_avatar_no_bio_copy",
        },
        "sourceMetrics": {
            "engagementScore": engagement_score,
            "outputScore": output_score,
            "platformStyle": platform_bucket,
            "popularityTier": popularity_tier,
            "outputTier": output_tier,
        },
        "diversitySlots": {
            "regionBucket": region_bucket,
            "archetypeBucket": archetype,
            "carrierBucket": carrier_bucket,
            "platformBucket": platform_bucket,
            "verticalSegment": vertical_segment,
            "sourceRegionClass": source_region_class,
            "sourceSiteId": source_site_id,
        },
        "provenance": {
            "sourceKind": source_kind_value,
            "sourceUrl": source_url_value,
            "sourceSiteId": source_site_id,
            "sourceRegionClass": source_region_class,
            "rightsPolicy": rights["rightsPolicy"],
            "modelReleaseStatus": model_release_status,
            "validationOnly": bool(validation_only),
            "crawlAllowed": bool(crawl_allowed),
            "commercialReadiness": commercial_readiness,
            "extractedSignals": {
                "region": region_bucket,
                "topics": topic_refs or _fallback_topics(vertical_refs, seq),
                "voice": "derivative",
                "verticalSegment": vertical_segment,
                "sourceSiteId": source_site_id,
                "sourceDomain": source_domain,
                "sourceProfileKey": source_profile_key,
                "sourceRegionClass": source_region_class,
                "chinaAnalogLabel": china_analog_label,
                "candidateRole": candidate_role,
                "crawlAllowed": crawl_allowed,
                "validationOnly": validation_only,
                "rightsPolicy": rights_policy,
                "modelReleaseStatus": model_release_status,
            },
            "derivationPolicy": "derivative_persona_v1",
            "citedSourcePaths": cited_source_paths or [],
        },
        "profile": {
            "displayName": display_name,
            "userHandle": user_handle,
            "bio": bio,
            "headline": headline,
            "slogan": slogan,
            "avatarObjectKey": f"cold_start/creators/{batch_id}/{user_handle}/avatar.jpg",
            "backgroundObjectKey": f"cold_start/creators/{batch_id}/{user_handle}/cover.jpg",
            "ipLocation": ip_location,
            "identityTags": _identity_tags(vertical_refs, vertical_segment),
        },
        "classification": {
            "verticalSegment": vertical_segment,
            "creatorArchetype": archetype,
            "verticalRefs": vertical_refs,
            "interestTagRefs": interest_tags,
            "publicProfileTagRefs": public_tags,
            "creatorClassTagRefs": class_tags,
        },
        "tags": {
            "creatorClassTagRefs": class_tags,
            "publicProfileTagRefs": public_tags,
            "interestTagRefs": interest_tags,
        },
        "relations": {
            "joinedCircleIds": relation_refs["joinedCircleIds"],
            "followedHomepageCanonicalIds": relation_refs["followedHomepageCanonicalIds"],
            "entityAffinityRefs": relation_refs["entityAffinityRefs"],
            "circleAffinityRefs": relation_refs["circleAffinityRefs"],
            "relationSeedPolicy": "deterministic_v1",
        },
        "content": {
            "verticalRefs": vertical_refs,
            "scenarioRefs": ["cold_start", "long_tail_fill"],
            "carrierAffinity": carrier,
            "coverageScope": coverage_scope,
            "preferredBlueprintIds": preferred_blueprints,
            "voiceStyle": {"narrativePointOfView": "资料整理", "tone": "亲切"},
            "publishCadence": {
                "intervalDays": 3,
                "randomizedRangeDays": [1, 5],
                "maxDailyPosts": 1,
            },
            "disclosure": DISCLOSURE,
            "claimPolicy": CLAIM_POLICY,
            "rights": rights,
        },
        "contentAffinity": {
            "carrierAffinity": carrier,
            "coverageScope": coverage_scope,
            "preferredBlueprintIds": preferred_blueprints,
            "voiceStyle": {"narrativePointOfView": "资料整理", "tone": "亲切"},
            "publishCadence": {
                "intervalDays": 3,
                "randomizedRangeDays": [1, 5],
                "maxDailyPosts": 1,
            },
            "disclosure": DISCLOSURE,
            "claimPolicy": CLAIM_POLICY,
        },
        "operations": {
            "cohortId": batch_id,
            "batchId": batch_id,
            "shardId": _shard_id(seq),
            "envEligibility": ["alpha", "beta", "gamma", "prod"],
            "status": "active",
            "maxDailyPosts": 1,
            "qualityScore": round(0.75 + engagement_score * 0.2, 2),
            "fatigueScore": 0.2,
            "riskTier": "low",
            "importVersion": "creator_pool_profile_import/1",
        },
    }


def bundle_to_creator_yaml(bundle: dict[str, Any]) -> dict[str, Any]:
    profile = bundle.get("profile") or {}
    content = bundle.get("content") or {}
    tags = bundle.get("tags") or {}
    ops = bundle.get("operations") or {}
    coverage = bundle.get("diversitySlots") or {}
    region = str(coverage.get("regionBucket") or "全国")
    return {
        "creatorProfileId": bundle["creatorProfileId"],
        "subAccountId": bundle["subAccountId"],
        "authorId": bundle["authorId"],
        "isSystemBuiltin": False,
        "displayName": profile.get("displayName"),
        "userHandle": profile.get("userHandle"),
        "avatarObjectKey": profile.get("avatarObjectKey"),
        "backgroundObjectKey": profile.get("backgroundObjectKey"),
        "headline": profile.get("headline"),
        "slogan": profile.get("slogan"),
        "bio": profile.get("bio"),
        "ipLocation": profile.get("ipLocation"),
        "creatorArchetype": bundle.get("creatorArchetype"),
        "status": ops.get("status", "active"),
        "cohortId": ops.get("cohortId"),
        "batchId": ops.get("batchId") or ops.get("cohortId"),
        "shardId": ops.get("shardId"),
        "envEligibility": ops.get("envEligibility") or ["alpha", "beta", "gamma", "prod"],
        "verticalRefs": content.get("verticalRefs", ["travel"]),
        "scenarioRefs": content.get("scenarioRefs", ["cold_start"]),
        "claimPolicy": content.get("claimPolicy"),
        "disclosure": content.get("disclosure"),
        "publishCadence": content.get("publishCadence"),
        "qualityScore": ops.get("qualityScore", 0.8),
        "fatigueScore": ops.get("fatigueScore", 0.2),
        "riskTier": ops.get("riskTier", "low"),
        "profileVersion": "1.0.0",
        "publicProfileTagRefs": tags.get("publicProfileTagRefs") or [],
        "recommendationTagRefs": tags.get("interestTagRefs") or [],
        "preferredBlueprintIds": content.get("preferredBlueprintIds")
        or _preferred_blueprints(str(bundle.get("creatorArchetype"))),
        "voiceStyle": content.get("voiceStyle"),
        "expertiseClaims": _expertise_claims(content.get("verticalRefs") or ["travel"]),
        "mustNotClaim": CLAIM_POLICY["forbiddenClaims"],
        "coverageScope": content.get("coverageScope")
        or {
            "kind": "regional",
            "label": f"{region}{_coverage_suffix(content.get('verticalRefs') or ['travel'])}",
            "regionRefs": [region],
        },
        "carrierAffinity": content.get("carrierAffinity"),
        "relations": bundle.get("relations") or {},
        "provenance": bundle.get("provenance") or {},
    }


def _creator_profile_id(*, primary_vertical: str, batch_id: str, archetype: str, suffix: str) -> str:
    return f"qwq_creator_{primary_vertical}_{batch_id}_{archetype}_{suffix}"


def _carrier_affinity(bucket: str) -> dict[str, float]:
    mapping = {
        "article": {"article": 0.75, "image": 0.2, "video": 0.05},
        "image": {"article": 0.2, "image": 0.7, "video": 0.1},
        "mixed": {"article": 0.45, "image": 0.35, "video": 0.2},
        "article_heavy": {"article": 0.75, "image": 0.2, "video": 0.05},
        "image_heavy": {"article": 0.2, "image": 0.7, "video": 0.1},
        "video_heavy": {"article": 0.1, "image": 0.2, "video": 0.7},
        "balanced": {"article": 0.45, "image": 0.35, "video": 0.2},
    }
    return mapping.get(bucket, mapping["mixed"])


def _popularity_tag(tier: str) -> str:
    mapping = {
        "head": "Audience/创作者/粉丝量级/头部博主",
        "waist": "Audience/创作者/粉丝量级/腰部博主",
        "rising": "Audience/创作者/粉丝量级/小博主",
        "niche": "Audience/创作者/粉丝量级/素人",
        "niche_expert": "Audience/创作者/粉丝量级/素人",
    }
    return mapping.get(tier, mapping["rising"])


def _interest_tags(
    archetype: str,
    region: str,
    seq: int,
    *,
    vertical_refs: list[str] | None = None,
    segment: str = "travel_primary",
    topic_refs: list[str] | None = None,
) -> list[str]:
    vertical_refs = vertical_refs or ["travel"]
    tags: list[str] = list(topic_refs or [])
    if "travel" in vertical_refs and not any(tag.startswith("Topic/旅行/") for tag in tags):
        tags.append(TRAVEL_TOPIC_REFS[seq % len(TRAVEL_TOPIC_REFS)])
    if "photography" in vertical_refs and not any(tag.startswith("Topic/摄影/") for tag in tags):
        tags.append(PHOTOGRAPHY_TOPIC_REFS[seq % len(PHOTOGRAPHY_TOPIC_REFS)])
    tags.extend(_public_tags(archetype, region, vertical_refs=vertical_refs, segment=segment))
    return _dedupe(tags)


def _public_tags(
    archetype: str,
    region: str,
    *,
    vertical_refs: list[str] | None = None,
    segment: str = "travel_primary",
) -> list[str]:
    vertical_refs = vertical_refs or ["travel"]
    base: list[str] = []
    if "travel" in vertical_refs:
        base.extend(["Topic/旅行", "Topic/旅行/旅行主题/文化深度游"])
    if "photography" in vertical_refs:
        base.extend(["Topic/摄影", "Topic/摄影/摄影教程"])
    if archetype == "self_drive_expert":
        base.append("Topic/旅行/出行方式/自驾")
    if archetype in {"landscape_photographer", "travel_landscape_photographer", "photo_landscape_photographer"}:
        base.append("Topic/旅行/玩法/摄影旅拍")
        base.append("Topic/摄影/风光摄影")
    if archetype == "food_columnist":
        base.append("Format/内容角度/探店/餐厅探店")
    if archetype == "food_travel_visualist":
        base.append("Topic/旅行/旅行主题/美食之旅")
        base.append("Topic/摄影/美食摄影")
    if archetype == "city_walk_photographer":
        base.append("Topic/旅行/旅行主题/城市漫步")
        base.append("Topic/摄影/街头摄影")
    if archetype == "heritage_documentary_photographer":
        base.append("Topic/旅行/旅行主题/文化深度游")
        base.append("Topic/摄影/纪实摄影")
    if archetype == "mobile_travel_creator":
        base.append("Topic/摄影/手机摄影")
    if archetype == "gear_lightweight_traveler":
        base.append("Topic/摄影/器材评测")
    if region == "西南":
        base.append("Topic/旅行/住宿/川西住宿")
    return _dedupe(base)


def _preferred_blueprints(archetype: str) -> list[str]:
    mapping = {
        "travel_blogger": ["景区_体验", "旅行_个人游记", "古镇_叙事"],
        "self_drive_expert": ["线路_周末短途", "线路_枢纽到达"],
        "landscape_photographer": ["景区_文化", "景区_攻略"],
        "geo_editor": ["景区_攻略", "景区_文化"],
        "food_columnist": ["餐厅_探店"],
        "pro_guide": ["景区_攻略", "景区_体验"],
        "portrait_photographer": ["图片_人像", "摄影_教程"],
        "photo_landscape_photographer": ["图片_风光", "摄影_教程"],
        "documentary_photographer": ["图片_纪实", "摄影_专题"],
        "street_photographer": ["图片_街拍", "摄影_专题"],
        "architecture_still_photographer": ["图片_建筑", "图片_静物"],
        "mobile_photographer": ["摄影_手机", "摄影_教程"],
        "gear_reviewer": ["摄影_器材", "摄影_教程"],
        "post_production_educator": ["摄影_后期", "摄影_教程"],
        "travel_landscape_photographer": ["景区_体验", "图片_风光"],
        "city_walk_photographer": ["城市_漫步", "图片_街拍"],
        "outdoor_hiking_photographer": ["线路_徒步", "图片_风光"],
        "food_travel_visualist": ["餐厅_探店", "图片_美食"],
        "heritage_documentary_photographer": ["景区_文化", "图片_纪实"],
        "mobile_travel_creator": ["旅行_个人游记", "摄影_手机"],
        "gear_lightweight_traveler": ["线路_周末短途", "摄影_器材"],
        "local_photo_walk_guide": ["城市_漫步", "景区_体验"],
    }
    return mapping.get(archetype, ["景区_体验"])


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _slogan(segment: str, archetype: str, region: str) -> str:
    if segment == "photography_primary":
        return f"用镜头整理{region}的光线、题材与出片节奏"
    if segment == "travel_photography_cross":
        return f"把{region}路线拍成可参考的图文现场"
    if archetype in {"self_drive_expert", "pro_guide"}:
        return f"把{region}行程拆成能落地的路线经验"
    return f"记录{region}旅行里的真实信息与选择理由"


def _ip_location(region: str) -> dict[str, str]:
    return {
        "countryCode": "CN",
        "regionRef": f"Region/中国/大区/{region}",
        "displayText": f"中国 · {region}",
        "source": "derived_from_region_bucket",
    }


def _identity_tags(vertical_refs: list[str], segment: str) -> list[str]:
    tags = ["platform_virtual_creator", "derivative_persona_v1", segment]
    tags.extend(f"vertical:{ref}" for ref in vertical_refs)
    return _dedupe(tags)


def _coverage_scope(*, region_bucket: str, vertical_refs: list[str], topic_refs: list[str]) -> dict[str, Any]:
    return {
        "kind": "regional_topic",
        "label": f"{region_bucket}{_coverage_suffix(vertical_refs)}",
        "regionRefs": [region_bucket],
        "topicRefs": topic_refs,
    }


def _relation_refs(
    *,
    batch_id: str,
    region_bucket: str,
    vertical_refs: list[str],
    topic_refs: list[str],
) -> dict[str, list[str]]:
    circle_ids = [f"fixture_circle_creator_{batch_id}_{region_bucket}"]
    entity_refs = [f"homepage/region/{region_bucket}"]
    circle_affinity = [f"circle/creator/{region_bucket}"]
    if "travel" in vertical_refs:
        circle_ids.append(f"fixture_circle_creator_{batch_id}_travel")
        entity_refs.append("homepage/topic/travel")
        circle_affinity.append("circle/topic/travel")
    if "photography" in vertical_refs:
        circle_ids.append(f"fixture_circle_creator_{batch_id}_photography")
        entity_refs.append("homepage/topic/photography")
        circle_affinity.append("circle/topic/photography")
    for ref in topic_refs[:3]:
        slug = ref.replace("/", "_")
        entity_refs.append(f"homepage/tag/{slug}")
    return {
        "joinedCircleIds": _dedupe(circle_ids),
        "followedHomepageCanonicalIds": _dedupe(entity_refs[:3]),
        "entityAffinityRefs": _dedupe(entity_refs),
        "circleAffinityRefs": _dedupe(circle_affinity),
    }


def _shard_id(seq: int) -> str:
    return f"shard_{((seq - 1) // 100) + 1:02d}"


def _fallback_topics(vertical_refs: list[str], seq: int) -> list[str]:
    topics: list[str] = []
    if "travel" in vertical_refs:
        topics.append(TRAVEL_TOPIC_REFS[seq % len(TRAVEL_TOPIC_REFS)])
    if "photography" in vertical_refs:
        topics.append(PHOTOGRAPHY_TOPIC_REFS[seq % len(PHOTOGRAPHY_TOPIC_REFS)])
    return topics


def _model_release_status(archetype: str, topic_refs: list[str]) -> str:
    if "portrait" in archetype or any(ref == "Topic/摄影/人像摄影" for ref in topic_refs):
        return "editorial_only"
    return "not_required"


def _expertise_claims(vertical_refs: list[str]) -> list[str]:
    refs = set(vertical_refs)
    if {"travel", "photography"}.issubset(refs):
        return ["旅行体验整理", "摄影题材观察", "图文叙事"]
    if "photography" in refs:
        return ["摄影题材观察", "器材与出片节奏"]
    return ["旅行体验", "行程串联"]


def _coverage_suffix(vertical_refs: list[str]) -> str:
    refs = set(vertical_refs)
    if {"travel", "photography"}.issubset(refs):
        return "旅拍"
    if "photography" in refs:
        return "摄影"
    return "旅行"
