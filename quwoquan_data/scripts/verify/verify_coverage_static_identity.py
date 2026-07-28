"""全国地点静态覆盖身份门（discovery_seed/2，仿 verify_tag_tree R1-R12 模式）。

walk `reference/travel/entities/china/{省}/{市州}.yaml`（目录即行政层级、市州级
一文件自闭环、无总控 index——裁决 8），逐文件校验：

  C1  - 目录归属：省目录名/市州文件名命中行政区树 `Topic/地理/行政区/{国}` 对应层级节点
  C2  - schema 同口径结构门：schema const、必填字段、字段类型、
        未知字段阻断（必填集/enum/字段白名单从 schema/governance/master_list.schema.json 读取，
        不维护第二真相源；homepageStatus 等易变状态字段借未知字段门天然阻断）
  C3  - 归属一致性：country/province/city 字段与磁盘路径一致
  C4  - district 命中行政区树该市州下的子节点；直辖市口径（市州槽位本身是
        行政区树叶子，如 中国/北京市/东城区）：文件即区县级，districts 恰一组
        且 district == city，geoTagRef 指向市州槽位叶子本身
  C5  - entityType 形如 `地点/{一级节点}`：命中 `Entity/地点` 树一级节点，
        且在试点 scope（PILOT_PRIMARY_TYPES，裁决 6）内
  C6  - typeTagRefs 命中 `Entity/地点/**` 已发布节点；主类型对应叶子必须在数组中
  C7  - geoTagRef = 本组区县的行政区树叶子路径（区县级主归属，与 district 分组一致）
  C8  - geoTagRefs 存在时：每项命中行政区树叶子，且 geoTagRef ∈ geoTagRefs
  C9  - canonicalName 跨文件全局唯一（跨省地点仅主归属省登记一次——裁决 7）
  C10 - 静态字段派生的 coverageKey 全局唯一

标签契约树按「契约跟代码走」以仓内路径解析（core.entity_type_taxonomy），
不随运行时 QWQ_DATA_ROOT 漂移。经 `qwq-data verify coverage-static-identity` 暴露，
经 `qwq-data verify coverage-static-identity` 暴露，本文件不提供业务直跑入口。
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from governance.coverage.master_list import (
    ADMIN_REGION_PREFIX,
    COVERAGE_MASTER_ROOT,
    MASTER_LIST_SCHEMA_PATH,
    coverage_identity_key,
    is_leaf_tag_node as _is_leaf_tag_node_shared,
    is_tag_node as _is_tag_node_shared,
)
from governance.coverage.admin_entity_catalog import admin_entity_catalog_report
from governance.coverage.entity_type_taxonomy import (
    CONTRACT_TAGS_ROOT,
    PILOT_PRIMARY_TYPES,
    PLACE_DOMAIN,
    entity_top_level_types,
    entity_type_tag_node_exists,
)


def _load_schema_contract(schema_path: Path) -> dict:
    """从 schema 文件读取同口径校验契约（const/required/enum/字段白名单）。"""
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    leaf_schema = (
        schema["properties"]["districts"]["items"]["properties"]["leaves"]["items"]
    )
    return {
        "schema": schema["properties"]["schema"]["const"],
        "fileRequired": list(schema.get("required") or []),
        "fileFields": set(schema.get("properties") or {}),
        "districtRequired": list(schema["properties"]["districts"]["items"].get("required") or []),
        "districtFields": set(schema["properties"]["districts"]["items"].get("properties") or {}),
        "leafRequired": list(leaf_schema.get("required") or []),
        "leafFields": set(leaf_schema.get("properties") or {}),
    }


# 标签树节点判定唯一实现在 core.coverage_master_list（单一真相源）。
_is_tag_node = _is_tag_node_shared
_is_leaf_tag_node = _is_leaf_tag_node_shared


def _check_leaf(
    leaf: dict,
    *,
    rel: str,
    district_geo_ref: str,
    contract: dict,
    valid_place_types: set[str],
    tags_root: Path,
    errors: list[str],
) -> str | None:
    """校验单个 leaf；返回 canonicalName（供全局唯一性核对）。"""
    label = f"{rel}: {leaf.get('canonicalName') or leaf.get('name') or '<未命名>'}"

    unknown = set(leaf) - contract["leafFields"]
    if unknown:
        errors.append(f"C2: {label} 含契约外字段 {sorted(unknown)}（homepageStatus 等易变状态不进主清单）")
    for field in contract["leafRequired"]:
        if field not in leaf or leaf.get(field) in (None, "", []):
            errors.append(f"C2: {label} 缺必填字段 {field}")

    priority = leaf.get("selectionPriority")
    if priority is not None and (isinstance(priority, bool) or not isinstance(priority, int) or priority < 1):
        errors.append(f"C2: {label} selectionPriority 必须是 >=1 整数，实得 {priority!r}")
    for list_field in ("typeTagRefs", "geoTagRefs", "aliases"):
        value = leaf.get(list_field)
        if value is not None and not isinstance(value, list):
            errors.append(f"C2: {label} {list_field} 必须是数组")

    # C5: entityType 主类型单值
    entity_type = str(leaf.get("entityType") or "")
    primary_name = ""
    if entity_type:
        parts = entity_type.split("/")
        if len(parts) != 2 or parts[0] != PLACE_DOMAIN:
            errors.append(f"C5: {label} entityType '{entity_type}' 必须形如 地点/{{Entity地点一级节点}}")
        else:
            primary_name = parts[1]
            if primary_name not in valid_place_types:
                errors.append(f"C5: {label} entityType '{entity_type}' 未命中 Entity/地点 树一级节点")
            elif primary_name not in PILOT_PRIMARY_TYPES:
                errors.append(
                    f"C5: {label} entityType '{entity_type}' 不在试点 scope {sorted(PILOT_PRIMARY_TYPES)}"
                )

    # C6: typeTagRefs 命中已发布叶子路径（精确到叶子；一级节点无子级时本身即叶子）
    #     + 主类型对应叶子必须在数组中
    type_refs = [str(t) for t in (leaf.get("typeTagRefs") or []) if str(t).strip()]
    for ref in type_refs:
        if not ref.startswith(f"Entity/{PLACE_DOMAIN}/"):
            errors.append(f"C6: {label} typeTagRef '{ref}' 必须以 Entity/{PLACE_DOMAIN}/ 开头")
        elif not entity_type_tag_node_exists(ref, tags_root=tags_root):
            errors.append(f"C6: {label} typeTagRef '{ref}' 未命中已发布标签节点")
        elif not _is_leaf_tag_node(tags_root, ref):
            errors.append(f"C6: {label} typeTagRef '{ref}' 必须精确到叶子（该节点下仍有子级细分）")
    if primary_name and type_refs:
        primary_prefix = f"Entity/{PLACE_DOMAIN}/{primary_name}"
        if not any(ref == primary_prefix or ref.startswith(primary_prefix + "/") for ref in type_refs):
            errors.append(f"C6: {label} typeTagRefs 缺少主类型 '{primary_name}' 对应叶子（{primary_prefix}[/**]）")

    # C7: geoTagRef 区县级主归属，与 district 分组一致
    geo_ref = str(leaf.get("geoTagRef") or "")
    if geo_ref:
        if geo_ref != district_geo_ref:
            errors.append(f"C7: {label} geoTagRef '{geo_ref}' 与所在区县分组 '{district_geo_ref}' 不一致")
        elif not _is_leaf_tag_node(tags_root, geo_ref):
            errors.append(f"C7: {label} geoTagRef '{geo_ref}' 未命中行政区树叶子")

    # C8: geoTagRefs 全量数组（含主归属）
    geo_refs = [str(g) for g in (leaf.get("geoTagRefs") or []) if str(g).strip()]
    if geo_refs:
        if geo_ref and geo_ref not in geo_refs:
            errors.append(f"C8: {label} geoTagRefs 必须包含主归属 geoTagRef '{geo_ref}'")
        for ref in geo_refs:
            if not ref.startswith(ADMIN_REGION_PREFIX + "/"):
                errors.append(f"C8: {label} geoTagRefs 项 '{ref}' 必须以 {ADMIN_REGION_PREFIX}/ 开头")
            elif not _is_leaf_tag_node(tags_root, ref):
                errors.append(f"C8: {label} geoTagRefs 项 '{ref}' 未命中行政区树叶子")

    canonical = str(leaf.get("canonicalName") or "").strip()
    return canonical or None


def scan_master_list(
    *,
    coverage_root: Path | None = None,
    tags_root: Path | None = None,
    schema_path: Path | None = None,
) -> tuple[list[str], int, int]:
    """walk 主清单目录，返回 (errors, fileCount, leafCount)。"""
    root = coverage_root or COVERAGE_MASTER_ROOT
    tags = tags_root or CONTRACT_TAGS_ROOT
    contract = _load_schema_contract(schema_path or MASTER_LIST_SCHEMA_PATH)
    errors: list[str] = []
    file_count = 0
    leaf_count = 0
    seen_canonical: dict[str, str] = {}
    seen_coverage_key: dict[str, str] = {}

    if not root.is_dir():
        return ([f"C1: 主清单根目录不存在: {root}"], 0, 0)
    declared_country: str | None = None

    for path in sorted(root.rglob("*.yaml")):
        rel = path.relative_to(root.parent).as_posix()
        file_count += 1
        parts = path.relative_to(root).parts
        if len(parts) != 2:
            errors.append(f"C1: {rel} 必须位于 <country-root>/{{省}}/{{市州}}.yaml 两级路径")
            continue
        province, city = parts[0], path.stem

        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            errors.append(f"C2: {rel} YAML 解析失败: {exc}")
            continue
        if not isinstance(data, dict):
            errors.append(f"C2: {rel} 顶层必须是 mapping")
            continue

        country = str(data.get("country") or "").strip()
        if not country:
            errors.append(f"C2: {rel} 缺 country")
            continue
        if declared_country is None:
            declared_country = country
            country_geo = f"{ADMIN_REGION_PREFIX}/{country}"
            if not _is_tag_node(tags, country_geo):
                errors.append(
                    f"C1: country '{country}' 未命中行政区树 {country_geo}"
                )
        elif country != declared_country:
            errors.append(
                f"C3: {rel} country='{country}' 与 reference 根其他文件 '{declared_country}' 不一致"
            )
        country_geo = f"{ADMIN_REGION_PREFIX}/{country}"
        province_geo = f"{country_geo}/{province}"
        city_geo = f"{province_geo}/{city}"
        if not _is_tag_node(tags, province_geo):
            errors.append(f"C1: {rel} 省目录 '{province}' 未命中行政区树 {province_geo}")
        if not _is_tag_node(tags, city_geo):
            errors.append(f"C1: {rel} 市州文件 '{city}' 未命中行政区树 {city_geo}")

        unknown = set(data) - contract["fileFields"]
        if unknown:
            errors.append(f"C2: {rel} 含契约外字段 {sorted(unknown)}")
        for field in contract["fileRequired"]:
            if not data.get(field):
                errors.append(f"C2: {rel} 缺必填字段 {field}")
        version = str(data.get("schema") or "")
        if version and version != contract["schema"]:
            errors.append(f"C2: {rel} schema '{version}' != '{contract['schema']}'")

        # C3: 归属字段 ↔ 路径一致
        for field, expected in (("province", province), ("city", city)):
            actual = str(data.get(field) or "")
            if actual and actual != expected:
                errors.append(f"C3: {rel} {field}='{actual}' 与路径 '{expected}' 不一致")

        districts = data.get("districts")
        if not isinstance(districts, list):
            continue
        valid_place_types = set(entity_top_level_types(PLACE_DOMAIN, tags_root=tags))
        # 直辖市口径：市州槽位本身是行政区树叶子（如 中国/北京市/东城区），
        # 文件即区县级，districts 只允许 district == city，geoTagRef 即市州槽位本身。
        city_is_district = _is_tag_node(tags, city_geo) and _is_leaf_tag_node(tags, city_geo)
        for group in districts:
            if not isinstance(group, dict):
                errors.append(f"C2: {rel} districts 项必须是 mapping")
                continue
            unknown = set(group) - contract["districtFields"]
            if unknown:
                errors.append(f"C2: {rel} districts 项含契约外字段 {sorted(unknown)}")
            district = str(group.get("district") or "")
            if not district:
                errors.append(f"C2: {rel} districts 项缺 district")
                continue
            if city_is_district:
                district_geo = city_geo
                if district != city:
                    errors.append(
                        f"C4: {rel} 直辖市区县级文件只允许 district == '{city}'，实得 '{district}'"
                    )
            else:
                district_geo = f"{city_geo}/{district}"
                if not _is_tag_node(tags, district_geo):
                    errors.append(f"C4: {rel} 区县 '{district}' 未命中行政区树 {district_geo}")
            leaves = group.get("leaves")
            if not isinstance(leaves, list) or not leaves:
                errors.append(f"C2: {rel} 区县 '{district}' leaves 必须是非空数组")
                continue
            for leaf in leaves:
                if not isinstance(leaf, dict):
                    errors.append(f"C2: {rel} 区县 '{district}' 含非 mapping leaf")
                    continue
                leaf_count += 1
                canonical = _check_leaf(
                    leaf,
                    rel=rel,
                    district_geo_ref=district_geo,
                    contract=contract,
                    valid_place_types=valid_place_types,
                    tags_root=tags,
                    errors=errors,
                )
                if canonical:
                    prior = seen_canonical.get(canonical)
                    if prior:
                        errors.append(
                            f"C9: canonicalName '{canonical}' 跨文件重复（{prior} ↔ {rel}；"
                            "跨省地点仅主归属省登记一次）"
                        )
                    else:
                        seen_canonical[canonical] = rel
                    try:
                        coverage_key = coverage_identity_key(
                            country=country,
                            province=province,
                            city=city,
                            district=district,
                            entity_type=str(leaf.get("entityType") or ""),
                            canonical_name=canonical,
                        )
                    except ValueError as exc:
                        errors.append(f"C10: {rel}: {canonical} 无法派生 coverageKey: {exc}")
                        continue
                    prior_key = seen_coverage_key.get(coverage_key)
                    current_ref = f"{rel}#{canonical}"
                    if prior_key:
                        errors.append(
                            f"C10: coverageKey '{coverage_key}' 冲突（{prior_key} ↔ {current_ref}）"
                        )
                    else:
                        seen_coverage_key[coverage_key] = current_ref

    return errors, file_count, leaf_count


def main() -> int:
    errors, file_count, leaf_count = scan_master_list()
    print(f"[verify-coverage-static-identity] files={file_count} leaves={leaf_count}")
    catalog_report = admin_entity_catalog_report()
    catalog_counts = catalog_report["counts"]
    print(
        "[verify-coverage-static-identity] "
        f"admin-provinces={catalog_counts['province']} "
        f"admin-prefectures={catalog_counts['prefecture']} "
        f"admin-counties={catalog_counts['county']} "
        f"admin-total={catalog_counts['total']}"
    )
    errors.extend(
        f"C11: 行政实体 catalog 缺 taxonomy path '{path}'"
        for path in catalog_report["missingTaxonomyPaths"]
    )
    errors.extend(
        f"C12: 行政实体 canonical identity 重复 '{identity}'"
        for identity in catalog_report["duplicateCanonicalIdentities"]
    )
    errors.extend(
        f"C13: 行政实体 canonical entityRef 重复 '{entity_ref}'"
        for entity_ref in catalog_report["duplicateCanonicalEntityRefs"]
    )
    if errors:
        print(f"[verify-coverage-static-identity] FAILED ({len(errors)} error(s)):")
        for item in errors[:100]:
            print(f"  ✗ {item}")
        if len(errors) > 100:
            print(f"  ... 还有 {len(errors) - 100} 条")
        return 1
    print("[verify-coverage-static-identity] PASSED")
    return 0
