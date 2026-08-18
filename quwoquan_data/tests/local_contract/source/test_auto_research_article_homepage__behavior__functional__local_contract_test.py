from __future__ import annotations

import pytest


from support.source_plan_guidance_fixtures import *  # noqa: F401,F403
from support.execution_manifest_fixture import ExecutionFixtureBuilder  # noqa: E402
from core.data_issue import DataIssueCode, DataRecoveryAction  # noqa: E402


def _build_execution(execution_id: str, entity_name: str) -> None:
    ExecutionFixtureBuilder(
        execution_id,
        targets=({"entityType": "地点/景区", "name": entity_name},),
    ).build()


@pytest.fixture(autouse=True)
def _isolate_canonical_baike_network(monkeypatch: pytest.MonkeyPatch):
    """Local contracts use explicit source fixtures; live resolution is integration evidence."""
    import content.source.research.auto_plan_writer as research_mod

    monkeypatch.setattr(
        research_mod,
        "resolve_toutiao_baike_page",
        lambda *_args, **_kwargs: None,
    )


def test_homepage_auto_research_discovers_runtime_wikipedia_source():
    import content.source.research.auto_plan_writer as research_mod

    task = "20260712--travel-homepage-source-url--cn-zhejiang--m1-001"
    entity = "普陀山"
    validated_url = "https://zh.wikipedia.org/wiki/%E6%99%AE%E9%99%80%E5%B1%B1"
    image = {
        "url": "https://upload.wikimedia.org/wikipedia/commons/1/11/Putuo_sample.jpg",
        "license": "CC BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:Putuo_sample.jpg",
        "width": 1600,
        "height": 1000,
        "caption": entity,
        "relevance": entity,
        "creator": "Wiki contributor",
        "collectionPageUrl": validated_url,
        "platform": "维基百科",
        "sourceUrl": "https://commons.wikimedia.org/wiki/File:Putuo_sample.jpg",
        "licenseSnapshot": "CC BY-SA 4.0 snapshot",
        "usageScope": "app_publish",
    }
    spec = ExecutionFixtureBuilder(
        task,
        targets=({"entityType": "地点/景区", "name": entity},),
    ).spec_payload()
    store.save_spec(spec)
    originals = {
        name: getattr(research_mod, name)
        for name in (
            "_wiki_title_for_entity",
            "_wiki_related_titles_for_entity",
            "_known_official_website",
            "_official_website",
            "_verified_homepage_sources_from_source_units",
            "_mediawiki_page_images",
            "_discover_open_license_image_pools",
            "_verified_image_collections_from_prior_plans",
            "_wikidata_item_for_zhwiki",
            "_wikidata_item_for_entity_search",
            "_wikidata_entity_aliases",
        )
    }
    try:
        research_mod._wiki_title_for_entity = (
            lambda host, _entity_id, entity_aliases=(): entity
            if host == "zh.wikipedia.org"
            else ""
        )
        research_mod._wiki_related_titles_for_entity = lambda *_args, **_kwargs: []
        research_mod._known_official_website = lambda *_args, **_kwargs: ""
        research_mod._official_website = lambda *_args, **_kwargs: ""
        research_mod._verified_homepage_sources_from_source_units = lambda *_args, **_kwargs: []
        research_mod._mediawiki_page_images = lambda *_args, **_kwargs: [image]
        research_mod._verified_image_collections_from_prior_plans = lambda *_args, **_kwargs: []
        research_mod._wikidata_item_for_zhwiki = lambda _title: ""
        research_mod._wikidata_item_for_entity_search = lambda _entity: ""
        research_mod._wikidata_entity_aliases = lambda _qid: []
        research_mod._discover_open_license_image_pools = lambda *_args, **_kwargs: {
            "commons": [],
            "hint_commons": [],
            "wikidata_commons": [],
            "openverse": [],
            "wiki_page_images": [image],
            "voyage_page_images": [],
        }
        report = write_auto_research_plans(
            task,
            [entity],
            entity_type="景区",
            force=True,
            lanes={"homepage"},
        )
    finally:
        for name, value in originals.items():
            setattr(research_mod, name, value)

    assert report["issues"] == []
    assert report["sourceAvailability"]["readyTargets"] == [entity]
    plan = (
        resolve_entity_object_dir(task, entity, etype_hint="景区")
        / "1.download"
        / "homepage_source_plan.json"
    )
    payload = read_json(plan)["payload"]
    assert payload["primaryEvidenceRef"] == "home_wikipedia"
    source = next(source for source in payload["sources"] if source["source_id"] == "home_wikipedia")
    assert source["url"] == validated_url
    assert source["discoveryProvider"] == "mediawiki_exact_title"
    assert source["sourceRole"] == "primary"



def test_parallel_image_auto_research_writes_availability_report():
    import content.source.research.auto_plan_article as article_mod
    import content.source.research.auto_plan_writer as research_mod

    spec = ExecutionFixtureBuilder(
        "20260711--travel-image-live-discovery--cn-zhejiang--canary-001",
        targets=(
            {"entityType": "地点/景区", "name": "可用景区"},
            {"entityType": "地点/景区", "name": "缺源景区"},
        ),
    ).spec_payload()
    task = spec["executionId"]
    store.save_spec(spec)
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
        "_wiki_title_for_entity": research_mod._wiki_title_for_entity,
        "_wiki_related_titles_for_entity": research_mod._wiki_related_titles_for_entity,
        "_wikidata_item_for_zhwiki": research_mod._wikidata_item_for_zhwiki,
        "_wikidata_item_for_entity_search": research_mod._wikidata_item_for_entity_search,
        "_official_website": research_mod._official_website,
        "_mediawiki_page_images": research_mod._mediawiki_page_images,
        "_discover_open_license_image_pools": research_mod._discover_open_license_image_pools,
        "_verified_image_collections_from_prior_plans": research_mod._verified_image_collections_from_prior_plans,
        "_trusted_external_links": research_mod._trusted_external_links,
    }
    article_originals = {
        "_qunar_travelogue_sources": article_mod._qunar_travelogue_sources,
        "_qunar_review_support_source": article_mod._qunar_review_support_source,
        "_known_article_sources": article_mod._known_article_sources,
        "_mediawiki_page_images": article_mod._mediawiki_page_images,
    }

    def fake_wiki_title(host: str, entity_id: str, *, entity_aliases=()) -> str:
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
        research_mod._wiki_title_for_entity = fake_wiki_title
        research_mod._wiki_related_titles_for_entity = lambda *_args, **_kwargs: []
        research_mod._wikidata_item_for_zhwiki = lambda title: ""
        research_mod._wikidata_item_for_entity_search = lambda entity_id: ""
        research_mod._official_website = lambda qid: ""
        research_mod._discover_open_license_image_pools = (
            lambda entity_id, **_kwargs: {
                "commons": [good_image, second_good_image]
                if entity_id == "可用景区"
                else [],
                "hint_commons": [],
                "wikidata_commons": [],
                "openverse": [],
                "wiki_page_images": [good_image]
                if entity_id == "可用景区"
                else [],
                "voyage_page_images": [],
            }
        )
        article_mod._mediawiki_page_images = (
            lambda host, title, entity_id, limit=6: [good_image] if entity_id == "可用景区" and title else []
        )
        research_mod._trusted_external_links = lambda title, limit=4: []
        article_mod._qunar_travelogue_sources = fake_qunar
        article_mod._qunar_review_support_source = lambda entity_id: _source(
            source_id="article_no_fallback",
            platform="测试",
            url="",
            category="travelogue",
            source_role="base",
        )
        article_mod._known_article_sources = lambda entity_id: []
        progress_events: list[dict] = []
        report = write_auto_research_plans(
            task,
            ["可用景区", "缺源景区"],
            entity_type="景区",
            force=True,
            max_workers=2,
            progress_callback=progress_events.append,
        )
    finally:
        for name, value in originals.items():
            setattr(research_mod, name, value)
        for name, value in article_originals.items():
            setattr(article_mod, name, value)
    availability = report["sourceAvailability"]
    assert availability["readyTargets"] == ["可用景区"], availability
    assert [item["entityId"] for item in availability["ineligibleTargets"]] == ["缺源景区"], availability
    assert report["throughput"]["maxWorkers"] == 2
    assert progress_events[0]["status"] == "running"
    assert progress_events[-1]["status"] == "succeeded"
    assert progress_events[-1]["completedCount"] == 2
    progress = read_json(execution_root(task) / "_shared" / "auto_research_progress.json")
    assert progress["status"] == "succeeded"
    assert progress["entityCount"] == 2
    assert progress["workers"] == 2
    persisted = read_json(execution_root(task) / "_shared" / "source_unavailable_targets.json")
    assert persisted["ineligibleTargets"][0]["entityId"] == "缺源景区"
    missing_image_plan = (
        resolve_entity_object_dir(task, "缺源景区", etype_hint="景区")
        / "1.download"
        / "image_source_plan.json"
    )
    missing_payload = read_json(missing_image_plan)["payload"]
    assert missing_payload["sourceUnavailable"][0]["lane"] == "image"
    diagnostics = missing_payload["imageDiscoveryDiagnostics"]
    assert diagnostics["desiredImageWorks"] >= 1
    # 图作品批次为 hard_quota：图即产出本体，缺源实体必须按需求量（≥1）判不就绪。
    assert diagnostics["requiredImageWorks"] == 1
    assert diagnostics["poolCounts"]["acceptedCollections"] == 0
    assert diagnostics["sourceUnavailable"][0]["code"] == DataIssueCode.MEDIA_RIGHTS_UNAVAILABLE.value
    assert diagnostics["sourceUnavailable"][0]["recovery"] == DataRecoveryAction.STOP.value


def test_parallel_auto_research_persists_incremental_report_on_interrupt(monkeypatch):
    import pytest
    import time
    import content.source.research.auto_plan_public as public_mod

    task = "20260711--travel-homepage-interrupt--cn-zhejiang--canary-002"
    shared = execution_root(task) / "_shared"
    shared.mkdir(parents=True, exist_ok=True)
    write_json(
        shared / "auto_research_plan.json",
        {
            "schema": "quwoquan.content.source.auto_research_plan",
            "executionId": task,
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

    def fake_impl(_execution_id, entity_ids, **_kwargs):
        entity_id = entity_ids[0]
        if entity_id == "慢景区":
            time.sleep(0.05)
            raise KeyboardInterrupt()
        return {
            "schema": "quwoquan.content.source.auto_research_plan",
            "executionId": task,
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
    import content.source.research.auto_plan_article as article_mod
    import content.source.research.auto_plan_writer as research_mod

    task = "20260711--travel-article-museum-source--cn-zhejiang--canary-003"
    entity = "三星堆博物馆"
    _build_execution(task, entity)
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
        "_wiki_title_for_entity": research_mod._wiki_title_for_entity,
        "_wiki_related_titles_for_entity": research_mod._wiki_related_titles_for_entity,
        "_wikidata_item_for_zhwiki": research_mod._wikidata_item_for_zhwiki,
        "_wikidata_item_for_entity_search": research_mod._wikidata_item_for_entity_search,
        "_wikidata_entity_aliases": research_mod._wikidata_entity_aliases,
        "_official_website": research_mod._official_website,
        "_known_official_website": research_mod._known_official_website,
        "_verified_image_collections_from_prior_plans": research_mod._verified_image_collections_from_prior_plans,
        "_discover_open_license_image_pools": research_mod._discover_open_license_image_pools,
        "_mediawiki_page_images": research_mod._mediawiki_page_images,
        "_trusted_external_links": research_mod._trusted_external_links,
        "_qunar_travelogue_sources": research_mod._qunar_travelogue_sources,
        "_known_article_sources": research_mod._known_article_sources,
    }
    article_originals = {
        "_qunar_travelogue_sources": article_mod._qunar_travelogue_sources,
        "_known_article_sources": article_mod._known_article_sources,
        "_mediawiki_page_images": article_mod._mediawiki_page_images,
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
        research_mod._wiki_title_for_entity = lambda host, entity_id, entity_aliases=(): ""
        research_mod._wiki_related_titles_for_entity = (
            lambda host, entity_id, entity_aliases=():
            ["三星堆遗址"] if entity_id == entity else []
        )
        research_mod._wikidata_item_for_zhwiki = lambda title: ""
        research_mod._wikidata_item_for_entity_search = lambda entity_id: ""
        research_mod._wikidata_entity_aliases = lambda qid: []
        research_mod._official_website = lambda qid: ""
        research_mod._known_official_website = lambda entity_id: ""
        research_mod._verified_image_collections_from_prior_plans = lambda *_args, **_kwargs: []
        research_mod._discover_open_license_image_pools = lambda *_args, **_kwargs: {
            "commons": [good_image],
            "hint_commons": [],
            "wikidata_commons": [],
            "openverse": [],
            "wiki_page_images": [],
            "voyage_page_images": [],
        }
        research_mod._mediawiki_page_images = lambda host, title, entity_id, limit=6: []
        research_mod._trusted_external_links = lambda title, limit=4: []
        research_mod._qunar_travelogue_sources = fake_qunar
        research_mod._known_article_sources = lambda entity_id: []
        article_mod._qunar_travelogue_sources = fake_qunar
        article_mod._known_article_sources = lambda entity_id: []
        article_mod._mediawiki_page_images = lambda *_args, **_kwargs: []
        report = write_auto_research_plans(
            task,
            [entity],
            entity_type="景区",
            force=True,
            lanes={"article"},
        )
    finally:
        for name, value in originals.items():
            setattr(research_mod, name, value)
        for name, value in article_originals.items():
            setattr(article_mod, name, value)

    assert report["issues"] == []
    assert report["sourceAvailability"]["readyTargets"] == [entity]
    plan = (
        resolve_entity_object_dir(task, entity, etype_hint="景区")
        / "1.download"
        / "article_source_plan.json"
    )
    sources = read_json(plan)["payload"]["sources"]
    assert any(source["source_id"].startswith("article_qunar_base_") for source in sources)

def test_homepage_only_auto_research_runs_media_but_skips_article_discovery():
    import content.source.research.auto_plan_writer as research_mod

    task = "20260711--travel-homepage-lightweight--cn-zhejiang--canary-004"
    entity = "故宫博物院"
    _build_execution(task, entity)
    wiki_image = {
        "url": "https://upload.wikimedia.org/wikipedia/commons/1/11/Forbidden_City_sample.jpg",
        "license": "CC BY-SA 4.0",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:Forbidden_City_sample.jpg",
        "width": 1600,
        "height": 1000,
        "caption": entity,
        "relevance": entity,
        "creator": "Wiki contributor",
        "collectionPageUrl": "https://zh.wikipedia.org/wiki/%E6%95%85%E5%AE%AB%E5%8D%9A%E7%89%A9%E9%99%A2",
        "platform": "维基百科",
        "sourceUrl": "https://commons.wikimedia.org/wiki/File:Forbidden_City_sample.jpg",
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
        "_mediawiki_page_images": research_mod._mediawiki_page_images,
        "_verified_image_collections_from_prior_plans": research_mod._verified_image_collections_from_prior_plans,
        "_discover_open_license_image_pools": research_mod._discover_open_license_image_pools,
        "_trusted_external_links": research_mod._trusted_external_links,
        "_qunar_travelogue_sources": research_mod._qunar_travelogue_sources,
    }

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("homepage-only repair must not run article discovery")

    def image_pools(*_args, **_kwargs):
        return {
            "commons": [],
            "hint_commons": [],
            "wikidata_commons": [],
            "openverse": [],
            "wiki_page_images": [wiki_image],
            "voyage_page_images": [],
        }

    try:
        research_mod._wiki_title_for_entity = (
            lambda host, entity_id, entity_aliases=(): entity if host == "zh.wikipedia.org" else ""
        )
        research_mod._wiki_related_titles_for_entity = lambda host, entity_id, entity_aliases=(): []
        research_mod._wikidata_item_for_zhwiki = lambda title: ""
        research_mod._wikidata_item_for_entity_search = lambda entity_id: ""
        research_mod._wikidata_entity_aliases = lambda qid: []
        research_mod._official_website = lambda qid: ""
        research_mod._mediawiki_page_images = (
            lambda host, title, entity_id, limit=8: [wiki_image]
            if host == "zh.wikipedia.org" and title == entity and entity_id == entity
            else []
        )
        research_mod._verified_image_collections_from_prior_plans = lambda *_args, **_kwargs: []
        research_mod._discover_open_license_image_pools = image_pools
        research_mod._trusted_external_links = fail_if_called
        research_mod._qunar_travelogue_sources = fail_if_called
        report = write_auto_research_plans(
            task,
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
        resolve_entity_object_dir(task, entity, etype_hint="景区")
        / "1.download"
        / "homepage_source_plan.json"
    )
    sources = read_json(plan)["payload"]["sources"]
    source_by_id = {source["source_id"]: source for source in sources}
    assert "home_wikipedia" in source_by_id
    assert "home_official" not in source_by_id
    assert all(
        source.get("sourceKind")
        in {"wikipedia", "baidu_baike", "toutiao_baike"}
        for source in sources
    )

def test_homepage_related_wiki_hydrates_same_source_images():
    import content.source.research.auto_plan_writer as research_mod

    task = "20260711--travel-homepage-wiki-images--cn-zhejiang--canary-005"
    entity = "武侯祠"
    _build_execution(task, entity)
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
        "_verified_image_collections_from_prior_plans": research_mod._verified_image_collections_from_prior_plans,
        "_discover_open_license_image_pools": research_mod._discover_open_license_image_pools,
        "_trusted_external_links": research_mod._trusted_external_links,
        "_qunar_travelogue_sources": research_mod._qunar_travelogue_sources,
        "_mediawiki_page_images": research_mod._mediawiki_page_images,
    }

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("homepage-only repair must not run article discovery")

    def empty_image_pools(*_args, **_kwargs):
        return {
            "commons": [],
            "hint_commons": [],
            "wikidata_commons": [],
            "openverse": [],
            "wiki_page_images": [],
            "voyage_page_images": [],
        }

    try:
        research_mod._wiki_title_for_entity = lambda host, entity_id, entity_aliases=(): ""
        research_mod._wiki_related_titles_for_entity = (
            lambda host, entity_id, entity_aliases=():
            [support_title] if entity_id == entity else []
        )
        research_mod._wikidata_item_for_zhwiki = lambda title: ""
        research_mod._wikidata_item_for_entity_search = lambda entity_id: ""
        research_mod._wikidata_entity_aliases = lambda qid: []
        research_mod._official_website = lambda qid: ""
        research_mod._known_official_website = lambda entity_id: ""
        research_mod._verified_image_collections_from_prior_plans = lambda *_args, **_kwargs: []
        research_mod._discover_open_license_image_pools = empty_image_pools
        research_mod._trusted_external_links = fail_if_called
        research_mod._qunar_travelogue_sources = fail_if_called
        research_mod._mediawiki_page_images = (
            lambda host, title, entity_id, limit=8: [support_image]
            if host == "zh.wikipedia.org" and title == support_title and entity_id == entity
            else []
        )
        report = write_auto_research_plans(
            task,
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
        resolve_entity_object_dir(task, entity, etype_hint="景区")
        / "1.download"
        / "homepage_source_plan.json"
    )
    sources = read_json(plan)["payload"]["sources"]
    support_source = next(
        source
        for source in sources
        if source.get("source_id") == "home_related_encyclopedia_support_1"
    )
    assert support_source["discoveryProvider"] == "mediawiki_related_title"
    assert support_source["imageEvidenceMode"] == "same_source"
    assert [item["url"] for item in support_source["imageUrls"]] == [support_image["url"]]


def test_homepage_registry_sources_without_same_source_images_use_independent_media():
    import content.source.research.auto_plan_homepage as homepage_mod
    import content.source.research.auto_plan_writer as research_mod

    task = "20260711--travel-homepage-wiki-no-image--cn-zhejiang--canary-006"
    entity = "瓦屋山"
    _build_execution(task, entity)
    homepage_url = "https://zh.wikipedia.org/wiki/%E7%93%A6%E5%B1%8B%E5%B1%B1"
    originals = {
        "_wiki_title_for_entity": research_mod._wiki_title_for_entity,
        "_wiki_related_titles_for_entity": research_mod._wiki_related_titles_for_entity,
        "_wikidata_item_for_zhwiki": research_mod._wikidata_item_for_zhwiki,
        "_wikidata_item_for_entity_search": research_mod._wikidata_item_for_entity_search,
        "_wikidata_entity_aliases": research_mod._wikidata_entity_aliases,
        "_official_website": research_mod._official_website,
        "_known_official_website": research_mod._known_official_website,
        "_verified_image_collections_from_prior_plans": research_mod._verified_image_collections_from_prior_plans,
        "_discover_open_license_image_pools": research_mod._discover_open_license_image_pools,
        "_trusted_external_links": research_mod._trusted_external_links,
        "_qunar_travelogue_sources": research_mod._qunar_travelogue_sources,
        "_mediawiki_page_images": research_mod._mediawiki_page_images,
        "resolve_baidu_baike_page": research_mod.resolve_baidu_baike_page,
        "resolve_toutiao_baike_page": research_mod.resolve_toutiao_baike_page,
    }
    original_hydrate = homepage_mod._hydrate_mediawiki_same_source_images

    media_image = {
        "url": "https://upload.wikimedia.org/wikipedia/commons/aa/Wawushan.jpg",
        "platform": "Wikimedia Commons",
        "license": "CC BY-SA 4.0",
        "credit": "Commons contributor",
        "sourceUrl": "https://commons.wikimedia.org/wiki/File:Wawushan.jpg",
        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "licenseSnapshot": "CC BY-SA 4.0 snapshot",
        "authorizationProof": "https://commons.wikimedia.org/wiki/File:Wawushan.jpg",
        "usageScope": "app_publish",
        "width": 1600,
        "height": 1000,
        "caption": f"{entity}山景",
        "relevance": f"{entity}山景",
        "creator": "Commons contributor",
        "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:Wawushan.jpg",
    }

    def image_pools(*_args, **_kwargs):
        return {
            "commons": [media_image],
            "hint_commons": [],
            "wikidata_commons": [],
            "openverse": [],
            "wiki_page_images": [],
            "voyage_page_images": [],
        }

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
        research_mod._verified_image_collections_from_prior_plans = lambda *_args, **_kwargs: []
        research_mod._discover_open_license_image_pools = image_pools
        research_mod._trusted_external_links = lambda *_args, **_kwargs: []
        research_mod._qunar_travelogue_sources = lambda *_args, **_kwargs: []
        research_mod._mediawiki_page_images = lambda host, title, entity_id, limit=8: []
        research_mod.resolve_baidu_baike_page = lambda *_args, **_kwargs: None
        research_mod.resolve_toutiao_baike_page = lambda *_args, **_kwargs: None
        homepage_mod._hydrate_mediawiki_same_source_images = (
            lambda source, *, entity_id: source
        )
        report = write_auto_research_plans(
            task,
            [entity],
            entity_type="景区",
            force=True,
            lanes={"homepage"},
        )
    finally:
        for name, value in originals.items():
            setattr(research_mod, name, value)
        homepage_mod._hydrate_mediawiki_same_source_images = original_hydrate

    assert report["issues"] == []
    assert report["sourceAvailability"]["readyTargets"] == [entity]
    assert report["sourceAvailability"]["ineligibleTargets"] == []
    assert report["sourceUnavailable"] == []
    plan = (
        resolve_entity_object_dir(task, entity, etype_hint="景区")
        / "1.download"
        / "homepage_source_plan.json"
    )
    payload = read_json(plan)["payload"]
    sources = payload["sources"]
    assert {source["source_id"] for source in sources} == {"home_wikipedia"}
    assert all(str(source.get("imageEvidenceMode") or "") == "" for source in sources)
    collections = payload["homepageMediaCollections"]
    assert len(collections) == 1
    assert collections[0]["mediaEvidenceMode"] == "independent_rights_cleared"
    assert collections[0]["images"][0]["url"] == media_image["url"]
