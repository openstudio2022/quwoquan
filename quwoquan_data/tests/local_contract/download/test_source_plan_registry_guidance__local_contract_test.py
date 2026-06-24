from __future__ import annotations



from support.source_plan_guidance_fixtures import *  # noqa: F401,F403



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
    # 静态采源指引抽到批次共享文件单一存放，per-entity 计划只保留摘要 + 引用，避免上千行重复内联。
    summary = payload["sourceCategorySummary"]
    assert summary["coreCategories"] == ["encyclopedia"]
    assert "travelogue" in summary["preferredCategories"]
    assert "official" in summary["preferredCategories"]
    assert "sourceCategoryGuidance" not in payload, "完整类别指引不应再内联进 per-entity 计划"
    assert "sourceRegistryGuidance" not in payload, "站点注册表指引不应再内联进 per-entity 计划"

    guidance_ref = payload["sourceGuidanceRef"]
    shared = read_json(batch_root(task, batch) / guidance_ref)
    assert shared["sourceCategoryGuidance"]["categories"]
    assert shared["sourceCategoryGuidance"]["coreCategories"] == ["encyclopedia"]
    registry = shared["sourceRegistryGuidance"]
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

