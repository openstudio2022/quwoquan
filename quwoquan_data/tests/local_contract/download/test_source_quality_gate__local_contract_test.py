from __future__ import annotations



from support.source_plan_guidance_fixtures import *  # noqa: F401,F403



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

def test_verified_homepage_reuse_filters_bad_or_thin_source_units():
    # 源单元复用过滤：消歧页/过短页应滤除，正常官网主页保留。
    # 真相源是 iter_source_units 读取的新版 sources/su_* 布局，故用 write_source_unit 写入，
    # 不再手工拼旧版 1.download/sources/NN.name（已随源单元布局迁移废弃，会被 iter 漏读）。
    from _common.source_unit import write_source_unit
    from _common.paths import ensure_task_layout, ensure_batch_layout
    from _common.batch_manifest import write_batch_manifest

    task = "旅行/地域/测试省/景区/homepage复用过滤"
    batch = "source_units"
    entity = "沙湖旅游景区"
    obj = resolve_entity_object_dir(task, batch, entity, etype_hint="地点/景区")
    shutil.rmtree(obj, ignore_errors=True)
    ensure_task_layout(task)
    ensure_batch_layout(task, batch, "download")
    write_batch_manifest(task, batch, command="download")
    target_ref = f"/entity/地点/景区/{entity}"

    write_source_unit(
        obj,
        ordinal=1,
        source_id="home_wikipedia",
        source_md="\n".join(
            [
                "沙湖可以指：",
                "沙湖：位于宁夏石嘴山市的湖泊。",
                "沙湖：位于武汉市的湖泊。",
                "沙湖：位于苏州市的湖泊。",
            ]
        ),
        quality={"sourceId": "home_wikipedia", "quality": "B-fact", "score": 6, "url": "https://zh.wikipedia.org/wiki/%E6%B2%99%E6%B9%96"},
        platform="维基百科",
        source_category="encyclopedia",
        research_lane="homepage",
        url="https://zh.wikipedia.org/wiki/%E6%B2%99%E6%B9%96",
        title="沙湖（消歧义）",
        target_ref=target_ref,
        task_id=task,
        batch_id=batch,
    )

    write_source_unit(
        obj,
        ordinal=2,
        source_id="home_official_thin",
        source_md="沙湖旅游景区位于宁夏，是一个景区简介页面。",
        quality={"sourceId": "home_official_thin", "quality": "B-fact", "score": 6, "url": "https://example.com/shahu"},
        platform="景区官网",
        source_category="official",
        research_lane="homepage",
        url="https://example.com/shahu",
        title="沙湖旅游景区",
        target_ref=target_ref,
        task_id=task,
        batch_id=batch,
    )

    write_source_unit(
        obj,
        ordinal=3,
        source_id="home_official",
        source_md=(
            "沙湖旅游景区位于宁夏石嘴山市平罗县境内。"
            "沙湖旅游景区由湖泊、沙漠、湿地和芦苇景观组成。"
            "沙湖旅游景区是国家5A级旅游景区。"
            "沙湖旅游景区主要游览项目包括湖区观光、沙漠体验和湿地观鸟。"
            "沙湖旅游景区开放、票务和交通接驳规则以官方公告为准。"
        ),
        quality={"sourceId": "home_official", "quality": "B-fact", "score": 6, "url": "https://example.com/shahu-home"},
        platform="景区官网",
        source_category="official",
        research_lane="homepage",
        url="https://example.com/shahu-home",
        title="沙湖旅游景区",
        target_ref=target_ref,
        task_id=task,
        batch_id=batch,
    )

    sources = _verified_homepage_sources_from_source_units(
        task,
        batch,
        entity,
        entity_type="地点/景区",
    )

    assert [source["source_id"] for source in sources] == ["home_official"]

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
                # RC4：文章配图必须同源（来自文章底稿自身图片）；本用例验证的是
                # 源「类别」是否被平等接纳，不再借用 same_authorized_collection 跨源图集。
                image_evidence_mode="same_source",
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

def test_clean_source_markdown_strips_wiki_tail_sections_and_citations():
    raw = (
        "---\n"
        "url: https://zh.wikipedia.org/wiki/都江堰\n"
        "platform: 维基百科\n"
        "title: 都江堰\n"
        "---\n"
        "都江堰位于四川省成都平原西部的岷江上，是著名的水利工程[1]。\n"
        "由秦国蜀郡太守李冰主持修建[12]，至今仍在灌溉成都平原。\n\n"
        "== 历史 ==\n"
        "都江堰始建于公元前256年，是世界文化遗产。\n\n"
        "== 参见 ==\n"
        "青城山\n"
        "=== 子条目 ===\n"
        "宝瓶口\n"
        "== 参考文献 ==\n"
        "李冰传[来源请求]\n"
        "https://example.com/ref1\n"
        "== 外部链接 ==\n"
        "官方网站 https://dujiangyan.gov.cn\n"
        "互联网档案馆 页面存档\n"
    )
    cleaned = clean_source_markdown(raw, raw_format="mediawiki_api_json")
    # 正文与正常小节保留
    assert "都江堰位于四川省" in cleaned
    assert "历史" in cleaned and "都江堰始建于公元前256年" in cleaned
    # 行内引用/失链标记清除
    assert "[1]" not in cleaned and "[12]" not in cleaned and "[来源请求]" not in cleaned
    # 尾节（含子节）整体剔除
    assert "参见" not in cleaned and "青城山" not in cleaned and "宝瓶口" not in cleaned
    assert "参考文献" not in cleaned and "李冰传" not in cleaned
    assert "外部链接" not in cleaned and "dujiangyan.gov.cn" not in cleaned
    assert "互联网档案馆" not in cleaned
    # 纯链接行被样板过滤
    assert "http" not in cleaned

def test_clean_source_markdown_differs_from_raw_and_keeps_facts():
    raw = (
        "成都自驾2小时到都江堰，建议先看开放时间和门票，再坐观光车进景区[3]。\n"
        "登录\n"
        "查看更多\n"
        "https://ad.example.com/promo\n"
        "鱼嘴把岷江分为内外江，是分水关键。\n"
    )
    cleaned = clean_source_markdown(raw)
    assert "开放时间" in cleaned and "门票" in cleaned and "观光车" in cleaned
    assert "鱼嘴把岷江分为内外江" in cleaned
    # 导航/广告/纯链接样板被剔除，clean 与 raw 不再雷同
    assert "登录" not in cleaned and "查看更多" not in cleaned
    assert "ad.example.com" not in cleaned
    assert "[3]" not in cleaned
    assert cleaned != raw

