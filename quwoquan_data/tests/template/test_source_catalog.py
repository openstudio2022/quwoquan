"""旅游/校园源类别注册表契约测试 ——「全」硬约束。

覆盖：platform→category 归类（含路书/营地/床车/地图等垂直源）、源类别覆盖门判定、
catalog 结构 lint。catalog 为 committed 真相源，按脚本相对路径定位，不受临时 root 影响。
可直接运行 python3 quwoquan_data/tests/template/test_source_catalog.py
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

from _common.source_catalog import (  # noqa: E402
    coverage_issues,
    platform_category,
    source_category_coverage,
    vertical_from_task_id,
)
from template.registry import TemplateRegistry  # noqa: E402
from template.source import validate_source_catalog  # noqa: E402


def test_platform_category_maps_vertical_sources():
    assert platform_category("维基百科") == "encyclopedia"
    assert platform_category("马蜂窝") == "travelogue"
    assert platform_category("携程攻略") == "travelogue"  # 包含匹配
    assert platform_category("去哪儿攻略") == "travelogue"
    assert platform_category("两步路") == "outdoor_route"  # 路书/经纬度/地形
    assert platform_category("安营") == "camping"  # 床车营地
    assert platform_category("高德地图") == "map_geo"
    assert platform_category("景区官网") == "official"
    assert platform_category("web") is None  # 通用兜底不计类别
    assert platform_category("某不存在平台xyz") is None


def test_vertical_inference():
    assert vertical_from_task_id("旅行/地域/四川省/景区/景区全覆盖") == "travel"
    assert vertical_from_task_id("校园/华东/某大学") == "campus"


def test_coverage_satisfied_when_diverse():
    sources = [
        {"platform": "百度百科"},
        {"platform": "马蜂窝"},
        {"platform": "景区官网"},
        {"platform": "两步路"},
    ]
    cov = source_category_coverage(sources, vertical="travel")
    assert cov["coveredCount"] >= 3
    assert cov["missingCore"] == [], cov
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
