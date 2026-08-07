from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from content.execution.planning.selection import select_targets
from core.control_types import TargetSelector
from core.schema import assert_valid
from governance.coverage.admin_entity_catalog import (
    ADMIN_ENTITY_TYPE,
    ADMIN_ENTITY_TYPE_TAG_REF,
    ADMIN_REGION_REFERENCE_PATH,
    ADMIN_TAXONOMY_ROOT_REF,
    admin_entity_candidates,
    admin_entity_catalog_report,
)
from governance.coverage.entity_type_taxonomy import CONTRACT_TAGS_ROOT
from governance.coverage.source_readiness_candidates import (
    _dedupe_candidates,
    _master_candidates,
    _qualify_candidate,
    _readiness_key,
)
from governance.coverage.source_readiness import _balanced_frozen_targets


_MUNICIPALITIES = {"北京市", "天津市", "上海市", "重庆市"}
_DIRECT_COUNTY_GROUPS = {"省直辖县级行政区划", "自治区直辖县级行政区划"}


def _taxonomy_provinces() -> set[str]:
    root = CONTRACT_TAGS_ROOT / ADMIN_TAXONOMY_ROOT_REF
    return {
        child.name
        for child in root.iterdir()
        if child.is_dir() and (child / "_definition.json").is_file()
    }


def _expected_counts() -> dict[str, int]:
    pca = json.loads(ADMIN_REGION_REFERENCE_PATH.read_text(encoding="utf-8"))
    prefectures = 0
    counties = 0
    for province, cities in pca.items():
        if not isinstance(cities, dict):
            continue
        if province not in _MUNICIPALITIES:
            prefectures += sum(
                1 for city in cities if city not in _DIRECT_COUNTY_GROUPS
            )
        for districts in cities.values():
            if isinstance(districts, (list, dict)):
                counties += len(districts)
    return {
        "province": len(set(pca) | _taxonomy_provinces()),
        "prefecture": prefectures,
        "county": counties,
        "total": len(set(pca) | _taxonomy_provinces())
        + prefectures
        + counties,
    }


def test_national_admin_catalog_enumerates_all_levels_from_canonical_sources():
    candidates = admin_entity_candidates()
    report = admin_entity_catalog_report()

    assert report["scope"] == "national"
    assert report["sourceProvinceCounts"] == {"pca": 31, "taxonomyOnly": 3}
    assert report["counts"] == _expected_counts()
    assert len(candidates) == report["counts"]["total"]
    assert set(report["selectedProvinces"]) == _taxonomy_provinces()
    assert {"香港特别行政区", "澳门特别行政区", "台湾省"} <= {
        row["province"] for row in candidates
    }
    assert report["missingTaxonomyPaths"] == []

    levels = Counter(row["adminLevel"] for row in candidates)
    assert levels == {
        level: report["counts"][level]
        for level in ("province", "prefecture", "county")
    }
    assert all(row["entityType"] == ADMIN_ENTITY_TYPE for row in candidates)
    assert all(
        row["typeTagRefs"] == [ADMIN_ENTITY_TYPE_TAG_REF]
        for row in candidates
    )
    assert all(
        (CONTRACT_TAGS_ROOT / row["geoTagRef"] / "_definition.json").is_file()
        for row in candidates
    )


def test_admin_catalog_canonical_identity_and_entity_ref_are_nationally_unique():
    candidates = admin_entity_candidates()
    identities = [row["canonicalIdentity"] for row in candidates]
    entity_refs = [row["canonicalEntityRef"] for row in candidates]

    assert len(identities) == len(set(identities))
    assert len(entity_refs) == len(set(entity_refs))
    assert all(_readiness_key(row) == row["canonicalIdentity"] for row in candidates)
    assert admin_entity_catalog_report()["duplicateCanonicalIdentities"] == []
    assert admin_entity_catalog_report()["duplicateCanonicalEntityRefs"] == []


def test_homepage_selection_consumes_pca_catalog_without_duplicate_yaml():
    targets, report = select_targets(
        discovery_path=ADMIN_REGION_REFERENCE_PATH,
        limit=1800,
        quota=1800,
        target_selector=TargetSelector.ALL,
    )

    assert len(targets) == report["selectedCount"] == 1800
    assert all(target["entityType"] == ADMIN_ENTITY_TYPE for target in targets)
    assert all(
        str(target["geoTagRef"]).startswith(ADMIN_TAXONOMY_ROOT_REF + "/")
        for target in targets
    )
    assert len({target["name"] for target in targets}) == 1800


def test_source_ready_pool_combines_national_admin_entities_with_existing_pois():
    provinces = admin_entity_catalog_report()["selectedProvinces"]
    combined = _master_candidates(provinces)
    deduped = _dedupe_candidates(combined, provinces=provinces)
    admin_rows = [
        row for row in deduped if row.get("candidateKind") == "admin_region"
    ]
    poi_rows = [row for row in deduped if row.get("source") == "master_list"]

    # M1000 的 1800 候选下界由全国行政实体本身满足；川浙 POI 是增量，
    # 不得把双省 POI 数量冒充全国 coverage。
    assert len(admin_rows) == admin_entity_catalog_report()["counts"]["total"]
    assert len(admin_rows) >= 1800
    assert all(row["entityType"] == ADMIN_ENTITY_TYPE for row in admin_rows)
    assert all(row["typeTagRefs"] == [ADMIN_ENTITY_TYPE_TAG_REF] for row in admin_rows)
    assert len(deduped) >= len(admin_rows)
    assert {"四川省", "浙江省"} <= {row["province"] for row in poi_rows}
    assert set(provinces) == _taxonomy_provinces()


def test_source_ready_freeze_preserves_admin_entity_type():
    candidate = admin_entity_candidates(provinces=["浙江省"])[0]
    frozen, covered = _balanced_frozen_targets(
        [
            {
                "schema": "quwoquan_data.source_ready_candidate",
                "identityKey": _readiness_key(candidate),
                "candidate": candidate,
                "attemptedSources": ["wikipedia"],
                "qualified": True,
                "evidence": {
                    "sourceKind": "wikipedia",
                    "extractor": "wikipedia_api",
                    "canonicalUrl": "https://zh.wikipedia.org/wiki/test",
                    "resolvedTitle": candidate["name"],
                    "matchConfidence": 1.0,
                },
                "qualifiedAt": "2026-07-28T00:00:00Z",
            }
        ],
        provinces=["浙江省"],
        minimum_per_province=1,
    )

    assert covered == {"浙江省": 1}
    assert frozen[0]["selection"]["coverageCell"]["entityType"] == ADMIN_ENTITY_TYPE


def test_admin_candidates_still_require_per_object_encyclopedia_qualification(
    monkeypatch,
):
    import governance.coverage.source_readiness_candidates as candidates_module

    candidate = admin_entity_candidates(provinces=["浙江省"])[0]
    monkeypatch.setattr(
        candidates_module,
        "_wikipedia_evidence",
        lambda _candidate: None,
    )
    monkeypatch.setattr(
        candidates_module,
        "_baike_evidence",
        lambda _candidate, *, source: None,
    )

    result = _qualify_candidate(
        candidate,
        sources=("wikipedia", "baidu_baike", "toutiao_baike"),
    )

    assert result["qualified"] is False
    assert "evidence" not in result
    assert result["attemptedSources"] == [
        "wikipedia",
        "baidu_baike",
        "toutiao_baike",
    ]
    assert_valid(
        result,
        "governance",
        "source_ready_candidate",
        label="admin source-ready candidate",
    )
