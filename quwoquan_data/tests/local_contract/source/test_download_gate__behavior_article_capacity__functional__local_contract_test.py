"""场景组：download gate article capacity 质量收据与 shortfall 吸收。

download gate 契约测试（对象优先）。

从 test_download_gate__behavior__functional__local_contract_test.py
按场景拆出；测试逐字搬移。
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from content.execution.context import ExecutionContext
from content.execution.controller.content_plan_prep import (
    _content_capacity_gate_for_entity,
)
from content.execution.controller.stage_download_build import (
    _run_download_fetch,
)
from content.execution.recovery.download_freshness import (
    _resolve_download_content_capacity_shortfall,
)
from content.execution.recovery.download_unresolved import (
    absorb_download_shortfall_if_any_ready,
)
from content.source.source_unit import (
    iter_source_units,
    write_source_unit,
)
from core.control_types import ExecutionStage, StageKind, StageStatus
from core.data_issue import (
    DataIssueCode,
    DataIssueLane,
    DataIssueStage,
    DataRecoveryAction,
    data_issue,
)
from core.io import read_json, write_json
from core.paths import (
    execution_entity_object_dir,
    execution_root,
)
from support.article_source_registry_fixture import (
    ARTICLE_SOURCE_UNIT_IDENTITY,
    article_source_registry_binding,
)
from support.download_gate_fixture import (
    ARTICLE_TASK,
    _clean_execution_root,
)
from support.execution_manifest_fixture import ExecutionFixtureBuilder
from support.image_fixture import jpeg_bytes


def test_article_capacity_requires_quality_receipts_not_rejects_cache_or_manual_probes():
    entity = "文章来源景区"
    fixture = ExecutionFixtureBuilder(
        ARTICLE_TASK,
        targets=({"entityType": "地点/景区", "name": entity},),
    )
    fixture.build()
    entity_dir = execution_entity_object_dir(ARTICLE_TASK, "地点", "景区", entity)
    body = f"# {entity}\n\n" + (f"{entity} 的旅行正文。 " * 400)
    for ordinal, source_id, quality in (
        (1, "article_rejected", {"sourceId": "article_rejected", "quality": "Reject", "score": 0}),
        (
            2,
            "article_cached",
            {
                "sourceId": "article_cached",
                "quality": "A-story",
                "score": 9,
                "retainedFromCache": True,
            },
        ),
        (3, "article_manual", {"sourceId": "article_manual", "quality": "A-story", "score": 9}),
    ):
        write_source_unit(
            entity_dir,
            ordinal=ordinal,
            source_id=source_id,
            source_md=body,
            quality=quality,
            platform="旅行平台",
            source_category="travelogue",
            source_role="base",
            research_lane="article",
            url=f"https://example.com/{source_id}",
            title=f"{entity}游记{ordinal}",
            target_ref=f"/entity/地点/景区/{entity}",
            publish_media_mode="text_only",
            **ARTICLE_SOURCE_UNIT_IDENTITY,
            source=article_source_registry_binding(
                platform="旅行平台",
                url=f"https://example.com/{source_id}",
            ),
        )
    manual_unit = next(
        unit
        for unit in iter_source_units(entity_dir)
        if read_json(unit / "meta.json").get("sourceId") == "article_manual"
    )
    manual_meta = read_json(manual_unit / "meta.json")
    manual_meta["manualProbe"] = True
    write_json(manual_unit / "meta.json", manual_meta)
    context = ExecutionContext(
        execution_id=ARTICLE_TASK,
        entity_ids=(entity,),
        spec=fixture.spec(),
    )

    passed, issues, diagnostics = _content_capacity_gate_for_entity(context, entity)

    assert not passed
    assert any("article base source shortfall" in issue for issue in issues)
    assert diagnostics["entityType"] == "地点/景区"
    assert diagnostics["qualifiedArticleBaseSources"] == 0
    assert diagnostics["articleSourceClosure"] == []
    assert diagnostics["articleRejects"] == {
        "manual_probe": 1,
        "quality_rejected": 1,
        "retained_from_cache": 1,
    }


def test_article_capacity_excludes_broad_city_page_and_keeps_direct_entity_source():
    entity = "杭州宋城"
    fixture = ExecutionFixtureBuilder(
        ARTICLE_TASK,
        targets=(
            {
                "entityType": "地点/主题乐园",
                "name": entity,
                "aliases": ["宋城", "杭州宋城景区"],
            },
        ),
    )
    fixture.build()
    entity_dir = execution_entity_object_dir(
        ARTICLE_TASK,
        "地点",
        "主题乐园",
        entity,
    )
    # 本用例断言的是容量判定（宽泛城市页 vs 直接实体页），来源身份只需可归因即可。
    # article lane 的 sourceAttribution 必须解析到已登记来源，商用游记站点尚未登记，
    # 所以这里用与 G1 实际入库文章相同的百科身份，避免 fixture 先撞归因门。
    article_source_contract = {
        "articleSiteId": "wikipedia_zh",
        "sourceDiscoveryProfileDigest": "sha256:" + "a" * 64,
        "articleCommercialAdmission": "commercial_release",
    }
    write_source_unit(
        entity_dir,
        ordinal=1,
        source_id="broad_hangzhou_overview",
        source_md=("西湖、运河、街区与博物馆构成杭州旅游主体。" * 120)
        + "杭州宋城是之江片区的一处主题项目。",
        quality={
            "sourceId": "broad_hangzhou_overview",
            "quality": "A-story",
            "score": 9,
        },
        platform="旅行平台",
        source_category="encyclopedia",
        source_kind="encyclopedia",
        extractor="wikipedia_api",
        policy_revision="article-source-registry-v1",
        source_use_mode="factual_reference_only",
        rights_mode="factual_reference_only",
        publish_media_mode="text_only",
        source_role="base",
        research_lane="article",
        url="https://example.com/hangzhou",
        title="杭州旅游",
        target_ref=f"/entity/地点/主题乐园/{entity}",
        source=article_source_contract,
    )
    write_source_unit(
        entity_dir,
        ordinal=2,
        source_id="direct_songcheng",
        source_md=(
            "宋城位于杭州之江片区。宋城的主题街区与演艺空间共同组织游览，"
            "杭州宋城的正文主线始终围绕园区展开。"
        )
        * 50,
        quality={
            "sourceId": "direct_songcheng",
            "quality": "B-fact",
            "score": 4,
        },
        platform="旅行平台",
        source_category="encyclopedia",
        source_kind="encyclopedia",
        extractor="wikipedia_api",
        policy_revision="article-source-registry-v1",
        source_use_mode="factual_reference_only",
        rights_mode="factual_reference_only",
        publish_media_mode="text_only",
        source_role="base",
        research_lane="article",
        url="https://example.com/songcheng",
        title="宋城",
        target_ref=f"/entity/地点/主题乐园/{entity}",
        source=article_source_contract,
    )
    context = ExecutionContext(
        execution_id=ARTICLE_TASK,
        entity_ids=(entity,),
        spec=fixture.spec(),
    )

    passed, issues, diagnostics = _content_capacity_gate_for_entity(
        context,
        entity,
    )

    assert passed, issues
    assert diagnostics["qualifiedArticleBaseSources"] == 1
    assert diagnostics["pickedArticleBaseSources"] == 1
    assert diagnostics["articleRejects"]["entity_anchor_mismatch"] == 1
    assert diagnostics["articleSourceClosure"][0]["sourceId"] == "direct_songcheng"


def _write_article_capacity_source_with_two_images(
    entity_dir: Path,
    entity: str,
    *,
    ordinal: int = 1,
    source_id: str = "article_two_images",
    seeds: tuple[int, int] = (31, 32),
) -> None:
    body = f"# {entity}实地游览\n\n" + (f"{entity} 的旅行正文与现场观察。 " * 400)
    images = [
        {
            "bytes": jpeg_bytes(seed=seed),
            "ext": ".jpg",
            "slug": role,
            "url": f"https://example.com/{entity}/{role}.jpg",
            "sourceUrl": f"https://example.com/{entity}/{role}.jpg",
            "caption": f"{entity} {role} 实景",
            "relevance": f"画面直接呈现{entity} {role} 实景",
            "visualSubject": entity,
            "pageResolvedTitle": entity,
            "sourceCollectionId": f"{entity}-{role}",
        }
        for seed, role in zip(seeds, ("cover", "body"), strict=True)
    ]
    write_source_unit(
        entity_dir,
        ordinal=ordinal,
        source_id=source_id,
        source_md=body,
        quality={
            "sourceId": source_id,
            "quality": "A-story",
            "score": 9,
        },
        platform="旅行平台",
        source_category="travelogue",
        source_role="base",
        research_lane="article",
        publish_media_mode="illustrated",
        url=f"https://example.com/{entity}/article",
        title=f"{entity}实地游览",
        target_ref=f"/entity/地点/景区/{entity}",
        images=images,
        execution_id=ARTICLE_TASK,
        build_variants=False,
        **ARTICLE_SOURCE_UNIT_IDENTITY,
        source=article_source_registry_binding(
            platform="旅行平台",
            url=f"https://example.com/{entity}/article",
        ),
    )


def test_article_capacity_keeps_quality_body_as_text_only_when_images_duplicate(
    monkeypatch,
):
    from content.execution.controller import content_plan_assets

    entity = "重复图片景区"
    fixture = ExecutionFixtureBuilder(
        ARTICLE_TASK,
        targets=({"entityType": "地点/景区", "name": entity},),
    )
    fixture.build()
    entity_dir = execution_entity_object_dir(ARTICLE_TASK, "地点", "景区", entity)
    _write_article_capacity_source_with_two_images(entity_dir, entity)
    monkeypatch.setattr(
        content_plan_assets,
        "_canonical_image_asset_issue",
        lambda _source_dir, row: (
            "canonical image identity duplicated"
            if "cover" in str(row.get("fileName") or "")
            else ""
        ),
    )
    monkeypatch.setattr(
        content_plan_assets,
        "_assess_content_plan_publish_image",
        lambda *_args: SimpleNamespace(blocks_image_publish=False),
    )
    context = ExecutionContext(
        execution_id=ARTICLE_TASK,
        entity_ids=(entity,),
        spec=fixture.spec(),
    )

    passed, issues, diagnostics = _content_capacity_gate_for_entity(context, entity)

    assert passed, issues
    assert diagnostics["qualifiedArticleBaseSources"] == 1
    assert diagnostics["pickedArticleBaseSources"] == 1
    assert diagnostics["articleRejects"] == {}
    assert diagnostics["articleImageSoftWarnings"]["no_publishable_source_asset"] == 1


def test_download_fetch_resume_keeps_text_only_article_ready_when_images_duplicate(
    monkeypatch,
):
    from content.execution.controller import content_plan_assets
    from content.execution.recovery import download_unresolved

    entity = "恢复容量景区"
    fixture = ExecutionFixtureBuilder(
        ARTICLE_TASK,
        targets=({"entityType": "地点/景区", "name": entity},),
        approved_quota=1,
    )
    fixture.build()
    entity_dir = execution_entity_object_dir(ARTICLE_TASK, "地点", "景区", entity)
    _write_article_capacity_source_with_two_images(entity_dir, entity)
    monkeypatch.setattr(
        download_unresolved,
        "_write_download_availability",
        lambda *_args, **_kwargs: {
            "readyTargets": [entity],
            "readyTargetCount": 1,
            "ineligibleTargets": [],
            "ineligibleTargetCount": 0,
        },
    )
    monkeypatch.setattr(
        content_plan_assets,
        "_canonical_image_asset_issue",
        lambda source_dir, row: (
            "canonical image identity duplicated"
            if read_json(source_dir / "meta.json").get("sourceId")
            == "article_two_images"
            and "cover" in str(row.get("fileName") or "")
            else ""
        ),
    )
    monkeypatch.setattr(
        content_plan_assets,
        "_assess_content_plan_publish_image",
        lambda *_args: SimpleNamespace(blocks_image_publish=False),
    )
    context = ExecutionContext(
        execution_id=ARTICLE_TASK,
        entity_ids=(entity,),
        spec=fixture.spec(),
    )

    first = _run_download_fetch(context)
    resumed = _run_download_fetch(context)

    for result in (first, resumed):
        assert result.status is StageStatus.DONE

    _write_article_capacity_source_with_two_images(
        entity_dir,
        entity,
        ordinal=2,
        source_id="article_new_two_images",
        seeds=(41, 42),
    )

    passed, issues, diagnostics = _content_capacity_gate_for_entity(context, entity)
    recovered = _run_download_fetch(context)

    assert passed, issues
    assert diagnostics["pickedArticleBaseSources"] == 1
    assert recovered.status is StageStatus.DONE
    assert "ready=1/quota=1" in recovered.message


def test_article_capacity_keeps_quality_body_as_text_only_when_one_image_is_unsafe(
    monkeypatch,
):
    from content.execution.controller import content_plan_assets

    entity = "安全图片景区"
    fixture = ExecutionFixtureBuilder(
        ARTICLE_TASK,
        targets=({"entityType": "地点/景区", "name": entity},),
    )
    fixture.build()
    entity_dir = execution_entity_object_dir(ARTICLE_TASK, "地点", "景区", entity)
    _write_article_capacity_source_with_two_images(entity_dir, entity)
    monkeypatch.setattr(
        content_plan_assets,
        "_canonical_image_asset_issue",
        lambda *_args: "",
    )
    monkeypatch.setattr(
        content_plan_assets,
        "_assess_content_plan_publish_image",
        lambda asset_path, _ctx: SimpleNamespace(
            blocks_image_publish="body" in asset_path.name
        ),
    )
    context = ExecutionContext(
        execution_id=ARTICLE_TASK,
        entity_ids=(entity,),
        spec=fixture.spec(),
    )

    passed, issues, diagnostics = _content_capacity_gate_for_entity(context, entity)

    assert passed, issues
    assert diagnostics["qualifiedArticleBaseSources"] == 1
    assert diagnostics["pickedArticleBaseSources"] == 1
    assert diagnostics["articleRejects"] == {}
    assert diagnostics["articleImageSoftWarnings"]["no_publishable_source_asset"] == 1


def test_article_source_shortfall_is_absorbed_when_any_object_is_ready():
    entity = "文章短缺景区"
    fixture = ExecutionFixtureBuilder(
        ARTICLE_TASK,
        targets=(
            {"entityType": "地点/景区", "name": entity},
            {"entityType": "地点/遗址", "name": "文章短缺遗址"},
        ),
        approved_quota=1,
    )
    fixture.build()
    context = ExecutionContext(
        execution_id=ARTICLE_TASK,
        entity_ids=(entity, "文章短缺遗址"),
        spec=fixture.spec(),
    )

    absorbed = absorb_download_shortfall_if_any_ready(
        context,
        {"readyTargetCount": 1, "ineligibleTargetCount": 1},
        stage=DataIssueStage.DOWNLOAD_FETCH,
        stage_enum=ExecutionStage.DOWNLOAD_FETCH,
        auto_mode=StageKind.AUTO,
        done_status=StageStatus.DONE,
    )

    assert absorbed is not None
    assert absorbed.status is StageStatus.DONE


def test_download_shortfall_blocks_when_zero_objects_are_ready():
    entity = "全量缺源景区"
    fixture = ExecutionFixtureBuilder(
        ARTICLE_TASK,
        targets=({"entityType": "地点/景区", "name": entity},),
        approved_quota=1,
    )
    fixture.build()
    context = ExecutionContext(
        execution_id=ARTICLE_TASK,
        entity_ids=(entity,),
        spec=fixture.spec(),
    )

    absorbed = absorb_download_shortfall_if_any_ready(
        context,
        {"readyTargetCount": 0, "ineligibleTargetCount": 1},
        stage=DataIssueStage.DOWNLOAD_FETCH,
        stage_enum=ExecutionStage.DOWNLOAD_FETCH,
        auto_mode=StageKind.AUTO,
        done_status=StageStatus.DONE,
    )

    assert absorbed is None


def test_article_capacity_shortfall_discards_only_failed_object():
    ready_entity = "合格攻略景区"
    short_entity = "短正文景区"
    fixture = ExecutionFixtureBuilder(
        ARTICLE_TASK,
        targets=(
            {"entityType": "地点/景区", "name": ready_entity},
            {"entityType": "地点/景区", "name": short_entity},
        ),
        approved_quota=2,
    )
    fixture.build()
    context = ExecutionContext(
        execution_id=ARTICLE_TASK,
        entity_ids=(ready_entity, short_entity),
        spec=fixture.spec(),
    )
    issue = data_issue(
        DataIssueCode.SOURCE_RETAINED_SHORTFALL,
        stage=DataIssueStage.DOWNLOAD_FETCH,
        ref=short_entity,
        lane=DataIssueLane.ARTICLE,
        recovery=DataRecoveryAction.STOP,
        message="qualified article base sources 0 < 1",
    )

    result = _resolve_download_content_capacity_shortfall(context, [issue])
    availability = read_json(
        execution_root(ARTICLE_TASK)
        / "_shared"
        / "source_unavailable_targets.json"
    )

    assert result is not None
    assert result.status is StageStatus.DONE
    assert availability["readyTargets"] == [ready_entity]
    assert availability["ineligibleTargetCount"] == 1
    assert availability["ineligibleTargets"][0]["entityId"] == short_entity
    assert availability["ineligibleTargets"][0]["lanes"] == ["article"]
    assert availability["ineligibleTargets"][0]["blockers"] == [issue.as_dict()]
