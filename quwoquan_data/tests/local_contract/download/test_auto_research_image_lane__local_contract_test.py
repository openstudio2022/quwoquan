from __future__ import annotations



from support.source_plan_guidance_fixtures import *  # noqa: F401,F403



def _purge_cross_task_image_plans(entity_id: str) -> None:
    """清理共享 runtime 下该实体的历史 image_source_plan.json（跨批次）。

    本套件 fixture 在导入期设了进程级共享 QWQ_RUNTIME_ROOT（tempfile.mkdtemp），同
    session 内多个测试文件共用同一 batches_root；跨任务复用门
    `_verified_image_collections_from_prior_plans` 会按 entity_id glob 所有批次的
    image_source_plan.json。为让"按本测试 seed 的已知 store 精确断言数量/救援重试"保持
    hermetic（不被兄弟测试为同名实体写入的计划污染），在 seed/运行前清掉该实体旧计划。
    生产里跨任务复用同实体 collections 是预期行为，这里仅做测试输入归零，不改任何业务逻辑。
    """
    from _common.paths import batches_root

    for plan in batches_root().glob(
        f"*/entities/地点/景区/{entity_id}/1.download/image_source_plan.json"
    ):
        try:
            plan.unlink()
        except OSError:
            pass


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
        research_mod._qunar_travelogue_sources = lambda entity_id, entity_aliases=(), limit=4: []
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
        research_mod._qunar_travelogue_sources = lambda entity_id, entity_aliases=(), limit=4: []
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
    _purge_cross_task_image_plans(entity)
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
            lambda entity_id, entity_aliases=(), limit=4: []
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
    _purge_cross_task_image_plans(entity)
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
            lambda entity_id, entity_aliases=(), limit=4: []
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
            lambda entity_id, entity_aliases=(), limit=4: []
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
                "research": {"imageCountPolicy": "hard_quota"},
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
        research_mod._qunar_travelogue_sources = lambda entity_id, entity_aliases=(), limit=4: []
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

    availability = report["sourceAvailability"]
    assert availability["readyTargets"] == [entity]
    assert availability["ineligibleTargets"] == []
    assert availability["imageSoftWarnings"][0]["entityId"] == entity
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
        research_mod._qunar_travelogue_sources = lambda entity_id, entity_aliases=(), limit=4: []
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
