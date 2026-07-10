"""存量实体标签回填契约（WP3-5，local_contract）。"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import json

import pytest
import yaml

from _common.io import read_json, write_json  # noqa: E402
from quality.entity_tag_backfill import (  # noqa: E402
    BACKFILL_SCHEMA_VERSION,
    apply_backfill,
    load_backfill_map,
    plan_backfill,
)

GEO_REF = "Topic/地理/行政区/中国/四川省/成都市/都江堰市"
TYPE_REF_5A = "Entity/地点/景区/5A景区"
TYPE_REF_HERITAGE = "Entity/地点/景区/世界遗产"


def _seed_tag_node(tags_root: Path, ref: str) -> None:
    node = tags_root / ref
    node.mkdir(parents=True, exist_ok=True)
    (node / "_definition.json").write_text(
        json.dumps({"label": node.name}, ensure_ascii=False), encoding="utf-8"
    )


def _seed_publish_entity(publish_root: Path, entity_ref: str, **extra) -> Path:
    entity_dir = publish_root / "entities" / entity_ref
    entity_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "label": entity_ref.split("/")[-1],
        "domain": entity_ref.split("/")[0],
        "type": entity_ref.split("/")[1],
        "sourceTaskId": "legacy/task",
        "entityRef": f"/entity/{entity_ref}",
        "tagRefs": ["Topic/旅行/玩法/观光游览", "Format/内容角度/攻略"],
        **extra,
    }
    write_json(entity_dir / "_entity.json", payload)
    return entity_dir / "_entity.json"


@pytest.fixture()
def roots(tmp_path: Path) -> tuple[Path, Path]:
    tags_root = tmp_path / "tags"
    publish_root = tmp_path / "publish"
    for ref in (GEO_REF, TYPE_REF_5A, TYPE_REF_HERITAGE):
        _seed_tag_node(tags_root, ref)
    return publish_root, tags_root


def _rows(**overrides) -> list[dict]:
    row = {
        "entityRef": "地点/景区/都江堰",
        "geoTagRef": GEO_REF,
        "geoTagRefs": [],
        "typeTagRefs": [TYPE_REF_5A, TYPE_REF_HERITAGE],
    }
    row.update(overrides)
    return [row]


def test_backfill_merges_geo_and_type_tags_preserving_existing(roots) -> None:
    publish_root, tags_root = roots
    entity_json = _seed_publish_entity(publish_root, "地点/景区/都江堰")

    plan = plan_backfill(_rows(), publish_root=publish_root, tags_root=tags_root)
    assert plan.ok and len(plan.changes) == 1
    applied = apply_backfill(plan)
    assert applied[0]["geoTagRef"] == GEO_REF
    assert applied[0]["overriddenGeoTagRef"] == ""

    data = read_json(entity_json)
    assert data["geoTagRef"] == GEO_REF
    # 既有 Topic/Format 标签保留在前，新增类型/地理标签保序合并在后。
    assert data["tagRefs"][:2] == ["Topic/旅行/玩法/观光游览", "Format/内容角度/攻略"]
    assert TYPE_REF_5A in data["tagRefs"]
    assert TYPE_REF_HERITAGE in data["tagRefs"]
    assert GEO_REF in data["tagRefs"]
    assert len(data["tagRefs"]) == len(set(data["tagRefs"]))


def test_backfill_is_idempotent(roots) -> None:
    publish_root, tags_root = roots
    _seed_publish_entity(publish_root, "地点/景区/都江堰")
    apply_backfill(plan_backfill(_rows(), publish_root=publish_root, tags_root=tags_root))

    second = plan_backfill(_rows(), publish_root=publish_root, tags_root=tags_root)
    assert second.ok
    assert not second.changes
    assert second.unchanged == ["地点/景区/都江堰"]


def test_backfill_rejects_geo_ref_missing_from_contract_tree(roots) -> None:
    publish_root, tags_root = roots
    _seed_publish_entity(publish_root, "地点/景区/都江堰")
    rows = _rows(geoTagRef="Topic/地理/行政区/中国/不存在省/不存在市/不存在县")
    plan = plan_backfill(rows, publish_root=publish_root, tags_root=tags_root)
    assert not plan.ok
    assert any("未命中行政区契约树节点" in issue for issue in plan.issues)
    with pytest.raises(ValueError):
        apply_backfill(plan)


def test_backfill_rejects_type_ref_outside_entity_tree(roots) -> None:
    publish_root, tags_root = roots
    _seed_publish_entity(publish_root, "地点/景区/都江堰")
    rows = _rows(typeTagRefs=["Topic/旅行/玩法/观光游览"])
    plan = plan_backfill(rows, publish_root=publish_root, tags_root=tags_root)
    assert not plan.ok
    assert any("typeTagRefs 必须在 Entity/** 树内" in issue for issue in plan.issues)


def test_backfill_requires_primary_geo_in_geo_tag_refs(roots) -> None:
    publish_root, tags_root = roots
    other_geo = "Topic/地理/行政区/中国/云南省/丽江市/宁蒗彝族自治县"
    _seed_tag_node(tags_root, other_geo)
    _seed_publish_entity(publish_root, "地点/景区/都江堰")
    rows = _rows(geoTagRefs=[other_geo])
    plan = plan_backfill(rows, publish_root=publish_root, tags_root=tags_root)
    assert not plan.ok
    assert any("必须包含主归属" in issue for issue in plan.issues)


def test_backfill_records_overridden_geo_tag_ref(roots) -> None:
    publish_root, tags_root = roots
    stale_geo = "Topic/地理/行政区/中国/四川省/成都市/武侯区"
    _seed_tag_node(tags_root, stale_geo)
    entity_json = _seed_publish_entity(publish_root, "地点/景区/都江堰", geoTagRef=stale_geo)
    plan = plan_backfill(_rows(), publish_root=publish_root, tags_root=tags_root)
    applied = apply_backfill(plan)
    assert applied[0]["overriddenGeoTagRef"] == stale_geo
    assert read_json(entity_json)["geoTagRef"] == GEO_REF


def test_backfill_reports_missing_publish_entity(roots) -> None:
    publish_root, tags_root = roots
    plan = plan_backfill(_rows(), publish_root=publish_root, tags_root=tags_root)
    assert not plan.ok
    assert any("publish 主线不存在" in issue for issue in plan.issues)


def test_load_backfill_map_validates_schema(tmp_path: Path) -> None:
    path = tmp_path / "map.yaml"
    path.write_text(
        yaml.safe_dump({"schemaVersion": "wrong", "entities": []}, allow_unicode=True),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="schemaVersion"):
        load_backfill_map(path)

    path.write_text(
        yaml.safe_dump(
            {
                "schemaVersion": BACKFILL_SCHEMA_VERSION,
                "entities": [{"entityRef": "地点/景区/都江堰", "geoTagRef": GEO_REF}],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="typeTagRefs"):
        load_backfill_map(path)


def test_repo_backfill_map_hits_real_contract_trees() -> None:
    """仓内 54 实体映射必须全部命中真实契约树与 publish 主线（发布态一致性门）。"""
    map_path = DATA_ROOT / "verticals" / "travel" / "coverage" / "legacy_h100_entity_tag_backfill.yaml"
    rows = load_backfill_map(map_path)
    assert len(rows) == 54
    publish_root = DATA_ROOT / "publish"
    tags_root = publish_root / "tags"
    plan = plan_backfill(rows, publish_root=publish_root, tags_root=tags_root)
    assert plan.ok, plan.issues
