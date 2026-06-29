from __future__ import annotations



from support.content_plan_source_reject_fixtures import *  # noqa: F401,F403



def test_content_plan_separated_research_has_no_per_target_quota_floor():
    batch = "per_target_quotas"
    entity = "四姑娘山"
    items = []
    for index, (carrier, intent) in enumerate(
        [
            ("article", "planning_consultation"),
            ("article", "decision_experience"),
            ("image", "decision_experience"),
            ("image", "decision_experience"),
        ],
        start=1,
    ):
        ref = f"siguniang_{index}"
        title = f"四姑娘山作品{index}"
        source_dir = (
            batch_root(TASK, batch)
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
            TASK,
            batch,
            ref,
            content_type="image" if carrier == "image" else "article",
            angle="画报" if carrier == "image" else "攻略",
            title=title,
        )
        brief_dir = content_object.content_object_stage_dir(TASK, batch, ref, STAGE_COMPOSE)
        write_json(brief_dir / content_object.BRIEF_FILE, {"titleHint": title})
        rel = source_path.relative_to(batch_root(TASK, batch)).as_posix()
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
            asset_dir = batch_root(TASK, batch) / "entities/地点/景区/四姑娘山/1.download/sources" / f"image_{index}" / "assets"
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
                    "assetRefs": [asset_file.relative_to(batch_root(TASK, batch)).as_posix()],
                    "baseSourceRef": "",
                    "sourceUseMode": "",
                }
            )
        elif article_asset is not None:
            item["assetRefs"] = [article_asset.relative_to(batch_root(TASK, batch)).as_posix()]
        items.append(item)
    write_json(
        batch_content_plan_packet_path(TASK, batch),
        {"schemaVersion": cp.CONTENT_PLAN_SCHEMA, "items": items},
    )
    spec = {
        "scope": {
            "coverageTargets": [{"entityType": "地点/景区", "name": entity}],
        },
        "content": {
            "quotas": {
                "entityArticlesPerTarget": 2,
                "imageWorksPerTarget": 2,
                "entityHomepagesPerTarget": 1,
                "routeArticles": 0,
            },
            "modalityContract": "separated_research",
            "research": {"imageCountPolicy": "hard_quota"},
        },
    }
    assert cp.validate_content_plan(TASK, batch, spec) == []
    write_json(
        batch_content_plan_packet_path(TASK, batch),
        {"schemaVersion": "quwoquan_data.content_plan_packet/1", "items": items},
    )
    schema_issues = cp.validate_content_plan(TASK, batch, spec)
    assert any("content_plan_packet.schemaVersion" in issue for issue in schema_issues), schema_issues
    write_json(
        batch_content_plan_packet_path(TASK, batch),
        {"schemaVersion": cp.CONTENT_PLAN_SCHEMA, "items": items[:-1]},
    )
    # 底稿中心：separated_research 下配额降级为车道开关，不存在 per-target 数量地板；
    # 删掉一件图片作品后不再触发 imageWorksPerTarget / entityArticlesPerTarget 配额报错。
    issues = cp.validate_content_plan(TASK, batch, spec)
    assert not any("imageWorksPerTarget quota" in issue for issue in issues), issues
    assert not any("entityArticlesPerTarget quota" in issue for issue in issues), issues

def test_content_plan_separated_research_keeps_image_lane_without_angle_coverage():
    batch = "per_target_4_plus_1"
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
            batch_root(TASK, batch)
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
            TASK,
            batch,
            ref,
            content_type="article",
            angle="攻略",
            title=title,
        )
        brief_dir = content_object.content_object_stage_dir(TASK, batch, ref, STAGE_COMPOSE)
        write_json(brief_dir / content_object.BRIEF_FILE, {"titleHint": title, "writingIntent": intent})
        rel = source_path.relative_to(batch_root(TASK, batch)).as_posix()
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
                    "assetRefs": [article_asset.relative_to(batch_root(TASK, batch)).as_posix()],
                    "sourceUseMode": "factual_reference_only",
                }
            )

    image_source = (
        batch_root(TASK, batch)
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
        TASK,
        batch,
        ref,
        content_type="image",
        angle="画报",
        title="九寨沟图片作品",
    )
    brief_dir = content_object.content_object_stage_dir(TASK, batch, ref, STAGE_COMPOSE)
    write_json(brief_dir / content_object.BRIEF_FILE, {"titleHint": "九寨沟图片作品"})
    items.append(
        {
            "ref": ref,
            "kind": "entity",
            "carrier": "image",
            "researchLane": "image",
            "title": "九寨沟图片作品",
            "entityRefs": [f"/entity/地点/景区/{entity}"],
            "evidenceRefs": [source_path.relative_to(batch_root(TASK, batch)).as_posix()],
            "rationale": "同一图片集合证据",
            "sourceCollectionId": "jiuzhaigou:image:one",
            "assetRefs": [asset_file.relative_to(batch_root(TASK, batch)).as_posix()],
        }
    )
    spec = {
        "scope": {"coverageTargets": [{"entityType": "地点/景区", "name": entity}]},
        "content": {
            "modalityContract": "separated_research",
            "quotas": {
                "entityArticlesPerTarget": 4,
                "imageWorksPerTarget": 1,
                "entityHomepagesPerTarget": 1,
                "routeArticles": 0,
            },
        },
        "acceptance": {
            "requiredAngles": [*article_intents, "image"],
        },
    }
    write_json(
        batch_content_plan_packet_path(TASK, batch),
        {"schemaVersion": cp.CONTENT_PLAN_SCHEMA, "items": items},
    )
    assert cp.validate_content_plan(TASK, batch, spec) == []
    write_json(
        image_source / "meta.json",
        {"researchLane": "article", "sourceCollectionId": "jiuzhaigou:image:one"},
    )
    lane_issues = cp.validate_content_plan(TASK, batch, spec)
    assert any("image asset must come from researchLane=image" in issue for issue in lane_issues), lane_issues
    write_json(
        image_source / "meta.json",
        {"researchLane": "image", "sourceCollectionId": "jiuzhaigou:image:one"},
    )
    write_json(
        batch_content_plan_packet_path(TASK, batch),
        {"schemaVersion": cp.CONTENT_PLAN_SCHEMA, "items": items[:2] + [items[-1]]},
    )
    state_dir = batch_root(TASK, batch) / "_shared"
    state_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        state_dir / "task_workflow_state.json",
        {
            "abandonedContentObjects": [
                {
                    "ref": f"{entity}_route_transport",
                    "status": "abandoned",
                    "reason": "fixture partial article source unavailable",
                },
                {
                    "ref": f"{entity}_seasonal_timing",
                    "status": "abandoned",
                    "reason": "fixture partial article source unavailable",
                },
            ]
        },
    )
    # 底稿中心：writingIntent 降为派生可选标签，不再有 acceptance.requiredAngles 角度覆盖硬门，
    # 也不再有 entityArticlesPerTarget 配额地板；缺角度/缺篇数都不阻断。
    issues = cp.validate_content_plan(TASK, batch, spec)
    assert not any("acceptance.requiredAngles" in issue for issue in issues), issues
    assert not any("entityArticlesPerTarget quota" in issue for issue in issues), issues
    partial_spec = {**spec, "workflowPolicy": {"allowContentQuotaShortfall": True}}
    assert cp.validate_content_plan(TASK, batch, partial_spec) == []

