"""Merge evidence-backed coverage candidates into the canonical provincial master list."""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from governance.coverage.master_list import (
    COVERAGE_MASTER_ROOT,
    admin_children,
    admin_geo_ref,
    city_is_district_level,
    dump_master_list_file,
    iter_master_leaves,
    load_master_list_file,
    master_list_files,
)
from governance.coverage.entity_type_taxonomy import (
    CONTRACT_TAGS_ROOT,
    entity_type_tag_node_exists,
    resolve_primary_entity_type,
)
from governance.coverage.coverage_runtime import coverage_workspace_root, now_iso
from governance.coverage.coverage_semantics import (
    normalize_name,
    semantic_rejection_reason as _semantic_rejection_reason,
)

# 名称 → 类型规则（顺序即优先级；(pattern, entityType, typeTagRef)）。
# 保守原则：规则只覆盖结论性后缀；不结论的进缺口清单交 Agent 语义复核。
_NAME_TYPE_RULES: tuple[tuple[str, str, str], ...] = (
    (r"(博物馆|纪念馆|陈列馆|美术馆|科技馆|展览馆)$", "地点/博物馆", "Entity/地点/博物馆"),
    (r"(寺|禅寺|禅院|庙|道观|教堂|清真寺|尼庵|庵)$", "地点/宗教场所", "Entity/地点/宗教场所"),
    (r"(古镇|古城|古街|老街)$", "地点/古镇", "Entity/地点/古镇/历史古镇"),
    (r"(古村|古村落|民族村)$", "地点/古镇", "Entity/地点/古镇/特色古村"),
    (r"(遗址|故居|旧址|古墓|墓|陵园|书院|文庙|会馆|祠|祠堂|牌坊|古塔|塔)$", "地点/遗址", "Entity/地点/遗址/历史建筑"),
    (r"温泉(度假村|度假区)?$", "地点/温泉", "Entity/地点/温泉"),
    (r"(乐园|游乐园|欢乐谷|海洋公园|野生动物园|动物园|水上世界)$", "地点/主题乐园", "Entity/地点/主题乐园/综合主题乐园"),
    (r"(湿地公园)$", "地点/景区", "Entity/地点/景区/湿地公园"),
    (r"(地质公园)$", "地点/景区", "Entity/地点/景区/地质公园"),
    (r"(国家森林公园|自然保护区)$", "地点/景区", "Entity/地点/景区/自然保护区"),
    (r"(公园|植物园)$", "地点/公园", "Entity/地点/公园"),
    (r"(山|峰|岭|崮|岩)$", "地点/自然景观", "Entity/地点/自然景观/山岳"),
    (r"(湖|潭|瀑布|泉|溪|江|河|海滩|沙滩)$", "地点/自然景观", "Entity/地点/自然景观/水体"),
    (r"(岛|列岛|群岛|半岛)$", "地点/自然景观", "Entity/地点/自然景观/海岸海岛"),
    (r"(峡谷|峡|溶洞|洞)$", "地点/自然景观", "Entity/地点/自然景观/山岳"),
    (r"(草原|草甸|森林)$", "地点/自然景观", "Entity/地点/自然景观/森林草原"),
    (r"(湿地)$", "地点/自然景观", "Entity/地点/自然景观/湿地荒漠"),
    (r"(广场|步行街|历史文化街区|文化街|风情街)$", "地点/打卡地", "Entity/地点/打卡地"),
)

# 分类证据 → 景区等级叶子（政府名录镜像：A 级/世界遗产分类是结论性等级证据）。
_CATEGORY_GRADE_RULES: tuple[tuple[str, str, str], ...] = (
    ("国家5A级旅游景区", "地点/景区", "Entity/地点/景区/5A景区"),
    ("国家4A级旅游景区", "地点/景区", "Entity/地点/景区/4A景区"),
    ("国家3A级旅游景区", "地点/景区", "Entity/地点/景区/3A景区"),
    ("世界遗产", "地点/景区", "Entity/地点/景区/世界遗产"),
    ("国家公园", "地点/景区", "Entity/地点/景区/国家公园"),
    ("全国重点文物保护单位", "地点/遗址", "Entity/地点/遗址/文化遗产"),
    # 省保单位名录镜像分类（「浙江省文物保护单位」「四川省文物保护单位」等）：
    # 政府名录结论性证据，映射历史建筑叶子（与主清单存量遗址项惯例一致）；
    # 必须排在「全国重点」之后作兜底（子串匹配顺序敏感）。
    ("文物保护单位", "地点/遗址", "Entity/地点/遗址/历史建筑"),
)

# OSM tag → 类型（结论性映射；attraction 走名称规则）。
_OSM_TAG_TYPE_RULES: tuple[tuple[str, str, str, str], ...] = (
    ("tourism", "museum", "地点/博物馆", "Entity/地点/博物馆"),
    ("tourism", "theme_park", "地点/主题乐园", "Entity/地点/主题乐园/综合主题乐园"),
    ("amenity", "place_of_worship", "地点/宗教场所", "Entity/地点/宗教场所"),
    ("historic", "monastery", "地点/宗教场所", "Entity/地点/宗教场所"),
    ("historic", "archaeological_site", "地点/遗址", "Entity/地点/遗址/考古遗址"),
    ("historic", "*", "地点/遗址", "Entity/地点/遗址/历史建筑"),
    ("leisure", "park", "地点/公园", "Entity/地点/公园"),
    ("natural", "peak", "地点/自然景观", "Entity/地点/自然景观/山岳"),
    ("natural", "water", "地点/自然景观", "Entity/地点/自然景观/水体"),
    ("natural", "beach", "地点/自然景观", "Entity/地点/自然景观/海岸海岛"),
)
def _existing_name_index(country: str = "中国") -> dict[str, str]:
    """全国主清单 identity/fallback 索引；名称本身绝不作为 identity。"""
    index: dict[str, str] = {}
    for path in master_list_files():
        data = load_master_list_file(path)
        rel = path.as_posix()
        for district, leaf in iter_master_leaves(data):
            identity = leaf.get("identityRefs") if isinstance(leaf.get("identityRefs"), dict) else {}
            for identity_key in _identity_keys(identity):
                index.setdefault(identity_key, rel)
            fallback = _fallback_identity_key(
                name=str(leaf.get("canonicalName") or leaf.get("name") or ""),
                district=district,
                coordinates=(
                    leaf.get("coordinates")
                    if isinstance(leaf.get("coordinates"), dict)
                    else {}
                ),
            )
            if fallback:
                index.setdefault(fallback, rel)
    return index


def _identity_keys(identity: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    qid = str(identity.get("qid") or "").strip().upper()
    if re.fullmatch(r"Q[1-9][0-9]*", qid):
        keys.append(f"qid:{qid}")
    pageid = int(identity.get("wikipediaPageId") or 0)
    if pageid > 0:
        keys.append(f"wikipedia_pageid:{pageid}")
    osm_type = str(identity.get("osmType") or "").strip()
    osm_id = str(identity.get("osmId") or "").strip()
    if osm_type in {"node", "way", "relation"} and osm_id.isdigit():
        keys.append(f"osm:{osm_type}:{osm_id}")
    return keys


def _fallback_identity_key(
    *, name: str, district: str, coordinates: dict[str, Any]
) -> str | None:
    normalized = normalize_name(name)
    lat = float(coordinates.get("lat") or 0)
    lon = float(coordinates.get("lon") or 0)
    if not normalized or not district or not lat or not lon:
        return None
    return f"name_county_coord:{normalized}|{district}|{lat:.5f}|{lon:.5f}"


def _candidate_identity_key(item: dict[str, Any]) -> str | None:
    identity = item.get("identityRefs") if isinstance(item.get("identityRefs"), dict) else {}
    keys = _identity_keys(identity)
    if keys:
        return keys[0]
    coordinates = item.get("coordinates") if isinstance(item.get("coordinates"), dict) else {}
    return _fallback_identity_key(
        name=str(item.get("name") or ""),
        district=str(item.get("district") or ""),
        coordinates=coordinates,
    )


def _classify_by_category(categories: list[str]) -> tuple[str, str] | None:
    for marker, etype, ref in _CATEGORY_GRADE_RULES:
        if any(marker in cat for cat in categories):
            return etype, ref
    return None


def _classify_by_name(name: str) -> tuple[str, str] | None:
    for pattern, etype, ref in _NAME_TYPE_RULES:
        if re.search(pattern, name):
            return etype, ref
    return None


def _classify_by_osm(tags: dict[str, str]) -> tuple[str, str] | None:
    for key, value, etype, ref in _OSM_TAG_TYPE_RULES:
        actual = str(tags.get(key) or "")
        if actual and (value == "*" or actual == value):
            return etype, ref
    return None


def _resolve_district_from_text(
    text: str,
    *,
    province: str,
    country: str = "中国",
) -> tuple[str, str] | None:
    """从 wiki extract/categories 文本解析 (city, district)。

    先锁市州（文本含市州名），再在该市州区县中匹配；跨市州同名区县
    （如四川两个市中区）靠市州先锁避免误归。仅当唯一命中才结论。
    """
    province_geo = admin_geo_ref(country, province)
    matched: list[tuple[str, str]] = []
    for city in admin_children(province_geo):
        if city_is_district_level(country, province, city):
            if city in text:
                matched.append((city, city))
            continue
        for district in admin_children(f"{province_geo}/{city}"):
            if district in text:
                # 区县名命中先记录；同市州多区县或跨市州多命中时由下方裁决
                matched.append((city, district))
    unique = sorted(set(matched))
    if len(unique) == 1:
        return unique[0]
    # 多命中：若唯一一个市州命中了区县且文本明确含该市州名，取之
    cities_hit = {c for c, _ in unique}
    if len(cities_hit) > 1:
        text_cities = [c for c in cities_hit if c in text]
        if len(text_cities) == 1:
            city_districts = sorted({d for c, d in unique if c == text_cities[0]})
            if len(city_districts) == 1:
                return text_cities[0], city_districts[0]
    return None


def _type_evidence(items: list[dict[str, Any]], name: str) -> tuple[str, list[str]] | None:
    refs: set[str] = set()
    for item in items:
        for ref in item.get("typeTagRefs") or []:
            normalized_ref = str(ref).strip().strip("/")
            if normalized_ref.startswith("Entity/地点/") and entity_type_tag_node_exists(
                normalized_ref, tags_root=CONTRACT_TAGS_ROOT
            ):
                refs.add(normalized_ref)
        if item.get("source") == "wiki_category":
            classified = _classify_by_category(
                [*(item.get("categories") or []), *(item.get("sourceCategories") or [])]
            )
            if classified:
                refs.add(classified[1])
    if not refs and any(item.get("source") != "osm_poi" for item in items):
        classified = _classify_by_name(name)
        if classified:
            refs.add(classified[1])
    if not refs:
        return None
    primary_name = resolve_primary_entity_type(
        {ref.split("/")[2] for ref in refs if len(ref.split("/")) >= 3}
    )
    primary_prefix = f"Entity/地点/{primary_name}"
    ordered_refs = sorted(
        refs,
        key=lambda ref: (0 if ref == primary_prefix or ref.startswith(primary_prefix + "/") else 1, ref),
    )
    return f"地点/{primary_name}", ordered_refs


_SOURCE_LOCATION_PRIORITY = {
    "wikidata_geo": 0,
    "wiki_category": 1,
    "baidu_baike_search": 2,
    "toutiao_baike_search": 3,
    "osm_poi": 4,
}


def _candidate_locations(
    items: list[dict[str, Any]], *, country: str
) -> list[tuple[str, str, str, str]]:
    locations: set[tuple[str, str, str, str]] = set()
    for item in items:
        province = str(item.get("province") or "")
        city = str(item.get("city") or "")
        district = str(item.get("district") or "")
        if not city or not district:
            text = " ".join(
                [str(item.get("extract") or ""), *(item.get("categories") or [])]
            )
            resolved = _resolve_district_from_text(
                text, province=province, country=country
            )
            if resolved:
                city, district = resolved
        if province and city and district:
            geo_ref = (
                admin_geo_ref(country, province, city)
                if city == district and city_is_district_level(country, province, city)
                else admin_geo_ref(country, province, city, district)
            )
            locations.add((province, city, district, geo_ref))
    return sorted(locations)


def merge_candidates(
    provinces: list[str],
    *,
    candidate_files: list[Path],
    apply: bool = False,
    country: str = "中国",
) -> dict[str, Any]:
    """去重 + 打标 + （--apply）写回；不结论候选进缺口清单。"""
    existing = _existing_name_index(country)
    wanted = set(provinces)
    merged: dict[str, dict[str, Any]] = {}
    rejected_items: list[dict[str, Any]] = []
    unresolved_identity_items: list[dict[str, Any]] = []
    for path in candidate_files:
        with Path(path).open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                item = json.loads(line)
                if str(item.get("province") or "") not in wanted:
                    continue
                semantic_reason = _semantic_rejection_reason(item)
                if semantic_reason:
                    rejected_items.append({"reason": semantic_reason, "evidence": item})
                    continue
                normalized_name = normalize_name(str(item.get("name") or ""))
                if not normalized_name:
                    continue
                key = _candidate_identity_key(item)
                if not key:
                    unresolved_identity_items.append(item)
                    continue
                slot = merged.setdefault(key, {"name": item["name"], "items": []})
                slot["items"].append(item)

    appended: list[dict[str, Any]] = []
    duplicates = 0
    gaps: list[dict[str, Any]] = [
        {
            "name": str(item.get("name") or ""),
            "province": str(item.get("province") or ""),
            "missing": ["stableIdentityOrNameCountyCoordinate"],
            "reason": "identity_unresolved_without_guessing",
            "evidence": [item],
        }
        for item in unresolved_identity_items
    ]
    patches: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = {}
    osm_only_rejected = 0
    cross_region_count = 0
    canonical_names: set[str] = set()
    for path in master_list_files():
        data = load_master_list_file(path)
        canonical_names.update(
            str(leaf.get("canonicalName") or "").strip()
            for _district, leaf in iter_master_leaves(data)
            if str(leaf.get("canonicalName") or "").strip()
        )

    for key, slot in sorted(merged.items()):
        name = str(slot["name"])
        if key in existing:
            duplicates += 1
            continue
        items = slot["items"]
        province = str(items[0].get("province"))
        non_osm_items = [item for item in items if item.get("source") != "osm_poi"]
        if not non_osm_items:
            osm_only_rejected += 1
            gaps.append(
                {
                    "name": name,
                    "province": province,
                    "missing": ["nonOsmCorroboration"],
                    "reason": "osm_poi is discovery-only and cannot directly enter master list",
                    "evidence": items[:2],
                }
            )
            continue
        classified = _type_evidence(items, name)
        locations = _candidate_locations(items, country=country)
        if not classified or not locations:
            gaps.append(
                {
                    "name": name,
                    "province": province,
                    "missing": [
                        *(["entityType"] if not classified else []),
                        *(["district"] if not locations else []),
                    ],
                    "evidence": items[:2],
                }
            )
            continue
        etype, type_refs = classified
        ordered_items = sorted(
            items,
            key=lambda item: (
                _SOURCE_LOCATION_PRIORITY.get(str(item.get("source") or ""), 99),
                str(item.get("province") or ""),
                str(item.get("city") or ""),
                str(item.get("district") or ""),
            ),
        )
        primary_location: tuple[str, str, str, str] | None = None
        for item in ordered_items:
            item_location = _candidate_locations([item], country=country)
            if item_location:
                primary_location = item_location[0]
                break
        primary_location = primary_location or locations[0]
        province, city, district, primary_geo_ref = primary_location
        geo_refs = sorted({location[3] for location in locations})
        if len(geo_refs) > 1:
            cross_region_count += 1
        identity_refs: dict[str, Any] = {}
        for identity_field in ("qid", "wikipediaPageId", "osmType", "osmId"):
            for item in items:
                identity = (
                    item.get("identityRefs")
                    if isinstance(item.get("identityRefs"), dict)
                    else {}
                )
                value = identity.get(identity_field)
                if value not in (None, "", 0):
                    identity_refs[identity_field] = value
                    break
        coordinates: dict[str, float] = {}
        for item in items:
            raw_coordinates = (
                item.get("coordinates")
                if isinstance(item.get("coordinates"), dict)
                else {}
            )
            lat = float(raw_coordinates.get("lat") or 0)
            lon = float(raw_coordinates.get("lon") or 0)
            if lat and lon:
                coordinates = {"lat": lat, "lon": lon}
                break
        canonical_name = name
        if canonical_name in canonical_names:
            canonical_name = f"{name}（{district}）"
        suffix = 2
        while canonical_name in canonical_names:
            canonical_name = f"{name}（{district}{suffix}）"
            suffix += 1
        canonical_names.add(canonical_name)
        entry = {
            "name": name,
            "canonicalName": canonical_name,
            "entityType": etype,
            "typeTagRefs": type_refs,
            "geoTagRef": primary_geo_ref,
            "discoverySources": sorted(
                {str(item.get("source") or "") for item in items if str(item.get("source") or "")}
            ),
        }
        if len(geo_refs) > 1:
            entry["geoTagRefs"] = [primary_geo_ref, *[ref for ref in geo_refs if ref != primary_geo_ref]]
        if identity_refs:
            entry["identityRefs"] = identity_refs
        if coordinates:
            entry["coordinates"] = coordinates
        patches.setdefault((province, city), {}).setdefault(district, []).append(entry)
        appended.append(
            {
                "name": name,
                "canonicalName": canonical_name,
                "province": province,
                "city": city,
                "district": district,
                "entityType": etype,
                "typeTagRefs": type_refs,
                "geoTagRef": primary_geo_ref,
                "geoTagRefs": entry.get("geoTagRefs") or [primary_geo_ref],
                "identityRefs": identity_refs,
            }
        )

    written_files: list[str] = []
    if apply:
        for (province, city), district_map in sorted(patches.items()):
            path = COVERAGE_MASTER_ROOT / province / f"{city}.yaml"
            if not path.is_file():
                gaps.append(
                    {"name": f"<市州文件缺失: {province}/{city}>", "province": province, "missing": ["cityFile"], "evidence": []}
                )
                continue
            data = load_master_list_file(path)
            districts = data.setdefault("districts", [])
            by_district = {str(g.get("district") or ""): g for g in districts if isinstance(g, dict)}
            for district, entries in sorted(district_map.items()):
                group = by_district.get(district)
                if group is None:
                    group = {"district": district, "leaves": []}
                    districts.append(group)
                    by_district[district] = group
                leaves = group.setdefault("leaves", [])
                next_priority = max(
                    [int(l.get("selectionPriority") or 0) for l in leaves if isinstance(l, dict)] or [0]
                ) + 1
                for entry in entries:
                    leaf = dict(entry)
                    leaf["selectionPriority"] = next_priority
                    next_priority += 1
                    leaves.append(leaf)
            dump_master_list_file(path, data)
            written_files.append(path.as_posix())

    expand_runtime_dir = coverage_workspace_root()
    expand_runtime_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = {
        "schema": "quwoquan_data.coverage_merge_report",
        "generatedAt": now_iso(),
        "provinces": provinces,
        "apply": apply,
        "candidatesUnique": len(merged),
        "duplicatesAgainstMaster": duplicates,
        "appended": len(appended),
        "appendedItems": appended,
        "gaps": len(gaps),
        "osmOnlyRejected": osm_only_rejected,
        "semanticRejected": len(rejected_items),
        "semanticRejectReasons": dict(
            Counter(str(row["reason"]) for row in rejected_items).most_common()
        ),
        "identityUnresolved": len(unresolved_identity_items),
        "crossRegionCanonicalEntities": cross_region_count,
        "gapItems": gaps,
        "semanticRejectedItems": rejected_items,
        "writtenFiles": written_files,
    }
    report_path = expand_runtime_dir / f"merge_report_{stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["reportPath"] = str(report_path)
    return report
