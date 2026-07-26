from __future__ import annotations



from support.source_plan_guidance_fixtures import *  # noqa: F401,F403
from content.source.research import network_io as network_io_mod  # noqa: E402
from content.source.research import source_quality as source_quality_mod  # noqa: E402
from content.source.research import qunar_sources as qunar_sources_mod  # noqa: E402



def test_prepare_source_plan_includes_registry_guidance_for_travel():
    task = "20260711--travel-article-source-guidance--test-region-b--pilot-001"
    entity = {"entityId": "九寨沟", "canonicalName": "九寨沟", "entityType": "景区"}
    prepare_source_plan(task, [entity])
    plan = (
        resolve_entity_object_dir(task, "九寨沟", etype_hint="景区")
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
    shared = read_json(execution_root(task) / guidance_ref)
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

def test_homepage_wikivoyage_preserves_explicit_encyclopedia_category():
    source = _source(
        source_id="home_wikivoyage",
        platform="维基导游",
        url="https://zh.wikivoyage.org/wiki/九寨沟",
        category="encyclopedia",
        discovery_provider="test",
        match_confidence=0.9,
    )
    assert source["category"] == "encyclopedia"

def test_qunar_travelogue_sources_search_multiple_entity_aliases():
    original_curl_json = network_io_mod.curl_json
    original_sleep = qunar_sources_mod.time.sleep
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
        network_io_mod.curl_json = _fake_curl_json
        qunar_sources_mod.time.sleep = lambda *_args, **_kwargs: None
        sources = _qunar_travelogue_sources(
            "八达岭—慕田峪长城旅游区",
            entity_aliases=[],
            limit=4,
        )
    finally:
        network_io_mod.curl_json = original_curl_json
        qunar_sources_mod.time.sleep = original_sleep

    assert "八达岭" in queries
    assert len(sources) == 1
    assert sources[0]["sourceRole"] == "base"
    assert sources[0]["url"] == "https://touch.travel.qunar.com/youji/10001"

def test_qunar_travelogue_sources_preserve_author_and_freshness_metadata():
    original_curl_json = network_io_mod.curl_json
    original_curl_text = network_io_mod.curl_text
    original_sleep = qunar_sources_mod.time.sleep

    def _fake_curl_json(url: str, *, timeout: int = 0):
        _ = timeout
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("q", [""])[0]
        if query != "锦里":
            return {"ret": True, "data": {"bookList": [], "more": False}}
        return {
            "ret": True,
            "data": {
                "bookList": [
                    {
                        "id": "7869929",
                        "title": "成都及周边6天5晚自由行",
                        "travelRoute": ["锦里古街", "成都大熊猫繁育研究基地"],
                        "cityName": "成都",
                        "userId": "1355244214@qunar",
                        "userName": "去哪儿用户",
                        "startTime": 1727539200000,
                    }
                ],
                "more": False,
            },
        }

    try:
        network_io_mod.curl_json = _fake_curl_json
        network_io_mod.curl_text = lambda *_args, **_kwargs: ""
        qunar_sources_mod.time.sleep = lambda *_args, **_kwargs: None
        sources = _qunar_travelogue_sources("锦里", entity_aliases=["锦里古街"], limit=4)
    finally:
        network_io_mod.curl_json = original_curl_json
        network_io_mod.curl_text = original_curl_text
        qunar_sources_mod.time.sleep = original_sleep

    assert sources[0]["authorName"] == "去哪儿用户"
    assert sources[0]["authorId"] == "1355244214@qunar"
    assert sources[0]["authorBooksUrl"] == "https://touch.travel.qunar.com/1355244214@qunar/books"
    assert sources[0]["publishedAt"] == "2024-09-29"

def test_qunar_travelogue_sources_prioritize_high_intent_queries():
    original_curl_json = network_io_mod.curl_json
    original_curl_text = network_io_mod.curl_text
    original_sleep = qunar_sources_mod.time.sleep
    queries: list[str] = []

    def _fake_curl_json(url: str, *, timeout: int = 0):
        _ = timeout
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("q", [""])[0]
        queries.append(query)
        if query != "都江堰攻略":
            return {"ret": True, "data": {"bookList": [], "more": False}}
        return {
            "ret": True,
            "data": {
                "bookList": [
                    {
                        "id": "7783661",
                        "title": "成都—都江堰5日游攻略",
                        "travelRoute": ["都江堰景区", "青城山"],
                        "userId": "1383305677@qunar",
                        "userName": "去哪儿用户",
                        "startTime": 1684252800000,
                    }
                ],
                "more": False,
            },
        }

    try:
        network_io_mod.curl_json = _fake_curl_json
        network_io_mod.curl_text = lambda *_args, **_kwargs: ""
        qunar_sources_mod.time.sleep = lambda *_args, **_kwargs: None
        sources = _qunar_travelogue_sources("都江堰", limit=4)
    finally:
        network_io_mod.curl_json = original_curl_json
        network_io_mod.curl_text = original_curl_text
        qunar_sources_mod.time.sleep = original_sleep

    assert queries[0] == "都江堰攻略"
    assert sources[0]["url"] == "https://touch.travel.qunar.com/youji/7783661"
    assert sources[0]["title"] == "成都—都江堰5日游攻略"

def test_qunar_travelogue_sources_expand_same_author_books_page():
    original_curl_json = network_io_mod.curl_json
    original_curl_text = network_io_mod.curl_text
    original_sleep = qunar_sources_mod.time.sleep

    def _fake_curl_json(url: str, *, timeout: int = 0):
        _ = timeout
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("q", [""])[0]
        if query != "锦里":
            return {"ret": True, "data": {"bookList": [], "more": False}}
        return {
            "ret": True,
            "data": {
                "bookList": [
                    {
                        "id": "7825234",
                        "title": "成都的乒乓、熊猫之旅",
                        "travelRoute": ["锦里古街", "杜甫草堂"],
                        "userId": "265590601@qunar",
                        "userName": "猫成",
                        "startTime": 1714521600000,
                    }
                ],
                "more": False,
            },
        }

    def _fake_curl_text(url: str, *, timeout: int = 0):
        _ = timeout
        assert url == "https://touch.travel.qunar.com/265590601@qunar/books"
        return (
            '<a href="https://touch.travel.qunar.com/youji/7825234" class="list_txt_link">'
            '<p class="tit-text">成都的乒乓、熊猫之旅</p><p class="tit-time">2024.05.01出发/共4天</p></a>'
            '<a href="https://touch.travel.qunar.com/youji/7894819" class="list_txt_link">'
            '<p class="tit-text">锦里夜游复盘</p><p class="tit-time">2025.07.06出发/共2天</p></a>'
            '<a href="https://touch.travel.qunar.com/youji/7899999" class="list_txt_link">'
            '<p class="tit-text">山西古建巡游</p><p class="tit-time">2025.07.09出发/共5天</p></a>'
        )

    try:
        network_io_mod.curl_json = _fake_curl_json
        network_io_mod.curl_text = _fake_curl_text
        qunar_sources_mod.time.sleep = lambda *_args, **_kwargs: None
        sources = _qunar_travelogue_sources("锦里", entity_aliases=["锦里古街"], limit=4)
    finally:
        network_io_mod.curl_json = original_curl_json
        network_io_mod.curl_text = original_curl_text
        qunar_sources_mod.time.sleep = original_sleep

    assert [source["url"] for source in sources] == [
        "https://touch.travel.qunar.com/youji/7825234",
        "https://touch.travel.qunar.com/youji/7894819",
    ]
    assert sources[1]["discoveryProvider"] == "qunar_author_books_page"
    assert sources[1]["authorId"] == "265590601@qunar"
    assert sources[1]["publishedAt"] == "2025.07.06出发/共2天"
    assert "https://touch.travel.qunar.com/youji/7899999" not in {
        source["url"] for source in sources
    }

def test_qunar_travelogue_sources_caps_search_budget_and_single_page():
    original_curl_json = network_io_mod.curl_json
    original_sleep = qunar_sources_mod.time.sleep
    calls: list[tuple[str, str]] = []

    def _fake_curl_json(url: str, *, timeout: int = 0):
        _ = timeout
        params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        query = params.get("q", [""])[0]
        page = params.get("page", [""])[0]
        calls.append((query, page))
        return {
            "ret": True,
            "data": {
                "bookList": [
                    {
                        "id": f"900{len(calls)}",
                        "title": "无关城市周末游",
                        "travelRoute": ["无关城市"],
                        "cityName": "无关",
                    }
                ],
                "more": True,
            },
        }

    try:
        network_io_mod.curl_json = _fake_curl_json
        qunar_sources_mod.time.sleep = lambda *_args, **_kwargs: None
        sources = _qunar_travelogue_sources(
            "测试实体甲",
            entity_aliases=["test entity alias"],
            limit=4,
        )
    finally:
        network_io_mod.curl_json = original_curl_json
        qunar_sources_mod.time.sleep = original_sleep

    unique_queries = list(dict.fromkeys(query for query, _page in calls))
    assert sources == []
    assert len(unique_queries) <= 8
    assert "test entity alias" in unique_queries
    assert {page for _query, page in calls} == {"1"}

def test_qunar_travelogue_sources_fetch_second_page_after_anchor_hits():
    original_curl_json = network_io_mod.curl_json
    original_sleep = qunar_sources_mod.time.sleep
    calls: list[tuple[str, str]] = []

    def _fake_curl_json(url: str, *, timeout: int = 0):
        _ = timeout
        params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        query = params.get("q", [""])[0]
        page = params.get("page", [""])[0]
        calls.append((query, page))
        if query != "锦里":
            return {"ret": True, "data": {"bookList": [], "more": False}}
        if page == "1":
            return {
                "ret": True,
                "data": {
                    "bookList": [
                        {
                            "id": "7825234",
                            "title": "锦里夜游攻略",
                            "travelRoute": ["锦里古街"],
                            "cityName": "成都",
                            "viewCount": 100,
                        }
                    ],
                    "more": True,
                },
            }
        return {
            "ret": True,
            "data": {
                "bookList": [
                    {
                        "id": "7894819",
                        "title": "锦里古街半日游",
                        "travelRoute": ["锦里古街", "武侯祠"],
                        "cityName": "成都",
                        "viewCount": 90,
                    }
                ],
                "more": False,
            },
        }

    try:
        network_io_mod.curl_json = _fake_curl_json
        qunar_sources_mod.time.sleep = lambda *_args, **_kwargs: None
        sources = _qunar_travelogue_sources("锦里", entity_aliases=["锦里古街"], limit=4)
    finally:
        network_io_mod.curl_json = original_curl_json
        qunar_sources_mod.time.sleep = original_sleep

    assert [source["url"] for source in sources] == [
        "https://touch.travel.qunar.com/youji/7825234",
        "https://touch.travel.qunar.com/youji/7894819",
    ]
    assert ("锦里", "2") in calls

def test_source_registry_has_no_entity_specific_source_or_alias_fallbacks():
    assert _known_entity_aliases("测试实体甲") == []
    assert _known_article_sources("测试实体甲") == []
    assert _known_official_website("测试实体甲") == ""

def test_homepage_seed_source_four_encyclopedia_closed_set():
    assert _homepage_can_seed_base_draft({
        "sourceKind": "wikipedia",
        "extractor": "wikipedia_api",
        "canonicalUrl": "https://zh.wikipedia.org/wiki/example",
        "policyRevision": "encyclopedia-primary",
    })
    assert _homepage_can_seed_base_draft({
        "sourceKind": "toutiao_baike",
        "extractor": "toutiao_baike_html",
        "canonicalUrl": "https://www.baike.com/wiki/example",
        "policyRevision": "encyclopedia-primary",
    })
    assert not _homepage_can_seed_base_draft({
        "platform": "维基导游",
        "category": "encyclopedia",
        "url": "https://zh.wikivoyage.org/wiki/example",
    })
    assert not _homepage_can_seed_base_draft({
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

def test_qunar_travelogue_sources_match_runtime_alias_route_names():
    original_curl_json = network_io_mod.curl_json
    original_sleep = qunar_sources_mod.time.sleep
    queries: list[str] = []

    def _fake_curl_json(url: str, *, timeout: int = 0):
        _ = timeout
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("q", [""])[0]
        queries.append(query)
        if query != "test entity alias":
            return {"ret": True, "data": {"bookList": [], "more": False}}
        return {
            "ret": True,
            "data": {
                "bookList": [
                    {
                        "id": "7442970",
                        "title": "test entity alias travel note",
                        "travelRoute": ["test entity alias", "other stop"],
                        "cityName": "test city",
                        "userName": "test author",
                        "viewCount": 1200,
                    }
                ],
                "more": False,
            },
        }

    try:
        network_io_mod.curl_json = _fake_curl_json
        qunar_sources_mod.time.sleep = lambda *_args, **_kwargs: None
        sources = _qunar_travelogue_sources(
            "测试实体甲",
            entity_aliases=["test entity alias"],
            limit=4,
        )
    finally:
        network_io_mod.curl_json = original_curl_json
        qunar_sources_mod.time.sleep = original_sleep

    assert "test entity alias" in queries
    assert len(sources) == 1
    assert sources[0]["url"] == "https://touch.travel.qunar.com/youji/7442970"

def test_qunar_travelogue_sources_use_explicit_composite_aliases():
    original_curl_json = network_io_mod.curl_json
    original_sleep = qunar_sources_mod.time.sleep
    queries: list[str] = []

    def _fake_curl_json(url: str, *, timeout: int = 0):
        _ = timeout
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("q", [""])[0]
        queries.append(query)
        if query != "test entity composite alias":
            return {"ret": True, "data": {"bookList": [], "more": False}}
        return {
            "ret": True,
            "data": {
                "bookList": [
                    {
                        "id": "7674519",
                        "title": "test entity composite alias journey",
                        "travelRoute": ["test entity composite alias", "other stop"],
                        "cityName": "test city",
                        "userName": "test author",
                        "viewCount": 1200,
                    }
                ],
                "more": False,
            },
        }

    try:
        network_io_mod.curl_json = _fake_curl_json
        qunar_sources_mod.time.sleep = lambda *_args, **_kwargs: None
        sources = _qunar_travelogue_sources(
            "测试实体甲",
            entity_aliases=["test entity composite alias"],
            limit=4,
        )
    finally:
        network_io_mod.curl_json = original_curl_json
        qunar_sources_mod.time.sleep = original_sleep

    assert "test entity composite alias" in queries
    assert len(sources) == 1
    assert sources[0]["url"] == "https://touch.travel.qunar.com/youji/7674519"

def test_qunar_travelogue_sources_search_explicit_aliases():
    original_curl_json = network_io_mod.curl_json
    original_sleep = qunar_sources_mod.time.sleep
    queries: list[str] = []

    def _fake_curl_json(url: str, *, timeout: int = 0):
        _ = timeout
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("q", [""])[0]
        queries.append(query)
        if query != "test entity search alias":
            return {"ret": True, "data": {"bookList": [], "more": False}}
        return {
            "ret": True,
            "data": {
                "bookList": [
                    {
                        "id": "7900533",
                        "title": "test entity search alias journey",
                        "travelRoute": ["test entity search alias", "other stop"],
                        "cityName": "test city",
                        "userName": "test author",
                        "viewCount": 1200,
                    }
                ],
                "more": False,
            },
        }

    try:
        network_io_mod.curl_json = _fake_curl_json
        qunar_sources_mod.time.sleep = lambda *_args, **_kwargs: None
        sources = _qunar_travelogue_sources(
            "测试实体甲",
            entity_aliases=["test entity search alias"],
            limit=4,
        )
    finally:
        network_io_mod.curl_json = original_curl_json
        qunar_sources_mod.time.sleep = original_sleep

    assert "test entity search alias" in queries
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

def test_homepage_entity_specific_support_override_is_removed():
    assert not hasattr(source_quality_mod, "_known_homepage_support_websites")

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

def test_homepage_core_sources_only_keep_four_encyclopedia_closed_set():
    from content.source.research.homepage_source_policy import _homepage_core_sources

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
            source_kind="wikipedia",
            source_title="九寨沟",
            category="encyclopedia",
            discovery_provider="test",
            match_confidence=0.99,
        ),
        _source(
            source_id="home_wikivoyage",
            platform="维基导游",
            url="https://zh.wikivoyage.org/wiki/九寨沟",
            category="encyclopedia",
            discovery_provider="test",
            match_confidence=0.88,
        ),
        _source(
            source_id="home_baidu",
            platform="百度百科",
            url="https://baike.baidu.com/item/九寨沟",
            source_kind="baidu_baike",
            source_title="九寨沟",
            category="encyclopedia",
            discovery_provider="test",
            match_confidence=0.86,
        ),
        _source(
            source_id="home_toutiao",
            platform="今日头条百科",
            url="https://www.baike.com/wiki/九寨沟",
            source_kind="toutiao_baike",
            source_title="九寨沟",
            category="encyclopedia",
            discovery_provider="test",
            match_confidence=0.92,
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
    assert len(selected) == 3
    selected_ids = {source["source_id"] for source in selected}
    assert selected_ids == {"home_wikipedia", "home_baidu", "home_toutiao"}
    assert selected[0]["source_id"] == "home_wikipedia"
    assert "home_media" not in selected_ids
    assert "home_official" not in selected_ids
    assert "home_support_gov" not in selected_ids
    assert "home_wikivoyage" not in selected_ids

def test_source_unit_image_collection_id_is_global_not_local_source_id():
    from content.source.handler_images import stable_source_image_collection_id

    cid = stable_source_image_collection_id(
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
    from content.source.handler_images import stable_source_image_collection_id

    common_category = "https://commons.wikimedia.org/wiki/Category%3AMount_Qingcheng"
    cid_a = stable_source_image_collection_id(
        entity_id="青城山",
        source_id="article_qunar_base_3",
        spec={
            "collectionPageUrl": common_category,
            "authorizationProof": "https://commons.wikimedia.org/wiki/File:Mount_Qingcheng_A.jpg",
            "sourceUrl": "https://commons.wikimedia.org/wiki/File:Mount_Qingcheng_A.jpg",
        },
    )
    cid_b = stable_source_image_collection_id(
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

def test_provider_policy_controls_fetchability_without_entity_url_special_cases():
    assert _travel_registry_url_fetchable("https://zh.wikipedia.org/wiki/Test_entity")
    assert not _travel_registry_url_fetchable("https://blocked.example.invalid/测试实体甲")
    official = _source(
        source_id="home_official",
        platform="official site",
        url="https://example.com/about",
        category="official",
        discovery_provider="provider_policy",
        match_confidence=0.94,
        source_role="primary",
    )
    assert not _homepage_can_seed_base_draft(official)
