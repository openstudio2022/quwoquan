from __future__ import annotations



from support.content_plan_source_reject_fixtures import *  # noqa: F401,F403



def test_content_plan_separated_research_enforces_per_target_quota_count():
    entity = "四姑娘山"
    items_by_execution = {EXECUTION_ID: [], IMAGE_EXECUTION_ID: []}
    for index, (carrier, intent) in enumerate(
        [
            ("article", "planning_consultation"),
            ("article", "decision_experience"),
            ("image", "decision_experience"),
            ("image", "decision_experience"),
        ],
        start=1,
    ):
        execution_id = IMAGE_EXECUTION_ID if carrier == "image" else EXECUTION_ID
        root = execution_root(execution_id)
        ref = f"siguniang_{index}"
        title = f"四姑娘山作品{index}"
        source_dir = (
            root
            / "entities/地点/景区/四姑娘山/1.download/sources"
            / f"{index:02d}.source_{index}"
        )
        source_dir.mkdir(parents=True, exist_ok=True)
        source_path = source_dir / "source.md"
        source_path.write_text(
            (f"四姑娘山来源证据 {index}，这是一段包含交通、季节、游览动线和体验判断的图文底稿。" * 45),
            encoding="utf-8",
        )
        article_asset = None
        if carrier != "image":
            article_asset = _write_article_source_asset(source_dir, label=f"article_{index}")
        write_json(
            source_dir / "meta.json",
            {
                "sourceUseMode": "factual_reference_only",
                "researchLane": "article",
                "sourceRole": "base",
                "category": "travelogue",
            },
        )
        content_object.register_content_object(
            execution_id,
            ref,
            content_type="image" if carrier == "image" else "article",
            angle="画报" if carrier == "image" else "攻略",
            title=title,
        )
        brief_dir = content_object.content_object_stage_dir(execution_id, ref, STAGE_COMPOSE)
        write_json(brief_dir / content_object.BRIEF_FILE, {"titleHint": title})
        rel = source_path.relative_to(root).as_posix()
        item = {
            "ref": ref,
            "kind": "entity",
            "carrier": carrier,
            "title": title,
            "entityRefs": [f"/entity/地点/景区/{entity}"],
            "evidenceRefs": [rel],
            "rationale": f"证据驱动主题 {index}",
            "writingIntent": intent,
            "baseSourceRef": rel,
            "sourceUseMode": "factual_reference_only",
            "researchLane": "article",
        }
        if carrier == "image":
            asset_dir = root / "entities/地点/景区/四姑娘山/1.download/sources" / f"image_{index}" / "assets"
            asset_dir.mkdir(parents=True, exist_ok=True)
            asset_file = asset_dir / f"asset_{index}.jpg"
            asset_file.write_bytes(_real_jpeg(index))
            write_json(
                asset_dir / "index.json",
                {
                    "assets": [
                        {
                            "fileName": asset_file.name,
                            "sourceCollectionId": f"collection_{index}",
                        }
                    ]
                },
            )
            write_json(
                asset_dir.parent / "meta.json",
                {"researchLane": "image", "sourceCollectionId": f"collection_{index}"},
            )
            item.update(
                {
                    "researchLane": "image",
                    "sourceCollectionId": f"collection_{index}",
                    "assetRefs": [asset_file.relative_to(root).as_posix()],
                    "baseSourceRef": "",
                    "sourceUseMode": "",
                }
            )
        elif article_asset is not None:
            item["assetRefs"] = [article_asset.relative_to(root).as_posix()]
        items_by_execution[execution_id].append(item)
    for execution_id, items in items_by_execution.items():
        write_json(
            execution_content_plan_packet_path(execution_id),
            {"schema": cp.CONTENT_PLAN_SCHEMA, "items": items},
        )
    article_spec = {
        "scope": {
            "coverageTargets": [{"entityType": "地点/景区", "name": entity}],
        },
        "content": {
            "quotas": {
                "entityArticlesPerTarget": 2,
                "imageWorksPerTarget": 0,
                "entityHomepagesPerTarget": 0,
                "routeArticles": 0,
            },
            "modalityContract": "separated_research",
            "research": {"imageCountPolicy": "hard_quota"},
        },
    }
    image_spec = {
        "scope": article_spec["scope"],
        "content": {
            "quotas": {
                "entityArticlesPerTarget": 0,
                "imageWorksPerTarget": 2,
                "entityHomepagesPerTarget": 0,
                "routeArticles": 0,
            },
            "modalityContract": "separated_research",
            "research": {"imageCountPolicy": "hard_quota"},
        },
    }
    assert cp.validate_content_plan(EXECUTION_ID, article_spec) == []
    assert cp.validate_content_plan(IMAGE_EXECUTION_ID, image_spec) == []
    write_json(
        execution_content_plan_packet_path(EXECUTION_ID),
        {
            "schema": "invalid.content_plan_packet",
            "items": items_by_execution[EXECUTION_ID],
        },
    )
    schema_issues = cp.validate_content_plan(EXECUTION_ID, article_spec)
    assert any("content_plan_packet.schema" in issue for issue in schema_issues), schema_issues
    write_json(
        execution_content_plan_packet_path(IMAGE_EXECUTION_ID),
        {
            "schema": cp.CONTENT_PLAN_SCHEMA,
            "items": items_by_execution[IMAGE_EXECUTION_ID][:-1],
        },
    )
    # 跨载体配额由 sibling executions 汇总；单 execution 内只校验自己的载体配额。
    issues = cp.validate_content_plan(IMAGE_EXECUTION_ID, image_spec)
    assert any("imageWorksPerTarget quota" in issue for issue in issues), issues
    assert not any("entityArticlesPerTarget quota" in issue for issue in issues), issues


def test_content_plan_commercial_closure_treats_per_target_quota_as_ceiling():
    entity = "黄龙"
    root = execution_root(EXECUTION_ID)
    source_dir = root / "entities/地点/景区/黄龙/1.download/sources/01.article"
    source_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / "source.md"
    source_path.write_text(
        ("黄龙单底稿证据，包含交通、预约、海拔、步道节奏和季节体验。" * 80),
        encoding="utf-8",
    )
    write_json(
        source_dir / "meta.json",
        {
            "sourceUseMode": "factual_reference_only",
            "researchLane": "article",
            "sourceRole": "base",
            "category": "travelogue",
        },
    )
    ref = "huanglong_article_1"
    title = "黄龙行前实用底稿"
    content_object.register_content_object(
            EXECUTION_ID,
            ref,
        content_type="article",
        angle="攻略",
        title=title,
    )
    brief_dir = content_object.content_object_stage_dir(EXECUTION_ID, ref, STAGE_COMPOSE)
    write_json(brief_dir / content_object.BRIEF_FILE, {"titleHint": title})
    source_ref = source_path.relative_to(root).as_posix()
    write_json(
        execution_content_plan_packet_path(EXECUTION_ID),
        {
            "schema": cp.CONTENT_PLAN_SCHEMA,
            "items": [
                {
                    "ref": ref,
                    "kind": "entity",
                    "carrier": "article",
                    "researchLane": "article",
                    "title": title,
                    "entityRefs": [f"/entity/地点/景区/{entity}"],
                    "evidenceRefs": [source_ref],
                    "rationale": "商业闭环下 shared pool 只要求最小可交付作品",
                    "writingIntent": "planning_consultation",
                    "baseSourceRef": source_ref,
                    "sourceUseMode": "factual_reference_only",
                }
            ],
        },
    )
    spec = {
        "executionPolicy": {
            "articleCommercialClosure": True,
            "targetObjectCount": 100,
        },
        "scope": {"coverageTargets": [{"entityType": "地点/景区", "name": entity}]},
        "content": {
            "modalityContract": "separated_research",
            "quotas": {
                "entityArticlesPerTarget": 4,
                "imageWorksPerTarget": 0,
                "entityHomepagesPerTarget": 0,
                "routeArticles": 0,
            },
        },
    }

    issues = cp.validate_content_plan(EXECUTION_ID, spec)

    assert issues == [], issues

def test_content_plan_separated_research_keeps_image_lane_without_angle_coverage():
    entity = "九寨沟"
    article_intents = [
        "planning_consultation",
        "decision_experience",
        "route_transport",
        "seasonal_timing",
    ]
    items = []
    for index, intent in enumerate(article_intents, start=1):
        ref = f"{entity}_{intent}"
        title = f"九寨沟{intent}"
        source_dir = (
            execution_root(EXECUTION_ID)
            / "entities/地点/景区/九寨沟/1.download/sources"
            / f"{index:02d}.{intent}"
        )
        source_dir.mkdir(parents=True, exist_ok=True)
        source_path = source_dir / "source.md"
        source_path.write_text(
            (f"九寨沟 {intent} 来源证据，含图文混合底稿 {index}，补充路线、季节、停留时长和风险提示。" * 45),
            encoding="utf-8",
        )
        article_asset = _write_article_source_asset(source_dir, label=f"jiuzhaigou_{index}")
        write_json(
            source_dir / "meta.json",
            {
                "sourceUseMode": "factual_reference_only",
                "researchLane": "article",
                "sourceRole": "base",
                "category": "travelogue",
            },
        )
        content_object.register_content_object(
            EXECUTION_ID,
            ref,
            content_type="article",
            angle="攻略",
            title=title,
        )
        brief_dir = content_object.content_object_stage_dir(EXECUTION_ID, ref, STAGE_COMPOSE)
        write_json(brief_dir / content_object.BRIEF_FILE, {"titleHint": title, "writingIntent": intent})
        rel = source_path.relative_to(execution_root(EXECUTION_ID)).as_posix()
        items.append(
            {
                "ref": ref,
                "kind": "entity",
                "carrier": "article",
                "researchLane": "article",
                "title": title,
                "entityRefs": [f"/entity/地点/景区/{entity}"],
                "evidenceRefs": [rel],
                "rationale": f"{intent} 主线证据",
                    "writingIntent": intent,
                    "baseSourceRef": rel,
                    "assetRefs": [article_asset.relative_to(execution_root(EXECUTION_ID)).as_posix()],
                    "sourceUseMode": "factual_reference_only",
                }
            )

    image_source = (
        execution_root(IMAGE_EXECUTION_ID)
        / "entities/地点/景区/九寨沟/1.download/sources/05.image_collection"
    )
    asset_dir = image_source / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    source_path = image_source / "source.md"
    source_path.write_text("九寨沟同一摄影集合，图片底稿。", encoding="utf-8")
    asset_file = asset_dir / "asset_1.jpg"
    asset_file.write_bytes(_real_jpeg(41))
    write_json(
        asset_dir / "index.json",
        {"assets": [{"fileName": asset_file.name, "sourceCollectionId": "jiuzhaigou:image:one"}]},
    )
    write_json(
        image_source / "meta.json",
        {"researchLane": "image", "sourceCollectionId": "jiuzhaigou:image:one"},
    )
    ref = f"{entity}_image"
    content_object.register_content_object(
        IMAGE_EXECUTION_ID,
        ref,
        content_type="image",
        angle="画报",
        title="九寨沟图片作品",
    )
    brief_dir = content_object.content_object_stage_dir(IMAGE_EXECUTION_ID, ref, STAGE_COMPOSE)
    write_json(brief_dir / content_object.BRIEF_FILE, {"titleHint": "九寨沟图片作品"})
    image_item = {
        "ref": ref,
        "kind": "entity",
        "carrier": "image",
        "researchLane": "image",
        "title": "九寨沟图片作品",
        "entityRefs": [f"/entity/地点/景区/{entity}"],
        "evidenceRefs": [source_path.relative_to(execution_root(IMAGE_EXECUTION_ID)).as_posix()],
        "rationale": "同一图片集合证据",
        "sourceCollectionId": "jiuzhaigou:image:one",
        "assetRefs": [asset_file.relative_to(execution_root(IMAGE_EXECUTION_ID)).as_posix()],
    }
    article_spec = {
        "scope": {"coverageTargets": [{"entityType": "地点/景区", "name": entity}]},
        "content": {
            "modalityContract": "separated_research",
            "quotas": {
                "entityArticlesPerTarget": 4,
                "imageWorksPerTarget": 0,
                "entityHomepagesPerTarget": 0,
                "routeArticles": 0,
            },
        },
        "acceptance": {
            "requiredAngles": article_intents,
        },
    }
    image_spec = {
        "scope": article_spec["scope"],
        "content": {
            "modalityContract": "separated_research",
            "quotas": {
                "entityArticlesPerTarget": 0,
                "imageWorksPerTarget": 1,
                "entityHomepagesPerTarget": 0,
                "routeArticles": 0,
            },
        },
        "acceptance": {"requiredAngles": ["image"]},
    }
    write_json(
        execution_content_plan_packet_path(EXECUTION_ID),
        {"schema": cp.CONTENT_PLAN_SCHEMA, "items": items},
    )
    write_json(
        execution_content_plan_packet_path(IMAGE_EXECUTION_ID),
        {"schema": cp.CONTENT_PLAN_SCHEMA, "items": [image_item]},
    )
    assert cp.validate_content_plan(EXECUTION_ID, article_spec) == []
    assert cp.validate_content_plan(IMAGE_EXECUTION_ID, image_spec) == []
    write_json(
        image_source / "meta.json",
        {"researchLane": "article", "sourceCollectionId": "jiuzhaigou:image:one"},
    )
    lane_issues = cp.validate_content_plan(IMAGE_EXECUTION_ID, image_spec)
    assert any("image asset must come from researchLane=image" in issue for issue in lane_issues), lane_issues
    write_json(
        image_source / "meta.json",
        {"researchLane": "image", "sourceCollectionId": "jiuzhaigou:image:one"},
    )
    write_json(
        execution_content_plan_packet_path(EXECUTION_ID),
        {"schema": cp.CONTENT_PLAN_SCHEMA, "items": items[:2]},
    )
    # writingIntent 仍是派生可选标签，但 per-target 数量是冻结放量合同；
    # 缺篇数必须阻断，不存在 execution 级部分交付旁路。
    issues = cp.validate_content_plan(EXECUTION_ID, article_spec)
    assert not any("acceptance.requiredAngles" in issue for issue in issues), issues
    assert any("entityArticlesPerTarget quota" in issue for issue in issues), issues
