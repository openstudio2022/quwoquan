"""主清单坐标必须一路透传到发布态，且不得被推断补全。

坐标链路：master list leaf.coordinates -> coverageTarget -> homepage payload
-> _entity.json.coordinates -> entity-service importer -> Homepage.location（2dsphere）
-> 搜索 filters.near「附近」。链路上任一段丢字段，附近召回就静默失效；
任一段自行补点，就会把「未知位置」伪装成事实位置。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from content.execution.planning.selection_discovery import (  # noqa: E402
    apply_master_list_fields,
    coverage_target_from_selection,
)
from content.homepage.homepage import _coverage_targets  # noqa: E402
from governance.coverage.master_list import leaf_coordinates  # noqa: E402
from core.schema import assert_valid  # noqa: E402


WEST_LAKE = {"lat": 30.2447, "lon": 120.1497}


def test_master_list_coordinates_reach_coverage_target() -> None:
    row = apply_master_list_fields(
        {"name": "西湖", "entityType": "地点/景区"},
        {
            "name": "西湖",
            "geoTagRef": "Topic/地理/行政区/中国/浙江省/杭州市/西湖区",
            "coordinates": dict(WEST_LAKE),
        },
    )
    assert row["coordinates"] == WEST_LAKE

    target = coverage_target_from_selection(
        {"name": "西湖", "entityType": "地点/景区", "coordinates": dict(WEST_LAKE)}
    )
    assert target["coordinates"] == WEST_LAKE


def test_coverage_target_coordinates_reach_homepage_payload() -> None:
    rows = _coverage_targets(
        {
            "scope": {
                "coverageTargets": [
                    {
                        "name": "西湖",
                        "entityType": "地点/景区",
                        "geoTagRef": "Topic/地理/行政区/中国/浙江省/杭州市/西湖区",
                        "coordinates": dict(WEST_LAKE),
                    },
                    {"name": "灵隐寺", "entityType": "地点/宗教场所"},
                ]
            }
        }
    )
    by_name = {row["name"]: row for row in rows}
    assert by_name["西湖"]["coordinates"] == WEST_LAKE
    # 无坐标目标不得被补出坐标。
    assert "coordinates" not in by_name["灵隐寺"]


@pytest.mark.parametrize(
    "coordinates",
    [
        None,
        {},
        {"lat": 30.2447},
        {"lat": "north", "lon": 120.1497},
        {"lat": 120.1497, "lon": 30.2447},
        {"lat": 0, "lon": 0},
    ],
)
def test_untrustworthy_coordinates_never_reach_publish(coordinates: object) -> None:
    assert leaf_coordinates({"coordinates": coordinates}) is None
    assert apply_master_list_fields({}, {"coordinates": coordinates}).get("coordinates") is None


def test_publish_entity_schema_accepts_coordinates() -> None:
    payload = {
        "label": "西湖",
        "domain": "地点",
        "type": "景区",
        "executionId": "20260728--travel-homepage-golden--hangzhou-west-lake--pilot-006",
        "entityRef": "/entity/地点/景区/西湖",
        "tagRefs": ["Entity/地点/景区"],
        "geoTagRef": "Topic/地理/行政区/中国/浙江省/杭州市/西湖区",
        "coordinates": dict(WEST_LAKE),
        "primarySource": {
            "sourceKind": "wikipedia",
            "entityName": "杭州西湖",
            "extractor": "wikipedia_api",
            "canonicalUrl": "https://zh.wikipedia.org/wiki/西湖",
            "sourceUrl": "https://zh.wikipedia.org/wiki/西湖",
            "title": "西湖",
            "fetchedAt": "2026-07-28T01:41:54Z",
            "snapshotHash": "sha256:" + "0" * 64,
            "policyRevision": "encyclopedia-primary",
            "sourceUseMode": "licensed_adaptation",
        },
        "sourceUrls": ["https://zh.wikipedia.org/wiki/西湖"],
    }
    assert_valid(payload, "publish", "entity", label="entity:西湖")

    payload["coordinates"] = {"lat": 120.1497, "lon": 30.2447}
    with pytest.raises(Exception):
        assert_valid(payload, "publish", "entity", label="entity:西湖")
