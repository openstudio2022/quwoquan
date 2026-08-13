# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-004.t1
"""场景组：frozen source pool 目标选择与 runtime 绑定护栏。

从 test_scale_source_pool_homepage_article__catalog_projection__contract
__local_contract_test.py 按场景拆出（本文件经 git mv 承接原文件历史）；
测试逐字搬移。
"""
from __future__ import annotations

from pathlib import Path

import pytest
from content.source.research.scale_source_pool_runtime import (
    ScaleSourcePoolRuntimeError,
    frozen_scale_source_pool_targets,
    select_frozen_source_pool_targets,
)


def test_frozen_source_pool_selection_joins_exact_governed_geo_target(
    tmp_path: Path,
) -> None:
    discovery = tmp_path / "entities"
    province = discovery / "四川省"
    province.mkdir(parents=True)
    (province / "成都市.yaml").write_text(
        """schema: quwoquan_data.discovery_seed
country: 中国
province: 四川省
city: 成都市
districts:
- district: 都江堰市
  leaves:
  - name: 都江堰
    canonicalName: 都江堰
    entityType: 地点/景区
    geoTagRef: Topic/地理/行政区/中国/四川省/成都市/都江堰市
    typeTagRefs:
    - Entity/地点/景区/世界遗产
""",
        encoding="utf-8",
    )

    rows, report = select_frozen_source_pool_targets(
        targets=({"entityType": "地点/景区", "name": "都江堰"},),
        requested_limit=1,
        approved_quota=1,
        target_names=("都江堰",),
        discovery_path=discovery,
        pool_binding={"planDigest": "sha256:" + "d" * 64},
        lane_selection={
            "candidateCount": 1,
            "selectionDigest": "sha256:" + "e" * 64,
        },
    )

    assert rows == [
        {
            "entityType": "地点/景区",
            "name": "都江堰",
            "geoTagRef": "Topic/地理/行政区/中国/四川省/成都市/都江堰市",
            "typeTagRefs": ["Entity/地点/景区/世界遗产"],
        }
    ]
    assert report["selectionAuthority"] == "frozen_scale_source_pool"


def test_frozen_source_pool_selection_nfkc_normalizes_exact_canonical_name(
    tmp_path: Path,
) -> None:
    discovery = tmp_path / "entities"
    province = discovery / "浙江省"
    province.mkdir(parents=True)
    (province / "台州市.yaml").write_text(
        """schema: quwoquan_data.discovery_seed
country: 中国
province: 浙江省
city: 台州市
districts:
- district: 天台县
  leaves:
  - name: 天台山
    canonicalName: 天台山（台州）
    entityType: 地点/景区
    geoTagRef: Topic/地理/行政区/中国/浙江省/台州市/天台县
    typeTagRefs:
    - Entity/地点/景区
""",
        encoding="utf-8",
    )

    rows, _report = select_frozen_source_pool_targets(
        targets=({"entityType": "地点/景区", "name": "天台山(台州)"},),
        requested_limit=1,
        approved_quota=1,
        target_names=("天台山(台州)",),
        discovery_path=discovery,
        pool_binding={"planDigest": "sha256:" + "d" * 64},
        lane_selection={
            "candidateCount": 1,
            "selectionDigest": "sha256:" + "e" * 64,
        },
    )

    assert rows[0]["name"] == "天台山(台州)"
    assert rows[0]["geoTagRef"].endswith("/天台县")


def test_frozen_source_pool_selection_joins_exact_admin_regions_in_frozen_order(
    tmp_path: Path,
) -> None:
    entity_refs = (
        "/entity/地点/城市/四川省",
        "/entity/地点/城市/四川省乐山市",
        "/entity/地点/城市/四川省乐山市夹江县",
        "/entity/地点/城市/四川省乐山市沙湾区",
        "/entity/地点/城市/四川省乐山市马边彝族自治县",
        "/entity/地点/城市/四川省内江市威远县",
        "/entity/地点/城市/四川省凉山彝族自治州",
        "/entity/地点/城市/四川省凉山彝族自治州西昌市",
        "/entity/地点/城市/四川省南充市",
        "/entity/地点/城市/四川省南充市阆中市",
        "/entity/地点/城市/四川省宜宾市",
        "/entity/地点/城市/四川省成都市",
    )
    targets = tuple(
        {
            "entityType": "地点/城市",
            "name": entity_ref.rsplit("/", 1)[-1],
            "canonicalEntityRef": entity_ref,
        }
        for entity_ref in entity_refs
    )

    rows, report = select_frozen_source_pool_targets(
        targets=targets,
        requested_limit=12,
        approved_quota=12,
        target_names=tuple(row["name"] for row in targets),
        # 行政实体只能来自 canonical pca projection；这里故意不给旅游 master。
        discovery_path=tmp_path / "absent-tourism-master",
        pool_binding={"planDigest": "sha256:" + "d" * 64},
        lane_selection={
            "candidateCount": 12,
            "selectionDigest": "sha256:" + "e" * 64,
        },
    )

    assert [row["canonicalEntityRef"] for row in rows] == list(entity_refs)
    assert [row["name"] for row in rows] == [row["name"] for row in targets]
    assert all(row["geoTagRef"].startswith("Topic/地理/行政区/中国/四川省") for row in rows)
    assert all(row["typeTagRefs"] == ["Entity/地点/城市"] for row in rows)
    assert report["selectedCount"] == 12


def test_frozen_source_pool_selection_rejects_admin_canonical_ref_drift(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ScaleSourcePoolRuntimeError,
        match="missing governed admin target for 地点/城市/四川省",
    ):
        select_frozen_source_pool_targets(
            targets=(
                {
                    "entityType": "地点/城市",
                    "name": "四川省",
                    "canonicalEntityRef": "/entity/地点/城市/冒名四川省",
                },
            ),
            requested_limit=1,
            approved_quota=1,
            target_names=("四川省",),
            discovery_path=tmp_path / "absent-tourism-master",
            pool_binding={"planDigest": "sha256:" + "d" * 64},
            lane_selection={
                "candidateCount": 1,
                "selectionDigest": "sha256:" + "e" * 64,
            },
        )


def test_scale_source_pool_runtime_forbids_unbound_campaign_context() -> None:
    with pytest.raises(ScaleSourcePoolRuntimeError, match="RUNTIME_INPUT_UNBOUND"):
        frozen_scale_source_pool_targets(
            "20260808--travel-homepage-m100--china--scale-992", "homepage"
        )
