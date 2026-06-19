"""source_catalog.yaml 结构校验 ——「全」约束真相源完整性门。

随 `qwq-data template lint`（lint_all）执行：保证 category 必填字段齐全、id 唯一、
platformAliases / coveragePolicy.coreCategories 指向真实存在的 category。
"""
from __future__ import annotations

from template.registry import TemplateRegistry

_CATEGORY_REQUIRED = ("id", "label", "verticals", "description", "evidenceFocus", "examplePlatforms")


def validate_source_catalog(registry: TemplateRegistry) -> list[str]:
    errors: list[str] = []
    catalog = registry.catalogs.get("source_catalog")
    if not isinstance(catalog, dict):
        errors.append("source_catalog: missing or invalid catalog")
        return errors

    categories = catalog.get("categories")
    if not isinstance(categories, list) or not categories:
        errors.append("source_catalog: categories must be a non-empty list")
        return errors

    ids: set[str] = set()
    for idx, cat in enumerate(categories):
        label = f"source_catalog.categories[{idx}]"
        if not isinstance(cat, dict):
            errors.append(f"{label}: must be a map")
            continue
        for field in _CATEGORY_REQUIRED:
            if cat.get(field) in (None, "", [], {}):
                errors.append(f"{label}: missing {field}")
        cid = str(cat.get("id") or "")
        if cid:
            if cid in ids:
                errors.append(f"{label}: duplicate category id '{cid}'")
            ids.add(cid)
        examples = cat.get("examplePlatforms")
        if isinstance(examples, list) and len(examples) < 2:
            errors.append(f"{label}: examplePlatforms should list >= 2 representative platforms")

    aliases = catalog.get("platformAliases") or {}
    if isinstance(aliases, dict):
        for alias, cid in aliases.items():
            if cid is not None and str(cid) not in ids:
                errors.append(f"source_catalog.platformAliases.{alias}: unknown category '{cid}'")

    policies = catalog.get("coveragePolicy") or {}
    if isinstance(policies, dict):
        for vertical, pol in policies.items():
            if not isinstance(pol, dict):
                errors.append(f"source_catalog.coveragePolicy.{vertical}: must be a map")
                continue
            if not isinstance(pol.get("minCategoriesPerEntity"), int):
                errors.append(f"source_catalog.coveragePolicy.{vertical}.minCategoriesPerEntity must be int")
            for core in pol.get("coreCategories") or []:
                if str(core) not in ids:
                    errors.append(f"source_catalog.coveragePolicy.{vertical}: unknown coreCategory '{core}'")
            for preferred in pol.get("preferredCategories") or []:
                if str(preferred) not in ids:
                    errors.append(
                        f"source_catalog.coveragePolicy.{vertical}: "
                        f"unknown preferredCategory '{preferred}'"
                    )

    return errors
