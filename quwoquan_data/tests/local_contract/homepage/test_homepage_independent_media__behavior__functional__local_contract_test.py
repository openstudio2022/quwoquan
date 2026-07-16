"""Entity homepage media evidence stays separate from encyclopedia text evidence."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core.paths import ensure_execution_command_layout, ensure_execution_layout  # noqa: E402
from content.source.source_unit import resolve_entity_object_dir, write_source_unit  # noqa: E402
from core.asset_identity import compute_post_asset_id  # noqa: E402
from content.post.draft_io import is_placeholder  # noqa: E402
from content.homepage.homepage_assets import select_homepage_assets  # noqa: E402
from content.homepage.homepage_materialization import _homepage_source_figure_issues  # noqa: E402
from content.homepage.homepage_prompt import (  # noqa: E402
    _homepage_base_text_with_image_placeholders,
    _write_entity_page_prompt_and_placeholder,
)
from content.homepage.homepage_validation import _asset_closure_issues  # noqa: E402


def test_homepage_assets_fall_back_to_independent_rights_cleared_media_unit():
    execution_id = "20260712--travel-homepage-media-contract--cn-zhejiang--canary-001"
    entity = "独立媒体景区"
    ensure_execution_layout(execution_id)
    ensure_execution_command_layout(execution_id, "source")
    obj = resolve_entity_object_dir(
        execution_id,
        entity,
        etype_hint="地点/景区",
    )
    shutil.rmtree(obj, ignore_errors=True)
    primary = write_source_unit(
        obj,
        ordinal=1,
        source_id="home_toutiao_baike",
        source_md=f"{entity}位于浙江省。{entity}包含自然景观与游览步道。",
        quality={"sourceId": "home_toutiao_baike", "quality": "B-fact", "score": 6},
        platform="今日头条百科",
        source_category="encyclopedia",
        source_kind="toutiao_baike",
        extractor="toutiao_baike_html",
        policy_revision="encyclopedia-primary-v2",
        source_use_mode="factual_reference_only",
        research_lane="homepage",
        url="https://www.baike.com/wikiid/123",
        title=entity,
        target_ref=f"/entity/地点/景区/{entity}",
        execution_id=execution_id,
    )
    write_source_unit(
        obj,
        ordinal=2,
        source_id="homepage_media_1",
        source_md=f"{entity}独立开放许可媒体集合。",
        quality={"sourceId": "homepage_media_1", "quality": "B-fact", "score": 1},
        platform="Wikimedia Commons",
        source_category="image_collection",
        source_use_mode="licensed_adaptation",
        research_lane="homepage_image",
        license_value="CC BY-SA 4.0",
        url="https://commons.wikimedia.org/wiki/File:Independent.jpg",
        title=f"{entity}开放许可图片",
        target_ref=f"/entity/地点/景区/{entity}",
        relevance=entity,
        images=[
            {
                "bytes": b"\xff\xd8\xff\xe0" + b"homepage-media" * 100,
                "ext": ".jpg",
                "url": "https://upload.wikimedia.org/Independent.jpg",
                "sourceUrl": "https://commons.wikimedia.org/wiki/File:Independent.jpg",
                "sourceCollectionId": "homepage_media:independent",
                "license": "CC BY-SA 4.0",
                "credit": "Commons contributor",
                "creator": "Commons contributor",
                "termsUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
                "authorizationProof": "https://commons.wikimedia.org/wiki/File:Independent.jpg",
                "usageScope": "app_publish",
                "caption": entity,
                "relevance": entity,
            }
        ],
        execution_id=execution_id,
        build_variants=False,
    )
    primary_ref = str(primary["sourceRef"])
    assets = select_homepage_assets(
        execution_id,
        "地点",
        "景区",
        entity,
        primary_ref=primary_ref,
    ).publishable
    assert len(assets) == 1
    assert assets[0]["researchLane"] == "homepage_image"
    assert assets[0]["sourceCollectionId"] == "homepage_media:independent"
    assert assets[0]["authorizationProof"].startswith("https://commons.wikimedia.org/")


def test_homepage_asset_closure_allows_independent_media_source(tmp_path: Path):
    entity_dir = tmp_path / "独立媒体景区"
    assets_dir = entity_dir / "assets"
    assets_dir.mkdir(parents=True)
    asset_id = compute_post_asset_id(
        entity_name="独立媒体景区",
        role="cover",
        execution_sequence=1,
        ref="sources/media/assets/001.jpg",
        caption="山景",
        ordinal=1,
    )
    file_name = f"{asset_id}.jpg"
    (assets_dir / file_name).write_bytes(b"independent-media")
    (entity_dir / "page.md").write_text("---\ncoverImage: asset://" + asset_id + "\n---\n正文", encoding="utf-8")
    text_ref = "sources/primary/source.md"
    image_ref = "sources/media/source.md"
    manifest = {
        "textSourceRefs": [text_ref],
        "imageSourceRefs": [image_ref],
        "assets": [
            {
                "assetId": asset_id,
                "fileName": file_name,
                "role": "cover",
                "sourceRef": image_ref,
                "sourceAssetRef": "sources/media/assets/001.jpg",
                "authorizationProof": "https://commons.wikimedia.org/wiki/File:Independent.jpg",
            }
        ],
    }

    assert _asset_closure_issues(entity_dir, manifest, "独立媒体景区") == []


def test_changed_homepage_base_source_invalidates_stale_draft_and_failure():
    execution_id = "20260712--travel-homepage-source-refresh--cn-zhejiang--canary-001"
    entity = "来源刷新景区"
    ensure_execution_layout(execution_id)
    ensure_execution_command_layout(execution_id, "homepage")
    obj = resolve_entity_object_dir(
        execution_id,
        entity,
        etype_hint="地点/景区",
    )
    shutil.rmtree(obj, ignore_errors=True)

    def payload(source_ref: str) -> dict:
        return {
            "name": entity,
            "domain": "地点",
            "etype": "景区",
            "baseDraft": {
                "sourceRef": source_ref,
                "primaryEvidenceRef": source_ref,
                "sourceUseMode": "licensed_adaptation",
                "text": f"{entity}的有效百科底稿正文。" * 30,
            },
            "availableImages": [],
            "imagePlaceholderBindings": [],
        }

    _write_entity_page_prompt_and_placeholder(
        execution_id,
        "地点",
        "景区",
        entity,
        payload("sources/old/source.md"),
    )
    draft_dir = obj / "4.draft"
    (draft_dir / "page.md").write_text("# 已创作但来源已过期的正文", encoding="utf-8")
    (draft_dir / "failure.json").write_text("{}", encoding="utf-8")
    for name in ("page.md", "_entity.json", "manifest.json"):
        (obj / name).write_text("stale", encoding="utf-8")

    _write_entity_page_prompt_and_placeholder(
        execution_id,
        "地点",
        "景区",
        entity,
        payload("sources/new/source.md"),
    )

    assert is_placeholder((draft_dir / "page.md").read_text(encoding="utf-8"))
    assert not (draft_dir / "failure.json").exists()
    assert not (obj / "page.md").exists()
    assert not (obj / "_entity.json").exists()
    assert not (obj / "manifest.json").exists()


def test_homepage_source_asset_refs_defer_to_canonical_image_placeholders():
    base = {
        "markdown": (
            "## 生态保护\n\n[[IMG:fig_02]]\n\n"
            ":::figure\n![旧来源图注](asset://001_002)\n旧来源图注\n:::\n"
        )
    }
    draft = "## 生态保护\n\n[[IMG:fig_02]]\n\n正文。"

    assert _homepage_source_figure_issues(base, draft, "测试实体") == []


def test_homepage_agent_base_draft_hides_group_media_without_inline_binding():
    """图集成员不进入 Agent 输入，仍由 finalize 归入相关图片区。"""
    base = (
        "# 东钱湖\n\n概况正文。\n\n"
        ":::figure\n![](asset://001_001)\n:::\n\n"
        "## 主要景点\n\n景点正文。\n\n"
        ":::gallery ids=\"001_002,001_003\"\nasset://001_002\nasset://001_003\n:::\n"
    )

    prepared = _homepage_base_text_with_image_placeholders(base, [])

    assert "asset://" not in prepared
    assert ":::figure" not in prepared
    assert ":::gallery" not in prepared
    assert "[[IMG:" not in prepared
    assert "概况正文" in prepared
    assert "景点正文" in prepared


def test_homepage_agent_base_draft_exposes_only_bound_inline_placeholders():
    """正文锚定图由最小占位符承接，非锚定来源图不会泄漏给 Agent。"""
    base = (
        "# 普陀山\n\n概况正文。\n\n"
        "## 地理生态\n\n地理正文。\n\n"
        ":::figure\n![](asset://001_002)\n:::\n\n"
        ":::figure\n![](asset://001_003)\n:::\n"
    )
    bindings = [
        {
            "figId": "fig_02",
            "sourceAssetId": "001_002",
            "caption": "普陀山全貌模型",
            "sectionAnchor": "地理生态",
            "paragraphIndex": 1,
        }
    ]

    prepared = _homepage_base_text_with_image_placeholders(base, bindings)

    assert prepared.count("[[IMG:fig_02]]") == 1
    assert "001_003" not in prepared
    assert "asset://" not in prepared
    assert ":::figure" not in prepared
