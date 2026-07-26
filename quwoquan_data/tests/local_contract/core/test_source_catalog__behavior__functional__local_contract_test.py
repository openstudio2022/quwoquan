"""旅游/校园源类别注册表契约测试 ——「全」硬约束。

覆盖：platform→category 归类（含路书/营地/床车/地图等垂直源）、源类别覆盖门判定、
catalog 结构 lint。catalog 为 committed 真相源，按脚本相对路径定位，不受临时 root 影响。
可直接运行 python3 quwoquan_data/tests/local_contract/core/test_source_catalog__behavior__functional__local_contract_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import sys
from pathlib import Path

sys.path.insert(0, str(SCRIPTS_ROOT))

from core.source_catalog import (  # noqa: E402
    coverage_issues,
    coverage_policy,
    platform_category,
    source_category_coverage,
    vertical_from_task_id,
)
from content.templates.registry import TemplateRegistry  # noqa: E402
from content.templates.source import validate_source_catalog  # noqa: E402


def test_platform_category_maps_vertical_sources():
    assert platform_category("维基百科") == "encyclopedia"
    assert platform_category("马蜂窝") == "travelogue"
    assert platform_category("携程攻略") == "travelogue"  # 包含匹配
    assert platform_category("去哪儿攻略") == "travelogue"
    assert platform_category("两步路") == "outdoor_route"  # 路书/经纬度/地形
    assert platform_category("安营") == "camping"  # 床车营地
    assert platform_category("高德地图") == "map_geo"
    assert platform_category("景区官网") == "official"
    assert platform_category("官方文章") == "official"
    assert platform_category("今日头条") == "platform_article"
    assert platform_category("Toutiao") == "platform_article"
    assert platform_category("微博") == "community_post"
    assert platform_category("web") is None  # 通用兜底不计类别
    assert platform_category("某不存在平台xyz") is None


def test_photography_image_work_sources_route_by_license_metadata_first():
    """图片作品=专业图库一源一作品：开放许可图库可发布；图虫等摄影社区需逐图授权；
    Pinterest 在 source_catalog 中仍归入 editorial_reference_only 覆盖类别，但真实可发布性
    由 content_source_registry / rights policy 决定。来源类目与许可分流的唯一真相源是
    source_catalog.yaml（metadata-first），代码只读不另立第二真相源。"""
    # 开放许可图库（Wikimedia Commons / Unsplash / Pexels / Pixabay / Openverse）→ open_license。
    for platform in ("Wikimedia Commons", "unsplash", "pexels", "pixabay", "openverse"):
        assert platform_category(platform) == "open_license", platform
    # 摄影社区（图虫/500px/Flickr/Behance）→ photography_platform（按平台条款逐图授权）。
    for platform in ("图虫", "tuchong", "500px", "flickr", "behance"):
        assert platform_category(platform) == "photography_platform", platform
    # 授权图库（Getty/Adobe Stock/视觉中国授权）→ stock_authorized（须授权凭证）。
    for platform in ("Adobe Stock", "depositphotos", "摄图网", "图虫创意"):
        assert platform_category(platform) == "stock_authorized", platform
    # Pinterest / 摄影灵感 → editorial_reference_only：这里只表达 coverage 类别，不直接代表最终发布资格。
    for platform in ("Pinterest", "pinterest", "小红书摄影灵感"):
        assert platform_category(platform) == "editorial_reference_only", platform

    # 图片作品准出核心类目只接受 open_license + photography_platform；
    # editorial_reference_only 绝不在准出核心类目内（如实标注受限，不绕硬门）。
    photo_core = set(coverage_policy("photography").get("coreCategories") or [])
    assert photo_core == {"open_license", "photography_platform"}, photo_core
    assert "editorial_reference_only" not in photo_core
    assert "stock_authorized" not in photo_core


def test_vertical_inference():
    assert vertical_from_task_id("旅行/地域/test-region-b/景区/景区全覆盖") == "travel"
    assert vertical_from_task_id("校园/华东/某大学") == "campus"


def test_coverage_satisfied_when_diverse():
    sources = [
        {"platform": "百度百科"},
        {"platform": "马蜂窝"},
        {"platform": "两步路"},
    ]
    cov = source_category_coverage(sources, vertical="travel")
    assert cov["coveredCount"] >= 3
    assert cov["missingCore"] == [], cov
    assert "official" in cov["missingPreferred"], cov
    assert cov["satisfied"] is True
    assert coverage_issues(sources, vertical="travel") == []


def test_coverage_accepts_quality_article_sources_without_travelogue():
    sources = [
        {"platform": "百度百科"},
        {"platform": "文旅局"},
        {"platform": "新华网"},
    ]
    cov = source_category_coverage(sources, vertical="travel")
    assert cov["coveredCategories"] == ["authoritative_reference", "encyclopedia", "official"], cov
    assert cov["missingCore"] == [], cov
    assert "travelogue" in cov["missingPreferred"], cov
    assert cov["satisfied"] is True
    assert coverage_issues(sources, vertical="travel") == []


def test_coverage_blocks_single_category():
    sources = [{"platform": "马蜂窝"}, {"platform": "携程"}]
    cov = source_category_coverage(sources, vertical="travel")
    assert cov["satisfied"] is False
    issues = coverage_issues(sources, vertical="travel", entity_id="九寨沟")
    assert any("source categories" in i for i in issues), issues
    assert any("missing core" in i for i in issues), issues


def test_unknown_platform_reported():
    cov = source_category_coverage([{"platform": "随便一个平台"}], vertical="travel")
    assert "随便一个平台" in cov["unknownPlatforms"]


def test_catalog_structure_is_valid():
    registry = TemplateRegistry.load()
    assert validate_source_catalog(registry) == [], validate_source_catalog(registry)


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"source catalog tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
