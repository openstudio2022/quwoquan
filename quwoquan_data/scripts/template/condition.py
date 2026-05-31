"""Region / season condition-axis validation gates.

校验地域/季节条件修饰维的 catalog 完整性、conditionAxes 引用合法性，
以及受众是否存在孤儿（定义却无任何模板引用）。
"""
from __future__ import annotations

from typing import Any

from template.registry import TemplateRegistry, tag_exists


# 模板正文骨架（structure.required + mustIncludeFacts）禁止出现的地域专有词。
# 这些事实必须由 region_catalog 在 brief 阶段按 region 注入，模板保持地域无关。
REGION_LOCKED_TERMS = [
    "高原",
    "海拔",
    "雪山",
    "高反",
    "沿海",
    "海岛",
    "沙漠",
    "戈壁",
    "热带",
    "雨林",
    "台风",
    "潮汐",
]


def validate_region_season(registry: TemplateRegistry) -> list[str]:
    errors: list[str] = []
    errors.extend(_validate_catalog(registry, "region_catalog", "regions", "region"))
    errors.extend(_validate_catalog(registry, "season_catalog", "seasons", "season"))
    errors.extend(_validate_condition_axes(registry))
    errors.extend(_validate_no_orphan_audiences(registry))
    return errors


def _validate_catalog(
    registry: TemplateRegistry, catalog_key: str, entries_key: str, label: str
) -> list[str]:
    errors: list[str] = []
    catalog = registry.catalogs.get(catalog_key)
    if not isinstance(catalog, dict):
        errors.append(f"{catalog_key}: missing or invalid catalog")
        return errors
    entries = catalog.get(entries_key)
    if not isinstance(entries, dict) or not entries:
        errors.append(f"{catalog_key}: '{entries_key}' must be a non-empty map")
        return errors
    for name, profile in entries.items():
        prefix = f"{catalog_key}.{name}"
        if not isinstance(profile, dict):
            errors.append(f"{prefix}: must be a map")
            continue
        facts = profile.get("conditionFacts")
        if not isinstance(facts, list) or not facts:
            errors.append(f"{prefix}: conditionFacts must be a non-empty list")
        for tag_ref in profile.get("tagRefs", []) or []:
            if not tag_exists(str(tag_ref)):
                errors.append(f"{prefix}: tagRef not found: {tag_ref}")
    return errors


def _validate_condition_axes(registry: TemplateRegistry) -> list[str]:
    errors: list[str] = []
    for template_id, blueprint in registry.blueprints.items():
        axes = blueprint.get("conditionAxes")
        if axes is None:
            continue
        if not isinstance(axes, dict):
            errors.append(f"blueprint {template_id}: conditionAxes must be a map")
            continue
        for axis_name in ("region", "season"):
            axis = axes.get(axis_name)
            if axis is None:
                continue
            if not isinstance(axis, dict):
                errors.append(f"blueprint {template_id}: conditionAxes.{axis_name} must be a map")
                continue
            if not isinstance(axis.get("applicable"), bool):
                errors.append(
                    f"blueprint {template_id}: conditionAxes.{axis_name}.applicable must be a bool"
                )
            if axis.get("applicable") and not isinstance(axis.get("slot"), str):
                errors.append(
                    f"blueprint {template_id}: conditionAxes.{axis_name}.slot must be a string when applicable"
                )
    return errors


def _validate_no_orphan_audiences(registry: TemplateRegistry) -> list[str]:
    errors: list[str] = []
    catalog = registry.catalogs.get("audience_catalog", {})
    defined = catalog.get("audiences", {})
    if not isinstance(defined, dict):
        return errors
    referenced: set[str] = set()
    for blueprint in registry.blueprints.values():
        for audience in blueprint.get("audiences", []) or []:
            referenced.add(str(audience))
    for audience_id in defined:
        if audience_id not in referenced:
            errors.append(f"audience '{audience_id}' is defined but referenced by no blueprint")
    return errors


def scan_region_locked_terms(blueprint: dict[str, Any]) -> list[str]:
    """扫描模板骨架是否硬编码地域专有词。"""
    hits: list[str] = []
    skeleton: list[str] = []
    structure = blueprint.get("structure")
    if isinstance(structure, dict):
        skeleton.extend(str(item) for item in structure.get("required", []) or [])
    skeleton.extend(str(item) for item in blueprint.get("mustIncludeFacts", []) or [])
    for field in skeleton:
        for term in REGION_LOCKED_TERMS:
            if term in field:
                hits.append(f"{field} (term: {term})")
    return hits
