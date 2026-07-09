from __future__ import annotations



from support.source_plan_guidance_fixtures import *  # noqa: F401,F403



def test_parallel_auto_research_writes_availability_report():
    import download.research_plan as research_mod

    spec = store.scaffold_spec(
        vertical="travel",
        organize_by="地域",
        key="测试省",
        category="景区",
        name="并行可用性报告隔离",
        scope={
            "region": "测试省",
            "entityTypes": ["地点/景区"],
            "coverageTargets": [
                {"entityType": "地点/景区", "name": "可用景区"},
                {"entityType": "地点/景区", "name": "缺源景区"},
            ],
        },
        content={
            "modalityContract": "separated_research",
            "quotas": {
                "entityHomepagesPerTarget": 1,
                "entityArticlesPerTarget": 1,
                "imageWorksPerTarget": 1,
            },
        },
        created_by="test",
    )
    task = spec["taskId"]
    store.save_spec(spec)
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
        "_qunar_review_support_source": research_mod._qunar_review_support_source,
        "_known_article_sources": research_mod._known_article_sources,
    }

    def fake_wiki_title(host: str, entity_id: str) -> str:
        if entity_id == "可用景区" and host == "zh.wikipedia.org":
            return entity_id
        return ""

    def fake_qunar(
        entity_id: str,
        *,
        entity_aliases: list[str] | tuple[str, ...] = (),
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
                # RC4：UGC 游记文章配图必须同源；不再用 same_authorized_collection 跨源图集。
                image_evidence_mode="same_source",
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
        research_mod._qunar_review_support_source = lambda entity_id: _source(
            source_id="article_no_fallback",
            platform="测试",
            url="",
            category="travelogue",
            source_role="base",
        )
        research_mod._known_article_sources = lambda entity_id: []
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
    assert diagnostics["desiredImageWorks"] >= 1
    assert diagnostics["requiredImageWorks"] == 0
    assert diagnostics["poolCounts"]["acceptedCollections"] == 0
    assert diagnostics["sourceUnavailable"][0]["nextAction"] == "manual_authorized_gallery_or_target_replacement"


def test_parallel_auto_research_persists_incremental_report_on_interrupt(monkeypatch):
    import pytest
    import time
    import download.research.auto_plan_public as public_mod

    task = "旅行/地域/测试省/景区/并行中断增量报告"
    batch = "parallel_incremental_interrupt"
    shared = batch_root(task, batch) / "_shared"
    shared.mkdir(parents=True, exist_ok=True)
    write_json(
        shared / "auto_research_plan.json",
        {
            "schemaVersion": "quwoquan.download.auto_research_plan",
            "taskId": task,
            "batchId": batch,
            "vertical": "travel",
            "updated": [{"entityId": "既有景区", "lane": "article", "sources": 4}],
            "issues": [],
            "candidates": [{"entityId": "既有景区", "lane": "article", "passed": True}],
            "imageCollections": [],
            "sourceUnavailable": [],
            "waves": [{"scope": "primary", "entityIds": ["既有景区"]}],
            "sourceAvailability": {
                "readyTargets": ["既有景区"],
                "readyTargetCount": 1,
                "ineligibleTargets": [],
                "ineligibleTargetCount": 0,
            },
            "throughput": {"maxWorkers": 2, "entityCount": 1, "elapsedSeconds": 10.0},
        },
    )

    def fake_prepare_source_plan(*_args, **_kwargs):
        return None

    def fake_impl(_task_id, _batch_id, entity_ids, **_kwargs):
        entity_id = entity_ids[0]
        if entity_id == "慢景区":
            time.sleep(0.05)
            raise KeyboardInterrupt()
        return {
            "schemaVersion": "quwoquan.download.auto_research_plan",
            "taskId": task,
            "batchId": batch,
            "vertical": "travel",
            "updated": [{"entityId": entity_id, "lane": "article", "sources": 4}],
            "issues": [],
            "candidates": [{"entityId": entity_id, "lane": "article", "passed": True}],
            "imageCollections": [],
            "sourceUnavailable": [],
            "rescueEvents": [],
        }

    monkeypatch.setattr(public_mod, "prepare_source_plan", fake_prepare_source_plan)
    monkeypatch.setattr(public_mod, "_write_auto_research_plans_impl", fake_impl)

    with pytest.raises(KeyboardInterrupt):
        write_auto_research_plans(
            task,
            batch,
            ["快景区", "慢景区"],
            entity_type="景区",
            max_workers=2,
        )

    persisted = read_json(shared / "auto_research_plan.json")
    assert persisted["partialRun"] is True
    assert persisted["partialReason"] == "interrupted_auto_research_checkpoint"
    assert persisted["remainingEntityIds"] == ["慢景区"]
    assert persisted["sourceAvailability"]["readyTargetCount"] == 2
    assert persisted["sourceAvailability"]["readyTargets"] == ["快景区", "既有景区"]
    assert [item["entityId"] for item in persisted["updated"]] == ["既有景区", "快景区"]
    progress = read_json(shared / "auto_research_progress.json")
    assert progress["status"] == "interrupted"
    assert progress["completedCount"] == 1


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
                # RC4：UGC 游记文章配图必须同源；不再用 same_authorized_collection 跨源图集。
                image_evidence_mode="same_source",
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

def test_homepage_registry_wiki_support_hydrates_same_source_images():
    import download.research_plan as research_mod

    task = "旅行/地域/测试省/景区/homepage注册wiki补图"
    batch = "homepage_registry_wiki_hydrate"
    entity = "武侯祠"
    support_title = "成都武侯祠"
    support_url = "https://zh.wikipedia.org/wiki/%E6%88%90%E9%83%BD%E6%AD%A6%E4%BE%AF%E7%A5%A0"
    support_image = {
        "url": "https://upload.wikimedia.org/wikipedia/commons/bb/Chengdu_Wuhou_Shrine.jpg",
        "license": "CC BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:Chengdu_Wuhou_Shrine.jpg",
        "width": 1600,
        "height": 1000,
        "caption": support_title,
        "relevance": support_title,
        "creator": "Wiki contributor",
        "collectionPageUrl": support_url,
        "platform": "维基百科",
        "sourceUrl": "https://commons.wikimedia.org/wiki/File:Chengdu_Wuhou_Shrine.jpg",
        "licenseSnapshot": "CC BY-SA 4.0 snapshot",
        "usageScope": "app_publish",
    }
    originals = {
        "_wiki_title_for_entity": research_mod._wiki_title_for_entity,
        "_wiki_related_titles_for_entity": research_mod._wiki_related_titles_for_entity,
        "_wikidata_item_for_zhwiki": research_mod._wikidata_item_for_zhwiki,
        "_wikidata_item_for_entity_search": research_mod._wikidata_item_for_entity_search,
        "_wikidata_entity_aliases": research_mod._wikidata_entity_aliases,
        "_official_website": research_mod._official_website,
        "_known_official_website": research_mod._known_official_website,
        "_known_homepage_support_websites": research_mod._known_homepage_support_websites,
        "_verified_image_collections_from_prior_plans": research_mod._verified_image_collections_from_prior_plans,
        "_discover_open_license_image_pools": research_mod._discover_open_license_image_pools,
        "_trusted_external_links": research_mod._trusted_external_links,
        "_qunar_travelogue_sources": research_mod._qunar_travelogue_sources,
        "_mediawiki_page_images": research_mod._mediawiki_page_images,
    }

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("homepage-only repair must not run visual/article discovery")

    try:
        research_mod._wiki_title_for_entity = lambda host, entity_id, entity_aliases=(): ""
        research_mod._wiki_related_titles_for_entity = lambda host, entity_id, entity_aliases=(): []
        research_mod._wikidata_item_for_zhwiki = lambda title: ""
        research_mod._wikidata_item_for_entity_search = lambda entity_id: ""
        research_mod._wikidata_entity_aliases = lambda qid: []
        research_mod._official_website = lambda qid: ""
        research_mod._known_official_website = lambda entity_id: ""
        research_mod._known_homepage_support_websites = lambda entity_id: (
            [
                {
                    "source_id": "home_wikipedia_chengdu_wuhou_shrine",
                    "platform": "维基百科",
                    "url": support_url,
                    "category": "encyclopedia",
                }
            ]
            if entity_id == entity
            else []
        )
        research_mod._verified_image_collections_from_prior_plans = fail_if_called
        research_mod._discover_open_license_image_pools = fail_if_called
        research_mod._trusted_external_links = fail_if_called
        research_mod._qunar_travelogue_sources = fail_if_called
        research_mod._mediawiki_page_images = (
            lambda host, title, entity_id, limit=8: [support_image]
            if host == "zh.wikipedia.org" and title == support_title and entity_id == entity
            else []
        )
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
    plan = (
        resolve_entity_object_dir(task, batch, entity, etype_hint="景区")
        / "1.download"
        / "homepage_source_plan.json"
    )
    sources = read_json(plan)["payload"]["sources"]
    support_source = next(
        source
        for source in sources
        if source.get("source_id") == "home_wikipedia_chengdu_wuhou_shrine"
    )
    assert support_source["discoveryProvider"] == "travel_source_registry"
    assert support_source["imageEvidenceMode"] == "same_source"
    assert [item["url"] for item in support_source["imageUrls"]] == [support_image["url"]]


def test_homepage_registry_sources_without_same_source_images_mark_target_ineligible():
    import download.research_plan as research_mod

    task = "旅行/地域/测试省/景区/homepage注册wiki无图"
    batch = "homepage_registry_wiki_no_same_source"
    entity = "瓦屋山"
    homepage_url = "https://zh.wikipedia.org/wiki/%E7%93%A6%E5%B1%8B%E5%B1%B1"
    originals = {
        "_wiki_title_for_entity": research_mod._wiki_title_for_entity,
        "_wiki_related_titles_for_entity": research_mod._wiki_related_titles_for_entity,
        "_wikidata_item_for_zhwiki": research_mod._wikidata_item_for_zhwiki,
        "_wikidata_item_for_entity_search": research_mod._wikidata_item_for_entity_search,
        "_wikidata_entity_aliases": research_mod._wikidata_entity_aliases,
        "_official_website": research_mod._official_website,
        "_known_official_website": research_mod._known_official_website,
        "_known_homepage_support_websites": research_mod._known_homepage_support_websites,
        "_verified_image_collections_from_prior_plans": research_mod._verified_image_collections_from_prior_plans,
        "_discover_open_license_image_pools": research_mod._discover_open_license_image_pools,
        "_trusted_external_links": research_mod._trusted_external_links,
        "_qunar_travelogue_sources": research_mod._qunar_travelogue_sources,
        "_mediawiki_page_images": research_mod._mediawiki_page_images,
    }

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("homepage-only repair must not run visual/article discovery")

    try:
        research_mod._wiki_title_for_entity = (
            lambda host, entity_id, entity_aliases=(): entity
            if host == "zh.wikipedia.org" and entity_id == entity
            else ""
        )
        research_mod._wiki_related_titles_for_entity = lambda host, entity_id, entity_aliases=(): []
        research_mod._wikidata_item_for_zhwiki = lambda title: ""
        research_mod._wikidata_item_for_entity_search = lambda entity_id: ""
        research_mod._wikidata_entity_aliases = lambda qid: []
        research_mod._official_website = lambda qid: ""
        research_mod._known_official_website = lambda entity_id: ""
        research_mod._known_homepage_support_websites = lambda entity_id: (
            [
                {
                    "source_id": "home_wikipedia_wawu_mountain",
                    "platform": "维基百科",
                    "url": homepage_url,
                    "category": "encyclopedia",
                }
            ]
            if entity_id == entity
            else []
        )
        research_mod._verified_image_collections_from_prior_plans = fail_if_called
        research_mod._discover_open_license_image_pools = fail_if_called
        research_mod._trusted_external_links = fail_if_called
        research_mod._qunar_travelogue_sources = fail_if_called
        research_mod._mediawiki_page_images = lambda host, title, entity_id, limit=8: []
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
    assert report["sourceAvailability"]["readyTargets"] == []
    assert [item["entityId"] for item in report["sourceAvailability"]["ineligibleTargets"]] == [entity]
    blocker = report["sourceUnavailable"][0]
    assert blocker["lane"] == "homepage"
    assert blocker["nextAction"] == "manual_homepage_seed_source_or_target_replacement"
    assert "same-source publishable image evidence" in blocker["reason"]
    plan = (
        resolve_entity_object_dir(task, batch, entity, etype_hint="景区")
        / "1.download"
        / "homepage_source_plan.json"
    )
    sources = read_json(plan)["payload"]["sources"]
    assert {source["source_id"] for source in sources} >= {
        "home_wikipedia",
        "home_wikipedia_wawu_mountain",
        "home_baidu_baike",
    }
    assert all(str(source.get("imageEvidenceMode") or "") == "" for source in sources)

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
            lambda entity_id, entity_aliases=(), limit=4: []
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


def test_auto_research_article_commercial_closure_blocks_known_and_prior_article_reuse():
    import download.research_plan as research_mod

    spec = store.scaffold_spec(
        vertical="travel",
        organize_by="地域",
        key="测试省",
        category="景区",
        name="文章商业主线禁用历史旁路",
        scope={"region": "测试省", "entityTypes": ["地点/景区"], "coverageTargets": []},
        content={
            "modalityContract": "separated_research",
            "quotas": {
                "entityHomepagesPerTarget": 0,
                "entityArticlesPerTarget": 2,
                "imageWorksPerTarget": 0,
            },
        },
        created_by="test",
    )
    spec["workflowPolicy"] = {"articleCommercialClosure": True}
    task = spec["taskId"]
    store.save_spec(spec)
    prior_batch = "prior_article_pool_blocked"
    batch = "current_article_pool_blocked"
    entity = "故宫博物院"
    prior_plan = (
        resolve_entity_object_dir(task, prior_batch, entity, etype_hint="景区")
        / "1.download"
        / "article_source_plan.json"
    )
    prior_plan.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        prior_plan,
        {
            "payload": {
                "sources": [
                    {
                        "source_id": "article_prior_base_1",
                        "platform": "去哪儿攻略",
                        "url": "https://touch.travel.qunar.com/article/prior-1",
                        "sourceUseMode": "factual_reference_only",
                        "category": "travelogue",
                        "discoveryProvider": "verified_source_pool_reuse",
                        "matchConfidence": 0.93,
                        "evidenceReason": "历史批次已验证文章底稿",
                        "sourceRole": "base",
                        "entityMatch": "strong",
                        "title": f"{entity} 历史底稿 1",
                        "candidateGate": {
                            "passed": True,
                            "issues": [],
                            "warnings": [],
                            "category": "travelogue",
                            "matchConfidence": 0.93,
                            "role": "base",
                        },
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
        "_known_article_sources": research_mod._known_article_sources,
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
            lambda entity_id, entity_aliases=(), limit=4: []
        )
        research_mod._known_article_sources = lambda entity_id: [
            {
                "source_id": "article_registry_base_1",
                "platform": "垂类专业站",
                "url": "https://example.com/known-article-1",
                "category": "travelogue",
                "title": f"{entity} 已登记底稿",
                "fetchable": True,
            }
        ]
        research_mod._task_content_quotas = lambda task_id: {
            "entityArticlesPerTarget": 2,
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

    assert report["articleCommercialClosure"] is True
    assert any("article base sources" in issue for issue in report["issues"]), report["issues"]
    plan = (
        resolve_entity_object_dir(task, batch, entity, etype_hint="景区")
        / "1.download"
        / "article_source_plan.json"
    )
    sources = read_json(plan)["payload"]["sources"]
    assert all(
        source.get("discoveryProvider") not in {"verified_source_pool_reuse", "travel_source_registry"}
        for source in sources
    ), sources


def test_prior_qunar_source_pool_reuse_rechecks_entity_anchor():
    from download.research.plan_state import _verified_article_sources_from_prior_plans

    task = "旅行/地域/测试省/景区/去哪儿历史池复用"
    prior_batch = "prior_qunar_pool"
    batch = "current_qunar_pool"
    entity = "海螺沟"
    prior_plan = (
        resolve_entity_object_dir(task, prior_batch, entity, etype_hint="景区")
        / "1.download"
        / "article_source_plan.json"
    )
    prior_plan.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        prior_plan,
        {
            "payload": {
                "sources": [
                    {
                        "source_id": "article_qunar_base_good",
                        "platform": "去哪儿攻略",
                        "url": "https://touch.travel.qunar.com/youji/7646378",
                        "sourceUseMode": "factual_reference_only",
                        "category": "travelogue",
                        "discoveryProvider": "qunar_touch_search_json",
                        "matchConfidence": 0.94,
                        "evidenceReason": "历史批次已验证海螺沟文章底稿",
                        "sourceRole": "base",
                        "entityMatch": "strong",
                        "title": "2021年元旦自驾海螺沟",
                        "candidateGate": {
                            "passed": True,
                            "issues": [],
                            "warnings": [],
                            "category": "travelogue",
                            "matchConfidence": 0.94,
                            "role": "base",
                        },
                    },
                    {
                        "source_id": "article_qunar_base_polluted_author",
                        "platform": "去哪儿攻略",
                        "url": "https://touch.travel.qunar.com/youji/7723878",
                        "sourceUseMode": "factual_reference_only",
                        "category": "travelogue",
                        "discoveryProvider": "qunar_author_books_page",
                        "matchConfidence": 0.86,
                        "evidenceReason": "去哪儿攻略同作者作品集补源 海螺沟；title=南方人的快乐！年末去东北玩雪花",
                        "sourceRole": "base",
                        "entityMatch": "strong",
                        "candidateGate": {
                            "passed": True,
                            "issues": [],
                            "warnings": [],
                            "category": "travelogue",
                            "matchConfidence": 0.86,
                            "role": "base",
                        },
                    },
                ]
            }
        },
    )

    reused = _verified_article_sources_from_prior_plans(
        task,
        batch,
        entity,
        entity_type="景区",
        entity_aliases=["海螺沟冰川"],
        limit=8,
    )
    urls = {source["url"] for source in reused}

    assert "https://touch.travel.qunar.com/youji/7646378" in urls
    assert "https://touch.travel.qunar.com/youji/7723878" not in urls
