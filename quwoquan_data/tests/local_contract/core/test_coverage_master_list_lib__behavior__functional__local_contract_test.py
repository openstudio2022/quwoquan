"""主清单共享库契约：walk/统计/地理覆盖门/decompose 投影 单一真相源。
- 地理覆盖门 geo_coverage_issues：市州文件齐全 + 文件内区县全覆盖 +
  直辖市区县级文件口径（与 verify 门 C4 同口径）。
- discovery_partitions_from_master_list：主清单 → decompose 省/市州/区县分区树只读投影。
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from governance.coverage import master_list as cml


def _mk_tag(root: Path, ref: str) -> None:
    node = root / ref
    node.mkdir(parents=True, exist_ok=True)
    (node / "_definition.json").write_text(json.dumps({"name": node.name}), encoding="utf-8")


def _fake_tags_root(tmp_path: Path) -> Path:
    """迷你行政区树：测试省（普通两级）+ 直辖省（市州槽位即区县）。"""
    tags = tmp_path / "tags"
    _mk_tag(tags, "Topic/地理/行政区/中国")
    _mk_tag(tags, "Topic/地理/行政区/中国/测试省")
    _mk_tag(tags, "Topic/地理/行政区/中国/测试省/甲市")
    _mk_tag(tags, "Topic/地理/行政区/中国/测试省/甲市/一区")
    _mk_tag(tags, "Topic/地理/行政区/中国/测试省/甲市/二县")
    _mk_tag(tags, "Topic/地理/行政区/中国/测试省/乙州")
    _mk_tag(tags, "Topic/地理/行政区/中国/测试省/乙州/三县")
    _mk_tag(tags, "Topic/地理/行政区/中国/直辖省")
    _mk_tag(tags, "Topic/地理/行政区/中国/直辖省/直一区")
    return tags


def _write_city_file(
    coverage_root: Path,
    province: str,
    city: str,
    district_leaves: dict[str, list[str]],
) -> Path:
    districts = [
        {
            "district": district,
            "leaves": [
                {
                    "name": name,
                    "canonicalName": name,
                    "entityType": "地点/打卡地",
                    "typeTagRefs": ["Entity/地点/打卡地"],
                    "geoTagRef": f"Topic/地理/行政区/中国/{province}/{city}/{district}"
                    if district != city
                    else f"Topic/地理/行政区/中国/{province}/{city}",
                    "selectionPriority": 2,
                }
                for name in names
            ],
        }
        for district, names in district_leaves.items()
    ]
    payload = {
        "schema": "quwoquan_data.discovery_seed",
        "country": "中国",
        "province": province,
        "city": city,
        "districts": districts,
    }
    path = coverage_root / province / f"{city}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def test_city_is_district_level_matches_admin_tree(tmp_path):
    tags = _fake_tags_root(tmp_path)
    assert cml.city_is_district_level("中国", "直辖省", "直一区", tags_root=tags)
    assert not cml.city_is_district_level("中国", "测试省", "甲市", tags_root=tags)


def test_geo_coverage_issues_flag_missing_city_and_district(tmp_path):
    tags = _fake_tags_root(tmp_path)
    root = tmp_path / "coverage" / "中国"
    # 甲市缺"二县"分组；乙州整文件缺失。
    _write_city_file(root, "测试省", "甲市", {"一区": ["甲市一区点"]})
    issues = cml.geo_coverage_issues(["测试省"], coverage_root=root, tags_root=tags)
    assert any("缺市州文件 '乙州.yaml'" in i for i in issues), issues
    assert any("甲市.yaml 缺区县 '二县'" in i for i in issues), issues


def test_geo_coverage_issues_pass_and_municipality(tmp_path):
    tags = _fake_tags_root(tmp_path)
    root = tmp_path / "coverage" / "中国"
    _write_city_file(root, "测试省", "甲市", {"一区": ["点A"], "二县": ["点B"]})
    _write_city_file(root, "测试省", "乙州", {"三县": ["点C"]})
    _write_city_file(root, "直辖省", "直一区", {"直一区": ["点D"]})
    assert cml.geo_coverage_issues(["测试省", "直辖省"], coverage_root=root, tags_root=tags) == []
    # 直辖市区县级文件出现其他 district → 阻断
    _write_city_file(root, "直辖省", "直一区", {"直一区": ["点D"], "别的区": ["点E"]})
    issues = cml.geo_coverage_issues(["直辖省"], coverage_root=root, tags_root=tags)
    assert any("只允许 district" in i for i in issues), issues


def test_discovery_partitions_projection(tmp_path):
    tags = _fake_tags_root(tmp_path)  # noqa: F841  # 投影只读主清单，不读树
    root = tmp_path / "coverage" / "中国"
    _write_city_file(root, "测试省", "甲市", {"一区": ["点A", "点B"], "二县": ["点C"]})
    parts = cml.discovery_partitions_from_master_list(["测试省"], coverage_root=root)
    assert len(parts) == 1 and parts[0]["key"] == "测试省"
    cities = parts[0]["partitions"]
    assert [c["key"] for c in cities] == ["甲市"]
    districts = cities[0]["partitions"]
    assert [d["key"] for d in districts] == ["一区", "二县"]
    assert [l["name"] for l in districts[0]["leaves"]] == ["点A", "点B"]
    assert districts[0]["leaves"][0]["entityType"] == "地点/打卡地"


def test_master_list_stats_counts_types(tmp_path):
    root = tmp_path / "coverage" / "中国"
    _write_city_file(root, "测试省", "甲市", {"一区": ["点A"], "二县": ["点B"]})
    stats = cml.master_list_stats(coverage_root=root)
    assert stats["files"] == 1 and stats["districts"] == 2 and stats["leaves"] == 2
    assert stats["byEntityType"] == {"地点/打卡地": 2}
    assert stats["crossProvinceLeaves"] == []
