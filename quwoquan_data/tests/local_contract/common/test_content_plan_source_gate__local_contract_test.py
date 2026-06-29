from __future__ import annotations



from support.content_plan_source_reject_fixtures import *  # noqa: F401,F403



def test_reject_source_ids_collects_only_rejects():
    _seed()
    rejects = cp.reject_source_ids(TASK, BATCH)
    assert rejects == {"reject1"}

def test_content_plan_blocks_rejected_source():
    _seed()
    issues = cp.validate_content_plan(TASK, BATCH, {})
    assert any("cites rejected source" in i and "reject1" in i for i in issues), issues

def test_content_plan_blocks_missing_creator_assignment_when_required():
    batch = "creator_assignment_required"
    entity = "九寨沟"
    root = batch_root(TASK, batch)
    evidence = root / "entities/地点/景区/九寨沟/1.download/sources/01.article/source.md"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text("九寨沟 " * 400, encoding="utf-8")
    evidence_ref = evidence.relative_to(root).as_posix()
    item = {
        "ref": f"{entity}_planning_consultation",
        "kind": "entity",
        "carrier": "article",
        "researchLane": "article",
        "title": f"{entity}·行前建议",
        "entityRefs": [f"/entity/地点/景区/{entity}"],
        "evidenceRefs": [evidence_ref],
        "baseSourceRef": evidence_ref,
        "sourceUseMode": "factual_reference_only",
        "rationale": "fixture evidence plan",
        "writingIntent": "planning_consultation",
    }
    write_json(
        batch_content_plan_packet_path(TASK, batch),
        {"schemaVersion": cp.CONTENT_PLAN_SCHEMA, "items": [item]},
    )
    content_object.write_brief_object(
        TASK,
        batch,
        item["ref"],
        {
            "titleHint": item["title"],
            "templateId": "travel.entity.guide",
            "carrier": "article",
            "entityRefs": item["entityRefs"],
        },
        content_type="article",
    )
    issues = cp.validate_content_plan(
        TASK,
        batch,
        {
            "workflowPolicy": {"requireCreatorAssignment": True},
            "scope": {"coverageTargets": [{"entityType": "地点/景区", "name": entity}]},
            "content": {
                "modalityContract": "separated_research",
                "quotas": {"entityArticlesPerTarget": 1, "entityHomepagesPerTarget": 1},
            },
        },
    )
    assert any("creatorAssignment.authorId required" in issue for issue in issues), issues
    assert any("creatorAssignment.creatorProfileId required" in issue for issue in issues), issues

def test_content_plan_accepts_off_entity_source_as_multi_tag_work():
    """底稿中心 1:1：实体退化为多标签后，多目的地/弱主体底稿不再被 entity_focus_gate 误杀。

    原 `test_content_plan_blocks_weak_focus_source_unit_as_primary_evidence` 断言 off_entity/weak
    会被弃稿；新模型下文章/图片只来自单一底稿、实体作为标签集合，不应再出现 entity_focus_gate 阻断。
    """
    batch = "off_entity_multi_tag_accept"
    entity = "九寨沟"
    root = batch_root(TASK, batch)
    article_dir = root / "entities/地点/景区/九寨沟/1.download/sources/01.weak_article"
    article_dir.mkdir(parents=True, exist_ok=True)
    article_source = article_dir / "source.md"
    article_source.write_text("四川旅游总览中顺带提到九寨沟，主体篇幅讲成都和川西线路。" * 60, encoding="utf-8")
    write_json(
        article_dir / "meta.json",
        {
            "sourceId": "weak_article",
            "researchLane": "article",
            "sourceRole": "base",
            "sourceUseMode": "factual_reference_only",
            "entityFocusVerdict": "weak",
            "entityFocusScore": 0.15,
        },
    )
    image_dir = root / "entities/地点/景区/九寨沟/1.download/sources/02.weak_image"
    asset_dir = image_dir / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    image_source = image_dir / "source.md"
    image_source.write_text("九寨沟图片页，但主体图片为四川线路集合图。", encoding="utf-8")
    image_file = asset_dir / "weak.jpg"
    image_file.write_bytes(_real_jpeg(33))
    write_json(
        asset_dir / "index.json",
        {
            "assets": [
                {
                    "fileName": image_file.name,
                    "sourceAssetId": "weak_img",
                    "sha256": "sha256:weak-img",
                    "sourceCollectionId": "weak:image",
                    "license": "CC-BY-4.0",
                    "credit": "fixture",
                    "sourceUrl": "https://example.com/weak.jpg",
                    "termsUrl": "https://example.com/terms",
                    "usageScope": "commercial_editorial",
                    "caption": "四川线路集合图",
                    "relevance": "弱相关",
                }
            ]
        },
    )
    write_json(
        image_dir / "meta.json",
        {
            "sourceId": "weak_image",
            "researchLane": "image",
            "sourceCollectionId": "weak:image",
            "entityFocusVerdict": "supporting_only",
        },
    )
    article_ref = f"{entity}_weak_article"
    image_ref = f"{entity}_weak_image"
    for ref, content_type in ((article_ref, "article"), (image_ref, "image")):
        content_object.register_content_object(
            TASK,
            batch,
            ref,
            content_type=content_type,
            angle="攻略" if content_type == "article" else "画报",
            title=ref,
        )
        brief_dir = content_object.content_object_stage_dir(TASK, batch, ref, STAGE_COMPOSE)
        write_json(brief_dir / content_object.BRIEF_FILE, {"titleHint": ref})
    article_source_ref = article_source.relative_to(root).as_posix()
    image_source_ref = image_source.relative_to(root).as_posix()
    image_asset_ref = image_file.relative_to(root).as_posix()
    write_json(
        batch_content_plan_packet_path(TASK, batch),
        {
            "schemaVersion": cp.CONTENT_PLAN_SCHEMA,
            "items": [
                {
                    "ref": article_ref,
                    "kind": "entity",
                    "carrier": "article",
                    "researchLane": "article",
                    "title": "九寨沟弱主体文章",
                    "entityRefs": [f"/entity/地点/景区/{entity}"],
                    "evidenceRefs": [article_source_ref],
                    "rationale": "弱主体网页不应作为 base",
                    "baseSourceRef": article_source_ref,
                    "sourceUseMode": "factual_reference_only",
                },
                {
                    "ref": image_ref,
                    "kind": "entity",
                    "carrier": "image",
                    "researchLane": "image",
                    "title": "九寨沟弱主体图片",
                    "entityRefs": [f"/entity/地点/景区/{entity}"],
                    "evidenceRefs": [image_source_ref],
                    "rationale": "弱主体图片集不应作为图片作品主证据",
                    "assetRefs": [image_asset_ref],
                    "sourceCollectionId": "weak:image",
                },
            ],
        },
    )
    spec = {
        "scope": {"coverageTargets": [{"entityType": "地点/景区", "name": entity}]},
        "content": {
            "modalityContract": "separated_research",
            "quotas": {
                "entityArticlesPerTarget": 1,
                "imageWorksPerTarget": 1,
                "entityHomepagesPerTarget": 0,
                "routeArticles": 0,
            },
        },
    }

    issues = cp.validate_content_plan(TASK, batch, spec)

    # 底稿中心：不得再出现任何 entity_focus_gate 阻断（弱主体/off_entity 仍可成稿，实体作多标签）。
    assert not any("entity_focus_gate" in issue for issue in issues), issues

def test_content_plan_quotas_required_includes_image_works():
    spec = {"content": {"modalityContract": "separated_research", "quotas": {"imageWorksPerTarget": 2}}}
    assert cp.content_plan_quotas_required(spec) is True

def test_content_plan_blocks_base_source_reuse_policy_in_strict_mode():
    batch = "base_source_reuse_policy_disallowed"
    entity = "九寨沟"
    source_dir = (
        batch_root(TASK, batch)
        / "entities/地点/景区/九寨沟/1.download/sources/01.shared_article"
    )
    source_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / "source.md"
    source_path.write_text(
        (
            "九寨沟长篇图文底稿，包含行前交通、沟内动线、旺季预约、季节差异、"
            "拍摄视角和游览节奏判断。"
        )
        * 80,
        encoding="utf-8",
    )
    article_asset = _write_article_source_asset(source_dir, label="jiuzhaigou_shared")
    write_json(
        source_dir / "meta.json",
        {
            "sourceId": "shared_article",
            "sourceUseMode": "factual_reference_only",
            "researchLane": "article",
            "sourceRole": "base",
            "category": "travelogue",
        },
    )
    source_ref = source_path.relative_to(batch_root(TASK, batch)).as_posix()
    items = []
    for index, intent in enumerate(("planning_consultation", "seasonal_timing"), start=1):
        ref = f"{entity}_{intent}"
        title = f"九寨沟{intent}"
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
        item = {
            "ref": ref,
            "kind": "entity",
            "carrier": "article",
            "researchLane": "article",
            "title": title,
            "entityRefs": [f"/entity/地点/景区/{entity}"],
            "evidenceRefs": [source_ref],
            "rationale": f"{intent} 主线证据",
            "writingIntent": intent,
            "baseSourceRef": source_ref,
            "assetRefs": [article_asset.relative_to(batch_root(TASK, batch)).as_posix()],
            "sourceUseMode": "factual_reference_only",
        }
        if index == 2:
            item["baseSourceReusePolicy"] = "multi_intent_source_bundle"
        items.append(item)
    write_json(
        batch_content_plan_packet_path(TASK, batch),
        {"schemaVersion": cp.CONTENT_PLAN_SCHEMA, "items": items},
    )
    spec = {
        "scope": {"coverageTargets": [{"entityType": "地点/景区", "name": entity}]},
        "content": {
            "modalityContract": "separated_research",
            "quotas": {
                "entityArticlesPerTarget": 2,
                "imageWorksPerTarget": 0,
                "entityHomepagesPerTarget": 1,
                "routeArticles": 0,
            },
        },
    }
    issues = cp.validate_content_plan(TASK, batch, spec)
    assert any("baseSourceReusePolicy is not allowed" in issue for issue in issues), issues
    assert any("baseSourceRef reused by" in issue for issue in issues), issues

def test_content_plan_blocks_cross_source_unit_asset_and_records_conflict():
    batch = "cross_source_unit_article_asset"
    entity = "九寨沟"
    ref = f"{entity}_cross_source_unit"
    title = "九寨沟图文同源检查"
    base_dir = (
        batch_root(TASK, batch)
        / "entities/地点/景区/九寨沟/1.download/sources/01.article_base"
    )
    other_dir = (
        batch_root(TASK, batch)
        / "entities/地点/景区/九寨沟/1.download/sources/02.other_page"
    )
    base_dir.mkdir(parents=True, exist_ok=True)
    other_dir.mkdir(parents=True, exist_ok=True)
    base_source = base_dir / "source.md"
    base_source.write_text(
        (
            "九寨沟同一网页底稿，包含游览动线、季节差异、拍摄位置、预约方式和交通建议。"
        )
        * 80,
        encoding="utf-8",
    )
    write_json(
        base_dir / "meta.json",
        {
            "sourceId": "article_base",
            "sourceUseMode": "factual_reference_only",
            "researchLane": "article",
            "sourceRole": "base",
            "category": "travelogue",
        },
    )
    write_json(
        other_dir / "meta.json",
        {
            "sourceId": "other_page",
            "sourceUseMode": "factual_reference_only",
            "researchLane": "article",
            "sourceRole": "base",
            "category": "travelogue",
        },
    )
    other_asset = _write_article_source_asset(other_dir, label="cross_source_unit")
    content_object.register_content_object(
        TASK,
        batch,
        ref,
        content_type="article",
        angle="攻略",
        title=title,
    )
    brief_dir = content_object.content_object_stage_dir(TASK, batch, ref, STAGE_COMPOSE)
    write_json(brief_dir / content_object.BRIEF_FILE, {"titleHint": title, "writingIntent": "planning_consultation"})
    base_ref = base_source.relative_to(batch_root(TASK, batch)).as_posix()
    other_asset_ref = other_asset.relative_to(batch_root(TASK, batch)).as_posix()
    write_json(
        batch_content_plan_packet_path(TASK, batch),
        {
            "schemaVersion": cp.CONTENT_PLAN_SCHEMA,
            "items": [
                {
                    "ref": ref,
                    "kind": "entity",
                    "carrier": "article",
                    "researchLane": "article",
                    "title": title,
                    "entityRefs": [f"/entity/地点/景区/{entity}"],
                    "evidenceRefs": [base_ref],
                    "rationale": "验证同一网页/sourceUnit 原子性",
                    "writingIntent": "planning_consultation",
                    "baseSourceRef": base_ref,
                    "assetRefs": [other_asset_ref],
                    "sourceUseMode": "factual_reference_only",
                }
            ],
        },
    )
    spec = {
        "scope": {"coverageTargets": [{"entityType": "地点/景区", "name": entity}]},
        "content": {"modalityContract": "separated_research", "quotas": {}},
    }

    issues = cp.validate_content_plan(TASK, batch, spec)

    assert any("assetRefs must stay in same sourceUnit as baseSourceRef" in issue for issue in issues), issues
    conflicts = og.read_jsonl(og.conflict_ledger_path(TASK, batch))
    assert conflicts[-1]["conflictType"] == "source_unit_atomicity"
    assert conflicts[-1]["status"] == "pending_reconcile"

def test_content_plan_allows_text_only_article_base_source_without_source_assets():
    batch = "article_base_without_source_assets_text_only"
    entity = "九寨沟"
    ref = f"{entity}_planning_consultation"
    title = "九寨沟行前怎么安排"
    source_dir = (
        batch_root(TASK, batch)
        / "entities/地点/景区/九寨沟/1.download/sources/01.no_image_article"
    )
    source_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / "source.md"
    source_path.write_text(
        (
            "九寨沟长篇图文底稿，覆盖交通方式、沟内换乘、开放时间、季节差异、"
            "拍照点、亲子老人同行和雨雪天气替代安排。"
        )
        * 80,
        encoding="utf-8",
    )
    write_json(
        source_dir / "meta.json",
        {
            "sourceId": "no_image_article",
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
    write_json(brief_dir / content_object.BRIEF_FILE, {"titleHint": title, "writingIntent": "planning_consultation"})
    source_ref = source_path.relative_to(batch_root(TASK, batch)).as_posix()
    write_json(
        batch_content_plan_packet_path(TASK, batch),
        {
            "schemaVersion": cp.CONTENT_PLAN_SCHEMA,
            "items": [
                {
                    "ref": ref,
                    "kind": "entity",
                    "carrier": "article",
                    "researchLane": "article",
                    "title": title,
                    "entityRefs": [f"/entity/地点/景区/{entity}"],
                    "evidenceRefs": [source_ref],
                    "rationale": "优质文字底稿可无源图发布",
                    "writingIntent": "planning_consultation",
                    "baseSourceRef": source_ref,
                    "sourceUseMode": "factual_reference_only",
                    "publishMediaMode": "text_only",
                }
            ],
        },
    )
    spec = {
        "scope": {"coverageTargets": [{"entityType": "地点/景区", "name": entity}]},
        "content": {
            "modalityContract": "separated_research",
            "quotas": {
                "entityArticlesPerTarget": 1,
                "imageWorksPerTarget": 0,
                "entityHomepagesPerTarget": 1,
                "routeArticles": 0,
            },
        },
    }
    issues = cp.validate_content_plan(TASK, batch, spec)
    assert issues == []

def test_content_plan_blocks_declared_article_asset_missing_rights_fields():
    batch = "article_declared_asset_missing_rights"
    entity = "九寨沟"
    ref = f"{entity}_planning_consultation"
    title = "九寨沟行前怎么安排"
    source_dir = (
        batch_root(TASK, batch)
        / "entities/地点/景区/九寨沟/1.download/sources/01.article_with_unlicensed_asset"
    )
    asset_dir = source_dir / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / "source.md"
    source_path.write_text(
        (
            "九寨沟长篇图文底稿，覆盖交通方式、沟内换乘、开放时间、季节差异、"
            "拍照点、亲子老人同行和雨雪天气替代安排。"
        )
        * 80,
        encoding="utf-8",
    )
    asset_path = asset_dir / "source.jpg"
    asset_path.write_bytes(b"fake-image")
    write_json(
        source_dir / "meta.json",
        {
            "sourceId": "article_with_unlicensed_asset",
            "sourceUseMode": "factual_reference_only",
            "researchLane": "article",
            "sourceRole": "base",
            "category": "travelogue",
        },
    )
    write_json(
        asset_dir / "index.json",
        {"assets": [{"fileName": asset_path.name, "sha256": "sha256:test"}]},
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
    write_json(brief_dir / content_object.BRIEF_FILE, {"titleHint": title, "writingIntent": "planning_consultation"})
    source_ref = source_path.relative_to(batch_root(TASK, batch)).as_posix()
    asset_ref = asset_path.relative_to(batch_root(TASK, batch)).as_posix()
    write_json(
        batch_content_plan_packet_path(TASK, batch),
        {
            "schemaVersion": cp.CONTENT_PLAN_SCHEMA,
            "items": [
                {
                    "ref": ref,
                    "kind": "entity",
                    "carrier": "article",
                    "researchLane": "article",
                    "title": title,
                    "entityRefs": [f"/entity/地点/景区/{entity}"],
                    "evidenceRefs": [source_ref],
                    "rationale": "声明源图必须权利完整",
                    "writingIntent": "planning_consultation",
                    "baseSourceRef": source_ref,
                    "assetRefs": [asset_ref],
                    "sourceUseMode": "factual_reference_only",
                }
            ],
        },
    )
    spec = {
        "scope": {"coverageTargets": [{"entityType": "地点/景区", "name": entity}]},
        "content": {
            "modalityContract": "separated_research",
            "quotas": {
                "entityArticlesPerTarget": 1,
                "imageWorksPerTarget": 0,
                "entityHomepagesPerTarget": 1,
                "routeArticles": 0,
            },
        },
    }

    issues = cp.validate_content_plan(TASK, batch, spec)

    assert any("missing rights fields" in issue for issue in issues), issues

def test_content_plan_blocks_oversized_image_asset_refs():
    batch = "image_asset_safety_gate"
    entity = "九寨沟"
    image_source = (
        batch_root(TASK, batch)
        / "entities/地点/景区/九寨沟/1.download/sources/01.image_collection"
    )
    asset_dir = image_source / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    source_path = image_source / "source.md"
    source_path.write_text("九寨沟同一摄影集合，图片底稿。", encoding="utf-8")
    asset_file = asset_dir / "oversized.png"
    asset_file.write_bytes(_oversized_png_header())
    write_json(
        asset_dir / "index.json",
        {"assets": [{"fileName": asset_file.name, "sourceCollectionId": "jiuzhaigou:image:huge"}]},
    )
    write_json(
        image_source / "meta.json",
        {"researchLane": "image", "sourceCollectionId": "jiuzhaigou:image:huge"},
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
    write_json(
        batch_content_plan_packet_path(TASK, batch),
        {
            "schemaVersion": cp.CONTENT_PLAN_SCHEMA,
            "items": [
                {
                    "ref": ref,
                    "kind": "entity",
                    "carrier": "image",
                    "researchLane": "image",
                    "title": "九寨沟图片作品",
                    "entityRefs": [f"/entity/地点/景区/{entity}"],
                    "evidenceRefs": [source_path.relative_to(batch_root(TASK, batch)).as_posix()],
                    "rationale": "同一图片集合证据",
                    "sourceCollectionId": "jiuzhaigou:image:huge",
                    "assetRefs": [asset_file.relative_to(batch_root(TASK, batch)).as_posix()],
                }
            ],
        },
    )
    spec = {
        "scope": {"coverageTargets": [{"entityType": "地点/景区", "name": entity}]},
        "content": {
            "modalityContract": "separated_research",
            "quotas": {
                "entityArticlesPerTarget": 0,
                "imageWorksPerTarget": 1,
                "entityHomepagesPerTarget": 1,
                "routeArticles": 0,
            },
        },
        "acceptance": {"requiredAngles": ["image"]},
    }

    issues = cp.validate_content_plan(TASK, batch, spec)

    assert any("image asset blocked by image safety gate" in issue for issue in issues), issues
    assert any("image_pixels_too_large" in issue for issue in issues), issues

def test_content_plan_blocks_image_work_reusing_article_base_asset():
    batch = "article_image_asset_reuse_gate"
    entity = "九寨沟"
    root = batch_root(TASK, batch)
    article_source = root / "entities/地点/景区/九寨沟/1.download/sources/01.article_base"
    image_source = root / "entities/地点/景区/九寨沟/1.download/sources/02.image_collection"
    shared_bytes = _real_jpeg(91)
    shared_digest = __import__("hashlib").sha256(shared_bytes).hexdigest()
    for source_dir, lane, file_name in [
        (article_source, "article", "article.jpg"),
        (image_source, "image", "image.jpg"),
    ]:
        asset_dir = source_dir / "assets"
        asset_dir.mkdir(parents=True, exist_ok=True)
        (source_dir / "source.md").write_text("九寨沟图文底稿。" * 120, encoding="utf-8")
        (asset_dir / file_name).write_bytes(shared_bytes)
        write_json(
            source_dir / "meta.json",
            {
                "researchLane": lane,
                "sourceRole": "base" if lane == "article" else "",
                "sourceUseMode": "factual_reference_only",
                "category": "travelogue" if lane == "article" else "image_collection",
                "sourceCollectionId": "shared:collection",
            },
        )
        write_json(
            asset_dir / "index.json",
            {
                "assets": [
                    {
                        "fileName": file_name,
                        "sha256": f"sha256:{shared_digest}",
                        "sourceCollectionId": "shared:collection",
                        "caption": "九寨沟共享图",
                        "license": "CC-BY-SA 4.0",
                        "credit": "测试摄影师",
                        "sourceUrl": "https://example.test/shared",
                        "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                        "usageScope": "app_publish",
                    }
                ]
            },
        )
    article_ref = f"{entity}_planning_consultation"
    image_ref = f"{entity}_image"
    for ref, content_type, title in [
        (article_ref, "article", "九寨沟文章"),
        (image_ref, "image", "九寨沟图片"),
    ]:
        content_object.register_content_object(
            TASK,
            batch,
            ref,
            content_type=content_type,
            angle="攻略",
            title=title,
        )
        brief_dir = content_object.content_object_stage_dir(TASK, batch, ref, STAGE_COMPOSE)
        write_json(brief_dir / content_object.BRIEF_FILE, {"titleHint": title})
    article_source_ref = (article_source / "source.md").relative_to(root).as_posix()
    article_asset_ref = (article_source / "assets" / "article.jpg").relative_to(root).as_posix()
    image_source_ref = (image_source / "source.md").relative_to(root).as_posix()
    image_asset_ref = (image_source / "assets" / "image.jpg").relative_to(root).as_posix()
    write_json(
        batch_content_plan_packet_path(TASK, batch),
        {
            "schemaVersion": cp.CONTENT_PLAN_SCHEMA,
            "items": [
                {
                    "ref": article_ref,
                    "kind": "entity",
                    "carrier": "article",
                    "researchLane": "article",
                    "title": "九寨沟文章",
                    "entityRefs": [f"/entity/地点/景区/{entity}"],
                    "evidenceRefs": [article_source_ref],
                    "rationale": "文章底稿",
                        "writingIntent": "planning_consultation",
                        "baseSourceRef": article_source_ref,
                        "assetRefs": [article_asset_ref],
                        "sourceUseMode": "factual_reference_only",
                    },
                {
                    "ref": image_ref,
                    "kind": "entity",
                    "carrier": "image",
                    "researchLane": "image",
                    "title": "九寨沟图片",
                    "entityRefs": [f"/entity/地点/景区/{entity}"],
                    "evidenceRefs": [image_source_ref],
                    "rationale": "图片作品",
                    "sourceCollectionId": "shared:collection",
                    "assetRefs": [image_asset_ref],
                },
            ],
        },
    )
    spec = {
        "scope": {"coverageTargets": [{"entityType": "地点/景区", "name": entity}]},
        "content": {
            "modalityContract": "separated_research",
            "quotas": {
                "entityArticlesPerTarget": 1,
                "imageWorksPerTarget": 1,
                "entityHomepagesPerTarget": 1,
                "routeArticles": 0,
            },
        },
        "acceptance": {"requiredAngles": ["planning_consultation", "image"]},
    }

    issues = cp.validate_content_plan(TASK, batch, spec)

    assert any("image sha256" in issue and "reused" in issue for issue in issues), issues
    assert any("sourceCollectionId" in issue and "reused" in issue for issue in issues), issues

