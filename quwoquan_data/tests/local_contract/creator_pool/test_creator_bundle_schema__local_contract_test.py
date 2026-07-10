from __future__ import annotations

import json
from pathlib import Path

import pytest

from _common.creator_pool.bundle import build_creator_bundle

REPO = Path(__file__).resolve().parents[4]
SCHEMA = REPO / "quwoquan_data/schema/creator/creator_bundle.schema.json"
GOLDEN = REPO / "quwoquan_data/tests/support/fixtures/creator_pool/travel_scale10_verify/golden_creator_bundle.json"


def test_golden_creator_bundle_required_fields() -> None:
    data = json.loads(GOLDEN.read_text(encoding="utf-8"))
    for field in (
        "creatorProfileId",
        "subAccountId",
        "authorId",
        "creatorArchetype",
        "profile",
        "provenance",
        "content",
        "operations",
    ):
        assert field in data
    assert data["provenance"]["derivationPolicy"] == "derivative_persona_v1"
    assert data["schemaVersion"] == "quwoquan_data.creator_bundle/1"


def test_creator_bundle_profile_import_contract_fields() -> None:
    bundle = build_creator_bundle(
        seq=1,
        vertical="travel",
        batch_id="travel_photo_1k_v1",
        archetype="travel_landscape_photographer",
        region_bucket="西南",
        carrier_bucket="image",
        platform_bucket="gallery_portfolio",
        display_name="西南旅拍风光员001",
        user_handle="travel_photography_cross_travel_landscape_photographer_001",
        headline="西南旅拍路线与画面叙事",
        bio="结合西南旅行场景与摄影表达，偏图文和图片载体，基于公开风格信号生成衍生 persona。",
        engagement_score=0.8,
        output_score=0.8,
        popularity_tier="rising",
        cited_source_paths=["/tmp/source.md"],
        vertical_segment="travel_photography_cross",
        vertical_refs=["travel", "photography"],
        topic_refs=["Topic/旅行/玩法/摄影旅拍", "Topic/摄影/旅行摄影"],
        source_kind="open_web_profile",
        source_url="https://www.thewanderinglens.com/",
        source_site_id="the_wandering_lens",
        source_region_class="non_china",
        rights_policy="discovery_only",
        model_release_status="not_required",
    )
    assert bundle["identity"]["personaVersion"] == "derivative_persona_v1"
    assert bundle["identity"]["sourceClonePolicy"] == "no_real_name_no_avatar_no_bio_copy"
    assert bundle["profile"]["slogan"]
    assert bundle["profile"]["ipLocation"]["source"] == "derived_from_region_bucket"
    assert bundle["profile"]["avatarObjectKey"].endswith("/avatar.jpg")
    assert bundle["profile"]["backgroundObjectKey"].endswith("/cover.jpg")
    assert bundle["classification"]["verticalSegment"] == "travel_photography_cross"
    assert {"travel", "photography"}.issubset(set(bundle["classification"]["verticalRefs"]))
    assert bundle["relations"]["relationSeedPolicy"] == "deterministic_v1"
    assert bundle["relations"]["entityAffinityRefs"]
    assert bundle["contentAffinity"]["preferredBlueprintIds"]
    assert bundle["operations"]["envEligibility"] == ["alpha", "beta", "gamma", "prod"]
    assert bundle["operations"]["importVersion"] == "creator_pool_profile_import/1"


def test_creator_bundle_schema_file_exists() -> None:
    assert SCHEMA.is_file()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert schema["$id"] == "quwoquan_data.creator_bundle"
