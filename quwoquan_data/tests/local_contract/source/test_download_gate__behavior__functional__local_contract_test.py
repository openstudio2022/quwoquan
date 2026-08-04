"""download gate 契约测试（对象优先）。"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import os
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(SCRIPTS_ROOT))


from core.paths import (  # noqa: E402
    execution_command_root,
    execution_entity_object_dir,
    execution_root,
    ensure_execution_layout,
)
from core.io import read_json, write_json  # noqa: E402
from core.data_issue import (  # noqa: E402
    DataIssueCode,
    DataIssueStage,
    DataIssueLane,
    DataRecoveryAction,
    data_issue,
)
from core.control_types import ExecutionStage, StageKind, StageStatus  # noqa: E402
from core.article_package import sha256_text  # noqa: E402
from content.source.source_unit import iter_source_units, write_source_unit  # noqa: E402
from content.source.source_inputs import curated_sources_for_entity  # noqa: E402
from content.source.gate import (  # noqa: E402
    DownloadRequirements,
    download_requirements,
    gate_download,
)
from content.execution.recovery.download_gate import _download_repair_active_issues  # noqa: E402
from content.execution.recovery.download_repair import _record_download_repair  # noqa: E402
from content.execution.recovery.download_research_gate import _download_research_lane_issues  # noqa: E402
from content.execution.recovery.download_unresolved import absorb_download_shortfall_if_quota_met  # noqa: E402
from content.execution.controller.content_plan_prep import _content_capacity_gate_for_entity  # noqa: E402
from content.execution.context import ExecutionContext  # noqa: E402
from support.execution_manifest_fixture import ExecutionFixtureBuilder  # noqa: E402
from support.image_fixture import jpeg_bytes  # noqa: E402

TASK = "20260711--travel-homepage-download-gate--test-region-b--pilot-001"
VIDEO_TASK = "20260711--travel-video-download-gate--test-region-b--pilot-001"
ARTICLE_TASK = "20260711--travel-article-download-gate--test-region-b--pilot-001"


@pytest.fixture(autouse=True)
def _clean_execution_root():
    shutil.rmtree(execution_root(TASK), ignore_errors=True)
    shutil.rmtree(execution_root(ARTICLE_TASK), ignore_errors=True)
    ExecutionFixtureBuilder(TASK).build()
    yield
    shutil.rmtree(execution_root(TASK), ignore_errors=True)
    shutil.rmtree(execution_root(ARTICLE_TASK), ignore_errors=True)


def test_homepage_only_download_requires_one_verified_text_source(monkeypatch):
    monkeypatch.setattr(
        "content.execution.store.load_spec_model",
        lambda _execution_id: ExecutionFixtureBuilder(TASK).spec(),
    )

    requirements = download_requirements(TASK)

    assert requirements.min_sources == 1
    assert requirements.min_homepage_sources == 1
    assert requirements.min_homepage_media == 0
    assert requirements.min_article_base_sources == 0


def test_homepage_low_resolution_candidate_does_not_invalidate_text_source():
    entity = "测试实体甲"
    fixture = ExecutionFixtureBuilder(TASK)
    obj = execution_entity_object_dir(TASK, "地点", "景区", entity)
    write_json(
        obj / "1.download" / "homepage_source_plan.json",
        {
            "payload": {
                "sources": [
                    {
                        "source_id": "home_wikipedia",
                        "sourceKind": "wikipedia",
                        "platform": "维基百科",
                        "category": "encyclopedia",
                        "sourceRole": "primary",
                        "url": "https://zh.wikipedia.org/wiki/test-entity-a",
                        "extractor": "wikipedia_api",
                        "policyRevision": "encyclopedia-primary",
                        "imageUrls": [
                            {
                                "url": "https://upload.wikimedia.org/test-small.jpg",
                                "width": 320,
                                "height": 240,
                                "caption": entity,
                            }
                        ],
                    }
                ]
            }
        },
    )
    context = ExecutionContext(
        execution_id=TASK,
        entity_ids=(entity,),
        spec=fixture.spec(),
    )

    assert _download_research_lane_issues(
        context,
        entity,
        "地点/景区",
        "homepage",
    ) == []


def test_video_download_does_not_accept_image_quota_as_video_supply(monkeypatch):
    fixture = ExecutionFixtureBuilder(VIDEO_TASK)
    monkeypatch.setattr(
        "content.execution.store.load_spec_model",
        lambda _execution_id: fixture.spec(),
    )

    requirements = download_requirements(VIDEO_TASK)

    assert requirements.min_images == 0
    assert not hasattr(requirements, "min_video_frames")


def test_download_repair_active_issues_only_decodes_typed_records():
    issue = data_issue(
        DataIssueCode.SOURCE_RETAINED_SHORTFALL,
        stage=DataIssueStage.DOWNLOAD_FETCH,
        ref="测试实体甲",
        lane=DataIssueLane.HOMEPAGE,
        recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
        message="retained source requirement is not met",
    )
    ctx = SimpleNamespace(entity_ids=["测试实体甲"])

    assert _download_repair_active_issues(
        ctx,
        {"entityId": "测试实体甲", "issueRecords": [issue.as_dict()]},
    ) == [str(issue)]

    with pytest.raises(ValueError, match="typed issueRecords"):
        _download_repair_active_issues(
            ctx,
            {"entityId": "测试实体甲", "issues": ["legacy message-only issue"]},
        )


def test_download_repair_uses_each_target_canonical_entity_type():
    entity = "刘基庙"
    shutil.rmtree(execution_root(TASK), ignore_errors=True)
    fixture = ExecutionFixtureBuilder(
        TASK,
        targets=(
            {"entityType": "地点/景区", "name": "测试景区"},
            {"entityType": "地点/遗址", "name": entity},
        ),
    )
    fixture.build()
    plan = (
        execution_entity_object_dir(TASK, "地点", "遗址", entity)
        / "1.download"
        / "homepage_source_plan.json"
    )
    write_json(plan, {"payload": {"entityId": entity, "sources": []}})
    issue = data_issue(
        DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING,
        stage=DataIssueStage.DOWNLOAD_FETCH,
        ref=entity,
        lane=DataIssueLane.HOMEPAGE,
        recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
        message="homepage primary authority source is missing",
    )

    packet_path = _record_download_repair(
        ExecutionContext(
            execution_id=TASK,
            entity_ids=(entity,),
            spec=fixture.spec(),
        ),
        [issue],
    )

    repair = read_json(packet_path)["entities"][0]
    assert Path(repair["sourcePlanPath"]) == plan
    assert all("/地点/遗址/刘基庙/" in path for path in repair["sourcePlanPaths"])


def _attach_image(unit_dir: Path, name: str) -> None:
    target_unit = unit_dir
    if unit_dir.parent.name == "sources" and unit_dir.parent.parent.name == "1.download":
        object_dir = unit_dir.parent.parent.parent
        ordinal_text, _, source_id = unit_dir.name.partition(".")
        for candidate in iter_source_units(object_dir):
            try:
                meta = __import__("json").loads((candidate / "meta.json").read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if str(meta.get("sourceId") or "") == source_id and int(meta.get("ordinal") or 0) == int(ordinal_text or 0):
                target_unit = candidate
                break
    assets = target_unit / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    image = assets / f"{name}.jpg"
    image.write_bytes(b"fake-image")
    write_json(
        assets / "index.json",
        {
            "assets": [
                {
                    "fileName": image.name,
                    "sourceAssetId": name,
                    "sha256": f"sha256:{name}",
                    "license": "CC-BY-4.0",
                    "credit": "fixture",
                    "sourceUrl": "https://example.com/image.jpg",
                    "termsUrl": "https://example.com/terms",
                    "usageScope": "commercial_editorial",
                    "rightsAuditStatus": "verified",
                }
            ]
        },
    )


def _write_verified_homepage_source(
    entity_dir: Path,
    *,
    entity_name: str,
    source_id: str,
    asset_name: str,
    source_title: str | None = None,
    qualified_authority_title: str = "",
) -> None:
    source_payload = (
        {"qualifiedAuthorityTitle": qualified_authority_title}
        if qualified_authority_title
        else None
    )
    write_source_unit(
        entity_dir,
        ordinal=1,
        source_id=source_id,
        source_md=(
            f"# {entity_name}\n\n{entity_name}位于test-region-b。"
            f"{entity_name}主峰海拔三千余米。"
            f"{entity_name}是中国著名山岳景区。"
            f"{entity_name}景区包括多条登山步道。"
            f"{entity_name}始建于2001年，保护范围覆盖核心山体与历史建筑。"
            f"{entity_name}每日开放，游客可通过预约渠道进入主要游览区域。"
            f"{entity_name}设有服务中心、公共停车场和交通接驳设施。"
            f"{entity_name}管理方持续巡检步道、观景平台与服务设施，并公布季节开放信息。"
            f"{entity_name}周边保留多处历史遗址、自然植被与传统村落，形成连续游览空间。"
            f"{entity_name}管理机构设置分时客流引导、无障碍通道和环境保护巡查制度。"
            f"{entity_name}通过步行线路、观景节点和公共标识连接主要景观与服务区域。"
            f"{entity_name}每年结合气候条件发布安全提示，并维护交通接驳和游客咨询服务。"
            f"{entity_name}按照承载能力安排分时游览，定期检查山体、栈道和公共设施的安全状况。"
            f"{entity_name}在主要入口提供导览信息、应急联络和文明游览提示，帮助游客规划行程。"
            f"{entity_name}周边公共交通覆盖主要到达点，景区在节假日实施客流疏导与秩序维护。"
        ),
        quality={"sourceId": source_id, "quality": "B-fact", "score": 5},
        platform="Wikipedia",
        source_category="encyclopedia",
        source_kind="wikipedia",
        extractor="wikipedia_api",
        policy_revision="encyclopedia-primary",
        source_role="primary",
        research_lane="homepage",
        url=f"https://zh.wikipedia.org/wiki/{entity_name}",
        title=source_title or entity_name,
        target_ref=f"/entity/地点/景区/{entity_name}",
        source=source_payload,
    )
    _attach_image(entity_dir / f"1.download/sources/01.{source_id}", asset_name)


def test_gate_download_passes_object_first_sources():
    ensure_execution_layout(TASK)
    entity_dir = execution_entity_object_dir(TASK, "地点", "景区", "峨眉山")
    _write_verified_homepage_source(
        entity_dir,
        entity_name="峨眉山",
        source_id="overview_baike",
        asset_name="emei_1",
    )
    write_source_unit(
        entity_dir,
        ordinal=2,
        source_id="travel_notes",
        source_md="# 峨眉山\n\n游记",
        quality={"sourceId": "travel_notes", "quality": "A-story", "score": 8},
        platform="travelogue",
        source_category="travelogue",
        url="https://example.com/2",
        title="峨眉山（游记）",
        target_ref="/entity/地点/景区/峨眉山",
    )
    _attach_image(entity_dir / "1.download/sources/02.travel_notes", "emei_2")
    issues = gate_download(TASK)
    assert issues == [], issues
    assert (execution_root(TASK) / "entities").is_dir()


def test_gate_download_accepts_frozen_authority_title_alias():
    """Frozen selection and downloaded source units must use one authority binding."""
    ensure_execution_layout(TASK)
    entity_dir = execution_entity_object_dir(TASK, "地点", "打卡地", "嘉兴梅湾街")
    _write_verified_homepage_source(
        entity_dir,
        entity_name="嘉兴梅湾街",
        source_id="home_wikipedia",
        asset_name="meiwan_1",
        source_title="梅湾街",
        qualified_authority_title="梅湾街",
    )

    issues = gate_download(TASK)

    assert issues == [], issues


def test_frozen_authority_title_survives_plan_to_source_unit_projection():
    """The bound authority title must survive the actual plan-to-unit adapter."""
    ensure_execution_layout(TASK)
    entity_dir = execution_entity_object_dir(TASK, "地点", "打卡地", "嘉兴梅湾街")
    plan_path = entity_dir / "1.download" / "homepage_source_plan.json"
    write_json(
        plan_path,
        {
            "sources": [
                {
                    "source_id": "home_wikipedia",
                    "platform": "维基百科",
                    "url": "https://zh.wikipedia.org/wiki/%E6%A2%85%E6%B9%BE%E8%A1%97",
                    "sourceKind": "wikipedia",
                    "sourceTitle": "梅湾街",
                    "qualifiedAuthorityTitle": "梅湾街",
                    "extractor": "wikipedia_api",
                    "policyRevision": "encyclopedia-primary",
                    "category": "encyclopedia",
                    "sourceRole": "primary",
                }
            ]
        },
    )

    sources = curated_sources_for_entity(
        TASK,
        "嘉兴梅湾街",
        "地点/打卡地",
        research_lane="homepage",
    )

    assert sources[0]["qualifiedAuthorityTitle"] == "梅湾街"
    manifest = write_source_unit(
        entity_dir,
        ordinal=1,
        source_id="home_wikipedia",
        source_md="# 梅湾街\n\n梅湾街位于嘉兴市，是当地历史街区。",
        quality={"sourceId": "home_wikipedia", "quality": "B-fact", "score": 5},
        platform="Wikipedia",
        source_category="encyclopedia",
        source_kind="wikipedia",
        extractor="wikipedia_api",
        policy_revision="encyclopedia-primary",
        research_lane="homepage",
        url=sources[0]["url"],
        title="梅湾街",
        target_ref="/entity/地点/打卡地/嘉兴梅湾街",
        source=sources[0],
    )
    assert manifest["qualifiedAuthorityTitle"] == "梅湾街"


def test_commercial_article_binding_survives_plan_to_fetch_projection():
    """Fetch must revalidate the exact frontier profile frozen by research."""
    ensure_execution_layout(TASK)
    entity_dir = execution_entity_object_dir(TASK, "地点", "景区", "峨眉山")
    plan_path = entity_dir / "1.download" / "article_source_plan.json"
    profile_digest = sha256_text("article frontier profile fixture")
    write_json(
        plan_path,
        {
            "sources": [
                {
                    "source_id": "article_frontier_wikivoyage",
                    "platform": "维基导游",
                    "url": "https://zh.wikivoyage.org/wiki/%E5%B3%A8%E7%9C%89%E5%B1%B1",
                    "sourceUseMode": "factual_reference_only",
                    "publishMediaMode": "illustrated",
                    "category": "travelogue",
                    "sourceRole": "base",
                    "imageEvidenceMode": "same_source",
                    "articleCommercialAdmission": "commercial_release",
                    "articleSiteId": "wikivoyage_zh",
                    "sourceDiscoveryProfileDigest": profile_digest,
                    "candidateGate": {"passed": True, "issues": []},
                }
            ]
        },
    )

    sources = curated_sources_for_entity(
        TASK,
        "峨眉山",
        "地点/景区",
        research_lane="article",
    )

    assert sources[0]["publishMediaMode"] == "illustrated"
    assert sources[0]["articleCommercialAdmission"] == "commercial_release"
    assert sources[0]["articleSiteId"] == "wikivoyage_zh"
    assert sources[0]["sourceDiscoveryProfileDigest"] == profile_digest


def test_image_collection_source_catalog_accepts_attribution_contract():

    ensure_execution_layout(TASK)
    entity_dir = execution_entity_object_dir(TASK, "地点", "景区", "乐山大佛")

    manifest = write_source_unit(
        entity_dir,
        ordinal=1,
        source_id="image_collection_1",
        source_md="# 乐山大佛\n\n清权图片来源集合。",
        quality={"sourceId": "image_collection_1", "quality": "B-fact", "score": 1},
        platform="Wikimedia Commons",
        source_category="image_collection",
        source_kind="image_collection",
        extractor="image_collection_download",
        policy_revision="image-collection-attribution",
        source_use_mode="licensed_adaptation",
        research_lane="image",
        license_value="CC BY 4.0",
        url="https://commons.wikimedia.org/wiki/File:Leshan_Giant_Buddha.jpg",
        title="乐山大佛",
        target_ref="/entity/地点/景区/乐山大佛",
        images=[
            {
                "bytes": jpeg_bytes(),
                "url": "https://upload.wikimedia.org/wikipedia/commons/example.jpg",
                "sourceUrl": "https://commons.wikimedia.org/wiki/File:Leshan_Giant_Buddha.jpg",
                "collectionPageUrl": "https://commons.wikimedia.org/wiki/File:Leshan_Giant_Buddha.jpg",
                "license": "CC BY 4.0",
                "credit": "Example photographer",
                "creator": "Example photographer",
                "termsUrl": "https://creativecommons.org/licenses/by/4.0/",
                "authorizationProof": "https://commons.wikimedia.org/wiki/File:Leshan_Giant_Buddha.jpg",
                "usageScope": "app_publish",
                "caption": "乐山大佛",
                "relevance": "乐山大佛",
            }
        ],
        execution_id=TASK,
        build_variants=False,
    )

    assert manifest["researchLane"] == "image"
    assert manifest["hasVideo"] is False
    assert manifest["sourceKind"] == "image_collection"
    assert manifest["assetCount"] == 1


def test_gate_download_blocks_single_source_unit():
    ensure_execution_layout(TASK)
    entity_dir = execution_entity_object_dir(TASK, "地点", "景区", "乐山大佛")
    write_source_unit(
        entity_dir,
        ordinal=1,
        source_id="overview_baike",
        source_md="# 乐山大佛\n\n概述",
        quality={"sourceId": "overview_baike", "quality": "B-fact", "score": 5},
        platform="baike",
        source_category="overview_baike",
        url="https://example.com/3",
        title="乐山大佛（百科）",
        target_ref="/entity/地点/景区/乐山大佛",
    )
    issues = gate_download(TASK)
    assert any(
        issue.code is DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING
        and issue.lane is DataIssueLane.HOMEPAGE
        for issue in issues
    ), issues


def test_gate_download_blocks_reject_only_units():
    ensure_execution_layout(TASK)
    entity_dir = execution_entity_object_dir(TASK, "地点", "景区", "九寨沟")
    write_source_unit(
        entity_dir,
        ordinal=1,
        source_id="probe_1",
        source_md="---\nretained: false\n---\n\nmanual_source_plan_note: 探针页\n",
        quality={"sourceId": "probe_1", "quality": "Reject", "score": 0},
        platform="mafengwo",
        source_category="travelogue",
        url="https://example.com/r1",
        title="探针页1",
        target_ref="/entity/地点/景区/九寨沟",
    )
    write_source_unit(
        entity_dir,
        ordinal=2,
        source_id="probe_2",
        source_md="---\nretained: false\n---\n\nmanual_source_plan_note: 探针页\n",
        quality={"sourceId": "probe_2", "quality": "Reject", "score": 0},
        platform="ctrip",
        source_category="travelogue",
        url="https://example.com/r2",
        title="探针页2",
        target_ref="/entity/地点/景区/九寨沟",
    )
    issues = gate_download(TASK)
    assert any(issue.code is DataIssueCode.SOURCE_RETAINED_SHORTFALL for issue in issues), issues


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


def test_article_source_shortfall_is_absorbed_when_ready_pool_meets_quota():
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

    absorbed = absorb_download_shortfall_if_quota_met(
        context,
        {"readyTargetCount": 1, "ineligibleTargetCount": 1},
        stage=DataIssueStage.DOWNLOAD_FETCH,
        stage_enum=ExecutionStage.DOWNLOAD_FETCH,
        auto_mode=StageKind.AUTO,
        done_status=StageStatus.DONE,
    )

    assert absorbed is not None
    assert absorbed.status is StageStatus.DONE


def test_gate_download_blocks_missing_homepage_lane_text_unit():
    ensure_execution_layout(TASK)
    entity_dir = execution_entity_object_dir(TASK, "地点", "景区", "西塘古镇")
    dl = entity_dir / "1.download"
    write_json(
        dl / "homepage_source_plan.json",
        {
            "payload": {
                "sources": [
                    {
                        "source_id": "home_baidu_baike",
                        "platform": "百度百科",
                        "category": "encyclopedia",
                        "url": "https://baike.baidu.com/item/西塘古镇",
                        "sourceUseMode": "factual_reference_only",
                    }
                ]
            }
        },
    )
    write_json(
        dl / "article_source_plan.json",
        {
            "payload": {
                "sources": [
                    {
                        "source_id": "article_base_1",
                        "platform": "去哪儿攻略",
                        "category": "travelogue",
                        "url": "https://example.com/a1",
                        "sourceUseMode": "factual_reference_only",
                    },
                    {
                        "source_id": "article_base_2",
                        "platform": "马蜂窝",
                        "category": "travelogue",
                        "url": "https://example.com/a2",
                        "sourceUseMode": "factual_reference_only",
                    },
                ]
            }
        },
    )
    write_source_unit(
        entity_dir,
        ordinal=1,
        source_id="article_base_1",
        source_md="# 西塘古镇\n\n游记正文",
        quality={"sourceId": "article_base_1", "quality": "A-story", "score": 8},
        platform="去哪儿攻略",
        source_category="travelogue",
        research_lane="article",
        url="https://example.com/a1",
        title="西塘古镇游记",
        target_ref="/entity/地点/景区/西塘古镇",
    )
    _attach_image(entity_dir / "1.download/sources/01.article_base_1", "xitang_a1")
    write_source_unit(
        entity_dir,
        ordinal=2,
        source_id="article_base_2",
        source_md="# 西塘古镇\n\n另一篇游记正文",
        quality={"sourceId": "article_base_2", "quality": "A-story", "score": 8},
        platform="马蜂窝",
        source_category="travelogue",
        research_lane="article",
        url="https://example.com/a2",
        title="西塘古镇攻略",
        target_ref="/entity/地点/景区/西塘古镇",
    )
    _attach_image(entity_dir / "1.download/sources/02.article_base_2", "xitang_a2")

    issues = gate_download(TASK)

    assert any(
        issue.code is DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING
        and issue.lane is DataIssueLane.HOMEPAGE
        for issue in issues
    ), issues


def test_gate_download_strictly_blocks_missing_successful_sources():
    ensure_execution_layout(TASK)

    issues = gate_download(TASK, target_entities={"失败景区"})

    assert any(issue.code is DataIssueCode.SOURCE_MISSING for issue in issues), issues


def test_gate_download_ignores_disabled_image_lane_but_blocks_source_shortfall(monkeypatch):
    ensure_execution_layout(TASK)
    monkeypatch.setattr(
        "content.source.gate.download_requirements",
        lambda _execution_id: DownloadRequirements(
            min_sources=4,
            min_images=0,
            min_article_base_sources=4,
            min_homepage_sources=1,
            min_homepage_media=0,
        ),
    )
    entity_dir = execution_entity_object_dir(TASK, "地点", "景区", "软图景区")
    write_source_unit(
        entity_dir,
        ordinal=1,
        source_id="article_base_1",
        source_md="# 软图景区\n\n游记正文",
        quality={"sourceId": "article_base_1", "quality": "A-story", "score": 8},
        platform="马蜂窝",
        source_category="travelogue",
        research_lane="article",
        url="https://example.com/a1",
        title="软图景区攻略",
        target_ref="/entity/地点/景区/软图景区",
    )
    write_json(
        execution_root(TASK)
        / "source"
        / "results"
        / "image_fetch_gate"
        / "软图景区.json",
        {
            "payload": {
                "passed": False,
                "ref": "软图景区",
                "issues": [data_issue(
                    DataIssueCode.MEDIA_FETCH_FAILED,
                    stage=DataIssueStage.IMAGE_FETCH,
                    ref="软图景区",
                    lane=DataIssueLane.IMAGE,
                    recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
                    message="imageFetch: 未下到真实图片，请在 source_plan 提供可用 imageUrls(CC/PD/授权)",
                ).as_dict()],
            }
        },
    )

    issues = gate_download(TASK)

    assert any(issue.code is DataIssueCode.SOURCE_RETAINED_SHORTFALL for issue in issues), issues
    assert not any(issue.code is DataIssueCode.MEDIA_FETCH_FAILED for issue in issues), issues


def test_gate_download_image_only_ignores_text_source_bundle_sidecar(monkeypatch):
    ensure_execution_layout(TASK)
    monkeypatch.setattr(
        "content.source.gate.active_download_lanes",
        lambda _execution_id: frozenset({"image"}),
    )
    monkeypatch.setattr(
        "content.source.gate.download_requirements",
        lambda _execution_id: DownloadRequirements(
            min_sources=4,
            min_images=1,
            min_article_base_sources=0,
            min_homepage_sources=0,
            min_homepage_media=0,
        ),
    )
    entity_dir = execution_entity_object_dir(TASK, "地点", "景区", "图片景区")
    write_source_unit(
        entity_dir,
        ordinal=1,
        source_id="image_asset_1",
        source_md="",
        quality={"sourceId": "image_asset_1", "quality": "A-image", "score": 9},
        platform="Wikimedia Commons",
        source_category="open_license_image",
        research_lane="image",
        url="https://example.com/image",
        title="图片景区图集",
        target_ref="/entity/地点/景区/图片景区",
    )
    _attach_image(entity_dir / "1.download/sources/01.image_asset_1", "image_only_1")
    write_json(
        execution_root(TASK)
        / "source"
        / "results"
        / "entity_source_bundle_gate"
        / "图片景区.json",
        {
            "payload": {
                "passed": False,
                "ref": "图片景区",
                "issues": [data_issue(
                    DataIssueCode.SOURCE_RETAINED_SHORTFALL,
                    stage=DataIssueStage.ENTITY_SOURCE_BUNDLE,
                    ref="图片景区",
                    recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
                    message="sourceScreen: no retained source for entity",
                ).as_dict()],
            }
        },
    )

    issues = gate_download(TASK, target_entities={"图片景区"})

    assert issues == []


def test_gate_download_records_unverified_rights_without_blocking_travel(monkeypatch):
    ensure_execution_layout(TASK)
    monkeypatch.setattr(
        "content.source.gate.download_requirements",
        lambda _execution_id: DownloadRequirements(
            min_sources=4,
            min_images=0,
            min_article_base_sources=4,
            min_homepage_sources=1,
            min_homepage_media=0,
        ),
    )
    entity_dir = execution_entity_object_dir(TASK, "地点", "景区", "权利风险景区")
    write_source_unit(
        entity_dir,
        ordinal=1,
        source_id="article_base_1",
        source_md="# 权利风险景区\n\n游记正文",
        quality={"sourceId": "article_base_1", "quality": "A-story", "score": 8},
        platform="马蜂窝",
        source_category="travelogue",
        research_lane="article",
        url="https://example.com/a1",
        title="权利风险景区攻略",
        target_ref="/entity/地点/景区/权利风险景区",
        images=[{"bytes": jpeg_bytes(seed=1), "url": "https://example.com/risky.jpg"}],
        build_variants=False,
    )

    issues = gate_download(TASK)

    assert not any(
        issue.code is DataIssueCode.MEDIA_RIGHTS_UNAVAILABLE for issue in issues
    ), issues
    assert any(issue.code is DataIssueCode.SOURCE_RETAINED_SHORTFALL for issue in issues), issues
    unit = iter_source_units(entity_dir)[0]
    assets = read_json(unit / "assets/index.json")["assets"]
    assert assets[0]["rightsAuditStatus"] == "unverified"


def test_gate_download_blocks_homepage_source_without_base_draft_facts():
    ensure_execution_layout(TASK)
    entity_dir = execution_entity_object_dir(TASK, "地点", "景区", "织金洞景区")
    dl = entity_dir / "1.download"
    write_json(
        dl / "homepage_source_plan.json",
        {
            "payload": {
                "sources": [
                    {
                        "source_id": "home_baidu_baike",
                        "sourceKind": "baidu_baike",
                        "platform": "百度百科",
                        "category": "encyclopedia",
                        "url": "https://baike.baidu.com/item/织金洞",
                        "sourceUseMode": "factual_reference_only",
                    }
                ]
            }
        },
    )
    write_source_unit(
        entity_dir,
        ordinal=1,
        source_id="home_baidu_baike",
        source_md=(
            "---\nplatform: 百度百科\n---\n\n"
            "Coordinates 26°45′30″N 105°55′51″E. "
            "Karst cave in Guizhou, China."
        ),
        quality={"sourceId": "home_baidu_baike", "quality": "C-context", "score": 3},
        platform="百度百科",
        source_category="encyclopedia",
        source_kind="baidu_baike",
        extractor="baidu_baike_html",
        policy_revision="encyclopedia-primary",
        research_lane="homepage",
        source_use_mode="factual_reference_only",
        url="https://baike.baidu.com/item/织金洞",
        title="织金洞",
        target_ref="/entity/地点/景区/织金洞景区",
    )
    write_source_unit(
        entity_dir,
        ordinal=2,
        source_id="article_base_1",
        source_md="# 织金洞景区\n\n这是一篇可读文章来源。",
        quality={"sourceId": "article_base_1", "quality": "B-fact", "score": 5},
        platform="去哪儿攻略",
        source_category="travelogue",
        research_lane="article",
        url="https://example.com/a1",
        title="织金洞景区攻略",
        target_ref="/entity/地点/景区/织金洞景区",
    )

    issues = gate_download(TASK)

    assert any(
        issue.code is DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING
        and "baseDraft-ready" in issue.message
        for issue in issues
    ), issues


def test_gate_download_uses_full_homepage_source_not_article_clean_extract():
    """Homepage gate and author input must consume the same frozen source.md."""
    entity = "完整来源景区"
    entity_dir = execution_entity_object_dir(TASK, "地点", "景区", entity)
    write_source_unit(
        entity_dir,
        ordinal=1,
        source_id="home_wikipedia",
        source_md=(
            f"{entity}位于测试省测试市，始建于2001年，占地10平方公里。\n"
            "景区包括主展馆、历史街区和公共步道，是当地重要文化地标。\n"
            f"{entity}每天开放，游客可通过官方渠道预约，并设置交通接驳设施。\n"
            f"{entity}保护多处历史建筑和自然景观，长期开展公共教育活动。\n"
            f"{entity}建成游客服务中心、公共停车场和无障碍步行线路。"
            f"{entity}管理方持续巡检步道、观景平台和服务设施，并公布季节开放信息。"
            f"{entity}周边保留历史建筑、公共绿地与自然植被，形成连续可达的游览空间。"
            f"{entity}管理机构设置客流引导、无障碍通道和环境保护巡查制度。"
            f"{entity}通过步行线路、观景节点和公共标识连接主要景观与服务区域。"
            f"{entity}每年结合气候条件发布安全提示，并维护交通接驳和游客咨询服务。"
            f"{entity}按照承载能力安排分时游览，定期检查步道、栈道和公共设施的安全状况。"
            f"{entity}在主要入口提供导览信息、应急联络和文明游览提示，帮助游客规划行程。"
            f"{entity}周边公共交通覆盖主要到达点，景区在节假日实施客流疏导与秩序维护。"
        ),
        clean_md=f"{entity}是测试景区。",
        quality={"sourceId": "home_wikipedia", "quality": "A-fact", "score": 8},
        platform="维基百科",
        source_category="encyclopedia",
        source_kind="wikipedia",
        extractor="wikipedia_api",
        policy_revision="encyclopedia-primary",
        source_role="primary",
        research_lane="homepage",
        source_use_mode="licensed_adaptation",
        url="https://zh.wikipedia.org/wiki/完整来源景区",
        title=entity,
        target_ref=f"/entity/地点/景区/{entity}",
    )

    issues = gate_download(TASK, target_entities={entity})

    assert not any(
        issue.code is DataIssueCode.SOURCE_PRIMARY_AUTHORITY_MISSING
        for issue in issues
    ), issues


def test_gate_download_blocks_target_entity_without_sources_dir():
    ensure_execution_layout(TASK)
    entity_dir = execution_entity_object_dir(TASK, "地点", "景区", "峨眉山")
    write_source_unit(
        entity_dir,
        ordinal=1,
        source_id="overview_baike",
        source_md="# 峨眉山\n\n峨眉山位于test-region-b，是中国著名山岳型景区。",
        quality={"sourceId": "overview_baike", "quality": "B-fact", "score": 5},
        platform="baike",
        source_category="overview_baike",
        url="https://example.com/1",
        title="峨眉山（百科）",
        target_ref="/entity/地点/景区/峨眉山",
    )

    issues = gate_download(TASK, target_entities={"缺下载景区"})

    assert any(
        issue.code is DataIssueCode.SOURCE_MISSING and issue.ref == "缺下载景区"
        for issue in issues
    ), issues


def test_gate_download_includes_failed_stage_gate_sidecars():
    ensure_execution_layout(TASK)
    entity_dir = execution_entity_object_dir(TASK, "地点", "景区", "三苏祠")
    write_source_unit(
        entity_dir,
        ordinal=1,
        source_id="overview_baike",
        source_md="# 三苏祠\n\n概述",
        quality={"sourceId": "overview_baike", "quality": "B-fact", "score": 5},
        platform="baike",
        source_category="overview_baike",
        url="https://example.com/1",
        title="三苏祠（百科）",
        target_ref="/entity/地点/景区/三苏祠",
    )
    _attach_image(entity_dir / "1.download/sources/01.overview_baike", "sansuci_1")
    write_source_unit(
        entity_dir,
        ordinal=2,
        source_id="travel_notes",
        source_md="# 三苏祠\n\n游记",
        quality={"sourceId": "travel_notes", "quality": "A-story", "score": 8},
        platform="travelogue",
        source_category="travelogue",
        url="https://example.com/2",
        title="三苏祠（游记）",
        target_ref="/entity/地点/景区/三苏祠",
    )
    _attach_image(entity_dir / "1.download/sources/02.travel_notes", "sansuci_2")
    report_dir = execution_command_root(TASK, "source") / "results" / "image_fetch_gate"
    report_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        report_dir / "三苏祠.json",
        {
            "payload": {
                "ref": "三苏祠",
                "passed": False,
                "issues": [data_issue(
                    DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL,
                    stage=DataIssueStage.IMAGE_FETCH,
                    ref="三苏祠",
                    lane=DataIssueLane.IMAGE,
                    recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
                    message="imageCount: 三苏祠 仅下到 1 张合格图（要求 ≥2）",
                ).as_dict()],
            }
        },
    )

    issues = gate_download(TASK)
    assert any(issue.code is DataIssueCode.MEDIA_PUBLISHABLE_SHORTFALL for issue in issues), issues


def test_gate_download_scopes_to_target_entities():
    ensure_execution_layout(TASK)
    good_dir = execution_entity_object_dir(TASK, "地点", "景区", "峨眉山")
    _write_verified_homepage_source(
        good_dir,
        entity_name="峨眉山",
        source_id="overview_baike",
        asset_name="emei_scope_1",
    )
    write_source_unit(
        good_dir,
        ordinal=2,
        source_id="travel_notes",
        source_md="# 峨眉山\n\n游记",
        quality={"sourceId": "travel_notes", "quality": "A-story", "score": 8},
        platform="travelogue",
        source_category="travelogue",
        url="https://example.com/2",
        title="峨眉山（游记）",
        target_ref="/entity/地点/景区/峨眉山",
    )
    _attach_image(good_dir / "1.download/sources/02.travel_notes", "emei_scope_2")

    bad_dir = execution_entity_object_dir(TASK, "地点", "景区", "缺源景区")
    write_json(
        bad_dir / "1.download" / "homepage_source_plan.json",
        {"payload": {"sources": [{"source_id": "home_missing", "platform": "百度百科"}]}},
    )

    issues = gate_download(TASK, target_entities={"峨眉山"})

    assert issues == [], issues


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]:
        fn()
        print(f"PASS {fn.__name__}")
    print("download gate tests passed")
