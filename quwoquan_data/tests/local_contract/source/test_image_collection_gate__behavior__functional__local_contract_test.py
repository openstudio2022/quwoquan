from __future__ import annotations



from support.source_plan_guidance_fixtures import *  # noqa: F401,F403
from content.source.handler_fetch_media import _source_collection_title




def test_image_collection_source_title_never_falls_back_to_internal_identity():
    image = {
        "sourceCollectionId": "open_license_file:test-entity:internal-digest",
        "caption": "测试实体甲山谷中的溪流",
    }

    assert _source_collection_title(image) == ""
    assert _source_collection_title({**image, "title": "山谷溪流"}) == "山谷溪流"


def test_image_collection_gate_rejects_mixed_creators():
    collection = {
        "sourceCollectionId": "commons:测试实体甲:mixed",
        "creator": "A",
        "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:A.jpg",
        "license": "CC-BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:A.jpg",
        "images": [
            {
                "url": "https://img.example/a.jpg",
                "creator": "A",
                "caption": "测试实体甲 A",
                "relevance": "测试实体甲 A",
            },
            {
                "url": "https://img.example/b.jpg",
                "creator": "B",
                "caption": "测试实体甲 B",
                "relevance": "测试实体甲 B",
            },
        ],
    }
    verdict = _collection_gate(
        collection, entity_id="测试实体甲", vertical="travel"
    )
    assert not verdict["passed"]
    assert any("multiple creators" in issue for issue in verdict["issues"])

def test_image_collection_gate_rejects_constructed_relevance_without_real_match():
    collection = {
        "sourceCollectionId": "commons:测试实体甲:false-positive",
        "creator": "A",
        "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:%E7%B2%97%E5%9D%91.jpg",
        "license": "CC BY 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:%E7%B2%97%E5%9D%91.jpg",
        "images": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/b/b9/%E7%B2%97%E5%9D%91.jpg",
                "creator": "A",
                "caption": "粗坑在蘇澳永樂里境內",
                "relevance": "测试实体甲 Openverse licensed image",
            }
        ],
    }
    verdict = _collection_gate(
        collection, entity_id="测试实体甲", vertical="travel"
    )
    assert not verdict["passed"]
    assert any("relevance" in issue for issue in verdict["issues"])

def test_image_collection_gate_rejects_prior_collection_id_only_match():
    collection = {
        "sourceCollectionId": "open_license_file:测试实体甲:regional_icon",
        "creator": "Waltigs",
        "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:Henan-icon09.jpg",
        "platform": "Wikimedia Commons",
        "license": "CC BY-SA 3.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/3.0",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:Henan-icon09.jpg",
        "usageScope": "app_publish",
        "images": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/3/33/Henan-icon09.jpg",
                "caption": "Map of Henan Province, China",
                "relevance": "Map of Henan Province, China",
                "width": 1000,
                "height": 890,
            }
        ],
    }

    verdict = _collection_gate(
        collection,
        entity_id="测试实体甲",
        allow_verified_collection_id_match=False,
        vertical="travel",
    )
    assert not verdict["passed"]
    assert any("relevance" in issue for issue in verdict["issues"])
    assert not _collection_admissible_image_urls(
        [collection],
        entity_id="测试实体甲",
        vertical="travel",
    )

def test_image_collection_gate_rejects_same_name_from_other_region():
    collection = {
        "sourceCollectionId": "open_license_file:测试实体甲:other-region",
        "creator": "Example creator",
        "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:Other_region.jpg",
        "platform": "Wikimedia Commons",
        "license": "CC BY-SA 3.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/3.0/",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:wrong.jpg",
        "usageScope": "app_publish",
        "modelReleaseStatus": "not_required",
        "images": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/wrong.jpg",
                "creator": "Example creator",
                "caption": "other-region reservoir with a duplicated local name",
                "relevance": "other-region reservoir with a duplicated local name",
                "width": 1600,
                "height": 900,
            }
        ],
    }

    verdict = _collection_gate(
        collection, entity_id="测试实体甲", vertical="travel"
    )

    assert not verdict["passed"]
    assert any("relevance" in issue for issue in verdict["issues"])

def test_image_collection_gate_rejects_garbled_500px_caption():
    collection = {
        "sourceCollectionId": "open_license_file:测试实体甲:garbled_caption",
        "creator": "无相",
        "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:%E5%85%89%E9%9B%BE%E5%B1%B1.jpg",
        "platform": "Wikimedia Commons",
        "license": "CC BY 3.0",
        "termsUrl": "https://creativecommons.org/licenses/by/3.0/",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:%E5%85%89%E9%9B%BE%E5%B1%B1.jpg",
        "usageScope": "app_publish",
        "images": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/guangwushan.jpg",
                "creator": "无相",
                "caption": "500px provided description: ???????????????????????????????? [#?? ,#??]",
                "relevance": "500px provided description: ???????????????????????????????? [#?? ,#??]",
                "width": 1400,
                "height": 937,
            }
        ],
    }

    verdict = _collection_gate(
        collection, entity_id="测试实体甲", vertical="travel"
    )

    assert not verdict["passed"]
    assert any("imageCaption" in issue for issue in verdict["issues"])

def test_image_collection_gate_rejects_oversized_assets_before_fetch():
    collection = {
        "sourceCollectionId": "commons:测试实体甲:oversized",
        "creator": "A",
        "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:Oversized.jpg",
        "platform": "Wikimedia Commons",
        "license": "CC BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:Oversized.jpg",
        "usageScope": "app_publish",
        "images": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/oversized.jpg",
                "creator": "A",
                "caption": "测试实体甲 scenic view",
                "relevance": "测试实体甲 scenic view",
                "width": 12000,
                "height": 9000,
            }
        ],
    }

    verdict = _collection_gate(
        collection, entity_id="测试实体甲", vertical="travel"
    )

    assert not verdict["passed"]
    assert any("pixelCount" in issue for issue in verdict["issues"])


def test_image_collection_gate_rejects_non_place_specimen_subject():
    collection = {
        "sourceCollectionId": "commons:entity-a:specimen",
        "creator": "Research contributor",
        "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:Specimen.jpg",
        "platform": "Wikimedia Commons",
        "license": "CC BY 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:Specimen.jpg",
        "usageScope": "app_publish",
        "images": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/specimen.jpg",
                "creator": "Research contributor",
                "caption": "Test Entity A holotype in dorsal view",
                "relevance": "Test Entity A scientific specimen",
                "width": 1512,
                "height": 1382,
            }
        ],
    }

    verdict = _collection_gate(
        collection, entity_id="Test Entity A", vertical="travel"
    )

    assert not verdict["passed"]
    assert any("not representative" in issue for issue in verdict["issues"])


def test_image_collection_gate_accepts_place_habitat_despite_species_context():
    collection = {
        "sourceCollectionId": "commons:entity-a:habitat",
        "creator": "Research contributor",
        "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:Habitat.jpg",
        "platform": "Wikimedia Commons",
        "license": "CC BY 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:Habitat.jpg",
        "usageScope": "app_publish",
        "modelReleaseStatus": "not_required",
        "images": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/habitat.jpg",
                "creator": "Research contributor",
                "caption": "Test Entity A habitat landscape and forest stream",
                "relevance": "type locality habitat of a species sp. nov.",
                "width": 1512,
                "height": 1071,
            }
        ],
    }

    verdict = _collection_gate(
        collection, entity_id="Test Entity A", vertical="travel"
    )

    assert verdict["passed"], verdict

def test_image_collection_gate_accepts_verified_entity_alias():
    collection = {
        "sourceCollectionId": "commons:collection-a:main-entrance",
        "creator": "A",
        "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:South_gate_of_Sansu_Shrine.jpg",
        "license": "CC BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:South_gate_of_Sansu_Shrine.jpg",
        "usageScope": "app_publish",
        "modelReleaseStatus": "not_required",
        "images": [
            {
                "url": "https://img.example/south-gate.jpg",
                "creator": "A",
                "caption": "Main entrance of Example Landmark",
                "relevance": "Main entrance of Example Landmark",
            }
        ],
    }

    without_alias = _collection_gate(
        collection, entity_id="subject-z", vertical="travel"
    )
    with_alias = _collection_gate(
        collection,
        entity_id="subject-z",
        entity_aliases=["Example Landmark"],
        vertical="travel",
    )

    assert not without_alias["passed"]
    assert with_alias["passed"], with_alias

def test_image_collection_gate_rejects_unmatched_alias_collision():
    collection = {
        "sourceCollectionId": "commons:测试实体甲:other-target",
        "creator": "A",
        "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:NationalPalace_MuseumFrontView.jpg",
        "platform": "Wikimedia Commons",
        "license": "CC BY 3.0",
        "termsUrl": "https://creativecommons.org/licenses/by/3.0/",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:NationalPalace_MuseumFrontView.jpg",
        "usageScope": "app_publish",
        "modelReleaseStatus": "not_required",
        "images": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/b/b4/NationalPalace_MuseumFrontView.jpg",
                "creator": "A",
                "caption": "Other Target Museum, remote region.",
                "relevance": "Other Target Museum, remote region.",
            }
        ],
    }

    verdict = _collection_gate(
        collection,
        entity_id="测试实体甲",
        entity_aliases=["Test Entity A Museum"],
        vertical="travel",
    )

    assert not verdict["passed"]
    assert any("relevance" in issue for issue in verdict["issues"])

def test_image_collection_gate_accepts_core_name_from_english_scenic_alias():
    aliases = _expanded_entity_aliases(["Test Entity Alias Scenic Area"])
    collection = {
        "sourceCollectionId": "commons:entity-a:air",
        "creator": "A",
        "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:Wutai_Shan_from_the_air.jpg",
        "license": "CC BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:Wutai_Shan_from_the_air.jpg",
        "usageScope": "app_publish",
        "modelReleaseStatus": "not_required",
        "images": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/7/70/Wutai_Shan_from_the_air.jpg",
                "creator": "A",
                "caption": "Test Entity Alias from the air",
                "relevance": "Test Entity Alias from the air",
            }
        ],
    }

    assert "Test Entity Alias" in aliases
    verdict = _collection_gate(
        collection,
        entity_id="entity-a",
        entity_aliases=aliases,
        vertical="travel",
    )
    assert verdict["passed"], verdict

def test_openverse_filters_nc_nd_and_keeps_publishable_license():
    import content.source.research.network_io as research_mod

    orig_curl_json = research_mod.curl_json
    try:
        research_mod.curl_json = lambda url, timeout=25: {
            "results": [
                {
                    "id": "bad",
                    "title": "毕棚沟",
                    "foreign_landing_url": "https://www.flickr.com/bad",
                    "url": "https://img.example/bad.jpg",
                    "creator": "Bad",
                    "license": "by-nc-nd",
                    "license_version": "2.0",
                    "license_url": "https://creativecommons.org/licenses/by-nc-nd/2.0/",
                    "provider": "flickr",
                    "height": 1200,
                    "width": 1800,
                },
                {
                    "id": "good",
                    "title": "毕棚沟 秋色",
                    "foreign_landing_url": "https://commons.wikimedia.org/wiki/File:Good.jpg",
                    "url": "https://img.example/good.jpg",
                    "creator": "Good",
                    "license": "by-sa",
                    "license_version": "4.0",
                    "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
                    "provider": "wikimedia",
                    "height": 1200,
                    "width": 1800,
                },
            ]
        }
        images = _openverse_images("毕棚沟", limit=3)
    finally:
        research_mod.curl_json = orig_curl_json
    assert [image["url"] for image in images] == ["https://img.example/good.jpg"]
    assert images[0]["sourceCollectionId"].startswith("openverse:wikimedia:")

def test_article_candidate_warns_on_bad_optional_image_but_image_lane_blocks_it():
    assert _license_allows_app_publish(
        "CC0",
        "http://creativecommons.org/publicdomain/zero/1.0/deed.en",
    )
    assert not _license_allows_app_publish(
        "CC BY-SA 1.0",
        "https://creativecommons.org/licenses/by-sa/1.0/",
    )
    image = {
        "url": "https://img.example/jiuzhai.jpg",
        "license": "CC BY-SA 1.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/1.0/",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:Jiuzhai.jpg",
        "caption": "九寨沟",
        "relevance": "九寨沟",
    }
    article_verdict = _candidate_gate(
        _source(
            source_id="article_qunar_base_bad_license",
            platform="去哪儿攻略",
            url="https://touch.travel.qunar.com/youji/1",
            category="travelogue",
            discovery_provider="test",
            match_confidence=0.94,
            source_role="base",
            images=[image],
            # RC4：文章配图必须同源；此处模拟「底稿自身」含一张许可不达标的图——
            # 文章 lane 仅告警（可降级 text_only/跳过该图），image lane 则硬阻断。
            image_evidence_mode="same_source",
        ),
        entity_id="九寨沟",
        lane="article",
        vertical="travel",
    )
    assert article_verdict["passed"]
    assert any("unsupported license" in issue for issue in article_verdict["warnings"]), article_verdict
    travel_image_verdict = _candidate_gate(
        _source(
            source_id="image_audit_only_license",
            platform="Wikimedia Commons",
            url="https://commons.wikimedia.org/wiki/File:Jiuzhai.jpg",
            category="open_license",
            discovery_provider="test",
            match_confidence=0.94,
            source_role="supporting",
            images=[image],
            image_evidence_mode="same_source",
        ),
        entity_id="九寨沟",
        lane="image",
        vertical="travel",
    )
    assert travel_image_verdict["passed"], travel_image_verdict
    assert any(
        "unsupported license" in issue
        for issue in travel_image_verdict["warnings"]
    ), travel_image_verdict
    verdict = _candidate_gate(
        _source(
            source_id="image_bad_license",
            platform="Wikimedia Commons",
            url="https://commons.wikimedia.org/wiki/File:Jiuzhai.jpg",
            category="open_license",
            discovery_provider="test",
            match_confidence=0.94,
            source_role="supporting",
            images=[image],
            image_evidence_mode="same_source",
        ),
        entity_id="九寨沟",
        lane="image",
        vertical="photography",
    )
    assert not verdict["passed"]
    assert any("unsupported license" in issue for issue in verdict["issues"]), verdict

def test_qunar_travelogue_sources_require_entity_route_and_stay_text_only():
    import content.source.research.network_io as research_mod

    orig_curl_json = research_mod.curl_json
    try:
        research_mod.curl_json = lambda url, timeout=20: {
            "data": {
                "more": False,
                "bookList": [
                    {
                        "id": 1,
                        "title": "大美阿坝",
                        "travelRoute": ["九寨沟"],
                        "userName": "甲",
                    },
                    {
                        "id": 2,
                        "title": "秋假追雪毕棚沟",
                        "travelRoute": ["毕棚沟", "磐羊湖"],
                        "userName": "乙",
                        "routeDays": 1,
                    },
                ],
            }
        }
        sources = _qunar_travelogue_sources(
            "毕棚沟",
            limit=4,
        )
    finally:
        research_mod.curl_json = orig_curl_json
    assert len(sources) == 1
    assert sources[0]["sourceRole"] == "base"
    assert sources[0]["platform"] == "去哪儿攻略"
    # RC4：UGC 游记是 text-only 文章底稿，绝不携带跨源「授权图集」替代图——
    # imageEvidenceMode 恒为空（同源忠实，无假图；已删除 authorized_images 死参）。
    assert sources[0]["imageEvidenceMode"] == ""
