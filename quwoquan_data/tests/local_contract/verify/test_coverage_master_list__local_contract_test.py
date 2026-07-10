"""全国地点主清单门禁契约测试（discovery_seed/2，WP1）。

覆盖两块验收意图：
- schema 校验：仓内示例主清单对 master_list.schema.json 契约全绿；
  契约（schemaVersion const / 必填集 / enum / 字段白名单）只从 schema 文件读取。
- verify 门：C1-C9 每条规则各有可失败反例（tmp coverage root 注入 +
  真实契约标签树 CONTRACT_TAGS_ROOT，仓内路径不随 QWQ_DATA_ROOT 隔离漂移）。
"""
from __future__ import annotations

from pathlib import Path

import yaml

from _common.entity_type_taxonomy import CONTRACT_TAGS_ROOT
from verify.verify_coverage_master_list import (
    COVERAGE_MASTER_ROOT,
    MASTER_LIST_SCHEMA_PATH,
    _load_schema_contract,
    scan_master_list,
)

_VALID_LEAF = {
    "name": "都江堰",
    "canonicalName": "都江堰",
    "entityType": "地点/景区",
    "typeTagRefs": ["Entity/地点/景区/5A景区"],
    "geoTagRef": "Topic/地理/行政区/中国/四川省/成都市/都江堰市",
    "selectionPriority": 1,
    "sourceReadiness": "ready",
}


def _write_master_file(
    root: Path,
    *,
    province: str = "四川省",
    city: str = "成都市",
    district: str = "都江堰市",
    leaves: list[dict] | None = None,
    file_overrides: dict | None = None,
) -> Path:
    payload = {
        "schemaVersion": "quwoquan_data.discovery_seed/2",
        "country": root.name,
        "province": province,
        "city": city,
        "districts": [{"district": district, "leaves": leaves or [dict(_VALID_LEAF)]}],
        **(file_overrides or {}),
    }
    path = root / province / f"{city}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _scan(root: Path) -> list[str]:
    errors, _, _ = scan_master_list(coverage_root=root, tags_root=CONTRACT_TAGS_ROOT)
    return errors


def _tmp_country_root(tmp_path: Path) -> Path:
    root = tmp_path / "中国"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_repo_master_list_passes_gate():
    """仓内示例主清单（成都市 + 凉山州跨省示例）必须全绿。"""
    errors, file_count, leaf_count = scan_master_list()
    assert errors == [], errors
    assert file_count >= 2
    assert leaf_count >= 3
    assert COVERAGE_MASTER_ROOT.name == "中国"


def test_schema_contract_is_single_source():
    """必填集/enum/schemaVersion const 只从 schema 文件读取，不维护第二真相源。"""
    contract = _load_schema_contract(MASTER_LIST_SCHEMA_PATH)
    assert contract["schemaVersion"] == "quwoquan_data.discovery_seed/2"
    assert contract["sourceReadinessEnum"] == {"pending", "ready", "no_primary_source"}
    assert set(contract["leafRequired"]) == {
        "name", "canonicalName", "entityType", "typeTagRefs",
        "geoTagRef", "selectionPriority", "sourceReadiness",
    }
    assert "homepageStatus" not in contract["leafFields"]


def test_valid_tmp_file_passes(tmp_path):
    root = _tmp_country_root(tmp_path)
    _write_master_file(root)
    assert _scan(root) == []


def test_c1_unknown_province_and_city_blocked(tmp_path):
    root = _tmp_country_root(tmp_path)
    _write_master_file(root, province="不存在省", city="不存在市", district="不存在县")
    errors = _scan(root)
    assert any(e.startswith("C1") and "不存在省" in e for e in errors), errors
    assert any(e.startswith("C1") and "不存在市" in e for e in errors), errors


def test_c2_homepage_status_and_unknown_fields_blocked(tmp_path):
    """homepageStatus 等易变状态字段借未知字段门天然阻断（不进主清单）。"""
    root = _tmp_country_root(tmp_path)
    leaf = {**_VALID_LEAF, "homepageStatus": "published"}
    _write_master_file(root, leaves=[leaf], file_overrides={"extraTopField": 1})
    errors = _scan(root)
    assert any(e.startswith("C2") and "homepageStatus" in e for e in errors), errors
    assert any(e.startswith("C2") and "extraTopField" in e for e in errors), errors


def test_c2_missing_required_and_bad_enum_blocked(tmp_path):
    root = _tmp_country_root(tmp_path)
    leaf = dict(_VALID_LEAF)
    leaf.pop("canonicalName")
    leaf["sourceReadiness"] = "someday"
    leaf["selectionPriority"] = 0
    _write_master_file(root, leaves=[leaf])
    errors = _scan(root)
    assert any(e.startswith("C2") and "canonicalName" in e for e in errors), errors
    assert any(e.startswith("C2") and "someday" in e for e in errors), errors
    assert any(e.startswith("C2") and "selectionPriority" in e for e in errors), errors


def test_c3_province_field_path_mismatch_blocked(tmp_path):
    root = _tmp_country_root(tmp_path)
    _write_master_file(root, file_overrides={"province": "云南省"})
    errors = _scan(root)
    assert any(e.startswith("C3") and "云南省" in e for e in errors), errors


def test_c4_unknown_district_blocked(tmp_path):
    root = _tmp_country_root(tmp_path)
    leaf = {**_VALID_LEAF, "geoTagRef": "Topic/地理/行政区/中国/四川省/成都市/幻想区"}
    _write_master_file(root, district="幻想区", leaves=[leaf])
    errors = _scan(root)
    assert any(e.startswith("C4") and "幻想区" in e for e in errors), errors


def test_c5_entity_type_scope_blocked(tmp_path):
    root = _tmp_country_root(tmp_path)
    out_of_pilot = {**_VALID_LEAF, "canonicalName": "某民宿聚落", "entityType": "地点/住宿"}
    unknown_type = {**_VALID_LEAF, "canonicalName": "某未知类型", "entityType": "地点/不存在类型"}
    bad_shape = {**_VALID_LEAF, "canonicalName": "坏格式", "entityType": "景区"}
    _write_master_file(root, leaves=[out_of_pilot, unknown_type, bad_shape])
    errors = _scan(root)
    assert any(e.startswith("C5") and "地点/住宿" in e and "试点 scope" in e for e in errors), errors
    assert any(e.startswith("C5") and "地点/不存在类型" in e for e in errors), errors
    assert any(e.startswith("C5") and "坏格式" in e for e in errors), errors


def test_c6_type_tag_refs_blocked(tmp_path):
    root = _tmp_country_root(tmp_path)
    dangling = {**_VALID_LEAF, "typeTagRefs": ["Entity/地点/景区/不存在叶子"]}
    missing_primary = {
        **_VALID_LEAF,
        "canonicalName": "缺主类型叶子",
        "typeTagRefs": ["Entity/地点/博物馆"],  # entityType=地点/景区 但数组无景区叶子
    }
    non_leaf = {
        **_VALID_LEAF,
        "canonicalName": "非叶子类型引用",
        # 自然景观下仍有 山岳/水体 等子级细分 → 必须精确到叶子
        "typeTagRefs": ["Entity/地点/景区/5A景区", "Entity/地点/自然景观"],
    }
    _write_master_file(root, leaves=[dangling, missing_primary, non_leaf])
    errors = _scan(root)
    assert any(e.startswith("C6") and "不存在叶子" in e for e in errors), errors
    assert any(e.startswith("C6") and "缺少主类型" in e for e in errors), errors
    assert any(e.startswith("C6") and "必须精确到叶子" in e for e in errors), errors


def test_c7_geo_tag_ref_must_match_district_group(tmp_path):
    root = _tmp_country_root(tmp_path)
    leaf = {**_VALID_LEAF, "geoTagRef": "Topic/地理/行政区/中国/四川省/成都市/青羊区"}
    _write_master_file(root, district="都江堰市", leaves=[leaf])
    errors = _scan(root)
    assert any(e.startswith("C7") and "青羊区" in e for e in errors), errors


def test_c8_geo_tag_refs_must_contain_primary(tmp_path):
    root = _tmp_country_root(tmp_path)
    leaf = {
        **_VALID_LEAF,
        "geoTagRefs": ["Topic/地理/行政区/中国/云南省/丽江市/宁蒗彝族自治县"],
    }
    _write_master_file(root, leaves=[leaf])
    errors = _scan(root)
    assert any(e.startswith("C8") and "必须包含主归属" in e for e in errors), errors


def test_c9_canonical_name_globally_unique_across_files(tmp_path):
    """跨省地点仅主归属省登记一次（裁决 7）→ canonicalName 跨文件唯一。"""
    root = _tmp_country_root(tmp_path)
    _write_master_file(root, province="四川省", city="成都市", district="都江堰市")
    dup = {
        **_VALID_LEAF,
        "geoTagRef": "Topic/地理/行政区/中国/四川省/凉山彝族自治州/盐源县",
    }
    _write_master_file(root, province="四川省", city="凉山彝族自治州", district="盐源县", leaves=[dup])
    errors = _scan(root)
    assert any(e.startswith("C9") and "都江堰" in e and "跨文件重复" in e for e in errors), errors


_MUNICIPALITY_LEAF = {
    "name": "测试胡同",
    "canonicalName": "北京测试胡同",
    "entityType": "地点/打卡地",
    "typeTagRefs": ["Entity/地点/打卡地"],
    "geoTagRef": "Topic/地理/行政区/中国/北京市/东城区",
    "selectionPriority": 2,
    "sourceReadiness": "pending",
}


def test_c4_municipality_district_level_file_passes(tmp_path):
    """直辖市口径：市州槽位即区县（中国/北京市/东城区.yaml），district == city 全绿。"""
    root = _tmp_country_root(tmp_path)
    _write_master_file(
        root,
        province="北京市",
        city="东城区",
        district="东城区",
        leaves=[dict(_MUNICIPALITY_LEAF)],
    )
    assert _scan(root) == []


def test_c4_municipality_wrong_district_blocked(tmp_path):
    """直辖市区县级文件中 district != city（文件名）必须 C4 阻断。"""
    root = _tmp_country_root(tmp_path)
    leaf = {**_MUNICIPALITY_LEAF, "geoTagRef": "Topic/地理/行政区/中国/北京市/西城区"}
    _write_master_file(root, province="北京市", city="东城区", district="西城区", leaves=[leaf])
    errors = _scan(root)
    assert any(e.startswith("C4") and "只允许 district" in e for e in errors), errors
