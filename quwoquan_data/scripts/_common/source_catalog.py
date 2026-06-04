"""旅游/校园内容源类别注册表加载与归类 ——「全」的硬约束逻辑库。

`templates/_registry/catalogs/source_catalog.yaml` 是源类别唯一真相源：
platform → category 归类、每实体源类别覆盖统计。download 源类别覆盖门与 template lint
共用本模块，UI/脚本不另维护第二套平台清单。

committed 真相源按脚本相对路径定位，不随运行期 QWQ_DATA_ROOT 漂移。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

SOURCE_CATALOG_PATH = (
    Path(__file__).resolve().parents[2] / "templates" / "_registry" / "catalogs" / "source_catalog.yaml"
)

# 通用兜底/未知平台不计入类别覆盖。
_GENERIC_PLATFORMS = {"", "web", "unknown"}


@lru_cache(maxsize=1)
def load_source_catalog() -> dict[str, Any]:
    if not SOURCE_CATALOG_PATH.is_file():
        return {}
    with SOURCE_CATALOG_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def _category_index() -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str | None], ...]]:
    """返回 (examplePlatform_token_lower → categoryId, alias_lower → categoryId|None)。

    用 tuple 形态以兼容 lru_cache（dict 不可哈希）。
    """
    catalog = load_source_catalog()
    token_to_cat: dict[str, str] = {}
    for cat in catalog.get("categories") or []:
        cid = str(cat.get("id") or "")
        if not cid:
            continue
        for example in cat.get("examplePlatforms") or []:
            token_to_cat[str(example).strip().lower()] = cid
    aliases: dict[str, str | None] = {}
    for alias, cid in (catalog.get("platformAliases") or {}).items():
        aliases[str(alias).strip().lower()] = (str(cid) if cid else None)
    return tuple(token_to_cat.items()), tuple(aliases.items())


def known_category_ids() -> set[str]:
    return {str(c.get("id")) for c in (load_source_catalog().get("categories") or []) if c.get("id")}


def platform_category(platform: str) -> str | None:
    """把 source_plan 的 platform 字符串归类到 categoryId；通用兜底(web)与未知返回 None。"""
    if not platform:
        return None
    key = platform.strip().lower()
    token_items, alias_items = _category_index()
    aliases = dict(alias_items)
    if key in aliases:
        return aliases[key]
    token_to_cat = dict(token_items)
    if key in token_to_cat:
        return token_to_cat[key]
    # 包含匹配：platform 含某 example（"携程攻略"含"携程"），或 example 含 platform。
    for token, cid in token_to_cat.items():
        if token and (token in key or key in token):
            return cid
    return None


def coverage_policy(vertical: str) -> dict[str, Any]:
    policies = load_source_catalog().get("coveragePolicy") or {}
    pol = policies.get(vertical) or policies.get("travel") or {}
    return pol if isinstance(pol, dict) else {}


def vertical_from_task_id(task_id: str) -> str:
    head = (task_id or "").strip().strip("/").split("/")[0]
    if head in ("校园", "campus"):
        return "campus"
    if head in ("摄影", "photography"):
        return "photography"
    return "travel"


def source_category_coverage(
    sources: Sequence[Mapping[str, Any]], *, vertical: str = "travel"
) -> dict[str, Any]:
    """统计实体来源覆盖的源类别集合，并按 coveragePolicy 判定是否满足「全」。"""
    covered: set[str] = set()
    unknown: list[str] = []
    for src in sources or []:
        platform = str((src or {}).get("platform") or "")
        cid = platform_category(platform)
        if cid:
            covered.add(cid)
        elif platform.strip().lower() not in _GENERIC_PLATFORMS:
            unknown.append(platform)
    policy = coverage_policy(vertical)
    min_cats = int(policy.get("minCategoriesPerEntity") or 0)
    core = [str(c) for c in (policy.get("coreCategories") or [])]
    missing_core = [c for c in core if c not in covered]
    return {
        "vertical": vertical,
        "coveredCategories": sorted(covered),
        "coveredCount": len(covered),
        "minCategories": min_cats,
        "coreCategories": core,
        "missingCore": missing_core,
        "unknownPlatforms": sorted(set(unknown)),
        "satisfied": len(covered) >= min_cats and not missing_core,
    }


def coverage_issues(
    sources: Sequence[Mapping[str, Any]], *, vertical: str = "travel", entity_id: str = ""
) -> list[str]:
    """源类别覆盖门：每实体须覆盖 ≥minCategories 类、且包含 coreCategories。"""
    cov = source_category_coverage(sources, vertical=vertical)
    issues: list[str] = []
    prefix = f"{entity_id}: " if entity_id else ""
    if cov["coveredCount"] < cov["minCategories"]:
        issues.append(
            f"{prefix}source categories {cov['coveredCount']} < required {cov['minCategories']} "
            f"(covered={cov['coveredCategories']}; 按 source_catalog.yaml 补路书/营地/官方/地图等类别)"
        )
    if cov["missingCore"]:
        issues.append(f"{prefix}missing core source categories {cov['missingCore']}")
    return issues


def source_plan_guidance(vertical: str = "travel") -> dict[str, Any]:
    """给 agent 的 source_plan 引导：按类别全面采源（「全」），platform 取自类别 examplePlatforms 便于归类。"""
    catalog = load_source_catalog()
    policy = coverage_policy(vertical)
    cats: list[dict[str, Any]] = []
    for cat in catalog.get("categories") or []:
        if vertical in (cat.get("verticals") or []):
            cats.append(
                {
                    "id": cat.get("id"),
                    "label": cat.get("label"),
                    "description": cat.get("description"),
                    "examplePlatforms": list(cat.get("examplePlatforms") or [])[:4],
                }
            )
    return {
        "minCategoriesPerEntity": int(policy.get("minCategoriesPerEntity") or 0),
        "coreCategories": [str(x) for x in (policy.get("coreCategories") or [])],
        "categories": cats,
        "instruction": (
            "按类别全面采源（追求「全」）：每实体须覆盖 ≥minCategoriesPerEntity 类来源，"
            "且必须包含全部 coreCategories；每条 source 的 platform 字段取自对应类别的 "
            "examplePlatforms 之一，以便 download 源类别覆盖门正确归类。"
        ),
    }


__all__ = [
    "SOURCE_CATALOG_PATH",
    "load_source_catalog",
    "known_category_ids",
    "platform_category",
    "coverage_policy",
    "vertical_from_task_id",
    "source_category_coverage",
    "coverage_issues",
    "source_plan_guidance",
]
