from __future__ import annotations



from support.task_workflow_fixtures import *  # noqa: F401,F403


def _write_content_plan_source(
    object_dir,
    *,
    task_id: str,
    batch_id: str,
    ordinal: int,
    source_id: str,
    body: str,
    title: str,
    lane: str = "article",
    quality: float = 0.9,
    asset_name: str = "",
    asset_bytes: bytes | None = None,
    collection_id: str = "",
    caption: str = "",
    license_value: str = "CC-BY-SA 4.0",
    usage_scope: str = "app_publish",
):
    images = []
    if asset_bytes is not None:
        images.append(
            {
                "bytes": asset_bytes,
                "ext": Path(asset_name).suffix or ".jpg",
                "slug": Path(asset_name).stem or source_id,
                "sourceCollectionId": collection_id,
                "caption": caption,
                "license": license_value,
                "credit": "测试来源",
                "sourceUrl": f"https://example.test/{source_id}",
                "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                "usageScope": usage_scope,
            }
        )
    return write_structured_source_unit(
        object_dir,
        ordinal=ordinal,
        source_id=source_id,
        source_md=body,
        clean_md=body,
        quality={
            "sourceId": source_id,
            "quality": "A-story" if lane == "article" else "B-fact",
            "score": quality * 10,
            "sourceQualityScore": quality,
        },
        platform="fixture",
        source_category="travelogue" if lane == "article" else "image_collection",
        source_use_mode="factual_reference_only",
        publish_media_mode="same_source_media" if images else "text_only",
        source_role="base" if lane == "article" else "",
        research_lane=lane,
        license_value=license_value,
        url=f"https://example.test/{source_id}",
        title=title,
        target_ref=f"/entity/地点/景区/{_EID}",
        relevance=f"{_EID} fixture",
        images=images,
        task_id=task_id,
        batch_id=batch_id,
        build_variants=False,
    )



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
        _write_content_plan_source(
            object_dir,
            task_id=task_id,
            batch_id=batch_id,
            ordinal=index,
            source_id=f"article_fixture_{index}",
            body=repeated_body,
            title=f"测试底稿 {index}",
            asset_name="shared.jpg",
            asset_bytes=_real_jpeg(300 + index),
            collection_id=f"article-collection-{index}",
            caption=f"{_EID} 共享测试图",
            license_value="reference_only",
            usage_scope="factual_reference_only",
        )

    issues = run_mod._auto_content_plan(ctx, spec)

    assert issues == [], issues
    packet = read_json(batch_root(task_id, batch_id) / "_shared" / "content_plan_packet.json")
    article_items = [item for item in packet["items"] if item["carrier"] == "article"]
    # 底稿中心 1:1：4 个合格 article source unit -> 4 篇，各绑定唯一底稿与唯一源图。
    assert len(article_items) == 4
    assert len({item["baseSourceRef"] for item in article_items}) == 4
    assert len({item["assetRefs"][0] for item in article_items}) == 4
    # 标题取自底稿（meta.title），不再用 {实体}·{角度} 模板。
    assert all(item["title"].startswith("测试底稿") for item in article_items), [
        item["title"] for item in article_items
    ]
    # writingIntent 是底稿派生的合法标签；实体退化为含本实体的多标签。
    valid_intents = {"planning_consultation", "decision_experience", "post_trip_journal"}
    assert all(item["writingIntent"] in valid_intents for item in article_items)
    assert all(_EID in item["entityTags"] for item in article_items)

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
    _write_content_plan_source(
        object_dir,
        task_id=task_id,
        batch_id=batch_id,
        ordinal=1,
        source_id="article_site_base",
        body=repeated_body,
        title="网站线文章底稿",
        asset_name="site.jpg",
        asset_bytes=_real_jpeg(310),
        collection_id="site-source-collection",
        caption=f"{_EID} 来源图",
        license_value="reference_only",
        usage_scope="factual_reference_only",
    )
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
        body = (
            f"{name}是维基导游站点线动态候选，用于验证 content_plan packet 自带实体集合。"
            f"{name}的行前信息包含交通、季节、开放条件和游览动线，正文必须独立表达。"
        ) * 8
        manifest = write_source_unit(
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
        source_ref = manifest["sourceRef"]
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
    article_image = _real_jpeg(211)
    article_body = "\n".join(
        [
            f"{_EID}行前需要核对开放时间、门票预约、交通接驳和天气情况，并把停车、接驳车、返程末班都写入计划。",
            f"{_EID}适合把入口动线、核心观景点、返程交通和周边餐饮拆开记录，亲子或老人同行时还要降低坡道路段强度。",
            f"{_EID}不同季节体验差异明显，需要结合现场排队、道路坡度、遮阴条件和雨天湿滑风险来判断值不值得去。",
        ]
        * 90
    )
    _write_content_plan_source(
        object_dir,
        task_id=task_id,
        batch_id=batch_id,
        ordinal=1,
        source_id="article_base",
        body=article_body,
        title="有图文章底稿",
        asset_name="article.jpg",
        asset_bytes=article_image,
        collection_id="article:collection",
        caption=f"{_EID} 文章源图",
        usage_scope="factual_reference_only",
    )
    for index, (source_name, image_bytes, collection_id) in enumerate(
        [
            ("02.image_reused", article_image, "article:collection"),
            ("03.image_safe", _real_jpeg(212), "image:collection:safe"),
        ],
        start=2,
    ):
        _write_content_plan_source(
            object_dir,
            task_id=task_id,
            batch_id=batch_id,
            ordinal=index,
            source_id=source_name.split(".", 1)[1],
            body=f"# {_EID} 图片 {index}",
            title=f"图片 {index}",
            lane="image",
            asset_name="image.jpg",
            asset_bytes=image_bytes,
            collection_id=collection_id,
            caption=f"{_EID} 图片 {index}",
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
        data = _real_jpeg(120 + index) if has_asset else None
        _write_content_plan_source(
            object_dir,
            task_id=task_id,
            batch_id=batch_id,
            ordinal=index,
            source_id=source_id,
            body=repeated_body,
            title=f"测试底稿 {index}",
            quality=quality,
            asset_name="source.jpg",
            asset_bytes=data,
            collection_id="article-source-with-image" if has_asset else "",
            caption=f"{_EID} 图文底稿配图",
        )

    issues = run_mod._auto_content_plan(ctx, spec)

    assert issues == []
    packet = read_json(batch_root(task_id, batch_id) / "_shared" / "content_plan_packet.json")
    article_items = [item for item in packet["items"] if item["carrier"] == "article"]
    # 底稿中心 1:1：两个合格 article source 各成一篇；无源图者 text_only，有源图者绑定源图。
    assert len(article_items) == 2
    by_title = {item["title"]: item for item in article_items}
    text_only_item = by_title["测试底稿 1"]
    assert text_only_item["assetRefs"] == []
    assert text_only_item["publishMediaMode"] == "text_only"
    assert by_title["测试底稿 2"]["assetRefs"]
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
    for idx, (_source_dir_name, source_id, image_bytes, quality) in enumerate(source_specs, start=1):
        _write_content_plan_source(
            object_dir,
            task_id=task_id,
            batch_id=batch_id,
            ordinal=idx,
            source_id=source_id,
            body=body,
            title=f"测试底稿第{idx}篇",
            quality=quality,
            asset_name="source.jpg",
            asset_bytes=image_bytes,
            collection_id=f"article:{source_id}",
            caption=f"{_EID} 图文底稿源图",
        )

    issues = run_mod._auto_content_plan(ctx, spec)

    assert issues == [], issues
    packet = read_json(batch_root(task_id, batch_id) / "_shared" / "content_plan_packet.json")
    article_items = [item for item in packet["items"] if item["carrier"] == "article"]
    # 底稿中心 1:1：3 个合格 article source 各成一篇；复用同一物理源图者降级 text_only。
    assert len(article_items) == 3
    by_title = {item["title"]: item for item in article_items}
    assert by_title["测试底稿第1篇"].get("assetRefs")  # 最优先获得去重源图
    assert by_title["测试底稿第2篇"].get("assetRefs") == []  # 同图被占用 -> text_only
    assert by_title["测试底稿第2篇"]["publishMediaMode"] == "text_only"
    assert by_title["测试底稿第3篇"].get("assetRefs")  # 独立源图自成一篇
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
    shared_caption_prefix = "共享景观" * 16
    for index in range(1, 3):
        asset_name = f"image_{index}.jpg"
        asset_bytes = _real_jpeg(80 + index)
        _write_content_plan_source(
            object_dir,
            task_id=task_id,
            batch_id=batch_id,
            ordinal=index,
            source_id=f"image_fixture_{index}",
            body=f"# {_EID} 共享景观图 {index}",
            title="共享景观",
            lane="image",
            asset_name=asset_name,
            asset_bytes=asset_bytes,
            collection_id=f"fixture:image:{index}",
            caption=f"{shared_caption_prefix}{index}",
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
        _write_content_plan_source(
            object_dir,
            task_id=task_id,
            batch_id=batch_id,
            ordinal=index,
            source_id=source_name.split(".", 1)[1],
            body=f"# {_EID} {caption}",
            title=caption,
            lane="image",
            asset_name=asset_name,
            asset_bytes=asset_bytes,
            collection_id=collection_id,
            caption=caption,
        )

    issues = run_mod._auto_content_plan(ctx, spec)

    assert issues == []
    packet = read_json(batch_root(task_id, batch_id) / "_shared" / "content_plan_packet.json")
    image_items = [item for item in packet["items"] if item["carrier"] == "image"]
    assert len(image_items) == 1
    assert image_items[0]["sourceCollectionId"] == "fixture:image:a_safe"
    assert image_items[0]["assetRefs"][0].endswith("safe.jpg")
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
