"""全国行政实体候选投影。

候选只读 ``reference/admin_regions/pca.json`` 与行政区 taxonomy，不物化第二份
省/市/区县清单。港澳台当前只投影 taxonomy 已声明的省级节点；没有权威下级输入时
不推断或伪造市县。
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Iterator

from core.paths import _REPO_DATA_ROOT
from governance.coverage.entity_type_taxonomy import (
    CONTRACT_TAGS_ROOT,
    entity_type_tag_node_exists,
)


ADMIN_REGION_REFERENCE_PATH = (
    _REPO_DATA_ROOT / "reference" / "admin_regions" / "pca.json"
)
ADMIN_TAXONOMY_ROOT_REF = "Topic/地理/行政区/中国"
ADMIN_ENTITY_TYPE = "地点/城市"
ADMIN_ENTITY_TYPE_TAG_REF = "Entity/地点/城市"

_MUNICIPALITIES = frozenset({"北京市", "天津市", "上海市", "重庆市"})
_DIRECT_COUNTY_GROUPS = frozenset(
    {"省直辖县级行政区划", "自治区直辖县级行政区划"}
)
_ADMIN_LEVELS = ("province", "prefecture", "county")


def _taxonomy_children(ref: str, *, taxonomy_root: Path) -> list[str]:
    node = taxonomy_root / ref
    if not node.is_dir():
        return []
    return sorted(
        child.name
        for child in node.iterdir()
        if child.is_dir() and (child / "_definition.json").is_file()
    )


def _taxonomy_node_exists(ref: str, *, taxonomy_root: Path) -> bool:
    node = taxonomy_root / ref
    return node.is_dir() and (node / "_definition.json").is_file()


def _load_pca(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not payload:
        raise ValueError(f"行政区参考数据必须是非空 object: {path}")
    return payload


def _district_names(raw: Any) -> Iterator[str]:
    values: Iterable[Any]
    if isinstance(raw, dict):
        values = raw.keys()
    elif isinstance(raw, list):
        values = raw
    else:
        return
    for value in values:
        name = str(value).strip()
        if name:
            yield name


def _canonical_name(*parts: str) -> str:
    """以完整行政链派生跨全国唯一且可读的 entityRef 第三段。"""
    return "".join(str(part).strip() for part in parts if str(part).strip())


def _candidate(
    *,
    province: str,
    city: str,
    district: str,
    label: str,
    lineage: tuple[str, ...],
    admin_level: str,
    geo_tag_ref: str,
) -> dict[str, Any]:
    canonical_name = _canonical_name(*lineage)
    aliases = [label] if label != canonical_name else []
    canonical_identity = f"admin_region:{geo_tag_ref}"
    return {
        "name": label,
        "canonicalName": canonical_name,
        "province": province,
        "city": city,
        "district": district,
        "source": "admin_region_catalog",
        "candidateKind": "admin_region",
        "adminLevel": admin_level,
        "canonicalIdentity": canonical_identity,
        "canonicalEntityRef": f"/entity/地点/城市/{canonical_name}",
        "entityType": ADMIN_ENTITY_TYPE,
        "geoTagRef": geo_tag_ref,
        "geoTagRefs": [geo_tag_ref],
        "typeTagRefs": [ADMIN_ENTITY_TYPE_TAG_REF],
        **({"aliases": aliases} if aliases else {}),
    }


def _pca_candidates(pca: dict[str, Any]) -> Iterator[dict[str, Any]]:
    for province, raw_cities in pca.items():
        province = str(province).strip()
        if not province:
            continue
        province_ref = f"{ADMIN_TAXONOMY_ROOT_REF}/{province}"
        yield _candidate(
            province=province,
            city=province,
            district=province,
            label=province,
            lineage=(province,),
            admin_level="province",
            geo_tag_ref=province_ref,
        )
        if not isinstance(raw_cities, dict):
            continue
        if province in _MUNICIPALITIES:
            for raw_districts in raw_cities.values():
                for district in _district_names(raw_districts):
                    yield _candidate(
                        province=province,
                        city=province,
                        district=district,
                        label=district,
                        lineage=(province, district),
                        admin_level="county",
                        geo_tag_ref=f"{province_ref}/{district}",
                    )
            continue
        for city, raw_districts in raw_cities.items():
            city = str(city).strip()
            if not city:
                continue
            if city in _DIRECT_COUNTY_GROUPS:
                for district in _district_names(raw_districts):
                    yield _candidate(
                        province=province,
                        city=province,
                        district=district,
                        label=district,
                        lineage=(province, district),
                        admin_level="county",
                        geo_tag_ref=f"{province_ref}/{district}",
                    )
                continue
            city_ref = f"{province_ref}/{city}"
            yield _candidate(
                province=province,
                city=city,
                district=city,
                label=city,
                lineage=(province, city),
                admin_level="prefecture",
                geo_tag_ref=city_ref,
            )
            for district in _district_names(raw_districts):
                yield _candidate(
                    province=province,
                    city=city,
                    district=district,
                    label=district,
                    lineage=(province, city, district),
                    admin_level="county",
                    geo_tag_ref=f"{city_ref}/{district}",
                )


def admin_entity_candidates(
    *,
    provinces: Iterable[str] | None = None,
    pca_path: Path | None = None,
    taxonomy_root: Path | None = None,
) -> list[dict[str, Any]]:
    """投影全国行政实体；不执行 encyclopedia-primary 来源资格判定。"""
    reference_path = pca_path or ADMIN_REGION_REFERENCE_PATH
    tags_root = taxonomy_root or CONTRACT_TAGS_ROOT
    pca = _load_pca(reference_path)
    taxonomy_provinces = _taxonomy_children(
        ADMIN_TAXONOMY_ROOT_REF,
        taxonomy_root=tags_root,
    )
    available = set(pca) | set(taxonomy_provinces)
    wanted = {
        str(province).strip()
        for province in (provinces or available)
        if str(province).strip()
    }
    unknown = sorted(wanted - available)
    if unknown:
        raise ValueError(f"行政实体 catalog 包含未知省级节点: {unknown}")

    candidates = [
        candidate
        for candidate in _pca_candidates(pca)
        if candidate["province"] in wanted
    ]
    for province in sorted((set(taxonomy_provinces) - set(pca)) & wanted):
        candidates.append(
            _candidate(
                province=province,
                city=province,
                district=province,
                label=province,
                lineage=(province,),
                admin_level="province",
                geo_tag_ref=f"{ADMIN_TAXONOMY_ROOT_REF}/{province}",
            )
        )
    return sorted(
        candidates,
        key=lambda row: (
            str(row["province"]),
            _ADMIN_LEVELS.index(str(row["adminLevel"])),
            str(row["geoTagRef"]),
        ),
    )


def admin_entity_catalog_report(
    *,
    provinces: Iterable[str] | None = None,
    pca_path: Path | None = None,
    taxonomy_root: Path | None = None,
) -> dict[str, Any]:
    """生成全国行政实体 coverage 报告，并显式列出缺失 taxonomy path。"""
    reference_path = pca_path or ADMIN_REGION_REFERENCE_PATH
    tags_root = taxonomy_root or CONTRACT_TAGS_ROOT
    pca = _load_pca(reference_path)
    candidates = admin_entity_candidates(
        provinces=provinces,
        pca_path=reference_path,
        taxonomy_root=tags_root,
    )
    selected_provinces = sorted({str(row["province"]) for row in candidates})
    counts = Counter(str(row["adminLevel"]) for row in candidates)
    missing_paths = sorted(
        {
            str(row["geoTagRef"])
            for row in candidates
            if not _taxonomy_node_exists(
                str(row["geoTagRef"]),
                taxonomy_root=tags_root,
            )
        }
    )
    if not entity_type_tag_node_exists(
        ADMIN_ENTITY_TYPE_TAG_REF,
        tags_root=tags_root,
    ):
        missing_paths.append(ADMIN_ENTITY_TYPE_TAG_REF)
    identities = [str(row["canonicalIdentity"]) for row in candidates]
    entity_refs = [str(row["canonicalEntityRef"]) for row in candidates]
    duplicate_identities = sorted(
        key for key, count in Counter(identities).items() if count > 1
    )
    duplicate_entity_refs = sorted(
        key for key, count in Counter(entity_refs).items() if count > 1
    )
    digest_payload = "\n".join(
        f"{row['canonicalIdentity']}\t{row['canonicalEntityRef']}\t{row['entityType']}"
        for row in candidates
    )
    by_province: dict[str, dict[str, int]] = {}
    for province in selected_provinces:
        province_counts = Counter(
            str(row["adminLevel"])
            for row in candidates
            if row["province"] == province
        )
        by_province[province] = {
            **{level: province_counts.get(level, 0) for level in _ADMIN_LEVELS},
            "total": sum(province_counts.values()),
        }
    taxonomy_provinces = set(
        _taxonomy_children(ADMIN_TAXONOMY_ROOT_REF, taxonomy_root=tags_root)
    )
    report_counts = {
        **{level: counts.get(level, 0) for level in _ADMIN_LEVELS},
        "total": len(candidates),
    }
    return {
        "schema": "quwoquan_data.admin_entity_catalog_coverage",
        "scope": "national" if provinces is None else "province_subset",
        "sources": {
            "adminRegionReference": str(reference_path),
            "taxonomyRoot": str(tags_root / ADMIN_TAXONOMY_ROOT_REF),
        },
        "entityType": ADMIN_ENTITY_TYPE,
        "entityTypeTagRef": ADMIN_ENTITY_TYPE_TAG_REF,
        "selectedProvinces": selected_provinces,
        "sourceProvinceCounts": {
            "pca": len(set(pca) & set(selected_provinces)),
            "taxonomyOnly": len(
                (taxonomy_provinces - set(pca)) & set(selected_provinces)
            ),
        },
        "counts": report_counts,
        "byProvince": by_province,
        "missingTaxonomyPaths": sorted(set(missing_paths)),
        "duplicateCanonicalIdentities": duplicate_identities,
        "duplicateCanonicalEntityRefs": duplicate_entity_refs,
        "catalogDigest": "sha256:"
        + hashlib.sha256(digest_payload.encode("utf-8")).hexdigest(),
    }


def admin_entity_partitions(
    *,
    provinces: Iterable[str] | None = None,
    pca_path: Path | None = None,
    taxonomy_root: Path | None = None,
) -> list[dict[str, Any]]:
    """把行政实体 catalog 投影成 execution selection 可消费的 partitions。"""
    candidates = admin_entity_candidates(
        provinces=provinces,
        pca_path=pca_path,
        taxonomy_root=taxonomy_root,
    )
    return [
        {
            "key": province,
            "leaves": [
                row for row in candidates if str(row["province"]) == province
            ],
        }
        for province in sorted({str(row["province"]) for row in candidates})
    ]


__all__ = [
    "ADMIN_ENTITY_TYPE",
    "ADMIN_ENTITY_TYPE_TAG_REF",
    "ADMIN_REGION_REFERENCE_PATH",
    "ADMIN_TAXONOMY_ROOT_REF",
    "admin_entity_candidates",
    "admin_entity_catalog_report",
    "admin_entity_partitions",
]
