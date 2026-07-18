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
from core.io import write_json  # noqa: E402
from core.data_issue import (  # noqa: E402
    DataIssueCode,
    DataIssueStage,
    DataIssueLane,
    DataRecoveryAction,
    data_issue,
)
from content.source.source_unit import iter_source_units, write_source_unit  # noqa: E402
from content.source.gate import (  # noqa: E402
    DownloadRequirements,
    download_requirements,
    gate_download,
)
from content.execution.recovery.download_gate import _download_repair_active_issues  # noqa: E402
from support.execution_manifest_fixture import ExecutionFixtureBuilder  # noqa: E402

TASK = "20260711--travel-homepage-download-gate--cn-sichuan--canary-001"


@pytest.fixture(autouse=True)
def _clean_execution_root():
    shutil.rmtree(execution_root(TASK), ignore_errors=True)
    ExecutionFixtureBuilder(TASK).build()
    yield
    shutil.rmtree(execution_root(TASK), ignore_errors=True)


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


def test_download_repair_active_issues_only_decodes_typed_records():
    issue = data_issue(
        DataIssueCode.SOURCE_RETAINED_SHORTFALL,
        stage=DataIssueStage.DOWNLOAD_FETCH,
        ref="普陀山",
        lane=DataIssueLane.HOMEPAGE,
        recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
        message="retained source requirement is not met",
    )
    ctx = SimpleNamespace(entity_ids=["普陀山"])

    assert _download_repair_active_issues(
        ctx,
        {"entityId": "普陀山", "issueRecords": [issue.as_dict()]},
    ) == [str(issue)]

    with pytest.raises(ValueError, match="typed issueRecords"):
        _download_repair_active_issues(
            ctx,
            {"entityId": "普陀山", "issues": ["legacy message-only issue"]},
        )


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
) -> None:
    write_source_unit(
        entity_dir,
        ordinal=1,
        source_id=source_id,
        source_md=(
            f"# {entity_name}\n\n{entity_name}位于四川省。"
            f"{entity_name}主峰海拔三千余米。"
            f"{entity_name}是中国著名山岳景区。"
            f"{entity_name}景区包括多条登山步道。"
        ),
        quality={"sourceId": source_id, "quality": "B-fact", "score": 5},
        platform="Wikipedia",
        source_category="encyclopedia",
        source_kind="wikipedia",
        extractor="wikipedia_api",
        policy_revision="encyclopedia-primary",
        research_lane="homepage",
        url=f"https://zh.wikipedia.org/wiki/{entity_name}",
        title=entity_name,
        target_ref=f"/entity/地点/景区/{entity_name}",
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
            min_video_frames=0,
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
            min_video_frames=0,
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


def test_gate_download_reports_rights_and_source_shortfall(monkeypatch):
    ensure_execution_layout(TASK)
    monkeypatch.setattr(
        "content.source.gate.download_requirements",
        lambda _execution_id: DownloadRequirements(
            min_sources=4,
            min_images=0,
            min_article_base_sources=4,
            min_homepage_sources=1,
            min_homepage_media=0,
            min_video_frames=0,
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
        images=[{"bytes": b"not-a-real-image", "url": "https://example.com/risky.jpg"}],
        build_variants=False,
    )

    issues = gate_download(TASK)

    assert any(issue.code is DataIssueCode.MEDIA_RIGHTS_UNAVAILABLE for issue in issues), issues
    assert any(issue.code is DataIssueCode.SOURCE_RETAINED_SHORTFALL for issue in issues), issues


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
        extractor="baidu_baike_openapi",
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


def test_gate_download_blocks_target_entity_without_sources_dir():
    ensure_execution_layout(TASK)
    entity_dir = execution_entity_object_dir(TASK, "地点", "景区", "峨眉山")
    write_source_unit(
        entity_dir,
        ordinal=1,
        source_id="overview_baike",
        source_md="# 峨眉山\n\n峨眉山位于四川省，是中国著名山岳型景区。",
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
