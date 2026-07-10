"""地点实体类型唯一真相源契约测试（裁决 6 + 收债 9，WP1）。

覆盖两块验收意图：
- 主类型判定优先级：PRIMARY_TYPE_PRIORITY 常量与裁决 6 顺序一字不差；
  resolve_primary_entity_type 按表判定 + 兜底打卡地。
- 类型口径归一：task lint 的 known_entity_types 只来自 Entity 树一级节点
  （sop 拍平子级类型不再是合法 entityType）；sop/主页 目录与 Entity 树一致；
  发布态 _entity.json 物化必填集与 schema/publish/entity.schema.json 不漂移。
"""
from __future__ import annotations

import json

import pytest

from _common.entity_type_taxonomy import (
    CONTRACT_TAGS_ROOT,
    PILOT_CORE_PRIMARY_TYPES,
    PILOT_OPTIONAL_PRIMARY_TYPES,
    PILOT_PRIMARY_TYPES,
    PRIMARY_TYPE_FALLBACK,
    PRIMARY_TYPE_PRIORITY,
    entity_top_level_types,
    entity_type_tag_node_exists,
    find_entity_type_node_path,
    known_entity_type_paths,
    resolve_primary_entity_type,
)
from _common.paths import _REPO_DATA_ROOT


# ---------- 裁决 6：主类型判定优先级 ----------

def test_primary_type_priority_matches_ruling6_order():
    assert PRIMARY_TYPE_PRIORITY == (
        "景区", "博物馆", "宗教场所", "遗址", "古镇",
        "主题乐园", "自然景观", "公园", "温泉", "打卡地",
    )
    assert PRIMARY_TYPE_FALLBACK == "打卡地"


def test_priority_types_all_exist_in_entity_tree():
    """优先级表内每个类型必须是 Entity/地点 树一级节点（表不脱离契约树）。"""
    top_levels = set(entity_top_level_types("地点"))
    missing = [name for name in PRIMARY_TYPE_PRIORITY if name not in top_levels]
    assert missing == [], missing


def test_resolve_primary_entity_type_prefers_higher_priority():
    # 武侯祠 = 景区 + 博物馆 + 遗址 → 景区（裁决 6 示例）
    assert resolve_primary_entity_type({"博物馆", "遗址", "景区"}) == "景区"
    assert resolve_primary_entity_type({"遗址", "宗教场所"}) == "宗教场所"
    assert resolve_primary_entity_type({"公园", "温泉"}) == "公园"
    assert resolve_primary_entity_type(["打卡地"]) == "打卡地"


def test_resolve_primary_entity_type_fallback_to_checkin():
    assert resolve_primary_entity_type(set()) == "打卡地"
    assert resolve_primary_entity_type({"餐厅", "住宿"}) == "打卡地"
    assert resolve_primary_entity_type(["", "  "]) == "打卡地"


def test_pilot_scope_composition():
    assert PILOT_CORE_PRIMARY_TYPES == {
        "景区", "自然景观", "打卡地", "遗址", "古镇", "宗教场所", "博物馆", "公园",
    }
    assert PILOT_OPTIONAL_PRIMARY_TYPES == {"温泉", "主题乐园"}
    assert PILOT_PRIMARY_TYPES == PILOT_CORE_PRIMARY_TYPES | PILOT_OPTIONAL_PRIMARY_TYPES
    # 试点 scope 必须是优先级表的子集（同一契约面）
    assert PILOT_PRIMARY_TYPES <= set(PRIMARY_TYPE_PRIORITY)


# ---------- 收债 9：类型口径归一（Entity 树唯一定义处） ----------

def test_known_entity_types_come_from_entity_tree_only():
    from task.lint import known_entity_types

    types = known_entity_types()
    assert types == known_entity_type_paths()
    # 一级节点合法（现有任务 地点/景区 必须仍合法）
    assert "地点/景区" in types
    assert "地点/餐厅" in types
    assert "地点/住宿" in types
    # sop 拍平子级类型不可作 entityType 主类型（细分经 typeTagRefs 表达）
    for flat in ("地点/咖啡馆", "地点/茶馆", "地点/酒吧", "地点/火锅店",
                 "地点/民宿", "地点/客栈", "地点/酒店", "地点/度假村"):
        assert flat not in types, flat


def test_sop_home_taxonomy_consistent_with_entity_tree():
    from task.lint import sop_taxonomy_consistency_errors

    assert sop_taxonomy_consistency_errors() == []


def test_sop_flat_types_map_to_entity_tree_levels():
    """sop 拍平类型 ↔ Entity 树层级映射：餐饮/住宿细分是子级节点。"""
    assert find_entity_type_node_path("地点", "咖啡馆") == "Entity/地点/餐厅/咖啡馆"
    assert find_entity_type_node_path("地点", "民宿") == "Entity/地点/住宿/民宿"
    assert find_entity_type_node_path("地点", "景区") == "Entity/地点/景区"
    assert find_entity_type_node_path("地点", "不存在类型") is None


def test_entity_type_tag_node_exists_contract_tree():
    assert entity_type_tag_node_exists("Entity/地点/景区/5A景区")
    assert not entity_type_tag_node_exists("Entity/地点/景区/不存在叶子")
    assert not entity_type_tag_node_exists("")


def test_known_entity_type_paths_raises_on_missing_tree(tmp_path):
    """契约缺失显式抛错，禁止静默空集把所有类型误判为未知。"""
    with pytest.raises(RuntimeError):
        known_entity_type_paths(tags_root=tmp_path / "empty_tags")


def test_contract_tags_root_is_repo_path_not_runtime_root():
    """契约跟代码走：tags 真相源在仓内，不随 QWQ_DATA_ROOT 隔离漂移。"""
    assert CONTRACT_TAGS_ROOT == _REPO_DATA_ROOT / "publish" / "tags"
    assert (CONTRACT_TAGS_ROOT / "Entity" / "地点").is_dir()


# ---------- 发布态 _entity.json 契约不漂移 ----------

def test_required_entity_fields_subset_of_publish_schema():
    from build.homepage import _REQUIRED_ENTITY_FIELDS

    schema = json.loads(
        (_REPO_DATA_ROOT / "schema" / "publish" / "entity.schema.json").read_text(encoding="utf-8")
    )
    schema_required = set(schema["required"])
    assert "geoTagRef" in _REQUIRED_ENTITY_FIELDS
    assert set(_REQUIRED_ENTITY_FIELDS) <= schema_required
    # geoTagRefs 可选：在 schema 字段白名单内但不进必填集
    assert "geoTagRefs" in schema["properties"]
    assert "geoTagRefs" not in schema_required
