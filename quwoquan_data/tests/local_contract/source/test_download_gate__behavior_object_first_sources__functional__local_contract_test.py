"""场景组：download gate 对象优先来源、authority title 与来源目录契约。

download gate 契约测试（对象优先）。

从 test_download_gate__behavior__functional__local_contract_test.py
按场景拆出；测试逐字搬移。
"""
from __future__ import annotations

from content.source.gate import gate_download
from content.source.source_inputs import curated_sources_for_entity
from content.source.source_unit import write_source_unit
from core.article_package import sha256_text
from core.data_issue import (
    DataIssueCode,
    DataIssueLane,
)
from core.io import write_json
from core.paths import (
    ensure_execution_layout,
    execution_entity_object_dir,
    execution_root,
)
from support.download_gate_fixture import (
    TASK,
    _attach_image,
    _clean_execution_root,
    _write_verified_homepage_source,
)
from support.image_fixture import jpeg_bytes


def test_gate_download_passes_object_first_sources():
    ensure_execution_layout(TASK)
    entity_dir = execution_entity_object_dir(TASK, "地点", "景区", "峨眉山")
    _write_verified_homepage_source(
        entity_dir,
        entity_name="峨眉山",
        source_id="overview_baike",
        asset_name="emei_1",
    )
    write_source_unit(
        entity_dir,
        ordinal=2,
        source_id="travel_notes",
        source_md="# 峨眉山\n\n游记",
        quality={"sourceId": "travel_notes", "quality": "A-story", "score": 8},
        platform="travelogue",
        source_category="travelogue",
        url="https://example.com/2",
        title="峨眉山（游记）",
        target_ref="/entity/地点/景区/峨眉山",
    )
    _attach_image(entity_dir / "1.download/sources/02.travel_notes", "emei_2")
    issues = gate_download(TASK)
    assert issues == [], issues
    assert (execution_root(TASK) / "entities").is_dir()


def test_gate_download_accepts_frozen_authority_title_alias():
    """Frozen selection and downloaded source units must use one authority binding."""
    ensure_execution_layout(TASK)
    entity_dir = execution_entity_object_dir(TASK, "地点", "打卡地", "嘉兴梅湾街")
    _write_verified_homepage_source(
        entity_dir,
        entity_name="嘉兴梅湾街",
        source_id="home_wikipedia",
        asset_name="meiwan_1",
        source_title="梅湾街",
        qualified_authority_title="梅湾街",
    )

    issues = gate_download(TASK)

    assert issues == [], issues


def test_frozen_authority_title_survives_plan_to_source_unit_projection():
    """The bound authority title must survive the actual plan-to-unit adapter."""
    ensure_execution_layout(TASK)
    entity_dir = execution_entity_object_dir(TASK, "地点", "打卡地", "嘉兴梅湾街")
    plan_path = entity_dir / "1.download" / "homepage_source_plan.json"
    write_json(
        plan_path,
        {
            "sources": [
                {
                    "source_id": "home_wikipedia",
                    "platform": "维基百科",
                    "url": "https://zh.wikipedia.org/wiki/%E6%A2%85%E6%B9%BE%E8%A1%97",
                    "sourceKind": "wikipedia",
                    "sourceTitle": "梅湾街",
                    "qualifiedAuthorityTitle": "梅湾街",
                    "extractor": "wikipedia_api",
                    "policyRevision": "encyclopedia-primary",
                    "category": "encyclopedia",
                    "sourceRole": "primary",
                }
            ]
        },
    )

    sources = curated_sources_for_entity(
        TASK,
        "嘉兴梅湾街",
        "地点/打卡地",
        research_lane="homepage",
    )

    assert sources[0]["qualifiedAuthorityTitle"] == "梅湾街"
    manifest = write_source_unit(
        entity_dir,
        ordinal=1,
        source_id="home_wikipedia",
        source_md="# 梅湾街\n\n梅湾街位于嘉兴市，是当地历史街区。",
        quality={"sourceId": "home_wikipedia", "quality": "B-fact", "score": 5},
        platform="Wikipedia",
        source_category="encyclopedia",
        source_kind="wikipedia",
        extractor="wikipedia_api",
        policy_revision="encyclopedia-primary",
        research_lane="homepage",
        url=sources[0]["url"],
        title="梅湾街",
        target_ref="/entity/地点/打卡地/嘉兴梅湾街",
        source=sources[0],
    )
    assert manifest["qualifiedAuthorityTitle"] == "梅湾街"


def test_current_wikipedia_article_source_projects_complete_research_attribution():
    """Current registry identity must reach the source unit used by publish."""
    ensure_execution_layout(TASK)
    entity_dir = execution_entity_object_dir(TASK, "地点", "景区", "青城山")
    source_url = "https://zh.wikipedia.org/wiki/%E9%9D%92%E5%9F%8E%E5%B1%B1"

    manifest = write_source_unit(
        entity_dir,
        ordinal=1,
        source_id="article_frontier_wikipedia",
        source_md="# 青城山\n\n青城山位于四川省。",
        quality={
            "sourceId": "article_frontier_wikipedia",
            "quality": "B-fact",
            "score": 5,
        },
        platform="维基百科",
        source_category="encyclopedia",
        source_kind="encyclopedia",
        extractor="wikipedia_api",
        policy_revision="article-source-registry-v1",
        research_lane="article",
        source_use_mode="factual_reference_only",
        publish_media_mode="illustrated",
        source_role="base",
        image_evidence_mode="same_source",
        url=source_url,
        title="青城山",
        target_ref="/entity/地点/景区/青城山",
        source={
            "articleSiteId": "wikipedia_zh",
            "sourceDiscoveryProfileDigest": "sha256:" + "1" * 64,
            "articleCommercialAdmission": "commercial_release",
            "fetchedAt": "2026-08-15T00:00:00Z",
        },
    )

    attribution = manifest["sourceAttribution"]
    assert attribution["sourcePostUrl"] == source_url
    assert attribution["originalCreatorName"] == "维基百科贡献者"
    assert attribution["publicationAdmission"] == "research_release"
    assert attribution["collectedAt"] == "2026-08-15T00:00:00Z"


def test_commercial_article_binding_survives_plan_to_fetch_projection():
    """Fetch must revalidate the exact frontier profile frozen by research."""
    ensure_execution_layout(TASK)
    entity_dir = execution_entity_object_dir(TASK, "地点", "景区", "峨眉山")
    plan_path = entity_dir / "1.download" / "article_source_plan.json"
    profile_digest = sha256_text("article frontier profile fixture")
    write_json(
        plan_path,
        {
            "sources": [
                {
                    "source_id": "article_frontier_wikivoyage",
                    "platform": "维基导游",
                    "url": "https://zh.wikivoyage.org/wiki/%E5%B3%A8%E7%9C%89%E5%B1%B1",
                    "sourceUseMode": "factual_reference_only",
                    "publishMediaMode": "illustrated",
                    "category": "travelogue",
                    "sourceRole": "base",
                    "imageEvidenceMode": "same_source",
                    "articleCommercialAdmission": "commercial_release",
                    "articleSiteId": "wikivoyage_zh",
                    "sourceDiscoveryProfileDigest": profile_digest,
                    "candidateGate": {"passed": True, "issues": []},
                }
            ]
        },
    )

    sources = curated_sources_for_entity(
        TASK,
        "峨眉山",
        "地点/景区",
        research_lane="article",
    )

    assert sources[0]["publishMediaMode"] == "illustrated"
    assert sources[0]["articleCommercialAdmission"] == "commercial_release"
    assert sources[0]["articleSiteId"] == "wikivoyage_zh"
    assert sources[0]["sourceDiscoveryProfileDigest"] == profile_digest


def test_image_collection_source_catalog_accepts_attribution_contract():

    ensure_execution_layout(TASK)
    entity_dir = execution_entity_object_dir(TASK, "地点", "景区", "乐山大佛")

    manifest = write_source_unit(
        entity_dir,
        ordinal=1,
        source_id="image_collection_1",
        source_md="# 乐山大佛\n\n清权图片来源集合。",
        quality={"sourceId": "image_collection_1", "quality": "B-fact", "score": 1},
        platform="Wikimedia Commons",
        source_category="image_collection",
        source_kind="image_collection",
        extractor="image_collection_download",
        policy_revision="image-collection-attribution",
        source_use_mode="licensed_adaptation",
        research_lane="image",
        license_value="CC BY 4.0",
        url="https://commons.wikimedia.org/wiki/File:Leshan_Giant_Buddha.jpg",
        title="乐山大佛",
        target_ref="/entity/地点/景区/乐山大佛",
        images=[
            {
                "bytes": jpeg_bytes(),
                "url": "https://upload.wikimedia.org/wikipedia/commons/example.jpg",
                "sourceUrl": "https://commons.wikimedia.org/wiki/File:Leshan_Giant_Buddha.jpg",
                "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:Leshan_Giant_Buddha.jpg",
                "license": "CC BY 4.0",
                "credit": "Example photographer",
                "creator": "Example photographer",
                "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
                "authorizationProof": "https://commons.wikimedia.org/wiki/File:Leshan_Giant_Buddha.jpg",
                "usageScope": "app_publish",
                "caption": "乐山大佛",
                "relevance": "乐山大佛",
            }
        ],
        execution_id=TASK,
        build_variants=False,
    )

    assert manifest["researchLane"] == "image"
    assert manifest["hasVideo"] is False
    assert manifest["sourceKind"] == "image_collection"
    assert manifest["assetCount"] == 1
    assert manifest["imagePlacements"] == [
        {
            "fileName": "001_image_collection_1.jpg",
            "caption": "乐山大佛",
            "sourceOrder": 0,
            "placementType": "infoboxLead",
        }
    ]
    assert manifest["assetFunnel"]["candidateCount"] == 1
    assert manifest["assetFunnel"]["keptCount"] == 1


def test_gate_download_blocks_single_source_unit():
    ensure_execution_layout(TASK)
    entity_dir = execution_entity_object_dir(TASK, "地点", "景区", "乐山大佛")
    write_source_unit(
        entity_dir,
        ordinal=1,
        source_id="overview_baike",
        source_md="# 乐山大佛\n\n概述",
        quality={"sourceId": "overview_baike", "quality": "B-fact", "score": 5},
        platform="baike",
        source_category="overview_baike",
        url="https://example.com/3",
        title="乐山大佛（百科）",
        target_ref="/entity/地点/景区/乐山大佛",
    )
    issues = gate_download(TASK)
    assert any(
        issue.code is DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING
        and issue.lane is DataIssueLane.HOMEPAGE
        for issue in issues
    ), issues


def test_gate_download_blocks_reject_only_units():
    ensure_execution_layout(TASK)
    entity_dir = execution_entity_object_dir(TASK, "地点", "景区", "九寨沟")
    write_source_unit(
        entity_dir,
        ordinal=1,
        source_id="probe_1",
        source_md="---\nretained: false\n---\n\nmanual_source_plan_note: 探针页\n",
        quality={"sourceId": "probe_1", "quality": "Reject", "score": 0},
        platform="mafengwo",
        source_category="travelogue",
        url="https://example.com/r1",
        title="探针页1",
        target_ref="/entity/地点/景区/九寨沟",
    )
    write_source_unit(
        entity_dir,
        ordinal=2,
        source_id="probe_2",
        source_md="---\nretained: false\n---\n\nmanual_source_plan_note: 探针页\n",
        quality={"sourceId": "probe_2", "quality": "Reject", "score": 0},
        platform="ctrip",
        source_category="travelogue",
        url="https://example.com/r2",
        title="探针页2",
        target_ref="/entity/地点/景区/九寨沟",
    )
    issues = gate_download(TASK)
    assert any(issue.code is DataIssueCode.SOURCE_RETAINED_SHORTFALL for issue in issues), issues
