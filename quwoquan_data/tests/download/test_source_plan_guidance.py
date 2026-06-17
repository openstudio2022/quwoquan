"""source_plan guidance should include registry hints."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import os

_TMP = tempfile.mkdtemp(prefix="source_plan_guidance_")
os.environ["QWQ_RUNTIME_ROOT"] = _TMP

from _common.io import read_json  # noqa: E402
from _common.paths import batch_root  # noqa: E402
from _common.source_catalog import source_category_coverage  # noqa: E402
from _common.source_unit import resolve_entity_object_dir  # noqa: E402
from download.prepare import prepare_source_plan  # noqa: E402
from download.research_plan import (  # noqa: E402
    _article_base_candidate_limit,
    _candidate_gate,
    _collection_gate,
    _image_window,
    _known_homepage_support_websites,
    _known_official_website,
    _license_allows_app_publish,
    _openverse_images,
    _qunar_travelogue_sources,
    _select_article_plan_sources,
    _source,
    _source_availability_summary,
    _title_matches_entity,
    _wiki_related_titles,
    _wiki_title,
    _wiki_title_matches_entity,
    write_auto_research_plans,
)
import download.research_plan as research_plan_mod  # noqa: E402


def test_prepare_source_plan_includes_registry_guidance_for_travel():
    task = "旅行/地域/四川省/景区/景区全覆盖"
    batch = "guidance_batch"
    entity = {"entityId": "九寨沟", "canonicalName": "九寨沟", "entityType": "景区"}
    prepare_source_plan(task, batch, [entity])
    plan = (
        resolve_entity_object_dir(task, batch, "九寨沟", etype_hint="景区")
        / "1.download"
        / "article_source_plan.json"
    )
    payload = read_json(plan)["payload"]
    assert payload["sourceCategoryGuidance"]["categories"]
    registry = payload["sourceRegistryGuidance"]
    assert registry["fetchableSites"], registry
    assert any(site["siteId"] == "wikipedia_zh" for site in registry["fetchableSites"]), registry
    assert any(site["siteId"] == "mafengwo_travelogue" for site in registry["nonFetchableSites"]), registry


def test_auto_research_source_uses_candidate_image_window():
    images = [
        {"url": f"https://img.example/{index}.jpg", "license": "CC-BY-SA 4.0"}
        for index in range(5)
    ]
    source = _source(
        source_id="article_wikipedia",
        platform="维基百科",
        url="https://zh.wikipedia.org/wiki/九寨沟",
        images=_image_window(images, 2, count=3),
    )
    assert [item["url"] for item in source["imageUrls"]] == [
        "https://img.example/2.jpg",
        "https://img.example/3.jpg",
        "https://img.example/4.jpg",
    ]


def test_source_candidate_gate_rejects_weak_entity_match():
    assert not _title_matches_entity("雅安", "碧峰峡")
    assert not _title_matches_entity("墨泉", "墨石公园")
    source = _source(
        source_id="article_city_substitute",
        platform="维基导游",
        url="https://zh.wikivoyage.org/wiki/雅安",
        category="travelogue",
        discovery_provider="test",
        match_confidence=0.4,
        source_role="base",
    )
    verdict = _candidate_gate(source, entity_id="碧峰峡", lane="article")
    assert not verdict["passed"]
    assert any("matchConfidence" in issue for issue in verdict["issues"])


def test_source_category_coverage_uses_explicit_registry_category():
    coverage = source_category_coverage(
        [
            {
                "platform": "乐山大佛景区管委会",
                "category": "official",
                "url": "https://www.leshan.gov.cn/lsswszf/bmdt/92337825/3e865b0e7eee473a94ee6972e.html",
            },
            {"platform": "维基百科", "category": "encyclopedia"},
            {"platform": "去哪儿攻略", "category": "travelogue"},
        ],
        vertical="travel",
    )
    assert "official" in coverage["coveredCategories"]
    assert "乐山大佛景区管委会" not in coverage["unknownPlatforms"]


def test_wiki_title_skips_empty_exact_page_and_uses_search_page_with_extract():
    original = research_plan_mod._wiki_api

    def fake_wiki_api(_host: str, params: dict) -> dict:
        if params.get("titles") == "碧峰峡" and params.get("prop") != "extracts":
            return {"query": {"pages": {"1": {"pageid": 1, "title": "碧峰峡"}}}}
        if params.get("titles") == "碧峰峡" and params.get("prop") == "extracts":
            return {"query": {"pages": {"1": {"pageid": 1, "title": "碧峰峡", "extract": ""}}}}
        if params.get("list") == "search":
            return {"query": {"search": [{"title": "碧峰峡旅游景区"}]}}
        if params.get("titles") == "碧峰峡旅游景区" and params.get("prop") == "extracts":
            return {"query": {"pages": {"2": {"pageid": 2, "title": "碧峰峡旅游景区", "extract": "可用正文"}}}}
        return {}

    research_plan_mod._wiki_api = fake_wiki_api
    try:
        assert _wiki_title("zh.wikipedia.org", "碧峰峡") == "碧峰峡旅游景区"
    finally:
        research_plan_mod._wiki_api = original


def test_wiki_title_match_rejects_substitute_objects_like_airports():
    assert _wiki_title_matches_entity("碧峰峡旅游景区", "碧峰峡")
    assert _wiki_title_matches_entity("阆中古城", "阆中古城")
    assert not _wiki_title_matches_entity("阆中古城机场", "阆中古城")
    assert not _wiki_title_matches_entity("碧峰峡镇", "碧峰峡")


def test_related_wiki_titles_are_supporting_only_for_museum_parent_topics():
    original = research_plan_mod._wiki_api

    def fake_wiki_api(_host: str, params: dict) -> dict:
        if params.get("list") == "search":
            return {
                "query": {
                    "search": [
                        {"title": "三星堆遗址"},
                        {"title": "广汉市"},
                    ]
                }
            }
        if params.get("titles") == "三星堆遗址" and params.get("prop") == "extracts":
            return {"query": {"pages": {"1": {"title": "三星堆遗址", "extract": "古蜀文明遗址"}}}}
        return {}

    research_plan_mod._wiki_api = fake_wiki_api
    try:
        assert _wiki_related_titles("zh.wikipedia.org", "三星堆博物馆") == ["三星堆遗址"]
        assert _wiki_related_titles("zh.wikipedia.org", "九寨沟") == []
    finally:
        research_plan_mod._wiki_api = original


def test_article_base_rejects_entity_encyclopedia_with_same_source_images():
    image = {
        "url": "https://img.example/1.jpg",
        "license": "CC-BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:Example.jpg",
    }
    source = _source(
        source_id="article_wikipedia_as_base",
        platform="维基百科",
        url="https://zh.wikipedia.org/wiki/九寨沟",
        category="encyclopedia",
        discovery_provider="test",
        match_confidence=0.99,
        source_role="base",
        image_evidence_mode="same_authorized_collection",
        images=[image],
    )
    verdict = _candidate_gate(source, entity_id="九寨沟", lane="article")
    assert not verdict["passed"]
    assert any("article-quality source class" in issue for issue in verdict["issues"])


def test_article_base_accepts_ugc_and_platform_article_source_classes_equally():
    image = {
        "url": "https://img.example/jiuzhai.jpg",
        "license": "CC BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:Jiuzhai.jpg",
        "caption": "九寨沟",
        "relevance": "九寨沟",
    }
    for category, platform in (
        ("ugc_longform", "小红书"),
        ("platform_article", "今日头条"),
        ("vertical_professional", "携程攻略"),
    ):
        verdict = _candidate_gate(
            _source(
                source_id=f"article_{category}_base",
                platform=platform,
                url=f"https://example.com/{category}",
                category=category,
                discovery_provider="test",
                match_confidence=0.94,
                source_role="base",
                images=[image],
                image_evidence_mode="same_authorized_collection",
            ),
            entity_id="九寨沟",
            lane="article",
        )
        assert verdict["passed"], (category, verdict)


def test_image_collection_gate_rejects_mixed_creators():
    collection = {
        "sourceCollectionId": "commons:九寨沟:mixed",
        "creator": "A",
        "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:A.jpg",
        "license": "CC-BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:A.jpg",
        "images": [
            {
                "url": "https://img.example/a.jpg",
                "creator": "A",
                "caption": "九寨沟 A",
                "relevance": "九寨沟 A",
            },
            {
                "url": "https://img.example/b.jpg",
                "creator": "B",
                "caption": "九寨沟 B",
                "relevance": "九寨沟 B",
            },
        ],
    }
    verdict = _collection_gate(collection, entity_id="九寨沟")
    assert not verdict["passed"]
    assert any("multiple creators" in issue for issue in verdict["issues"])


def test_image_collection_gate_rejects_constructed_relevance_without_real_match():
    collection = {
        "sourceCollectionId": "commons:花溪谷:false-positive",
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
                "relevance": "花溪谷 Openverse 授权图片",
            }
        ],
    }
    verdict = _collection_gate(collection, entity_id="花溪谷")
    assert not verdict["passed"]
    assert any("relevance" in issue for issue in verdict["issues"])


def test_image_collection_gate_accepts_verified_entity_alias():
    collection = {
        "sourceCollectionId": "commons:三苏祠:south-gate",
        "creator": "A",
        "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:South_gate_of_Sansu_Shrine.jpg",
        "license": "CC BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:South_gate_of_Sansu_Shrine.jpg",
        "images": [
            {
                "url": "https://img.example/south-gate.jpg",
                "creator": "A",
                "caption": "South gate of Sansu Shrine",
                "relevance": "South gate of Sansu Shrine",
            }
        ],
    }

    without_alias = _collection_gate(collection, entity_id="三苏祠")
    with_alias = _collection_gate(collection, entity_id="三苏祠", entity_aliases=["Sansu Shrine"])

    assert not without_alias["passed"]
    assert with_alias["passed"], with_alias


def test_openverse_filters_nc_nd_and_keeps_publishable_license():
    import download.research_plan as research_mod

    orig_curl_json = research_mod._curl_json
    try:
        research_mod._curl_json = lambda url, timeout=25: {
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
        research_mod._curl_json = orig_curl_json
    assert [image["url"] for image in images] == ["https://img.example/good.jpg"]
    assert images[0]["sourceCollectionId"].startswith("openverse:wikimedia:")


def test_image_rights_rejects_cc_1_license():
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
    verdict = _candidate_gate(
        _source(
            source_id="article_qunar_base_bad_license",
            platform="去哪儿攻略",
            url="https://touch.travel.qunar.com/youji/1",
            category="travelogue",
            discovery_provider="test",
            match_confidence=0.94,
            source_role="base",
            images=[image],
            image_evidence_mode="same_authorized_collection",
        ),
        entity_id="九寨沟",
        lane="article",
    )
    assert not verdict["passed"]
    assert any("unsupported license" in issue for issue in verdict["issues"]), verdict


def test_qunar_travelogue_sources_require_entity_route_and_authorized_image():
    import download.research_plan as research_mod

    orig_curl_json = research_mod._curl_json
    try:
        research_mod._curl_json = lambda url, timeout=20: {
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
            authorized_images=[
                {
                    "url": "https://img.example/good.jpg",
                    "license": "CC BY-SA 4.0",
                    "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                    "authorizationProof": "https://commons.wikimedia.org/wiki/File:Good.jpg",
                }
            ],
            limit=4,
        )
    finally:
        research_mod._curl_json = orig_curl_json
    assert len(sources) == 1
    assert sources[0]["sourceRole"] == "base"
    assert sources[0]["platform"] == "去哪儿攻略"
    assert sources[0]["imageEvidenceMode"] == "same_authorized_collection"


def test_article_base_candidate_limit_has_research_buffer():
    assert _article_base_candidate_limit(1) == 3
    assert _article_base_candidate_limit(4) == 10
    assert _article_base_candidate_limit(10) == 22


def test_article_plan_source_selection_preserves_supporting_categories():
    sources = [
        _source(
            source_id=f"article_qunar_base_{index}",
            platform="去哪儿攻略",
            url=f"https://touch.travel.qunar.com/youji/{index}",
            category="travelogue",
            discovery_provider="test",
            match_confidence=0.95,
            source_role="base",
        )
        for index in range(1, 9)
    ]
    sources.extend(
        [
            _source(
                source_id="article_qunar_review_support",
                platform="去哪儿景点点评",
                url="https://touch.travel.qunar.com/search?q=九寨沟",
                category="review",
                discovery_provider="test",
                match_confidence=0.86,
                source_role="supporting",
            ),
            _source(
                source_id="article_wikipedia_support",
                platform="维基百科",
                url="https://zh.wikipedia.org/wiki/九寨沟",
                category="encyclopedia",
                discovery_provider="test",
                match_confidence=0.99,
                source_role="supporting",
            ),
            _source(
                source_id="article_unesco_support",
                platform="权威媒体",
                url="https://whc.unesco.org/en/list/637",
                category="authoritative_reference",
                discovery_provider="test",
                match_confidence=0.8,
                source_role="supporting",
            ),
        ]
    )
    selected = _select_article_plan_sources(sources, required_article_bases=4)
    categories = {source["category"] for source in selected}
    assert len(selected) <= 13
    assert sum(1 for source in selected if source["sourceRole"] == "base") == 8
    assert {"travelogue", "review", "encyclopedia"}.issubset(categories)


def test_homepage_core_sources_are_capped_at_five_and_encyclopedia_first():
    from download.research_plan import _homepage_core_sources

    sources = [
        _source(
            source_id="home_official",
            platform="景区官网",
            url="https://example.com/official",
            category="official",
            discovery_provider="test",
            match_confidence=0.96,
        ),
        _source(
            source_id="home_wikipedia",
            platform="维基百科",
            url="https://zh.wikipedia.org/wiki/九寨沟",
            category="encyclopedia",
            discovery_provider="test",
            match_confidence=0.99,
        ),
        _source(
            source_id="home_baidu",
            platform="百度百科",
            url="https://baike.baidu.com/item/九寨沟",
            category="encyclopedia",
            discovery_provider="test",
            match_confidence=0.86,
        ),
        _source(
            source_id="home_sogou",
            platform="搜狗百科",
            url="https://baike.sogou.com/v?query=九寨沟",
            category="encyclopedia",
            discovery_provider="test",
            match_confidence=0.78,
        ),
        _source(
            source_id="home_support_gov",
            platform="文旅局",
            url="https://example.gov.cn/jiuzhai",
            category="official",
            discovery_provider="test",
            match_confidence=0.8,
        ),
        _source(
            source_id="home_media",
            platform="权威媒体",
            url="https://example.com/media",
            category="authoritative_reference",
            discovery_provider="test",
            match_confidence=0.8,
        ),
    ]
    selected = _homepage_core_sources(sources)
    assert len(selected) == 5
    assert selected[0]["source_id"] == "home_wikipedia"
    assert "home_media" not in {source["source_id"] for source in selected}


def test_source_unit_image_collection_id_is_global_not_local_source_id():
    from download.handler import _stable_source_image_collection_id

    cid = _stable_source_image_collection_id(
        entity_id="毕棚沟",
        source_id="article_qunar_base_1",
        spec={
            "sourceCollectionId": "article:article_qunar_base_1",
            "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:Bipenggou.jpg",
            "authorizationProof": "https://commons.wikimedia.org/wiki/File:Bipenggou.jpg",
        },
    )

    assert cid.startswith("source_image:毕棚沟:")
    assert cid != "article:article_qunar_base_1"


def test_source_unit_image_collection_id_prefers_file_proof_over_category_page():
    from download.handler import _stable_source_image_collection_id

    common_category = "https://commons.wikimedia.org/wiki/Category%3AMount_Qingcheng"
    cid_a = _stable_source_image_collection_id(
        entity_id="青城山",
        source_id="article_qunar_base_3",
        spec={
            "collectionPageUrl": common_category,
            "authorizationProof": "https://commons.wikimedia.org/wiki/File:Mount_Qingcheng_A.jpg",
            "sourceUrl": "https://commons.wikimedia.org/wiki/File:Mount_Qingcheng_A.jpg",
        },
    )
    cid_b = _stable_source_image_collection_id(
        entity_id="青城山",
        source_id="article_qunar_base_4",
        spec={
            "collectionPageUrl": common_category,
            "authorizationProof": "https://commons.wikimedia.org/wiki/File:Mount_Qingcheng_B.jpg",
            "sourceUrl": "https://commons.wikimedia.org/wiki/File:Mount_Qingcheng_B.jpg",
        },
    )

    assert cid_a != cid_b


def test_parallel_auto_research_writes_availability_report():
    import download.research_plan as research_mod

    task = "旅行/地域/测试省/景区/景区全覆盖"
    batch = "parallel_source_discover"
    good_image = {
        "url": "https://img.example/good.jpg",
        "license": "CC BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:Good.jpg",
        "width": 1600,
        "height": 1000,
        "caption": "可用景区",
        "relevance": "可用景区",
        "creator": "Good",
        "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:Good.jpg",
    }
    second_good_image = {**good_image, "url": "https://img.example/good-2.jpg", "caption": "可用景区 2", "relevance": "可用景区 2"}
    originals = {
        "_wiki_title": research_mod._wiki_title,
        "_wikidata_item_for_zhwiki": research_mod._wikidata_item_for_zhwiki,
        "_wikidata_item_for_entity_search": research_mod._wikidata_item_for_entity_search,
        "_wikidata_commons_images": research_mod._wikidata_commons_images,
        "_official_website": research_mod._official_website,
        "_commons_images": research_mod._commons_images,
        "_openverse_images": research_mod._openverse_images,
        "_mediawiki_page_images": research_mod._mediawiki_page_images,
        "_trusted_external_links": research_mod._trusted_external_links,
        "_qunar_travelogue_sources": research_mod._qunar_travelogue_sources,
    }

    def fake_wiki_title(host: str, entity_id: str) -> str:
        if entity_id == "可用景区" and host == "zh.wikipedia.org":
            return entity_id
        return ""

    def fake_qunar(entity_id: str, *, authorized_images: list[dict], limit: int = 4):
        if entity_id != "可用景区":
            return []
        return [
            _source(
                source_id=f"article_qunar_base_{index}",
                platform="去哪儿攻略",
                url=f"https://touch.travel.qunar.com/youji/{index}",
                category="travelogue",
                discovery_provider="test",
                match_confidence=0.95,
                source_role="base",
                images=[good_image],
                image_evidence_mode="same_authorized_collection",
            )
            for index in range(1, 3)
        ]

    try:
        research_mod._wiki_title = fake_wiki_title
        research_mod._wikidata_item_for_zhwiki = lambda title: ""
        research_mod._wikidata_item_for_entity_search = lambda entity_id: ""
        research_mod._wikidata_commons_images = (
            lambda qid, entity_id, entity_aliases=(), limit=10: []
        )
        research_mod._official_website = lambda qid: ""
        research_mod._commons_images = lambda entity_id, limit=10: [good_image, second_good_image] if entity_id == "可用景区" else []
        research_mod._openverse_images = lambda entity_id, limit=12: []
        research_mod._mediawiki_page_images = (
            lambda host, title, entity_id, limit=6: [good_image] if entity_id == "可用景区" and title else []
        )
        research_mod._trusted_external_links = lambda title, limit=4: []
        research_mod._qunar_travelogue_sources = fake_qunar
        progress_events: list[dict] = []
        report = write_auto_research_plans(
            task,
            batch,
            ["可用景区", "缺源景区"],
            entity_type="景区",
            force=True,
            max_workers=2,
            progress_callback=progress_events.append,
        )
    finally:
        for name, value in originals.items():
            setattr(research_mod, name, value)
    availability = report["sourceAvailability"]
    assert availability["readyTargets"] == ["可用景区"]
    assert [item["entityId"] for item in availability["ineligibleTargets"]] == ["缺源景区"]
    assert report["throughput"]["maxWorkers"] == 2
    assert progress_events[0]["status"] == "running"
    assert progress_events[-1]["status"] == "succeeded"
    assert progress_events[-1]["completedCount"] == 2
    progress = read_json(batch_root(task, batch) / "_shared" / "auto_research_progress.json")
    assert progress["status"] == "succeeded"
    assert progress["entityCount"] == 2
    assert progress["workers"] == 2
    persisted = read_json(batch_root(task, batch) / "_shared" / "source_unavailable_targets.json")
    assert persisted["ineligibleTargets"][0]["entityId"] == "缺源景区"


def test_auto_research_uses_related_encyclopedia_to_complete_museum_article_categories():
    import download.research_plan as research_mod

    task = "旅行/地域/测试省/景区/博物馆覆盖"
    batch = "museum_related_support"
    entity = "三星堆博物馆"
    good_image = {
        "url": "https://img.example/sanxingdui.jpg",
        "license": "CC BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:Sanxingdui.jpg",
        "width": 1600,
        "height": 1000,
        "caption": entity,
        "relevance": entity,
        "creator": "Good",
        "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:Sanxingdui.jpg",
    }
    originals = {
        "_wiki_title": research_mod._wiki_title,
        "_wiki_related_titles": research_mod._wiki_related_titles,
        "_wikidata_item_for_zhwiki": research_mod._wikidata_item_for_zhwiki,
        "_wikidata_item_for_entity_search": research_mod._wikidata_item_for_entity_search,
        "_wikidata_commons_images": research_mod._wikidata_commons_images,
        "_official_website": research_mod._official_website,
        "_commons_images": research_mod._commons_images,
        "_openverse_images": research_mod._openverse_images,
        "_mediawiki_page_images": research_mod._mediawiki_page_images,
        "_trusted_external_links": research_mod._trusted_external_links,
        "_qunar_travelogue_sources": research_mod._qunar_travelogue_sources,
    }

    def fake_qunar(entity_id: str, *, authorized_images: list[dict], limit: int = 4):
        assert entity_id == entity
        return [
            _source(
                source_id=f"article_qunar_base_{index}",
                platform="去哪儿攻略",
                url=f"https://touch.travel.qunar.com/youji/{index}",
                category="travelogue",
                discovery_provider="test",
                match_confidence=0.95,
                source_role="base",
                images=[good_image],
                image_evidence_mode="same_authorized_collection",
            )
            for index in range(1, 5)
        ]

    try:
        research_mod._wiki_title = lambda host, entity_id: ""
        research_mod._wiki_related_titles = (
            lambda host, entity_id, limit=3: ["三星堆遗址"] if entity_id == entity else []
        )
        research_mod._wikidata_item_for_zhwiki = lambda title: ""
        research_mod._wikidata_item_for_entity_search = lambda entity_id: ""
        research_mod._wikidata_commons_images = (
            lambda qid, entity_id, entity_aliases=(), limit=10: []
        )
        research_mod._official_website = lambda qid: ""
        research_mod._commons_images = lambda entity_id, limit=10: [good_image]
        research_mod._openverse_images = lambda entity_id, limit=12: []
        research_mod._mediawiki_page_images = lambda host, title, entity_id, limit=6: []
        research_mod._trusted_external_links = lambda title, limit=4: []
        research_mod._qunar_travelogue_sources = fake_qunar
        report = write_auto_research_plans(
            task,
            batch,
            [entity],
            entity_type="景区",
            force=True,
            lanes={"article"},
        )
    finally:
        for name, value in originals.items():
            setattr(research_mod, name, value)

    assert report["issues"] == []
    assert report["sourceAvailability"]["readyTargets"] == [entity]
    plan = (
        resolve_entity_object_dir(task, batch, entity, etype_hint="景区")
        / "1.download"
        / "article_source_plan.json"
    )
    sources = read_json(plan)["payload"]["sources"]
    assert any(source["source_id"] == "article_related_encyclopedia_support_1" for source in sources)
    assert {
        source["category"]
        for source in sources
    } >= {"travelogue", "review", "encyclopedia"}


def test_auto_research_image_lane_prefers_non_homepage_alias_matched_image():
    import download.research_plan as research_mod

    task = "旅行/地域/测试省/景区/图库隔离"
    batch = "image_avoids_homepage"
    entity = "三苏祠"
    home_image = {
        "url": "https://img.example/home.jpg",
        "license": "CC BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:Sansu_home.jpg",
        "width": 1600,
        "height": 1000,
        "caption": entity,
        "relevance": entity,
        "creator": "A",
        "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:Sansu_home.jpg",
    }
    image_work = {
        "url": "https://img.example/south-gate.jpg",
        "license": "CC BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:South_gate_of_Sansu_Shrine.jpg",
        "width": 1600,
        "height": 1000,
        "caption": "South gate of Sansu Shrine",
        "relevance": "South gate of Sansu Shrine",
        "creator": "B",
        "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:South_gate_of_Sansu_Shrine.jpg",
    }
    originals = {
        "_wiki_title": research_mod._wiki_title,
        "_wikidata_item_for_zhwiki": research_mod._wikidata_item_for_zhwiki,
        "_wikidata_item_for_entity_search": research_mod._wikidata_item_for_entity_search,
        "_wikidata_entity_aliases": research_mod._wikidata_entity_aliases,
        "_wikidata_commons_images": research_mod._wikidata_commons_images,
        "_official_website": research_mod._official_website,
        "_commons_images": research_mod._commons_images,
        "_openverse_images": research_mod._openverse_images,
        "_mediawiki_page_images": research_mod._mediawiki_page_images,
        "_trusted_external_links": research_mod._trusted_external_links,
        "_qunar_travelogue_sources": research_mod._qunar_travelogue_sources,
    }
    try:
        research_mod._wiki_title = lambda host, entity_id: entity if host == "zh.wikipedia.org" else ""
        research_mod._wikidata_item_for_zhwiki = lambda title: "Q10866733"
        research_mod._wikidata_item_for_entity_search = lambda entity_id: "Q10866733"
        research_mod._wikidata_entity_aliases = lambda qid: ["Sansu Shrine"]
        research_mod._wikidata_commons_images = lambda qid, entity_id, entity_aliases=(), limit=10: []
        research_mod._official_website = lambda qid: ""
        research_mod._commons_images = lambda entity_id, limit=10: [home_image, image_work]
        research_mod._openverse_images = lambda entity_id, limit=12: []
        research_mod._mediawiki_page_images = (
            lambda host, title, entity_id, limit=6: [home_image] if host == "zh.wikipedia.org" else []
        )
        research_mod._trusted_external_links = lambda title, limit=4: []
        research_mod._qunar_travelogue_sources = lambda entity_id, authorized_images, limit=4: []
        report = write_auto_research_plans(
            task,
            batch,
            [entity],
            entity_type="景区",
            force=True,
            lanes={"image"},
        )
    finally:
        for name, value in originals.items():
            setattr(research_mod, name, value)

    assert report["issues"] == []
    plan = (
        resolve_entity_object_dir(task, batch, entity, etype_hint="景区")
        / "1.download"
        / "image_source_plan.json"
    )
    collections = read_json(plan)["payload"]["collections"]
    assert collections[0]["images"][0]["url"] == "https://img.example/south-gate.jpg"


def test_source_availability_summary_marks_failed_candidate_ineligible():
    report = {
        "issues": [],
        "sourceUnavailable": [],
        "candidates": [
            {
                "entityId": "九寨沟",
                "lane": "article",
                "source_id": "article_qunar_base_15",
                "passed": False,
                "issues": ["imageRights: unsupported license CC BY-SA 1.0"],
            }
        ],
    }
    summary = _source_availability_summary(report, ["九寨沟", "都江堰"])
    assert summary["readyTargets"] == ["都江堰"]
    assert summary["ineligibleTargets"][0]["entityId"] == "九寨沟"
    assert "article" in summary["ineligibleTargets"][0]["lanes"]
    assert "unsupported license" in "\n".join(summary["ineligibleTargets"][0]["issues"])


def test_known_official_site_registry_covers_previous_missing_official_sources():
    assert _known_official_website("毕棚沟") == "http://www.bipenggou.net/"
    assert _known_official_website("碧峰峡") == "http://www.bifengxia.com/info?crid=74&lan=cn&ckey=jqgk_dfbfx"
    assert _known_official_website("蜀南竹海") == "https://www.snzh.cn/"
    assert _known_official_website("海螺沟") == "https://www.hailuogou.com/"
    assert _known_official_website("青城山") == "https://www.djy517.com/"
    assert _known_official_website("乐山大佛") == ""
    support = _known_homepage_support_websites("碧峰峡")
    assert {row["source_id"] for row in support} >= {
        "home_official_ecology",
        "home_official_panda_base",
    }
    leshan_support = _known_homepage_support_websites("乐山大佛")
    assert any(
        row["source_id"] == "home_official_leshan_committee"
        and row["category"] == "official"
        and row["platform"] == "乐山大佛景区管委会"
        for row in leshan_support
    )


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"source plan guidance tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
