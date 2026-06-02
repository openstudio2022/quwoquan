"""style_profile_catalog.yaml 结构校验 ——「美·开篇不千篇一律」真相源完整性门。

随 `qwq-data template lint`（lint_all）执行：
- 顶层 openingStrategies 每项须有 label 与非空 markers。
- 每个 styleFamily 必须声明非空 allowedOpenings，且引用的策略 id 都在 openingStrategies 中
  （强约束，防止新增体裁忘配开篇策略、退回固定开头）。
"""
from __future__ import annotations

from template.registry import TemplateRegistry

_STRATEGY_REQUIRED = ("label", "hint", "markers")


def validate_style_catalog(registry: TemplateRegistry) -> list[str]:
    errors: list[str] = []
    catalog = registry.catalogs.get("style_profile_catalog")
    if not isinstance(catalog, dict):
        errors.append("style_profile_catalog: missing or invalid catalog")
        return errors

    strategies = catalog.get("openingStrategies")
    if not isinstance(strategies, dict) or not strategies:
        errors.append("style_profile_catalog: openingStrategies must be a non-empty map")
        return errors

    strategy_ids: set[str] = set()
    for sid, meta in strategies.items():
        label = f"style_profile_catalog.openingStrategies.{sid}"
        strategy_ids.add(str(sid))
        if not isinstance(meta, dict):
            errors.append(f"{label}: must be a map")
            continue
        for field in _STRATEGY_REQUIRED:
            if meta.get(field) in (None, "", [], {}):
                errors.append(f"{label}: missing {field}")
        markers = meta.get("markers")
        if isinstance(markers, list) and not markers:
            errors.append(f"{label}: markers must list >= 1 marker")

    families = catalog.get("styleFamilies")
    if not isinstance(families, dict) or not families:
        errors.append("style_profile_catalog: styleFamilies must be a non-empty map")
        return errors

    for name, fam in families.items():
        label = f"style_profile_catalog.styleFamilies.{name}"
        if not isinstance(fam, dict):
            errors.append(f"{label}: must be a map")
            continue
        allowed = fam.get("allowedOpenings")
        if not isinstance(allowed, list) or not allowed:
            errors.append(f"{label}: allowedOpenings must be a non-empty list of openingStrategy ids")
            continue
        for sid in allowed:
            if str(sid) not in strategy_ids:
                errors.append(f"{label}: unknown openingStrategy '{sid}'")

    return errors
