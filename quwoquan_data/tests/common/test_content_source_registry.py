"""Unified content source registry and prompt contracts."""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from _common.content_source_registry import (  # noqa: E402
    build_content_source_guidance,
    homepage_source_is_secondary_authority,
    render_lane_source_prompt,
    resolve_homepage_source_role,
    verify_content_source_registry,
)


def test_content_source_registry_is_valid_and_covers_all_lanes():
    assert verify_content_source_registry() == []
    guidance = build_content_source_guidance("travel")
    assert set(guidance["lanes"]) == {"homepage", "article", "image", "video"}
    homepage = guidance["lanes"]["homepage"]["sources"]
    image = guidance["lanes"]["image"]["sources"]
    article = guidance["lanes"]["article"]["sources"]
    assert any(row["platform"] == "维基百科" for row in homepage)
    assert any(row["platform"] == "维基导游" for row in homepage)
    assert any(row["platform"] == "头条百科" and row["homepageAuthorityRole"] == "reference_only" for row in homepage)
    assert any(row["platform"] == "Pinterest" for row in image)
    assert any(row["platform"] == "图虫" for row in image)
    assert any(row["sourceClass"] == "ugc_longform" for row in article)
    # R-HSE06 扩源：官网/政务文旅在 homepage lane 具备主源资格（第二权威）。
    assert any(
        row["sourceClass"] == "official_site" and row["homepageAuthorityRole"] == "primary"
        for row in homepage
    )
    assert any(
        row["sourceClass"] == "government_tourism" and row["homepageAuthorityRole"] == "primary"
        for row in homepage
    )


def test_homepage_role_two_tier_authority_resolution():
    """R-HSE06：两级权威角色解析唯一真相源 = lanePolicies.homepage。"""
    # 第一权威百科。
    assert resolve_homepage_source_role(platform="维基百科", category="encyclopedia") == "primary"
    # 第二权威：sourceClass 命中。
    assert resolve_homepage_source_role(platform="某景区官网", source_class="official_site") == "primary"
    assert resolve_homepage_source_role(platform="某文旅厅", source_class="government_tourism") == "primary"
    # 第二权威：词元命中（gov.cn URL）。
    assert resolve_homepage_source_role(platform="未知平台", url="https://wlt.sc.gov.cn/x") == "primary"
    # reference_only 裁决优先于百科词元。
    assert resolve_homepage_source_role(platform="头条百科", category="encyclopedia") == "reference_only"
    # supporting only：知识图谱/权威媒体。
    assert resolve_homepage_source_role(platform="Wikidata", source_class="knowledge_graph") == "supporting"
    assert resolve_homepage_source_role(platform="新华网", source_class="authoritative_media") == "supporting"
    # 第二权威判定（事实化压缩消费）：百科不是第二权威。
    assert homepage_source_is_secondary_authority({"platform": "官方网站", "sourceClass": "official_site"})
    assert homepage_source_is_secondary_authority({"platform": "x", "url": "https://wlt.sc.gov.cn/a"})
    assert not homepage_source_is_secondary_authority({"platform": "维基百科", "category": "encyclopedia"})
    assert not homepage_source_is_secondary_authority({"platform": "百度百科", "url": "https://baike.baidu.com/item/x"})


def test_lane_prompt_is_rendered_from_registry_policy():
    article_prompt = render_lane_source_prompt(
        "article",
        vertical="travel",
        per_target_articles=3,
        article_intents=["planning_consultation", "decision_experience", "route_transport"],
    )
    image_prompt = render_lane_source_prompt(
        "image",
        vertical="travel",
        per_target_image_works=2,
        image_asset_strategy="ai_generated_original",
    )
    homepage_prompt = render_lane_source_prompt("homepage", vertical="travel")
    assert "不得因 UGC/垂类专业/平台文章类别天然升降级" in article_prompt
    assert "去哪儿攻略" in article_prompt and "马蜂窝" in article_prompt
    assert "Pinterest" in image_prompt and "图虫" in image_prompt
    assert "imageAssetStrategy=ai_generated_original" in image_prompt
    assert "逐图授权链" in image_prompt
    assert "最多保留 5 个核心来源" in homepage_prompt
    assert "维基导游" in homepage_prompt
    assert "头条百科" in homepage_prompt


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"content source registry tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
