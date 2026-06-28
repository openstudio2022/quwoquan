"""Build CreatorBundle records and creator.yaml projections."""
from __future__ import annotations

from typing import Any

from _common.creator_pool.constants import CLAIM_POLICY, DISCLOSURE, TRAVEL_TOPIC_REFS


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
) -> dict[str, Any]:
    suffix = f"{seq:03d}"
    profile_id = f"qwq_creator_travel_{archetype}_{suffix}"
    sub_account = f"agent_sub_account_travel_{batch_id}_{suffix}"
    author_id = f"agent_author_travel_{batch_id}_{suffix}"
    carrier = _carrier_affinity(carrier_bucket)
    return {
        "schemaVersion": "quwoquan_data.creator_bundle/1",
        "creatorProfileId": profile_id,
        "subAccountId": sub_account,
        "authorId": author_id,
        "creatorArchetype": archetype,
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
        },
        "provenance": {
            "sourceKind": "fixture_synthetic" if fixture_mode else "open_web_profile",
            "sourceUrl": f"https://example.com/travel-signal/{user_handle}",
            "extractedSignals": {
                "region": region_bucket,
                "topics": ["旅行", archetype],
                "voice": "derivative",
            },
            "derivationPolicy": "derivative_persona_v1",
            "citedSourcePaths": cited_source_paths or [],
        },
        "profile": {
            "displayName": display_name,
            "userHandle": user_handle,
            "bio": bio,
            "headline": headline,
            "avatarObjectKey": f"cold_start/creators/{batch_id}/{user_handle}/avatar.jpg",
            "backgroundObjectKey": f"cold_start/creators/{batch_id}/{user_handle}/cover.jpg",
        },
        "tags": {
            "creatorClassTagRefs": [_popularity_tag(popularity_tier)],
            "publicProfileTagRefs": _public_tags(archetype, region_bucket),
            "interestTagRefs": _interest_tags(archetype, region_bucket, seq),
        },
        "relations": {
            "joinedCircleIds": [f"fixture_circle_travel_{region_bucket}"],
            "followedHomepageCanonicalIds": [],
        },
        "content": {
            "verticalRefs": [vertical],
            "scenarioRefs": ["cold_start", "long_tail_fill"],
            "carrierAffinity": carrier,
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
            "status": "active",
            "maxDailyPosts": 1,
            "qualityScore": round(0.75 + engagement_score * 0.2, 2),
            "fatigueScore": 0.2,
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
        "headline": profile.get("headline"),
        "bio": profile.get("bio"),
        "creatorArchetype": bundle.get("creatorArchetype"),
        "status": ops.get("status", "active"),
        "verticalRefs": content.get("verticalRefs", ["travel"]),
        "scenarioRefs": content.get("scenarioRefs", ["cold_start"]),
        "claimPolicy": content.get("claimPolicy"),
        "disclosure": content.get("disclosure"),
        "publishCadence": content.get("publishCadence"),
        "qualityScore": ops.get("qualityScore", 0.8),
        "fatigueScore": ops.get("fatigueScore", 0.2),
        "riskTier": "low",
        "profileVersion": "1.0.0",
        "publicProfileTagRefs": tags.get("publicProfileTagRefs") or [],
        "recommendationTagRefs": tags.get("interestTagRefs") or [],
        "preferredBlueprintIds": _preferred_blueprints(str(bundle.get("creatorArchetype"))),
        "voiceStyle": content.get("voiceStyle"),
        "expertiseClaims": ["旅行体验", "行程串联"],
        "mustNotClaim": CLAIM_POLICY["forbiddenClaims"],
        "coverageScope": {
            "kind": "regional",
            "label": f"{region}旅行",
            "regionRefs": [region],
        },
        "carrierAffinity": content.get("carrierAffinity"),
    }


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


def _interest_tags(archetype: str, region: str, seq: int) -> list[str]:
    tags = ["Topic/旅行", TRAVEL_TOPIC_REFS[seq % len(TRAVEL_TOPIC_REFS)]]
    tags.extend(_public_tags(archetype, region))
    # dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


def _public_tags(archetype: str, region: str) -> list[str]:
    base = ["Topic/旅行", f"Topic/旅行/旅行主题/文化深度游"]
    if archetype == "self_drive_expert":
        base.append("Topic/旅行/出行方式/自驾")
    if archetype == "landscape_photographer":
        base.append("Topic/旅行/玩法/摄影旅拍")
    if archetype == "food_columnist":
        base.append("Format/内容角度/探店/餐厅探店")
    if region == "西南":
        base.append("Topic/旅行/住宿/川西住宿")
    return base


def _preferred_blueprints(archetype: str) -> list[str]:
    mapping = {
        "travel_blogger": ["景区_体验", "旅行_个人游记", "古镇_叙事"],
        "self_drive_expert": ["线路_周末短途", "线路_枢纽到达"],
        "landscape_photographer": ["景区_文化", "景区_攻略"],
        "geo_editor": ["景区_攻略", "景区_文化"],
        "food_columnist": ["餐厅_探店"],
        "pro_guide": ["景区_攻略", "景区_体验"],
    }
    return mapping.get(archetype, ["景区_体验"])
