from __future__ import annotations



from support.task_workflow_fixtures import *  # noqa: F401,F403



def test_auto_content_plan_article_sources_reserve_unique_asset_refs():
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec.setdefault("content", {}).setdefault("quotas", {})["entityArticlesPerTarget"] = 4
    spec["content"]["quotas"]["imageWorksPerTarget"] = 0
    spec.setdefault("acceptance", {})["requiredAngles"] = [
        "planning_consultation",
        "decision_experience",
        "route_transport",
        "seasonal_timing",
    ]
    store.save_spec(spec)
    batch_id = "content_plan_article_dedupe_by_source_ref"
    ctx = _ctx(task_id, batch_id)
    object_dir = resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
    sources_dir = object_dir / STAGE_DOWNLOAD / "sources"
    repeated_body = "\n".join(
        [
            f"{_EID}是测试省核心景区，行前需要核对开放时间、门票预约、交通接驳和天气情况。",
            f"{_EID}的主要游览点之间有步行距离，建议安排半日到一日，携带饮水并预留返程时间。",
            f"{_EID}在不同季节体验差异明显，春夏看植被，秋季看层林，雨天需要注意路面湿滑。",
            f"{_EID}适合把入口动线、核心观景点、返程交通和周边餐饮拆开记录，避免只写百科式介绍。",
            f"{_EID}的体验判断需要结合现场排队、道路坡度、休息点密度、遮阴条件和亲子老人同行成本。",
            f"{_EID}如果遇到节假日，应提前确认分时预约、停车饱和、公共交通末班和临时限流通知。",
            f"{_EID}的文章底稿要能支持规划咨询、决策体验、路线交通和季节时机四种不同写作角度。",
            f"{_EID}的事实引用应保留来源边界，不能把同一段文字轻改成多篇，也不能混用图片发布权利。",
            f"{_EID}的游览建议需要说明适合人群、体力消耗、避峰时间和恶劣天气下的替代安排。",
            f"{_EID}的内容生产应优先形成可追溯的底稿，再由 agent 基于写作契约生成非模板化正文。",
        ]
        * 8
    )
    for index in range(1, 5):
        source_dir = sources_dir / f"{index:02d}.article_fixture_{index}"
        (source_dir / "assets").mkdir(parents=True, exist_ok=True)
        write_json(
            source_dir / "meta.json",
            {
                "sourceId": f"article_fixture_{index}",
                "researchLane": "article",
                "sourceRole": "base",
                "sourceUseMode": "factual_reference_only",
                "category": "travelogue",
                "title": f"测试底稿 {index}",
                "sourceQualityScore": 0.9,
            },
        )
        (source_dir / "source.md").write_text(repeated_body, encoding="utf-8")
        (source_dir / "assets" / "shared.jpg").write_bytes(_real_jpeg(300 + index))
        write_json(
            source_dir / "assets" / "index.json",
            {
                "assets": [
                    {
                        "fileName": "shared.jpg",
                        "sha256": f"sha256:article-image-sha-{index}",
                        "sourceCollectionId": f"article-collection-{index}",
                        "caption": f"{_EID} 共享测试图",
                        "license": "reference_only",
                        "credit": "测试来源",
                        "sourceUrl": f"https://example.test/{index}",
                        "termsUrl": "https://example.test/terms",
                        "usageScope": "factual_reference_only",
                    }
                ]
            },
        )

    issues = run_mod._auto_content_plan(ctx, spec)

    assert issues == [], issues
    packet = read_json(batch_root(task_id, batch_id) / "_shared" / "content_plan_packet.json")
    article_items = [item for item in packet["items"] if item["carrier"] == "article"]
    assert [item["writingIntent"] for item in article_items] == spec["acceptance"]["requiredAngles"]
    assert len({item["baseSourceRef"] for item in article_items}) == 4
    assert len({item["assetRefs"][0] for item in article_items}) == 4

def test_auto_content_plan_preserves_site_supply_source_site_provenance():
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec.setdefault("content", {}).setdefault("quotas", {})["entityArticlesPerTarget"] = 1
    spec["content"]["quotas"]["imageWorksPerTarget"] = 0
    spec.setdefault("acceptance", {})["requiredAngles"] = ["planning_consultation"]
    store.save_spec(spec)
    batch_id = "content_plan_preserves_site_source"
    ctx = _ctx(task_id, batch_id)
    object_dir = resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
    source_dir = object_dir / STAGE_DOWNLOAD / "sources" / "01.article_site_base"
    (source_dir / "assets").mkdir(parents=True, exist_ok=True)
    repeated_body = "\n".join(
        [
            f"{_EID}是测试省核心景区，行前需要核对开放时间、门票预约、交通接驳和天气情况。",
            f"{_EID}的主要游览点之间有步行距离，建议安排半日到一日，携带饮水并预留返程时间。",
            f"{_EID}在不同季节体验差异明显，春夏看植被，秋季看层林，雨天需要注意路面湿滑。",
            f"{_EID}适合把入口动线、核心观景点、返程交通和周边餐饮拆开记录，避免只写百科式介绍。",
            f"{_EID}的体验判断需要结合现场排队、道路坡度、休息点密度、遮阴条件和亲子老人同行成本。",
            f"{_EID}如果遇到节假日，应提前确认分时预约、停车饱和、公共交通末班和临时限流通知。",
            f"{_EID}的文章底稿要能支持规划咨询、决策体验、路线交通和季节时机四种不同写作角度。",
            f"{_EID}的事实引用应保留来源边界，不能把同一段文字轻改成多篇，也不能混用图片发布权利。",
            f"{_EID}的游览建议需要说明适合人群、体力消耗、避峰时间和恶劣天气下的替代安排。",
            f"{_EID}的内容生产应优先形成可追溯的底稿，再由 agent 基于写作契约生成非模板化正文。",
        ]
        * 8
    )
    (source_dir / "source.md").write_text(repeated_body, encoding="utf-8")
    write_json(
        source_dir / "meta.json",
        {
            "sourceId": "article_site_base",
            "researchLane": "article",
            "sourceRole": "base",
            "sourceUseMode": "factual_reference_only",
            "category": "wikivoyage",
            "title": "网站线文章底稿",
            "sourceQualityScore": 0.9,
        },
    )
    write_json(
        source_dir / "assets" / "index.json",
        {
            "assets": [
                {
                    "fileName": "site.jpg",
                    "sha256": "sha256:site-source-image",
                    "sourceCollectionId": "site-source-collection",
                    "caption": f"{_EID} 来源图",
                    "license": "reference_only",
                    "credit": "测试来源",
                    "sourceUrl": "https://example.test/site-source",
                    "termsUrl": "https://example.test/terms",
                    "usageScope": "factual_reference_only",
                }
            ]
        },
    )
    (source_dir / "assets" / "site.jpg").write_bytes(_real_jpeg(310))
    shared = batch_root(task_id, batch_id) / "_shared"
    shared.mkdir(parents=True, exist_ok=True)
    write_json(
        shared / "content_plan_packet.json",
        {
            "schemaVersion": "quwoquan_data.content_plan_packet",
            "taskId": task_id,
            "batchId": batch_id,
            "generatedBy": "site_supply_content_plan_bridge",
            "sourceSite": {"vertical": "travel", "siteId": "wikivoyage_zh", "batchId": "site_batch_1"},
            "items": [],
        },
    )

    issues = run_mod._auto_content_plan(ctx, spec)

    assert issues == [], issues
    packet = read_json(shared / "content_plan_packet.json")
    assert packet["generatedBy"] == "deterministic_source_ready_planner"
    assert packet["sourceSite"] == {
        "vertical": "travel",
        "siteId": "wikivoyage_zh",
        "batchId": "site_batch_1",
    }
    assert packet["items"]

def test_site_supply_dynamic_content_plan_uses_packet_targets_and_skips_legacy_plan():
    from _common.content_object import iter_content_refs, write_brief_object
    from _common.paths import relative_batch_ref, source_unit_dir
    from _common.source_unit import write_source_unit

    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec.setdefault("content", {})["quotas"] = {
        "entityArticlesPerTarget": 0,
        "imageWorksPerTarget": 0,
        "entityHomepagesPerTarget": 0,
        "routeArticles": 0,
    }
    spec.setdefault("workflowPolicy", {})["siteSupplyDynamicContentPlan"] = True
    store.save_spec(spec)
    batch_id = "site_supply_dynamic_content_plan"
    ctx = _ctx(task_id, batch_id)
    shared = batch_root(task_id, batch_id) / "_shared"
    shared.mkdir(parents=True, exist_ok=True)

    items = []
    for idx, name in enumerate(("中国", "北京"), start=1):
        ref = f"candidate_dynamic_{idx}"
        entity_ref = f"/entity/地点/景区/{name}"
        object_dir = resolve_entity_object_dir(task_id, batch_id, entity_ref)
        source_id = f"wikivoyage_dynamic_{idx}"
        source_dir = source_unit_dir(object_dir, idx, source_id)
        body = (
            f"{name}是维基导游站点线动态候选，用于验证 content_plan packet 自带实体集合。"
            f"{name}的行前信息包含交通、季节、开放条件和游览动线，正文必须独立表达。"
        ) * 8
        write_source_unit(
            object_dir,
            ordinal=idx,
            source_id=source_id,
            source_md=body,
            clean_md=body,
            html_bytes=None,
            quality={
                "sourceId": f"wikivoyage_dynamic_{idx}",
                "quality": "A-story",
                "score": 9,
                "reasons": ["site_supply_dynamic_content_plan"],
                "excerpt": body[:120],
                "url": f"https://zh.wikivoyage.org/wiki/{name}",
            },
            platform="wikivoyage_zh",
            source_category="wikivoyage",
            source_use_mode="factual_reference_only",
            source_role="base",
            image_evidence_mode="none",
            research_lane="article",
            license_value="CC BY-SA 4.0",
            url=f"https://zh.wikivoyage.org/wiki/{name}",
            title=f"{name} - 维基导游",
            target_ref=entity_ref,
            relevance=f"{name} 网站供给线动态候选",
            images=[],
            task_id=task_id,
            batch_id=batch_id,
            build_variants=False,
        )
        source_ref = relative_batch_ref(source_dir / "source.md", task_id, batch_id)
        write_brief_object(
            task_id,
            batch_id,
            ref,
            {
                "schemaVersion": "quwoquan.compose.brief",
                "templateId": "景区_攻略",
                "titleHint": f"{name}·行前指南",
                "entityRefs": [entity_ref],
                "baseSourceRef": source_ref,
                "sourceUseMode": "factual_reference_only",
                "writingIntent": "planning_consultation",
                "mustIncludeFacts": [name],
            },
            content_type="article",
        )
        items.append(
            {
                "ref": ref,
                "kind": "entity",
                "carrier": "article",
                "researchLane": "article",
                "title": f"{name}·行前指南",
                "entityRefs": [entity_ref],
                "evidenceRefs": [source_ref],
                "rationale": "site supply dynamic packet target",
                "baseSourceRef": source_ref,
                "sourceUseMode": "factual_reference_only",
                "writingIntent": "planning_consultation",
            }
        )

    write_json(
        shared / "content_plan_packet.json",
        {
            "schemaVersion": "quwoquan_data.content_plan_packet",
            "taskId": task_id,
            "batchId": batch_id,
            "generatedBy": "site_supply_content_plan_bridge",
            "sourceSite": {"vertical": "travel", "siteId": "wikivoyage_zh", "batchId": "site_batch_100"},
            "items": items,
        },
    )

    result = run_mod._run_produce_plan(ctx)

    assert result.status == "done", result
    assert sorted(iter_content_refs(task_id, batch_id)) == ["candidate_dynamic_1", "candidate_dynamic_2"]
    assert _EID not in "\n".join(iter_content_refs(task_id, batch_id))
    ctx.until = "produce_plan"
    assert run_mod.run_pipeline(ctx) == 0
    state = read_json(batch_workflow_state_path(task_id, batch_id))
    for stage in ("download_plan", "download_fetch", "build_prepare", "build_homepage", "build_validate"):
        assert stage in state["completed"]
    assert state["siteSupplyDynamicStageBypass"]["reason"].startswith("site_supply front-half")

def test_auto_content_plan_image_work_does_not_let_article_evidence_consume_publish_asset():
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec.setdefault("content", {}).setdefault("quotas", {})["entityArticlesPerTarget"] = 1
    spec["content"]["quotas"]["imageWorksPerTarget"] = 1
    spec.setdefault("acceptance", {})["requiredAngles"] = ["planning_consultation", "image"]
    store.save_spec(spec)
    batch_id = "content_plan_image_avoids_article_asset"
    ctx = _ctx(task_id, batch_id)
    object_dir = resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
    sources_dir = object_dir / STAGE_DOWNLOAD / "sources"
    article_image = _real_jpeg(211)
    article_digest = hashlib.sha256(article_image).hexdigest()
    article_dir = sources_dir / "01.article_base"
    (article_dir / "assets").mkdir(parents=True, exist_ok=True)
    (article_dir / "source.md").write_text(
        "\n".join(
            [
                f"{_EID}行前需要核对开放时间、门票预约、交通接驳和天气情况，并把停车、接驳车、返程末班都写入计划。",
                f"{_EID}适合把入口动线、核心观景点、返程交通和周边餐饮拆开记录，亲子或老人同行时还要降低坡道路段强度。",
                f"{_EID}不同季节体验差异明显，需要结合现场排队、道路坡度、遮阴条件和雨天湿滑风险来判断值不值得去。",
            ]
            * 90
        ),
        encoding="utf-8",
    )
    write_json(
        article_dir / "meta.json",
        {
            "sourceId": "article_base",
            "researchLane": "article",
            "sourceRole": "base",
            "sourceUseMode": "factual_reference_only",
            "category": "travelogue",
            "title": "有图文章底稿",
            "sourceQualityScore": 0.9,
        },
    )
    (article_dir / "assets" / "article.jpg").write_bytes(article_image)
    write_json(
        article_dir / "assets" / "index.json",
        {
            "assets": [
                {
                    "fileName": "article.jpg",
                    "sha256": f"sha256:{article_digest}",
                    "sourceCollectionId": "article:collection",
                    "caption": f"{_EID} 文章源图",
                    "license": "CC-BY-SA 4.0",
                    "credit": "测试作者",
                    "sourceUrl": "https://example.test/article-image",
                    "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                    "usageScope": "factual_reference_only",
                }
            ]
        },
    )
    for index, (source_name, image_bytes, collection_id) in enumerate(
        [
            ("02.image_reused", article_image, "article:collection"),
            ("03.image_safe", _real_jpeg(212), "image:collection:safe"),
        ],
        start=2,
    ):
        source_dir = sources_dir / source_name
        assets_dir = source_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        asset_name = "image.jpg"
        (source_dir / "source.md").write_text(f"# {_EID} 图片 {index}", encoding="utf-8")
        (assets_dir / asset_name).write_bytes(image_bytes)
        digest = hashlib.sha256(image_bytes).hexdigest()
        write_json(
            source_dir / "meta.json",
            {
                "sourceId": source_name,
                "researchLane": "image",
                "title": f"图片 {index}",
                "sourceCollectionId": collection_id,
            },
        )
        write_json(
            assets_dir / "index.json",
            {
                "assets": [
                    {
                        "fileName": asset_name,
                        "sha256": f"sha256:{digest}",
                        "sourceCollectionId": collection_id,
                        "caption": f"{_EID} 图片 {index}",
                        "license": "CC-BY-SA 4.0",
                        "credit": "测试摄影师",
                        "sourceUrl": f"https://example.test/image/{index}",
                        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                        "usageScope": "app_publish",
                    }
                ]
            },
        )

    issues = run_mod._auto_content_plan(ctx, spec)

    assert issues == []
    packet = read_json(batch_root(task_id, batch_id) / "_shared" / "content_plan_packet.json")
    image_items = [item for item in packet["items"] if item["carrier"] == "image"]
    assert len(image_items) == 1
    assert image_items[0]["sourceCollectionId"] == "image:collection:safe"
    diagnostics = read_json(batch_root(task_id, batch_id) / "_shared" / "content_plan_source_diagnostics.json")
    assert diagnostics["targets"][_EID]["imageRejects"]["source_asset_reused"] == 1

def test_auto_content_plan_allows_text_only_article_base_without_source_assets():
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec.setdefault("content", {}).setdefault("quotas", {})["entityArticlesPerTarget"] = 1
    spec["content"]["quotas"]["imageWorksPerTarget"] = 0
    spec.setdefault("acceptance", {})["requiredAngles"] = ["planning_consultation"]
    store.save_spec(spec)
    batch_id = "content_plan_article_allows_text_only_source"
    ctx = _ctx(task_id, batch_id)
    object_dir = resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
    sources_dir = object_dir / STAGE_DOWNLOAD / "sources"
    repeated_body = "\n".join(
        [
            f"{_EID}行前需要核对开放时间、门票预约、交通接驳和天气情况，并把停车、接驳车、返程末班都写入计划。",
            f"{_EID}核心游览点之间有步行距离，需要预留返程时间，同时说明亲子、老人同行时哪些路段应该降低强度。",
            f"{_EID}不同季节体验差异明显，雨天要注意路面湿滑，晴天则更适合把观景点和补给点拆成两段安排。",
            f"{_EID}文章底稿必须同时具备文字和可追溯源图，源图不是装饰，而是支撑现场判断和图文闭环的底稿证据。",
        ]
        * 90
    )
    for index, (source_id, has_asset, quality) in enumerate(
        [
            ("article_without_image", False, 1.0),
            ("article_with_image", True, 0.8),
        ],
        start=1,
    ):
        source_dir = sources_dir / f"{index:02d}.{source_id}"
        source_dir.mkdir(parents=True, exist_ok=True)
        write_json(
            source_dir / "meta.json",
            {
                "sourceId": source_id,
                "researchLane": "article",
                "sourceRole": "base",
                "sourceUseMode": "factual_reference_only",
                "category": "travelogue",
                "title": f"测试底稿 {index}",
                "sourceQualityScore": quality,
            },
        )
        (source_dir / "source.md").write_text(repeated_body, encoding="utf-8")
        if has_asset:
            assets_dir = source_dir / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)
            asset_name = "source.jpg"
            data = _real_jpeg(120 + index)
            (assets_dir / asset_name).write_bytes(data)
            write_json(
                assets_dir / "index.json",
                {
                    "assets": [
                        {
                            "fileName": asset_name,
                            "sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
                            "sourceCollectionId": "article-source-with-image",
                            "caption": f"{_EID} 图文底稿配图",
                            "license": "CC-BY-SA 4.0",
                            "credit": "测试摄影师",
                            "sourceUrl": "https://example.test/source-image",
                            "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                            "usageScope": "app_publish",
                        }
                    ]
                },
            )

    issues = run_mod._auto_content_plan(ctx, spec)

    assert issues == []
    packet = read_json(batch_root(task_id, batch_id) / "_shared" / "content_plan_packet.json")
    article_items = [item for item in packet["items"] if item["carrier"] == "article"]
    assert len(article_items) == 1
    assert "article_without_image" in article_items[0]["baseSourceRef"]
    assert article_items[0]["assetRefs"] == []
    assert article_items[0]["publishMediaMode"] == "text_only"
    diagnostics = read_json(batch_root(task_id, batch_id) / "_shared" / "content_plan_source_diagnostics.json")
    target_diag = diagnostics["targets"][_EID]
    assert target_diag["articleImageSoftWarnings"]["no_source_assets"] == 1
    assert "no_source_assets" not in target_diag["articleRejects"]

def test_auto_content_plan_allows_article_base_reusing_source_image_as_text_only():
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec.setdefault("content", {}).setdefault("quotas", {})["entityArticlesPerTarget"] = 2
    spec["content"]["quotas"]["imageWorksPerTarget"] = 0
    spec.setdefault("acceptance", {})["requiredAngles"] = [
        "planning_consultation",
        "decision_experience",
    ]
    store.save_spec(spec)
    batch_id = "content_plan_article_source_image_soft_unique"
    ctx = _ctx(task_id, batch_id)
    object_dir = resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
    sources_dir = object_dir / STAGE_DOWNLOAD / "sources"
    body = "\n".join(
        [
            f"{_EID}图文底稿同时包含文字判断与现场配图，需要核对交通、预约、停留时长、季节变化和返程安排。",
            f"{_EID}文章源图是底稿的一部分，不允许另一篇文章复用同一张物理图片，否则图文证据链会失真。",
            f"{_EID}读者需要看到同一底稿中的现场图像与正文判断互相支撑，不能用图库作品或其它来源临时拼接。",
        ]
        * 90
    )
    duplicate_image = _real_jpeg(531)
    source_specs = [
        ("01.article_a", "article_a", duplicate_image, 0.95),
        ("02.article_b_same_image", "article_b_same_image", duplicate_image, 0.90),
        ("03.article_c_unique_image", "article_c_unique_image", _real_jpeg(532), 0.80),
    ]
    for source_dir_name, source_id, image_bytes, quality in source_specs:
        source_dir = sources_dir / source_dir_name
        assets_dir = source_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        (source_dir / "source.md").write_text(body, encoding="utf-8")
        write_json(
            source_dir / "meta.json",
            {
                "sourceId": source_id,
                "researchLane": "article",
                "sourceRole": "base",
                "sourceUseMode": "factual_reference_only",
                "category": "travelogue",
                "title": source_id,
                "sourceQualityScore": quality,
            },
        )
        asset_name = "source.jpg"
        (assets_dir / asset_name).write_bytes(image_bytes)
        digest = hashlib.sha256(image_bytes).hexdigest()
        write_json(
            assets_dir / "index.json",
            {
                "assets": [
                    {
                        "fileName": asset_name,
                        "sha256": f"sha256:{digest}",
                        "sourceCollectionId": f"article:{source_id}",
                        "caption": f"{_EID} 图文底稿源图",
                        "license": "CC-BY-SA 4.0",
                        "credit": "测试摄影师",
                        "sourceUrl": f"https://example.test/article/{source_id}",
                        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                        "usageScope": "app_publish",
                    }
                ]
            },
        )

    issues = run_mod._auto_content_plan(ctx, spec)

    assert issues == [], issues
    packet = read_json(batch_root(task_id, batch_id) / "_shared" / "content_plan_packet.json")
    article_items = [item for item in packet["items"] if item["carrier"] == "article"]
    assert len(article_items) == 2
    assert "article_a" in article_items[0]["baseSourceRef"]
    assert "article_b_same_image" in article_items[1]["baseSourceRef"]
    assert article_items[0].get("assetRefs")
    assert article_items[1].get("assetRefs") == []
    assert article_items[1]["publishMediaMode"] == "text_only"
    diagnostics = read_json(batch_root(task_id, batch_id) / "_shared" / "content_plan_source_diagnostics.json")
    assert diagnostics["schemaVersion"] == "quwoquan_data.content_plan_source_diagnostics"
    target_diag = diagnostics["targets"][_EID]
    assert target_diag["articleImageSoftWarnings"]["source_asset_reused"] == 1
    assert "source_asset_reused" not in target_diag["articleRejects"]

def test_auto_content_plan_disambiguates_duplicate_image_captions():
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec.setdefault("content", {}).setdefault("quotas", {})["entityArticlesPerTarget"] = 0
    spec["content"]["quotas"]["imageWorksPerTarget"] = 2
    spec.setdefault("acceptance", {})["requiredAngles"] = ["image"]
    store.save_spec(spec)
    batch_id = "content_plan_duplicate_image_caption_titles"
    ctx = _ctx(task_id, batch_id)
    object_dir = resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
    sources_dir = object_dir / STAGE_DOWNLOAD / "sources"
    shared_caption_prefix = "共享景观" * 16
    for index in range(1, 3):
        source_dir = sources_dir / f"{index:02d}.image_fixture_{index}"
        assets_dir = source_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        asset_name = f"image_{index}.jpg"
        asset_bytes = _real_jpeg(80 + index)
        (assets_dir / asset_name).write_bytes(asset_bytes)
        digest = hashlib.sha256(asset_bytes).hexdigest()
        write_json(
            source_dir / "meta.json",
            {
                "sourceId": f"image_fixture_{index}",
                "researchLane": "image",
                "title": "共享景观",
                "sourceCollectionId": f"fixture:image:{index}",
            },
        )
        (source_dir / "source.md").write_text(f"# {_EID} 共享景观图 {index}", encoding="utf-8")
        write_json(
            assets_dir / "index.json",
            {
                "assets": [
                    {
                        "fileName": asset_name,
                        "sha256": f"sha256:{digest}",
                        "sourceCollectionId": f"fixture:image:{index}",
                        "caption": f"{shared_caption_prefix}{index}",
                        "license": "CC-BY-SA 4.0",
                        "credit": f"测试摄影师{index}",
                        "sourceUrl": f"https://example.test/image/{index}",
                        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                        "usageScope": "app_publish",
                    }
                ]
            },
        )

    issues = run_mod._auto_content_plan(ctx, spec)

    assert issues == []
    packet = read_json(batch_root(task_id, batch_id) / "_shared" / "content_plan_packet.json")
    image_items = [item for item in packet["items"] if item["carrier"] == "image"]
    title_prefix = shared_caption_prefix[:60]
    assert [item["title"] for item in image_items] == [
        f"{_EID}·{title_prefix}·视角1",
        f"{_EID}·{title_prefix}·视角2",
    ]

def test_auto_content_plan_skips_image_assets_blocked_by_safety_gate():
    task_id = _make_task()
    spec = store.load_spec(task_id)
    spec.setdefault("content", {}).setdefault("quotas", {})["entityArticlesPerTarget"] = 0
    spec["content"]["quotas"]["imageWorksPerTarget"] = 1
    spec.setdefault("acceptance", {})["requiredAngles"] = ["image"]
    store.save_spec(spec)
    batch_id = "content_plan_image_safety_prefilter"
    ctx = _ctx(task_id, batch_id)
    object_dir = resolve_entity_object_dir(task_id, batch_id, _EID, etype_hint="地点/景区")
    sources_dir = object_dir / STAGE_DOWNLOAD / "sources"
    fixtures = [
        (
            "01.image_bad",
            "oversized.png",
            _oversized_png_header(),
            "fixture:image:z_bad",
            "超大原图",
        ),
        (
            "02.image_safe",
            "safe.jpg",
            _real_jpeg(311),
            "fixture:image:a_safe",
            "合格视角",
        ),
    ]
    for index, (source_name, asset_name, asset_bytes, collection_id, caption) in enumerate(fixtures, start=1):
        source_dir = sources_dir / source_name
        assets_dir = source_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        (source_dir / "source.md").write_text(f"# {_EID} {caption}", encoding="utf-8")
        (assets_dir / asset_name).write_bytes(asset_bytes)
        digest = hashlib.sha256(asset_bytes).hexdigest()
        write_json(
            source_dir / "meta.json",
            {
                "sourceId": source_name,
                "researchLane": "image",
                "title": caption,
                "sourceCollectionId": collection_id,
            },
        )
        write_json(
            assets_dir / "index.json",
            {
                "assets": [
                    {
                        "fileName": asset_name,
                        "sha256": f"sha256:{digest}",
                        "sourceCollectionId": collection_id,
                        "caption": caption,
                        "license": "CC-BY-SA 4.0",
                        "credit": f"测试摄影师{index}",
                        "sourceUrl": f"https://example.test/image/{index}",
                        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                        "usageScope": "app_publish",
                    }
                ]
            },
        )

    issues = run_mod._auto_content_plan(ctx, spec)

    assert issues == []
    packet = read_json(batch_root(task_id, batch_id) / "_shared" / "content_plan_packet.json")
    image_items = [item for item in packet["items"] if item["carrier"] == "image"]
    assert len(image_items) == 1
    assert image_items[0]["sourceCollectionId"] == "fixture:image:a_safe"
    assert image_items[0]["assetRefs"][0].endswith("/safe.jpg")
    diagnostics = read_json(batch_root(task_id, batch_id) / "_shared" / "content_plan_source_diagnostics.json")
    target_diag = diagnostics["targets"][_EID]
    assert target_diag["rawImageAssets"] == 2
    assert target_diag["qualifiedImageAssets"] == 1
    assert target_diag["imageRejects"]["image_safety_blocked"] == 1
    assert "image_pixels_too_large" in target_diag["imageRejectExamples"]["image_safety_blocked"][0]

def test_content_plan_override_replaces_stale_brief_base_source():
    from produce.handler import _apply_writing_intent_override

    brief = {
        "writingIntent": "planning_consultation",
        "baseSourceRef": "entities/地点/景区/毕棚沟/1.download/sources/03.home_official/source.md",
        "carrier": "article",
    }
    override = {
        "writingIntent": "seasonal_timing",
        "baseSourceRef": "entities/地点/景区/毕棚沟/1.download/sources/07.article_wiki_seasonal/source.md",
        "carrier": "article",
    }

    merged = _apply_writing_intent_override(brief, override)
    assert merged["writingIntent"] == "seasonal_timing"
    assert merged["baseSourceRef"].endswith("07.article_wiki_seasonal/source.md")
    assert merged["_contentPlanBaseSourceLocked"] is True

def test_image_content_plan_override_clears_stale_article_base_source():
    from produce.handler import _apply_writing_intent_override

    brief = {
        "carrier": "article",
        "baseSourceRef": "entities/地点/景区/稻城亚丁/1.download/sources/07.article_wiki_seasonal/source.md",
        "_contentPlanBaseSourceLocked": True,
    }
    override = {
        "carrier": "image",
        "sourceCollectionId": "daochengyading:image:wikimedia",
        "assetRefs": ["entities/地点/景区/稻城亚丁/1.download/sources/09.image/assets/001.jpg"],
    }

    merged = _apply_writing_intent_override(brief, override)
    assert merged["carrier"] == "image"
    assert "baseSourceRef" not in merged
    assert "_contentPlanBaseSourceLocked" not in merged
    assert merged["sourceCollectionId"] == "daochengyading:image:wikimedia"

