from __future__ import annotations



from support.source_plan_guidance_fixtures import *  # noqa: F401,F403
from support.execution_manifest_fixture import ExecutionFixtureBuilder  # noqa: E402




def test_auto_research_image_lane_prefers_non_homepage_alias_matched_image():
    import content.source.research.auto_plan_writer as research_mod

    task = "20260711--travel-image-source-isolation--cn-zhejiang--canary-001"
    entity = "三苏祠"
    ExecutionFixtureBuilder(
        task,
        targets=({"entityType": "地点/景区", "name": entity},),
    ).build()
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
    }
    try:
        research_mod._wiki_title_for_entity = (
            lambda host, entity_id, entity_aliases=(): entity
            if host == "zh.wikipedia.org"
            else ""
        )
        research_mod._wiki_related_titles_for_entity = lambda *_args, **_kwargs: []
        research_mod._wikidata_item_for_zhwiki = lambda title: "Q10866733"
        research_mod._wikidata_item_for_entity_search = lambda entity_id: "Q10866733"
        research_mod._wikidata_entity_aliases = lambda qid: ["Sansu Shrine"]
        research_mod._official_website = lambda qid: ""
        research_mod._known_official_website = lambda entity_id: ""
        research_mod._verified_image_collections_from_prior_plans = lambda *_args, **_kwargs: []
        research_mod._discover_open_license_image_pools = lambda *_args, **_kwargs: {
            "commons": [home_image, image_work],
            "hint_commons": [],
            "wikidata_commons": [],
            "openverse": [],
            "wiki_page_images": [home_image],
            "voyage_page_images": [],
        }
        research_mod._trusted_external_links = lambda title, limit=4: []
        research_mod._qunar_travelogue_sources = lambda entity_id, entity_aliases=(), limit=4: []
        report = write_auto_research_plans(
            task,
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
        resolve_entity_object_dir(task, entity, etype_hint="景区")
        / "1.download"
        / "image_source_plan.json"
    )
    collections = read_json(plan)["payload"]["collections"]
    assert collections[0]["images"][0]["url"] == "https://img.example/south-gate.jpg"


def test_auto_research_rescues_image_lane_when_first_open_license_discovery_is_empty():
    import content.source.research.auto_plan_writer as research_mod

    spec = ExecutionFixtureBuilder(
        "20260711--travel-image-source-rescue--cn-zhejiang--canary-002",
        targets=({"entityType": "地点/景区", "name": "故宫博物院"},),
    ).spec_payload()
    spec["content"]["quotas"]["imageWorksPerTarget"] = 2
    spec["acceptance"]["minPostsPerEntity"] = 2
    spec["executionPolicy"]["targetObjectCount"] = 2
    task = spec["executionId"]
    store.save_spec(spec)
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
    }
    discovery_calls = {"count": 0}

    def fake_image_pools(entity_id, **kwargs):
        assert entity_id == entity
        discovery_calls["count"] += 1
        images = [] if discovery_calls["count"] == 1 else rescue_images
        if images:
            assert kwargs["commons_limit"] >= 20
        return {
            "commons": images,
            "hint_commons": [],
            "wikidata_commons": [],
            "openverse": [],
            "wiki_page_images": [],
            "voyage_page_images": [],
        }

    try:
        research_mod._wiki_title_for_entity = (
            lambda host, entity_id, entity_aliases=(): entity
            if host == "zh.wikipedia.org"
            else ""
        )
        research_mod._wiki_related_titles_for_entity = lambda *_args, **_kwargs: []
        research_mod._wikidata_item_for_zhwiki = lambda title: "Q2047427"
        research_mod._wikidata_item_for_entity_search = lambda entity_id: "Q2047427"
        research_mod._wikidata_entity_aliases = lambda qid: ["Palace Museum"]
        research_mod._official_website = lambda qid: ""
        research_mod._known_official_website = lambda entity_id: ""
        research_mod._verified_image_collections_from_prior_plans = lambda *_args, **_kwargs: []
        research_mod._discover_open_license_image_pools = fake_image_pools
        research_mod._trusted_external_links = lambda title, limit=4: []
        research_mod._qunar_travelogue_sources = (
            lambda entity_id, entity_aliases=(), limit=4: []
        )
        report = write_auto_research_plans(
            task,
            [entity],
            entity_type="景区",
            force=True,
            lanes={"image"},
        )
    finally:
        for name, value in originals.items():
            setattr(research_mod, name, value)

    assert discovery_calls["count"] == 2
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
        resolve_entity_object_dir(task, entity, etype_hint="景区")
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
    import content.source.research.auto_plan_writer as research_mod

    spec = ExecutionFixtureBuilder(
        "20260711--travel-image-alias-discovery--cn-zhejiang--canary-003",
        targets=({"entityType": "地点/景区", "name": "黄山风景区"},),
    ).spec_payload()
    spec["content"]["quotas"]["imageWorksPerTarget"] = 2
    spec["acceptance"]["minPostsPerEntity"] = 2
    spec["executionPolicy"]["targetObjectCount"] = 2
    task = spec["executionId"]
    store.save_spec(spec)
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
    }
    seen_aliases = {"value": []}

    def fake_image_pools(entity_id, *, entity_aliases=(), **_kwargs):
        assert entity_id == entity
        seen_aliases["value"] = list(entity_aliases)
        images = image_rows if "Mount Huangshan" in entity_aliases else []
        return {
            "commons": images,
            "hint_commons": [],
            "wikidata_commons": [],
            "openverse": [],
            "wiki_page_images": [],
            "voyage_page_images": [],
        }

    try:
        research_mod._wiki_title_for_entity = (
            lambda host, entity_id, entity_aliases=(): entity
            if host == "zh.wikipedia.org"
            else ""
        )
        research_mod._wiki_related_titles_for_entity = lambda *_args, **_kwargs: []
        research_mod._wikidata_item_for_zhwiki = lambda title: ""
        research_mod._wikidata_item_for_entity_search = lambda entity_id: ""
        research_mod._wikidata_entity_aliases = lambda qid: []
        research_mod._official_website = lambda qid: ""
        research_mod._known_official_website = lambda entity_id: ""
        research_mod._verified_image_collections_from_prior_plans = lambda *_args, **_kwargs: []
        research_mod._discover_open_license_image_pools = fake_image_pools
        research_mod._trusted_external_links = lambda title, limit=4: []
        research_mod._qunar_travelogue_sources = (
            lambda entity_id, entity_aliases=(), limit=4: []
        )
        report = write_auto_research_plans(
            task,
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
        resolve_entity_object_dir(task, entity, etype_hint="景区")
        / "1.download"
        / "image_source_plan.json"
    )
    collections = read_json(plan)["payload"]["collections"]
    assert len(collections) >= 2
    assert {collection["platform"] for collection in collections} == {"Wikimedia Commons"}
