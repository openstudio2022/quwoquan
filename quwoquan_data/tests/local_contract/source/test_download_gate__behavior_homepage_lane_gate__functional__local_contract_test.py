"""场景组：download gate homepage lane 阻断、rights 记录与目标实体范围。

download gate 契约测试（对象优先）。

从 test_download_gate__behavior__functional__local_contract_test.py
按场景拆出；测试逐字搬移。
"""
from __future__ import annotations

from content.source.gate import (
    DownloadRequirements,
    download_requirements,
    gate_download,
)
from content.source.source_unit import (
    iter_source_units,
    write_source_unit,
)
from core.data_issue import (
    DataIssueCode,
    DataIssueLane,
    DataIssueStage,
    DataRecoveryAction,
    data_issue,
)
from core.io import read_json, write_json
from core.paths import (
    ensure_execution_layout,
    execution_command_root,
    execution_entity_object_dir,
    execution_root,
)
from support.article_source_registry_fixture import (
    ARTICLE_SOURCE_UNIT_IDENTITY,
    article_source_registry_binding,
)
from support.download_gate_fixture import (
    TASK,
    _attach_image,
    _clean_execution_root,
    _write_verified_homepage_source,
)
from support.image_fixture import jpeg_bytes


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
        source_role="base",
        research_lane="article",
        url="https://example.com/a1",
        title="西塘古镇游记",
        target_ref="/entity/地点/景区/西塘古镇",
        publish_media_mode="illustrated",
        **ARTICLE_SOURCE_UNIT_IDENTITY,
        source=article_source_registry_binding(
            platform="去哪儿攻略",
            url="https://example.com/a1",
        ),
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
        source_role="base",
        research_lane="article",
        url="https://example.com/a2",
        title="西塘古镇攻略",
        target_ref="/entity/地点/景区/西塘古镇",
        publish_media_mode="illustrated",
        **ARTICLE_SOURCE_UNIT_IDENTITY,
        source=article_source_registry_binding(
            platform="马蜂窝",
            url="https://example.com/a2",
        ),
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
        source_role="base",
        research_lane="article",
        url="https://example.com/a1",
        title="软图景区攻略",
        target_ref="/entity/地点/景区/软图景区",
        publish_media_mode="text_only",
        **ARTICLE_SOURCE_UNIT_IDENTITY,
        source=article_source_registry_binding(
            platform="马蜂窝",
            url="https://example.com/a1",
        ),
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
        source_role="base",
        research_lane="article",
        url="https://example.com/a1",
        title="权利风险景区攻略",
        target_ref="/entity/地点/景区/权利风险景区",
        images=[{"bytes": jpeg_bytes(seed=1), "url": "https://example.com/risky.jpg"}],
        build_variants=False,
        publish_media_mode="illustrated",
        **ARTICLE_SOURCE_UNIT_IDENTITY,
        source=article_source_registry_binding(
            platform="马蜂窝",
            url="https://example.com/a1",
        ),
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
        source_role="base",
        research_lane="article",
        url="https://example.com/a1",
        title="织金洞景区攻略",
        target_ref="/entity/地点/景区/织金洞景区",
        publish_media_mode="text_only",
        **ARTICLE_SOURCE_UNIT_IDENTITY,
        source=article_source_registry_binding(
            platform="去哪儿攻略",
            url="https://example.com/a1",
        ),
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
