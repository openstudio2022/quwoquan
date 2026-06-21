"""source_plan guidance should include registry hints."""
from __future__ import annotations

import sys
import tempfile
import urllib.parse
import shutil
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

from _common.io import read_json, write_json  # noqa: E402
from _common.content_evidence import score_source_markdown  # noqa: E402
from _common.paths import batch_root  # noqa: E402
from _common.source_catalog import source_category_coverage  # noqa: E402
from _common.source_unit import resolve_entity_object_dir  # noqa: E402
from download.prepare import prepare_source_plan  # noqa: E402
from task import store  # noqa: E402
from download.research_plan import (  # noqa: E402
    _article_base_candidate_limit,
    _candidate_gate,
    _collection_gate,
    _collection_publishable_image_urls,
    _download_reject_memory,
    _expanded_entity_aliases,
    _external_article_category,
    _external_platform,
    _homepage_can_seed_base_draft,
    _image_window,
    _known_article_sources,
    _known_entity_aliases,
    _known_homepage_support_websites,
    _known_official_website,
    _license_allows_app_publish,
    _openverse_images,
    _qunar_travelogue_sources,
    _safe_collection_id,
    _select_article_plan_sources,
    _source,
    _source_availability_summary,
    _source_reject_should_enter_memory,
    _title_matches_entity,
    _url_looks_like_article,
    _travel_registry_url_fetchable,
    _verified_homepage_sources_from_source_units,
    _wiki_related_titles,
    _wiki_title,
    _wiki_title_for_entity,
    _wiki_title_matches_entity,
    write_auto_research_plans,
)
import download.research_plan as research_plan_mod  # noqa: E402


def test_auto_research_curl_defaults_support_public_api_scale_probe():
    assert research_plan_mod._AUTO_RESEARCH_CURL_TIMEOUT_SECONDS >= 25
    assert research_plan_mod._AUTO_RESEARCH_CURL_RETRIES >= 1


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
    assert payload["sourceCategoryGuidance"]["coreCategories"] == ["encyclopedia"]
    assert "travelogue" in payload["sourceCategoryGuidance"]["preferredCategories"]
    assert "official" in payload["sourceCategoryGuidance"]["preferredCategories"]
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


def test_qunar_travelogue_sources_search_multiple_entity_aliases():
    original_curl_json = research_plan_mod._curl_json
    original_sleep = research_plan_mod.time.sleep
    queries: list[str] = []

    def _fake_curl_json(url: str, *, timeout: int = 0):
        _ = timeout
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("q", [""])[0]
        queries.append(query)
        if query != "八达岭":
            return {"ret": True, "data": {"bookList": [], "more": False}}
        return {
            "ret": True,
            "data": {
                "bookList": [
                    {
                        "id": "10001",
                        "title": "八达岭长城一日游",
                        "travelRoute": ["八达岭长城", "居庸关"],
                        "cityName": "北京",
                        "userName": "旅行者",
                        "viewCount": 1200,
                    }
                ],
                "more": False,
            },
        }

    try:
        research_plan_mod._curl_json = _fake_curl_json
        research_plan_mod.time.sleep = lambda *_args, **_kwargs: None
        sources = _qunar_travelogue_sources(
            "八达岭—慕田峪长城旅游区",
            entity_aliases=[],
            authorized_images=[{"url": "https://img.example/badaling.jpg", "license": "CC BY 4.0"}],
            limit=4,
        )
    finally:
        research_plan_mod._curl_json = original_curl_json
        research_plan_mod.time.sleep = original_sleep

    assert "八达岭" in queries
    assert len(sources) == 1
    assert sources[0]["sourceRole"] == "base"
    assert sources[0]["url"] == "https://touch.travel.qunar.com/youji/10001"


def test_known_entity_aliases_registry_covers_operational_article_search_names():
    assert "沈阳世博园" in _known_entity_aliases("沈阳市沈阳植物园")
    assert "长春世界雕塑园" in _known_entity_aliases("世界雕塑公园景区")
    assert "趵突泉" in _known_entity_aliases("天下第一泉景区")
    assert "淹城春秋乐园" in _known_entity_aliases("春秋淹城旅游区")
    assert "洪泽湖" in _known_entity_aliases("洪泽湖湿地景区")
    assert "湄洲岛" in _known_entity_aliases("湄洲岛妈祖文化旅游区")


def test_known_article_sources_skip_non_fetchable_registry_sites():
    sources = _known_article_sources("南京市夫子庙－秦淮风光带")
    source_ids = {source["source_id"] for source in sources}
    urls = {source["url"] for source in sources}
    assert "article_registry_fuzimiao_qinhuai_route" in source_ids
    assert "http://www.njfzm.net/brc/53.htm" in urls
    assert any(source["platform"] == "景区官网" for source in sources)
    assert not any("you.ctrip.com" in url for url in urls)


def test_source_reject_memory_ignores_soft_fetch_policy_failures():
    assert not _source_reject_should_enter_memory(
        {
            "quality": "Reject",
            "score": 0,
            "reasons": [],
            "fetchSucceeded": False,
            "statusCode": 0,
            "url": "https://you.ctrip.com/travels/shenyang155/4062166.html",
        }
    )
    assert _source_reject_should_enter_memory(
        {
            "quality": "Reject",
            "score": 0,
            "reasons": [],
            "fetchSucceeded": False,
            "statusCode": 404,
            "url": "https://example.com/missing",
        }
    )
    assert _source_reject_should_enter_memory(
        {
            "quality": "Reject",
            "score": 0,
            "reasons": ["platform_visible"],
            "fetchSucceeded": True,
            "statusCode": 200,
            "url": "https://example.com/low-quality",
        }
    )


def test_download_reject_memory_ignores_registry_fetchable_homepage_baike_soft_failures():
    task = "旅行/地域/测试省/景区/homepage拒绝记忆"
    batch = "reject_memory"
    entity = "沙湖旅游景区"
    obj = resolve_entity_object_dir(task, batch, entity, etype_hint="地点/景区")
    shutil.rmtree(obj, ignore_errors=True)
    rejected = obj / "1.download" / "rejected_sources" / "01.home_baidu_baike"
    rejected.mkdir(parents=True, exist_ok=True)
    url = "https://baike.baidu.com/item/%E6%B2%99%E6%B9%96%E6%97%85%E6%B8%B8%E6%99%AF%E5%8C%BA"
    write_json(rejected / "meta.json", {
        "sourceId": "home_baidu_baike",
        "platform": "百度百科",
        "researchLane": "homepage",
        "url": url,
    })
    write_json(rejected / "source.quality.json", {
        "quality": "Reject",
        "score": 0,
        "reasons": [],
        "fetchSucceeded": False,
        "statusCode": 0,
        "url": url,
    })

    memory = _download_reject_memory(task, batch, entity, entity_type="地点/景区")

    assert not any("baike.baidu.com" in value for value in memory["sourceUrls"])


def test_homepage_candidate_gate_allows_registry_fetchable_baike_sources():
    baidu = _source(
        source_id="home_baidu_baike",
        platform="百度百科",
        url="https://baike.baidu.com/item/%E5%96%80%E7%BA%B3%E6%96%AF%E6%99%AF%E5%8C%BA",
        category="encyclopedia",
        discovery_provider="baidu_baike_exact_item_url",
        match_confidence=0.86,
    )
    baidu_verdict = _candidate_gate(baidu, entity_id="喀纳斯景区", lane="homepage")
    assert baidu_verdict["passed"]

    bare_official = _source(
        source_id="home_official_bare",
        platform="景区官网",
        url="https://example.invalid/kanas",
        category="official",
        discovery_provider="curated_official_url",
        match_confidence=0.9,
    )
    bare_verdict = _candidate_gate(bare_official, entity_id="喀纳斯景区", lane="homepage")
    assert not bare_verdict["passed"]
    assert "registry-fetchable" in "\n".join(bare_verdict["issues"])

    wiki = _source(
        source_id="home_wikipedia",
        platform="维基百科",
        url="https://zh.wikipedia.org/wiki/%E5%96%80%E7%BA%B3%E6%96%AF%E6%B9%96",
        category="encyclopedia",
        discovery_provider="Chinese Wikipedia",
        match_confidence=0.95,
    )
    assert _candidate_gate(wiki, entity_id="喀纳斯景区", lane="homepage")["passed"]

    snapshotted = _source(
        source_id="home_official_snapshot",
        platform="景区官网",
        url="https://example.invalid/kanas",
        category="official",
        discovery_provider="curated_official_snapshot",
        match_confidence=0.9,
    )
    snapshotted["body"] = "喀纳斯景区位于新疆阿勒泰，包含湖泊、森林、河湾等核心景观。"
    assert _candidate_gate(snapshotted, entity_id="喀纳斯景区", lane="homepage")["passed"]


def test_homepage_seed_source_requires_encyclopedia_or_official_primary():
    assert _homepage_can_seed_base_draft({
        "platform": "维基百科",
        "category": "encyclopedia",
        "url": "https://zh.wikipedia.org/wiki/example",
    })
    assert _homepage_can_seed_base_draft({
        "platform": "景区官网",
        "category": "official",
        "url": "https://example.com/about",
    })
    assert not _homepage_can_seed_base_draft({
        "platform": "文旅局",
        "category": "official",
        "url": "https://example.gov.cn/scenic",
    })
    assert not _homepage_can_seed_base_draft({
        "platform": "权威媒体",
        "category": "authoritative_reference",
        "url": "https://www.news.cn/example",
    })


def test_verified_homepage_reuse_filters_bad_or_thin_source_units():
    task = "旅行/地域/测试省/景区/homepage复用过滤"
    batch = "source_units"
    entity = "沙湖旅游景区"
    obj = resolve_entity_object_dir(task, batch, entity, etype_hint="地点/景区")
    shutil.rmtree(obj, ignore_errors=True)
    sources_root = obj / "1.download" / "sources"

    bad = sources_root / "01.home_wikipedia"
    bad.mkdir(parents=True, exist_ok=True)
    (bad / "source.md").write_text(
        "\n".join(
            [
                "沙湖可以指：",
                "沙湖：位于宁夏石嘴山市的湖泊。",
                "沙湖：位于武汉市的湖泊。",
                "沙湖：位于苏州市的湖泊。",
            ]
        ),
        encoding="utf-8",
    )
    write_json(bad / "meta.json", {
        "sourceId": "home_wikipedia",
        "platform": "维基百科",
        "category": "encyclopedia",
        "researchLane": "homepage",
        "url": "https://zh.wikipedia.org/wiki/%E6%B2%99%E6%B9%96",
    })
    write_json(bad / "source.quality.json", {"quality": "B-fact", "score": 6, "url": "https://zh.wikipedia.org/wiki/%E6%B2%99%E6%B9%96"})

    thin = sources_root / "02.home_official_thin"
    thin.mkdir(parents=True, exist_ok=True)
    (thin / "source.md").write_text("沙湖旅游景区位于宁夏，是一个景区简介页面。", encoding="utf-8")
    write_json(thin / "meta.json", {
        "sourceId": "home_official_thin",
        "platform": "景区官网",
        "category": "official",
        "researchLane": "homepage",
        "url": "https://example.com/shahu",
    })
    write_json(thin / "source.quality.json", {"quality": "B-fact", "score": 6, "url": "https://example.com/shahu"})

    good = sources_root / "03.home_official"
    good.mkdir(parents=True, exist_ok=True)
    (good / "source.md").write_text(
        (
            "沙湖旅游景区位于宁夏石嘴山市平罗县境内。"
            "沙湖旅游景区由湖泊、沙漠、湿地和芦苇景观组成。"
            "沙湖旅游景区是国家5A级旅游景区。"
            "沙湖旅游景区主要游览项目包括湖区观光、沙漠体验和湿地观鸟。"
            "沙湖旅游景区开放、票务和交通接驳规则以官方公告为准。"
        ),
        encoding="utf-8",
    )
    write_json(good / "meta.json", {
        "sourceId": "home_official",
        "platform": "景区官网",
        "category": "official",
        "researchLane": "homepage",
        "url": "https://example.com/shahu-home",
    })
    write_json(good / "source.quality.json", {"quality": "B-fact", "score": 6, "url": "https://example.com/shahu-home"})

    sources = _verified_homepage_sources_from_source_units(
        task,
        batch,
        entity,
        entity_type="地点/景区",
    )

    assert [source["source_id"] for source in sources] == ["home_official"]


def test_qunar_travelogue_sources_match_registry_alias_route_names():
    original_curl_json = research_plan_mod._curl_json
    original_sleep = research_plan_mod.time.sleep
    queries: list[str] = []

    def _fake_curl_json(url: str, *, timeout: int = 0):
        _ = timeout
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("q", [""])[0]
        queries.append(query)
        if query != "沈阳世博园":
            return {"ret": True, "data": {"bookList": [], "more": False}}
        return {
            "ret": True,
            "data": {
                "bookList": [
                    {
                        "id": "7442970",
                        "title": "沈阳10.12-10.14游记",
                        "travelRoute": ["张学良旧居", "沈阳世博园", "中街"],
                        "cityName": "沈阳",
                        "userName": "旅行者",
                        "viewCount": 1200,
                    }
                ],
                "more": False,
            },
        }

    try:
        research_plan_mod._curl_json = _fake_curl_json
        research_plan_mod.time.sleep = lambda *_args, **_kwargs: None
        sources = _qunar_travelogue_sources(
            "沈阳市沈阳植物园",
            entity_aliases=_known_entity_aliases("沈阳市沈阳植物园"),
            authorized_images=[{"url": "https://img.example/shenyang.jpg", "license": "CC BY 4.0"}],
            limit=4,
        )
    finally:
        research_plan_mod._curl_json = original_curl_json
        research_plan_mod.time.sleep = original_sleep

    assert "沈阳世博园" in queries
    assert len(sources) == 1
    assert sources[0]["url"] == "https://touch.travel.qunar.com/youji/7442970"


def test_qunar_travelogue_sources_use_composite_scenic_aliases():
    original_curl_json = research_plan_mod._curl_json
    original_sleep = research_plan_mod.time.sleep
    queries: list[str] = []

    def _fake_curl_json(url: str, *, timeout: int = 0):
        _ = timeout
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("q", [""])[0]
        queries.append(query)
        if query != "淹城春秋乐园":
            return {"ret": True, "data": {"bookList": [], "more": False}}
        return {
            "ret": True,
            "data": {
                "bookList": [
                    {
                        "id": "7674519",
                        "title": "三天两晚淹城春秋乐园穿越之旅",
                        "travelRoute": ["淹城春秋乐园", "淹城遗址公园", "春秋王宫"],
                        "cityName": "常州",
                        "userName": "旅行者",
                        "viewCount": 1200,
                    }
                ],
                "more": False,
            },
        }

    try:
        research_plan_mod._curl_json = _fake_curl_json
        research_plan_mod.time.sleep = lambda *_args, **_kwargs: None
        sources = _qunar_travelogue_sources(
            "春秋淹城旅游区",
            entity_aliases=_known_entity_aliases("春秋淹城旅游区"),
            authorized_images=[{"url": "https://img.example/yancheng.jpg", "license": "CC BY 4.0"}],
            limit=4,
        )
    finally:
        research_plan_mod._curl_json = original_curl_json
        research_plan_mod.time.sleep = original_sleep

    assert "淹城春秋乐园" in queries
    assert len(sources) == 1
    assert sources[0]["url"] == "https://touch.travel.qunar.com/youji/7674519"


def test_qunar_travelogue_sources_search_late_registry_aliases():
    original_curl_json = research_plan_mod._curl_json
    original_sleep = research_plan_mod.time.sleep
    queries: list[str] = []

    def _fake_curl_json(url: str, *, timeout: int = 0):
        _ = timeout
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("q", [""])[0]
        queries.append(query)
        if query != "洪泽湖":
            return {"ret": True, "data": {"bookList": [], "more": False}}
        return {
            "ret": True,
            "data": {
                "bookList": [
                    {
                        "id": "7900533",
                        "title": "国庆带娃游淮安",
                        "travelRoute": ["里运河", "洪泽湖", "河下古镇"],
                        "cityName": "淮安",
                        "userName": "旅行者",
                        "viewCount": 1200,
                    }
                ],
                "more": False,
            },
        }

    try:
        research_plan_mod._curl_json = _fake_curl_json
        research_plan_mod.time.sleep = lambda *_args, **_kwargs: None
        sources = _qunar_travelogue_sources(
            "洪泽湖湿地景区",
            entity_aliases=_known_entity_aliases("洪泽湖湿地景区"),
            authorized_images=[{"url": "https://img.example/hongze.jpg", "license": "CC BY 4.0"}],
            limit=4,
        )
    finally:
        research_plan_mod._curl_json = original_curl_json
        research_plan_mod.time.sleep = original_sleep

    assert "洪泽湖" in queries
    assert len(sources) == 1
    assert sources[0]["url"] == "https://touch.travel.qunar.com/youji/7900533"


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


def test_wiki_title_for_entity_uses_short_alias_variants():
    original = research_plan_mod._wiki_api

    def fake_wiki_api(_host: str, params: dict) -> dict:
        if params.get("titles") == "沈阳市沈阳植物园" and params.get("prop") != "extracts":
            return {"query": {"pages": {"-1": {"missing": ""}}}}
        if params.get("list") == "search" and params.get("srsearch") == "沈阳市沈阳植物园":
            return {"query": {"search": []}}
        if params.get("titles") == "沈阳植物园" and params.get("prop") != "extracts":
            return {"query": {"pages": {"1": {"pageid": 1, "title": "沈阳植物园"}}}}
        if params.get("titles") == "沈阳植物园" and params.get("prop") == "extracts":
            return {"query": {"pages": {"1": {"pageid": 1, "title": "沈阳植物园", "extract": "可用正文"}}}}
        return {}

    research_plan_mod._wiki_api = fake_wiki_api
    try:
        assert _wiki_title_for_entity("zh.wikipedia.org", "沈阳市沈阳植物园") == "沈阳植物园"
    finally:
        research_plan_mod._wiki_api = original


def test_wiki_title_for_entity_rejects_cross_entity_generic_alias_title():
    original = research_plan_mod._wiki_api

    def fake_wiki_api(_host: str, params: dict) -> dict:
        if params.get("prop") == "extracts":
            return {
                "query": {
                    "pages": {
                        "1": {
                            "pageid": 1,
                            "title": "悉尼奥林匹克公园",
                            "extract": "悉尼奥林匹克公园位于澳大利亚悉尼，是另一座奥林匹克公园。",
                        }
                    }
                }
            }
        if params.get("list") == "search":
            return {"query": {"search": [{"title": "悉尼奥林匹克公园"}]}}
        return {"query": {"pages": {"-1": {"missing": ""}}}}

    research_plan_mod._wiki_api = fake_wiki_api
    try:
        assert _wiki_title_for_entity("zh.wikipedia.org", "北京奥林匹克公园") == ""
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


def test_external_article_links_become_base_only_for_article_quality_classes():
    rows = [
        ("https://www.people.com.cn/n1/2026/0617/c1000-123.html", "媒体文章", "media_article"),
        ("https://whc.unesco.org/en/list/637", "专业机构", "vertical_professional"),
        ("https://you.ctrip.com/sight/beijing1/123.html", "旅行平台", "travelogue"),
        ("https://www.example.org/reference", "普通参考", "authoritative_reference"),
    ]
    for url, _label, expected_category in rows:
        platform = _external_platform(url)
        category = _external_article_category(url, platform)
        source = _source(
            source_id=f"article_external_{expected_category}",
            platform=platform,
            url=url,
            category=category,
            discovery_provider="test",
            match_confidence=0.9,
            source_role="base" if category != "authoritative_reference" else "supporting",
        )
        assert source["category"] == expected_category
        verdict = _candidate_gate(source, entity_id="九寨沟", lane="article")
        assert verdict["passed"], (url, source, verdict)


def test_external_article_category_uses_article_url_shape_not_portal_page():
    assert _url_looks_like_article("https://news.cctv.com/2023/03/25/ARTIu6rDhTd9.shtml")
    assert _url_looks_like_article("http://society.people.com.cn/n1/2020/1018/c1008-31896200.html")
    assert _url_looks_like_article("http://www.xinhuanet.com/local/2017-01/26/c_1120385110.htm")
    assert _url_looks_like_article("http://www.sh-aiguo.gov.cn/node2/node4/userobject1ai535.html")
    assert not _url_looks_like_article("http://www.sh-aiguo.gov.cn/")
    assert not _url_looks_like_article("http://www.shtong.gov.cn/newsite/node2/node2245/index.html")
    assert (
        _external_article_category("https://news.cctv.com/2023/03/25/ARTIu6rDhTd9.shtml", "央视网")
        == "media_article"
    )
    assert (
        _external_article_category("http://www.sh-aiguo.gov.cn/node2/node4/userobject1ai535.html", "文旅局")
        == "official_article"
    )
    assert _external_article_category("http://www.sh-aiguo.gov.cn/", "文旅局") == "official"


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


def test_image_collection_gate_rejects_prior_collection_id_only_match():
    collection = {
        "sourceCollectionId": "open_license_file:嵖岈山旅游景区:henan_icon",
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
        entity_id="嵖岈山旅游景区",
        allow_verified_collection_id_match=False,
    )
    assert not verdict["passed"]
    assert any("relevance" in issue for issue in verdict["issues"])
    assert not _collection_publishable_image_urls(
        [collection],
        entity_id="嵖岈山旅游景区",
    )


def test_image_collection_gate_rejects_oversized_assets_before_fetch():
    collection = {
        "sourceCollectionId": "commons:巨幅图:oversized",
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
                "caption": "巨幅图 scenic view",
                "relevance": "巨幅图 scenic view",
                "width": 12000,
                "height": 9000,
            }
        ],
    }

    verdict = _collection_gate(collection, entity_id="巨幅图")

    assert not verdict["passed"]
    assert any("pixelCount" in issue for issue in verdict["issues"])


def test_image_collection_gate_accepts_verified_entity_alias():
    collection = {
        "sourceCollectionId": "commons:三苏祠:south-gate",
        "creator": "A",
        "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:South_gate_of_Sansu_Shrine.jpg",
        "license": "CC BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:South_gate_of_Sansu_Shrine.jpg",
        "usageScope": "app_publish",
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


def test_image_collection_gate_rejects_configured_cross_entity_alias_collision():
    collection = {
        "sourceCollectionId": "commons:故宫博物院:national-palace-taiwan",
        "creator": "A",
        "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:NationalPalace_MuseumFrontView.jpg",
        "platform": "Wikimedia Commons",
        "license": "CC BY 3.0",
        "termsUrl": "https://creativecommons.org/licenses/by/3.0/",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:NationalPalace_MuseumFrontView.jpg",
        "usageScope": "app_publish",
        "images": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/b/b4/NationalPalace_MuseumFrontView.jpg",
                "creator": "A",
                "caption": "National Palace Museum, Taiwan.",
                "relevance": "National Palace Museum, Taiwan.",
            }
        ],
    }

    verdict = _collection_gate(
        collection,
        entity_id="故宫博物院",
        entity_aliases=["Palace Museum"],
    )

    assert not verdict["passed"]
    assert any("relevance" in issue for issue in verdict["issues"])


def test_image_collection_gate_accepts_core_name_from_english_scenic_alias():
    aliases = _expanded_entity_aliases(["Wutaishan Scenic Area"])
    collection = {
        "sourceCollectionId": "commons:五台山风景名胜区:air",
        "creator": "A",
        "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:Wutai_Shan_from_the_air.jpg",
        "license": "CC BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:Wutai_Shan_from_the_air.jpg",
        "usageScope": "app_publish",
        "images": [
            {
                "url": "https://upload.wikimedia.org/wikipedia/commons/7/70/Wutai_Shan_from_the_air.jpg",
                "creator": "A",
                "caption": "Wutai Shan from the air",
                "relevance": "Wutai Shan from the air",
            }
        ],
    }

    assert "Wutaishan" in aliases
    verdict = _collection_gate(
        collection,
        entity_id="五台山风景名胜区",
        entity_aliases=aliases,
    )
    assert verdict["passed"], verdict


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
            image_evidence_mode="same_authorized_collection",
        ),
        entity_id="九寨沟",
        lane="article",
    )
    assert article_verdict["passed"]
    assert any("unsupported license" in issue for issue in article_verdict["warnings"]), article_verdict
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
    assert _article_base_candidate_limit(4) == 16
    assert _article_base_candidate_limit(10) == 32


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


def test_safe_collection_id_uses_hash_suffix_to_avoid_long_prefix_collision():
    entity = "承德避暑山庄及周围寺庙景区"
    cid_a = _safe_collection_id(
        "open_license_file",
        entity,
        "https://commons.wikimedia.org/wiki/File:%E6%89%BF%E5%BE%B7%E9%81%BF%E6%9A%91%E5%B1%B1%E5%BA%84%E5%9B%9B%E7%9F%A5%E4%B9%A6%E5%B1%8B2025.11.jpg",
    )
    cid_b = _safe_collection_id(
        "open_license_file",
        entity,
        "https://commons.wikimedia.org/wiki/File:%E6%89%BF%E5%BE%B7%E9%81%BF%E6%9A%91%E5%B1%B1%E5%BA%84%E6%BE%B9%E6%B3%8A%E6%95%AC%E8%AF%9A%E6%AE%BF2025.11.jpg",
    )

    assert cid_a != cid_b
    assert len(cid_a.rsplit(":", 1)[-1]) == 10
    assert len(cid_b.rsplit(":", 1)[-1]) == 10


def test_parallel_auto_research_writes_availability_report():
    import download.research_plan as research_mod

    task = "旅行/地域/测试省/景区/并行可用性报告隔离"
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

    def fake_qunar(
        entity_id: str,
        *,
        entity_aliases: list[str] | tuple[str, ...] = (),
        authorized_images: list[dict],
        limit: int = 4,
    ):
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
        research_mod._commons_images = lambda entity_id, entity_aliases=(), limit=10: [good_image, second_good_image] if entity_id == "可用景区" else []
        research_mod._openverse_images = lambda entity_id, entity_aliases=(), limit=12: []
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
    assert availability["readyTargets"] == ["可用景区"], availability
    assert [item["entityId"] for item in availability["ineligibleTargets"]] == ["缺源景区"], availability
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
    missing_image_plan = (
        resolve_entity_object_dir(task, batch, "缺源景区", etype_hint="景区")
        / "1.download"
        / "image_source_plan.json"
    )
    missing_payload = read_json(missing_image_plan)["payload"]
    assert missing_payload["sourceUnavailable"][0]["lane"] == "image"
    diagnostics = missing_payload["imageDiscoveryDiagnostics"]
    assert diagnostics["requiredImageWorks"] >= 1
    assert diagnostics["poolCounts"]["acceptedCollections"] == 0
    assert diagnostics["sourceUnavailable"][0]["nextAction"] == "manual_authorized_gallery_or_target_replacement"


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

    def fake_qunar(
        entity_id: str,
        *,
        entity_aliases: list[str] | tuple[str, ...] = (),
        authorized_images: list[dict],
        limit: int = 4,
    ):
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
        research_mod._commons_images = lambda entity_id, entity_aliases=(), limit=10: [good_image]
        research_mod._openverse_images = lambda entity_id, entity_aliases=(), limit=12: []
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
    assert any(source["source_id"].startswith("article_qunar_base_") for source in sources)


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
        "_commons_category_images": research_mod._commons_category_images,
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
        research_mod._commons_images = lambda entity_id, entity_aliases=(), limit=10: [home_image, image_work]
        research_mod._openverse_images = lambda entity_id, entity_aliases=(), limit=12: []
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


def test_auto_research_reuses_prior_verified_image_collections_when_live_discovery_empty():
    import download.research_plan as research_mod

    task = "旅行/地域/测试省/景区/图库复用"
    prior_batch = "image_pool_prior"
    batch = "image_pool_current"
    entity = "九寨沟"
    prior_collections = []
    for index in range(2):
        collection_id = f"open_license_file:{entity}:prior_{index}"
        prior_collections.append(
            {
                "sourceCollectionId": collection_id,
                "creator": f"Creator {index}",
                "collectionPageUrl": f"https://commons.wikimedia.org/wiki/File:Jiuzhai_{index}.jpg",
                "platform": "Wikimedia Commons",
                "license": "CC BY-SA 4.0",
                "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                "authorizationProof": f"https://commons.wikimedia.org/wiki/File:Jiuzhai_{index}.jpg",
                "usageScope": "app_publish",
                "images": [
                    {
                        "url": f"https://img.example/jiuzhai_{index}.jpg",
                        "caption": "九寨沟 Jiuzhai Valley landscape",
                        "relevance": "九寨沟 Jiuzhai Valley landscape",
                        "width": 1600,
                        "height": 1000,
                    }
                ],
            }
        )
    prior_plan = (
        resolve_entity_object_dir(task, prior_batch, entity, etype_hint="景区")
        / "1.download"
        / "image_source_plan.json"
    )
    prior_plan.parent.mkdir(parents=True, exist_ok=True)
    write_json(prior_plan, {"payload": {"collections": prior_collections}})
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
        research_mod._wikidata_item_for_zhwiki = lambda title: ""
        research_mod._wikidata_item_for_entity_search = lambda entity_id: ""
        research_mod._wikidata_entity_aliases = lambda qid: []
        research_mod._wikidata_commons_images = lambda qid, entity_id, entity_aliases=(), limit=10: []
        research_mod._commons_category_images = (
            lambda category, entity_id, entity_aliases=(), limit=8: []
        )
        research_mod._official_website = lambda qid: ""
        research_mod._commons_images = lambda entity_id, entity_aliases=(), limit=10: []
        research_mod._openverse_images = lambda entity_id, entity_aliases=(), limit=12: []
        research_mod._mediawiki_page_images = lambda host, title, entity_id, limit=6: []
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

    assert not report["sourceUnavailable"]
    plan = (
        resolve_entity_object_dir(task, batch, entity, etype_hint="景区")
        / "1.download"
        / "image_source_plan.json"
    )
    collections = read_json(plan)["payload"]["collections"]
    assert len(collections) == 2
    assert {collection["discoveryProvider"] for collection in collections} == {"verified_source_pool_reuse"}


def test_auto_research_reuses_verified_image_collections_across_tasks_when_live_discovery_empty():
    import download.research_plan as research_mod

    prior_task = "旅行/地域/测试省/景区/跨任务图库缓存源"
    task = "旅行/地域/测试省/景区/跨任务图库缓存目标"
    prior_batch = "cross_task_image_pool_prior"
    batch = "cross_task_image_pool_current"
    entity = "黄山风景区"
    prior_collections = []
    for index in range(2):
        collection_id = f"open_license_file:{entity}:cross_task_{index}"
        prior_collections.append(
            {
                "sourceCollectionId": collection_id,
                "creator": f"Creator {index}",
                "collectionPageUrl": f"https://commons.wikimedia.org/wiki/File:Huangshan_{index}.jpg",
                "platform": "Wikimedia Commons",
                "license": "CC BY-SA 4.0",
                "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                "authorizationProof": f"https://commons.wikimedia.org/wiki/File:Huangshan_{index}.jpg",
                "usageScope": "app_publish",
                "images": [
                    {
                        "url": f"https://img.example/huangshan_{index}.jpg",
                        "caption": "黄山 Mount Huangshan landscape",
                        "relevance": "黄山 Mount Huangshan landscape",
                        "width": 1600,
                        "height": 1000,
                    }
                ],
            }
        )
    prior_plan = (
        resolve_entity_object_dir(prior_task, prior_batch, entity, etype_hint="景区")
        / "1.download"
        / "image_source_plan.json"
    )
    prior_plan.parent.mkdir(parents=True, exist_ok=True)
    write_json(prior_plan, {"payload": {"collections": prior_collections}})
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
        research_mod._wikidata_item_for_zhwiki = lambda title: ""
        research_mod._wikidata_item_for_entity_search = lambda entity_id: ""
        research_mod._wikidata_entity_aliases = lambda qid: []
        research_mod._wikidata_commons_images = lambda qid, entity_id, entity_aliases=(), limit=10: []
        research_mod._official_website = lambda qid: ""
        research_mod._commons_images = lambda entity_id, entity_aliases=(), limit=10: []
        research_mod._openverse_images = lambda entity_id, entity_aliases=(), limit=12: []
        research_mod._mediawiki_page_images = lambda host, title, entity_id, limit=6: []
        research_mod._trusted_external_links = lambda title, limit=4: []
        research_mod._qunar_travelogue_sources = (
            lambda entity_id, entity_aliases=(), authorized_images=(), limit=4: []
        )
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

    assert report["sourceAvailability"]["readyTargets"] == [entity]
    plan = (
        resolve_entity_object_dir(task, batch, entity, etype_hint="景区")
        / "1.download"
        / "image_source_plan.json"
    )
    collections = read_json(plan)["payload"]["collections"]
    assert len(collections) == 2
    assert {collection["reuseSourcePlan"] for collection in collections}


def test_auto_research_rescues_image_lane_when_first_open_license_discovery_is_empty():
    import download.research_plan as research_mod

    spec = store.scaffold_spec(
        vertical="travel",
        organize_by="地域",
        key="测试省",
        category="景区",
        name="图片救援发现",
        scope={
            "region": "测试省",
            "entityTypes": ["地点/景区"],
            "coverageTargets": [{"entityType": "地点/景区", "name": "故宫博物院"}],
        },
        content={
            "modalityContract": "separated_research",
            "quotas": {
                "entityHomepagesPerTarget": 0,
                "entityArticlesPerTarget": 0,
                "imageWorksPerTarget": 2,
            },
        },
        created_by="test",
    )
    task = spec["taskId"]
    store.save_spec(spec)
    batch = "image_rescue_current"
    entity = "故宫博物院"
    rescue_images = [
        {
            "url": f"https://upload.wikimedia.org/wikipedia/commons/rescue/gugong_{index}.jpg",
            "platform": "Wikimedia Commons",
            "license": "CC BY-SA 4.0",
            "credit": f"Rescue Creator {index}",
            "sourceUrl": f"https://commons.wikimedia.org/wiki/File:Gugong_{index}.jpg",
            "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
            "licenseSnapshot": "CC BY-SA 4.0 recorded on Wikimedia Commons file page",
            "authorizationProof": f"https://commons.wikimedia.org/wiki/File:Gugong_{index}.jpg",
            "usageScope": "app_publish",
            "width": 1600,
            "height": 1000,
            "caption": f"{entity} 开放授权图片 {index}",
            "relevance": f"{entity} 开放授权图片 {index}",
            "creator": f"Rescue Creator {index}",
            "collectionPageUrl": f"https://commons.wikimedia.org/wiki/File:Gugong_{index}.jpg",
        }
        for index in range(1, 4)
    ]
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
    commons_calls = {"count": 0}

    def fake_commons(entity_id, entity_aliases=(), limit=10):
        _ = entity_aliases
        assert entity_id == entity
        commons_calls["count"] += 1
        if commons_calls["count"] == 1:
            return []
        assert limit >= 20
        return rescue_images

    try:
        research_mod._wiki_title = lambda host, entity_id: entity if host == "zh.wikipedia.org" else ""
        research_mod._wikidata_item_for_zhwiki = lambda title: "Q2047427"
        research_mod._wikidata_item_for_entity_search = lambda entity_id: "Q2047427"
        research_mod._wikidata_entity_aliases = lambda qid: ["Palace Museum"]
        research_mod._wikidata_commons_images = lambda qid, entity_id, entity_aliases=(), limit=10: []
        research_mod._official_website = lambda qid: ""
        research_mod._commons_images = fake_commons
        research_mod._openverse_images = lambda entity_id, entity_aliases=(), limit=12: []
        research_mod._mediawiki_page_images = lambda host, title, entity_id, limit=6: []
        research_mod._trusted_external_links = lambda title, limit=4: []
        research_mod._qunar_travelogue_sources = (
            lambda entity_id, entity_aliases=(), authorized_images=(), limit=4: []
        )
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

    assert commons_calls["count"] == 2
    assert report["sourceAvailability"]["readyTargets"] == [entity]
    assert report["sourceUnavailable"] == []
    assert report["rescueEvents"] == [
        {
            "entityId": entity,
            "lane": "image",
            "reason": "open_license_image_discovery_empty_on_first_pass",
            "images": 3,
        }
    ]
    plan = (
        resolve_entity_object_dir(task, batch, entity, etype_hint="景区")
        / "1.download"
        / "image_source_plan.json"
    )
    collections = read_json(plan)["payload"]["collections"]
    assert len(collections) >= 3
    assert {
        image["url"]
        for collection in collections
        for image in collection["images"]
    } >= {image["url"] for image in rescue_images}


def test_auto_research_uses_registry_image_aliases_for_visual_discovery():
    import download.research_plan as research_mod

    spec = store.scaffold_spec(
        vertical="travel",
        organize_by="地域",
        key="测试省",
        category="景区",
        name="图片别名发现",
        scope={
            "region": "测试省",
            "entityTypes": ["地点/景区"],
            "coverageTargets": [{"entityType": "地点/景区", "name": "黄山风景区"}],
        },
        content={
            "modalityContract": "separated_research",
            "quotas": {
                "entityHomepagesPerTarget": 0,
                "entityArticlesPerTarget": 0,
                "imageWorksPerTarget": 2,
            },
        },
        created_by="test",
    )
    task = spec["taskId"]
    store.save_spec(spec)
    batch = "image_alias_current"
    entity = "黄山风景区"
    image_rows = [
        {
            "url": f"https://upload.wikimedia.org/wikipedia/commons/huangshan_{index}.jpg",
            "platform": "Wikimedia Commons",
            "license": "CC BY-SA 4.0",
            "credit": f"Huangshan Creator {index}",
            "sourceUrl": f"https://commons.wikimedia.org/wiki/File:Huangshan_{index}.jpg",
            "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
            "licenseSnapshot": "CC BY-SA 4.0 recorded on Wikimedia Commons file page",
            "authorizationProof": f"https://commons.wikimedia.org/wiki/File:Huangshan_{index}.jpg",
            "usageScope": "app_publish",
            "width": 1600,
            "height": 1000,
            "caption": f"Mount Huangshan landscape {index}",
            "relevance": f"Mount Huangshan landscape {index}",
            "creator": f"Huangshan Creator {index}",
            "collectionPageUrl": f"https://commons.wikimedia.org/wiki/File:Huangshan_{index}.jpg",
        }
        for index in range(1, 4)
    ]
    originals = {
        "_wiki_title": research_mod._wiki_title,
        "_wikidata_item_for_zhwiki": research_mod._wikidata_item_for_zhwiki,
        "_wikidata_item_for_entity_search": research_mod._wikidata_item_for_entity_search,
        "_wikidata_entity_aliases": research_mod._wikidata_entity_aliases,
        "_wikidata_commons_images": research_mod._wikidata_commons_images,
        "_commons_category_images": research_mod._commons_category_images,
        "_official_website": research_mod._official_website,
        "_commons_images": research_mod._commons_images,
        "_openverse_images": research_mod._openverse_images,
        "_mediawiki_page_images": research_mod._mediawiki_page_images,
        "_trusted_external_links": research_mod._trusted_external_links,
        "_qunar_travelogue_sources": research_mod._qunar_travelogue_sources,
    }
    seen_aliases = {"value": []}

    def fake_commons(entity_id, entity_aliases=(), limit=10):
        assert entity_id == entity
        seen_aliases["value"] = list(entity_aliases)
        if "Mount Huangshan" not in entity_aliases:
            return []
        return image_rows[:limit]

    try:
        research_mod._wiki_title = lambda host, entity_id: entity if host == "zh.wikipedia.org" else ""
        research_mod._wikidata_item_for_zhwiki = lambda title: ""
        research_mod._wikidata_item_for_entity_search = lambda entity_id: ""
        research_mod._wikidata_entity_aliases = lambda qid: []
        research_mod._wikidata_commons_images = lambda qid, entity_id, entity_aliases=(), limit=10: []
        research_mod._commons_category_images = (
            lambda category, entity_id, entity_aliases=(), limit=8: []
        )
        research_mod._official_website = lambda qid: ""
        research_mod._commons_images = fake_commons
        research_mod._openverse_images = lambda entity_id, entity_aliases=(), limit=12: []
        research_mod._mediawiki_page_images = lambda host, title, entity_id, limit=6: []
        research_mod._trusted_external_links = lambda title, limit=4: []
        research_mod._qunar_travelogue_sources = (
            lambda entity_id, entity_aliases=(), authorized_images=(), limit=4: []
        )
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

    assert "Mount Huangshan" in seen_aliases["value"]
    assert report["sourceAvailability"]["readyTargets"] == [entity]
    assert report["sourceUnavailable"] == []
    plan = (
        resolve_entity_object_dir(task, batch, entity, etype_hint="景区")
        / "1.download"
        / "image_source_plan.json"
    )
    collections = read_json(plan)["payload"]["collections"]
    assert len(collections) >= 2
    assert {collection["platform"] for collection in collections} == {"Wikimedia Commons"}


def test_homepage_only_auto_research_skips_visual_and_article_discovery():
    import download.research_plan as research_mod

    task = "旅行/地域/测试省/景区/homepage轻量修复"
    batch = "homepage_only_registry_fix"
    entity = "故宫博物院"
    originals = {
        "_wiki_title_for_entity": research_mod._wiki_title_for_entity,
        "_wiki_related_titles_for_entity": research_mod._wiki_related_titles_for_entity,
        "_wikidata_item_for_zhwiki": research_mod._wikidata_item_for_zhwiki,
        "_wikidata_item_for_entity_search": research_mod._wikidata_item_for_entity_search,
        "_wikidata_entity_aliases": research_mod._wikidata_entity_aliases,
        "_official_website": research_mod._official_website,
        "_verified_image_collections_from_prior_plans": research_mod._verified_image_collections_from_prior_plans,
        "_discover_open_license_image_pools": research_mod._discover_open_license_image_pools,
        "_trusted_external_links": research_mod._trusted_external_links,
        "_qunar_travelogue_sources": research_mod._qunar_travelogue_sources,
    }

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("homepage-only repair must not run visual/article discovery")

    try:
        research_mod._wiki_title_for_entity = (
            lambda host, entity_id, entity_aliases=(): entity if host == "zh.wikipedia.org" else ""
        )
        research_mod._wiki_related_titles_for_entity = lambda host, entity_id, entity_aliases=(): []
        research_mod._wikidata_item_for_zhwiki = lambda title: ""
        research_mod._wikidata_item_for_entity_search = lambda entity_id: ""
        research_mod._wikidata_entity_aliases = lambda qid: []
        research_mod._official_website = lambda qid: ""
        research_mod._verified_image_collections_from_prior_plans = fail_if_called
        research_mod._discover_open_license_image_pools = fail_if_called
        research_mod._trusted_external_links = fail_if_called
        research_mod._qunar_travelogue_sources = fail_if_called
        report = write_auto_research_plans(
            task,
            batch,
            [entity],
            entity_type="景区",
            force=True,
            lanes={"homepage"},
        )
    finally:
        for name, value in originals.items():
            setattr(research_mod, name, value)

    assert report["issues"] == []
    assert report["sourceUnavailable"] == []
    assert report["sourceAvailability"]["readyTargets"] == [entity]
    plan = (
        resolve_entity_object_dir(task, batch, entity, etype_hint="景区")
        / "1.download"
        / "homepage_source_plan.json"
    )
    sources = read_json(plan)["payload"]["sources"]
    source_by_id = {source["source_id"]: source for source in sources}
    assert set(source_by_id) >= {"home_official", "home_wikipedia"}
    assert source_by_id["home_official"]["url"] == "https://www.dpm.org.cn/Home.html"
    assert source_by_id["home_official"]["candidateGate"]["passed"] is True


def test_auto_research_marks_image_lane_unavailable_when_unique_publishable_images_insufficient():
    import download.research_plan as research_mod

    spec = store.scaffold_spec(
        vertical="travel",
        organize_by="地域",
        key="测试省",
        category="景区",
        name="图片唯一数量门",
        scope={
            "region": "测试省",
            "entityTypes": ["地点/景区"],
            "coverageTargets": [{"entityType": "地点/景区", "name": "九寨沟"}],
        },
        content={
            "modalityContract": "separated_research",
            "quotas": {
                "entityHomepagesPerTarget": 1,
                "entityArticlesPerTarget": 0,
                "imageWorksPerTarget": 2,
            },
        },
        created_by="test",
    )
    task = spec["taskId"]
    store.save_spec(spec)
    prior_batch = "image_unique_prior"
    batch = "image_unique_current"
    entity = "九寨沟"
    duplicate_url = "https://img.example/jiuzhai_same.jpg"
    prior_collections = []
    for index in range(2):
        prior_collections.append(
            {
                "sourceCollectionId": f"open_license_file:{entity}:prior_{index}",
                "creator": f"Creator {index}",
                "collectionPageUrl": f"https://commons.wikimedia.org/wiki/File:Jiuzhai_{index}.jpg",
                "platform": "Wikimedia Commons",
                "license": "CC BY-SA 4.0",
                "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                "authorizationProof": f"https://commons.wikimedia.org/wiki/File:Jiuzhai_{index}.jpg",
                "usageScope": "app_publish",
                "images": [
                    {
                        "url": duplicate_url,
                        "caption": "九寨沟 Jiuzhai Valley landscape",
                        "relevance": "九寨沟 Jiuzhai Valley landscape",
                        "width": 1600,
                        "height": 1000,
                    }
                ],
            }
        )
    prior_plan = (
        resolve_entity_object_dir(task, prior_batch, entity, etype_hint="景区")
        / "1.download"
        / "image_source_plan.json"
    )
    prior_plan.parent.mkdir(parents=True, exist_ok=True)
    write_json(prior_plan, {"payload": {"collections": prior_collections}})
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
        research_mod._wikidata_item_for_zhwiki = lambda title: ""
        research_mod._wikidata_item_for_entity_search = lambda entity_id: ""
        research_mod._wikidata_entity_aliases = lambda qid: []
        research_mod._wikidata_commons_images = lambda qid, entity_id, entity_aliases=(), limit=10: []
        research_mod._official_website = lambda qid: ""
        research_mod._commons_images = lambda entity_id, entity_aliases=(), limit=10: []
        research_mod._openverse_images = lambda entity_id, entity_aliases=(), limit=12: []
        research_mod._mediawiki_page_images = lambda host, title, entity_id, limit=6: []
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

    assert report["sourceAvailability"]["readyTargets"] == []
    assert report["sourceAvailability"]["ineligibleTargets"][0]["entityId"] == entity
    assert any(
        "unique publishable images=1 need>=2" in str(item.get("reason") or "")
        for item in report["sourceUnavailable"]
    )


def test_auto_research_filters_image_urls_hard_rejected_by_prior_fetch_gate():
    import download.research_plan as research_mod

    task = "旅行/地域/测试省/景区/图片失败记忆"
    batch = "image_reject_memory"
    entity = "五台山风景名胜区"
    bad_url = "https://upload.wikimedia.org/wikipedia/commons/bad/wutaishan_bad.jpg"
    good_url = "https://upload.wikimedia.org/wikipedia/commons/good/wutaishan_good.jpg"
    good_url_2 = "https://upload.wikimedia.org/wikipedia/commons/good/wutaishan_good_2.jpg"
    result_dir = batch_root(task, batch) / "task_download" / "results" / "image_fetch_gate"
    write_json(
        result_dir / f"{entity}.json",
        {
            "payload": {
                "passed": False,
                "evidenceSummary": {
                    "rejectedForQuality": [
                        f"imageSafety: {entity}#1 blocked (watermark) reasons=['watermark'] ({bad_url})"
                    ]
                },
            }
        },
    )
    bad_image = {
        "url": bad_url,
        "platform": "Wikimedia Commons",
        "license": "CC BY-SA 4.0",
        "credit": "Tester",
        "sourceUrl": "https://commons.wikimedia.org/wiki/File:bad.jpg",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "licenseSnapshot": "CC BY-SA 4.0 recorded on Wikimedia Commons file page",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:bad.jpg",
        "usageScope": "app_publish",
        "width": 1600,
        "height": 1000,
        "caption": f"{entity} failed image",
        "relevance": f"{entity} failed image",
        "creator": "Tester",
        "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:bad.jpg",
    }
    good_image = {
        **bad_image,
        "url": good_url,
        "sourceUrl": "https://commons.wikimedia.org/wiki/File:good.jpg",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:good.jpg",
        "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:good.jpg",
        "caption": f"{entity} good image",
        "relevance": f"{entity} good image",
    }
    good_image_2 = {
        **good_image,
        "url": good_url_2,
        "sourceUrl": "https://commons.wikimedia.org/wiki/File:good_2.jpg",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:good_2.jpg",
        "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:good_2.jpg",
        "caption": f"{entity} good image 2",
        "relevance": f"{entity} good image 2",
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
        research_mod._wiki_title = lambda host, entity_id: ""
        research_mod._wikidata_item_for_zhwiki = lambda title: ""
        research_mod._wikidata_item_for_entity_search = lambda entity_id: ""
        research_mod._wikidata_entity_aliases = lambda qid: []
        research_mod._wikidata_commons_images = lambda qid, entity_id, entity_aliases=(), limit=10: []
        research_mod._official_website = lambda qid: ""
        research_mod._commons_images = lambda entity_id, entity_aliases=(), limit=10: [
            bad_image,
            good_image,
            good_image_2,
        ]
        research_mod._openverse_images = lambda entity_id, entity_aliases=(), limit=12: []
        research_mod._mediawiki_page_images = lambda host, title, entity_id, limit=6: []
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

    assert report["sourceUnavailable"] == []
    plan = (
        resolve_entity_object_dir(task, batch, entity, etype_hint="景区")
        / "1.download"
        / "image_source_plan.json"
    )
    urls = [
        image["url"]
        for collection in read_json(plan)["payload"]["collections"]
        for image in collection["images"]
    ]
    assert good_url in urls
    assert good_url_2 in urls
    assert bad_url not in urls


def test_auto_research_reuses_prior_verified_article_base_sources_when_live_discovery_empty():
    import download.research_plan as research_mod

    task = "旅行/地域/测试省/景区/文章底稿复用"
    prior_batch = "article_pool_prior"
    batch = "article_pool_current"
    entity = "故宫博物院"
    prior_sources = []
    for index in range(5):
        prior_sources.append(
            {
                "source_id": f"article_platform_base_{index}",
                "platform": "今日头条",
                "url": f"https://example.com/article/{index}",
                "sourceUseMode": "factual_reference_only",
                "category": "platform_article",
                "discoveryProvider": "test_prior_article_pool",
                "matchConfidence": 0.9,
                "evidenceReason": f"历史批次已验证 {entity} 文章底稿 {index}",
                "sourceRole": "base",
                "entityMatch": "strong",
                "candidateGate": {
                    "passed": True,
                    "issues": [],
                    "warnings": [],
                    "category": "platform_article",
                    "matchConfidence": 0.9,
                    "role": "base",
                },
            }
        )
    prior_plan = (
        resolve_entity_object_dir(task, prior_batch, entity, etype_hint="景区")
        / "1.download"
        / "article_source_plan.json"
    )
    prior_plan.parent.mkdir(parents=True, exist_ok=True)
    write_json(prior_plan, {"payload": {"sources": prior_sources}})
    homepage_plan = (
        resolve_entity_object_dir(task, batch, entity, etype_hint="景区")
        / "1.download"
        / "homepage_source_plan.json"
    )
    homepage_plan.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        homepage_plan,
        {
            "payload": {
                "sources": [
                    {
                        "source_id": "home_wikipedia",
                        "platform": "维基百科",
                        "url": "https://example.com/article/0",
                        "category": "encyclopedia",
                        "sourceUseMode": "factual_reference_only",
                    }
                ]
            }
        },
    )
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
        "_task_content_quotas": research_mod._task_content_quotas,
    }
    try:
        research_mod._wiki_title = lambda host, entity_id: entity if host == "zh.wikipedia.org" else ""
        research_mod._wikidata_item_for_zhwiki = lambda title: ""
        research_mod._wikidata_item_for_entity_search = lambda entity_id: ""
        research_mod._wikidata_entity_aliases = lambda qid: []
        research_mod._wikidata_commons_images = lambda qid, entity_id, entity_aliases=(), limit=10: []
        research_mod._official_website = lambda qid: ""
        research_mod._commons_images = lambda entity_id, entity_aliases=(), limit=10: []
        research_mod._openverse_images = lambda entity_id, entity_aliases=(), limit=12: []
        research_mod._mediawiki_page_images = lambda host, title, entity_id, limit=6: []
        research_mod._trusted_external_links = lambda title, limit=4: []
        research_mod._qunar_travelogue_sources = (
            lambda entity_id, entity_aliases=(), authorized_images=(), limit=4: []
        )
        research_mod._task_content_quotas = lambda task_id: {
            "entityArticlesPerTarget": 4,
            "imageWorksPerTarget": 0,
            "entityHomepagesPerTarget": 0,
        }
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

    assert not report["sourceUnavailable"]
    plan = (
        resolve_entity_object_dir(task, batch, entity, etype_hint="景区")
        / "1.download"
        / "article_source_plan.json"
    )
    sources = read_json(plan)["payload"]["sources"]
    assert sum(1 for source in sources if source["sourceRole"] == "base") >= 4
    assert "https://example.com/article/0" not in {source["url"] for source in sources}
    reused_base_sources = [
        source
        for source in sources
        if source["sourceRole"] == "base"
        and source["discoveryProvider"] == "verified_source_pool_reuse"
    ]
    assert len(reused_base_sources) >= 4


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
    assert _known_official_website("故宫博物院") == "https://www.dpm.org.cn/Home.html"
    assert _travel_registry_url_fetchable("https://www.dpm.org.cn/Home.html")
    palace = _source(
        source_id="home_official",
        platform="景区官网",
        url="https://www.dpm.org.cn/Home.html",
        category="official",
        discovery_provider="travel_source_registry",
        match_confidence=0.94,
        source_role="primary",
    )
    assert _candidate_gate(palace, entity_id="故宫博物院", lane="homepage")["passed"]
    assert _known_official_website("秦始皇帝陵博物院景区") == "https://www.bmy.com.cn/index.html"
    assert _travel_registry_url_fetchable("https://www.bmy.com.cn/index.html")
    assert _known_official_website("黄果树瀑布景区") == "https://www.hgscn.com/"
    assert _travel_registry_url_fetchable("https://www.hgscn.com/")
    assert _known_official_website("布达拉宫景区") == "https://www.potalapalace.cn/"
    assert _travel_registry_url_fetchable("https://www.potalapalace.cn/")
    assert _known_official_website("毕棚沟") == "http://www.bipenggou.net/"
    assert _known_official_website("碧峰峡") == "http://www.bifengxia.com/info?crid=74&lan=cn&ckey=jqgk_dfbfx"
    assert _known_official_website("蜀南竹海") == "https://www.snzh.cn/"
    assert _known_official_website("海螺沟") == "https://www.hailuogou.com/"
    assert _known_official_website("青城山") == "https://www.djy517.com/"
    assert _known_official_website("南京市夫子庙－秦淮风光带") == "http://www.njfzm.net/brc/40.htm"
    assert _known_official_website("乐山大佛") == ""
    fuzimiao_support = _known_homepage_support_websites("南京市夫子庙－秦淮风光带")
    assert any(
        row["source_id"] == "home_wikipedia_fuzimiao"
        and row["category"] == "encyclopedia"
        and row["platform"] == "维基百科"
        for row in fuzimiao_support
    )
    tianxia_support = _known_homepage_support_websites("天下第一泉景区")
    assert {
        row["source_id"]
        for row in tianxia_support
        if row["category"] == "encyclopedia"
    } >= {"home_wikipedia_baotu_spring", "home_wikipedia_daming_lake"}
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
    tianjin_support = _known_homepage_support_websites("天津古文化街旅游区（津门故里）")
    assert any(
        row["source_id"] == "home_wikipedia_tianjin_ancient_culture_street"
        and row["category"] == "encyclopedia"
        and row["platform"] == "维基百科"
        for row in tianjin_support
    )
    assert {
        _known_homepage_support_websites(entity)[0]["source_id"]
        for entity in (
            "秦始皇帝陵博物院景区",
            "龙门石窟景区",
            "黄山风景区",
            "杭州西湖风景区",
            "鼓浪屿风景名胜区",
            "喀纳斯景区",
        )
    } == {
        "home_wikipedia_mausoleum_of_qin_shi_huang",
        "home_wikipedia_longmen_grottoes",
        "home_wikipedia_huangshan",
        "home_wikipedia_west_lake",
        "home_wikipedia_gulangyu",
        "home_wikipedia_kanas_lake",
    }


def test_auto_research_curl_json_preserves_call_timeout_and_retry_floor():
    original_timeout = research_plan_mod._AUTO_RESEARCH_CURL_TIMEOUT_SECONDS
    original_retries = research_plan_mod._AUTO_RESEARCH_CURL_RETRIES
    original_run = research_plan_mod.subprocess.run
    calls: list[list[str]] = []

    class _Proc:
        returncode = 0
        stdout = b'{"ok": true}'

    def _fake_run(cmd, *, capture_output, check):
        _ = (capture_output, check)
        calls.append(list(cmd))
        return _Proc()

    try:
        research_plan_mod._AUTO_RESEARCH_CURL_TIMEOUT_SECONDS = 7
        research_plan_mod._AUTO_RESEARCH_CURL_RETRIES = 0
        research_plan_mod.subprocess.run = _fake_run
        assert research_plan_mod._curl_json("https://example.test/api", timeout=25) == {"ok": True}
    finally:
        research_plan_mod._AUTO_RESEARCH_CURL_TIMEOUT_SECONDS = original_timeout
        research_plan_mod._AUTO_RESEARCH_CURL_RETRIES = original_retries
        research_plan_mod.subprocess.run = original_run

    cmd = calls[0]
    assert cmd[cmd.index("--max-time") + 1] == "25"
    assert cmd[cmd.index("--retry") + 1] == "1"


def test_auto_research_curl_json_tolerates_non_utf8_stdout():
    original_run = research_plan_mod.subprocess.run

    class _Proc:
        returncode = 0
        stdout = b'{"ok": "\\xff"}\xff'

    def _fake_run(cmd, *, capture_output, check):
        _ = (cmd, capture_output, check)
        return _Proc()

    try:
        research_plan_mod.subprocess.run = _fake_run
        assert research_plan_mod._curl_json("https://example.test/bad-encoding") == {}
    finally:
        research_plan_mod.subprocess.run = original_run


def test_source_quality_entity_grounding_accepts_common_entity_alias():
    assessment = score_source_markdown(
        "article_qunar_base_1",
        "杭州西湖适合清晨从断桥一路走到苏堤，沿线有门票、开放和交通提示。"
        "很多游客会把雷峰塔和三潭印月放在同一天，下午再返程。",
        entity_name="杭州西湖风景区",
    )
    assert "entity_grounded" in assessment.reasons
    assert assessment.quality != "Reject"


def test_source_quality_keeps_long_entity_grounded_ugc_with_platform_chrome():
    body = (
        "去哪儿攻略 首页 游记详情 相关游记。"
        "山海关早上可以先从天下第一关进入，随后步行到老龙头看海边长城。"
        "自驾到景区停车场后，建议把开放时间、门票和观光车信息提前核对；"
        "中午在关内吃浑锅，下午再去老龙头看日落，返程前可以顺路买糕点。"
        "如果带孩子，秦皇岛野生动物园和山海关可以拆成两天，车程和住宿都更轻松。"
    )
    assessment = score_source_markdown(
        "article_qunar_base_1",
        body,
        entity_name="山海关景区",
    )
    assert "platform_visible" in assessment.reasons
    assert "entity_grounded" in assessment.reasons
    assert assessment.quality != "Reject"


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"source plan guidance tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
