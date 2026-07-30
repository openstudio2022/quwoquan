from __future__ import annotations

import json
import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core.paths import CONTROL_PLANE_TAXONOMY_ROOT  # noqa: E402
from verify.tag_geo_coverage import (  # noqa: E402
    CHINA_SAR_TW_MIN_COVERAGE,
    MIN_OVERSEAS_COUNTRIES,
    OVERSEAS_MIN_COVERAGE,
    check_overseas_coverage,
)


def _tag(root: Path, rel: str) -> None:
    d = root / "Topic" / "地理" / "行政区" / rel
    d.mkdir(parents=True, exist_ok=True)
    (d / "_definition.json").write_text(
        json.dumps({"label": rel.split("/")[-1]}, ensure_ascii=False),
        encoding="utf-8",
    )


def _build_satisfying_tree(root: Path) -> None:
    """按最小集本身铺一棵刚好达标的树，城市直接挂在国家下。

    最小集刻意不约束一级行政区名，所以这里也不造一级行政区——同时验证「城市可位于
    国家的任意层级之下」这条语义确实成立。
    """
    for country, cities in OVERSEAS_MIN_COVERAGE.items():
        _tag(root, country)
        for city in cities:
            _tag(root, f"{country}/{city}")
    padding = MIN_OVERSEAS_COUNTRIES - len(OVERSEAS_MIN_COVERAGE)
    for i in range(max(0, padding)):
        _tag(root, f"占位国{i}")
    _tag(root, "中国")
    for province, cities in CHINA_SAR_TW_MIN_COVERAGE.items():
        _tag(root, f"中国/{province}")
        for city in cities:
            _tag(root, f"中国/{province}/{city}")


def test_real_taxonomy_satisfies_overseas_minimum() -> None:
    assert check_overseas_coverage(CONTROL_PLANE_TAXONOMY_ROOT) == []


def test_synthetic_minimum_tree_passes(tmp_path: Path) -> None:
    _build_satisfying_tree(tmp_path)
    assert check_overseas_coverage(tmp_path) == []


def test_missing_country_is_error_not_warning(tmp_path: Path) -> None:
    _build_satisfying_tree(tmp_path)
    admin = tmp_path / "Topic" / "地理" / "行政区" / "日本"
    for f in sorted(admin.rglob("_definition.json"), reverse=True):
        f.unlink()
    for d in sorted(admin.rglob("*"), reverse=True):
        d.rmdir()
    admin.rmdir()

    errors = check_overseas_coverage(tmp_path)
    assert any("境外最小集缺少国家：日本" in e for e in errors)


def test_missing_city_is_reported_per_city(tmp_path: Path) -> None:
    _build_satisfying_tree(tmp_path)
    target = tmp_path / "Topic" / "地理" / "行政区" / "泰国" / "苏梅岛"
    (target / "_definition.json").unlink()
    target.rmdir()

    errors = check_overseas_coverage(tmp_path)
    assert any("泰国 缺少最小集城市：苏梅岛" in e for e in errors)


def test_country_count_floor_blocks_bulk_deletion(tmp_path: Path) -> None:
    _tag(tmp_path, "中国")
    _tag(tmp_path, "日本")

    errors = check_overseas_coverage(tmp_path)
    assert any(f"< {MIN_OVERSEAS_COUNTRIES}" in e for e in errors)


def test_sar_and_taiwan_must_keep_subordinate_cities(tmp_path: Path) -> None:
    _build_satisfying_tree(tmp_path)
    target = tmp_path / "Topic" / "地理" / "行政区" / "中国" / "台湾省" / "花莲"
    (target / "_definition.json").unlink()
    target.rmdir()

    errors = check_overseas_coverage(tmp_path)
    assert any("中国/台湾省 缺少下级：花莲" in e for e in errors)


def test_missing_admin_root_reports_single_error(tmp_path: Path) -> None:
    errors = check_overseas_coverage(tmp_path)
    assert errors == ["R5: 行政区目录不存在：Topic/地理/行政区/"]
