"""download gate 契约测试共享常量、fixture 与来源写入 helper。

download gate 契约测试（对象优先）。

由 test_download_gate__behavior_* 场景组测试文件共享；
从原单体测试文件逐字下沉，不改变任何 fixture 逻辑。
``_clean_execution_root`` 是模块级 autouse fixture，场景测试文件
必须显式 import 它以保持 autouse 语义。
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from content.source.source_unit import (
    iter_source_units,
    write_source_unit,
)
from core.io import write_json
from core.paths import execution_root

from support.execution_manifest_fixture import ExecutionFixtureBuilder

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
                    "contentSha256": f"sha256:{name}",
                    "acquisitionStatus": "acquired",
                    "rightsStatus": "verified",
                    "authorizationRequired": False,
                    "distributionDecision": "commercial_allowed",
                    "license": "CC-BY-4.0",
                    "credit": "fixture",
                    "creator": "fixture",
                    "platform": "fixture-professional-library",
                    "capturedAt": "2026-08-05T00:00:00Z",
                    "sourceUrl": "https://example.com/image.jpg",
                    "termsUrl": "https://example.com/terms",
                    "authorizationProof": "https://example.com/authorization",
                    "rightsIssues": [],
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
