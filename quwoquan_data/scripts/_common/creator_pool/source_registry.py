"""Creator acquisition source registry contract."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from _common.paths import _REPO_DATA_ROOT

REGISTRY_PATH = _REPO_DATA_ROOT / "verticals" / "creator_pool" / "sources" / "source_registry.yaml"

REQUIRED_SITE_FIELDS: tuple[str, ...] = (
    "siteId",
    "verticals",
    "chinaAnalogLabel",
    "candidateRole",
    "crawlAllowed",
    "validationOnly",
    "rightsPolicy",
    "rateLimit",
    "sourceKind",
)

ALLOWED_VERTICALS: frozenset[str] = frozenset({"travel", "photography"})
ALLOWED_SOURCE_KINDS: frozenset[str] = frozenset(
    {
        "open_web_profile",
        "open_rss",
        "wikimedia",
        "tourism_board",
        "site_supply_author",
    }
)
ALLOWED_REGION_CLASSES: frozenset[str] = frozenset({"china", "non_china", "cross_region"})


def load_creator_source_registry(path: Path | None = None) -> dict[str, Any]:
    registry_path = path or REGISTRY_PATH
    with registry_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"creator source registry must be a mapping: {registry_path}")
    return data


def iter_creator_source_sites(path: Path | None = None) -> list[dict[str, Any]]:
    registry = load_creator_source_registry(path)
    sites = registry.get("sites") or []
    return [site for site in sites if isinstance(site, dict)]


def sites_for_segment(segment: str, *, region_class: str | None = None) -> list[dict[str, Any]]:
    required = _required_verticals_for_segment(segment)
    out: list[dict[str, Any]] = []
    for site in iter_creator_source_sites():
        verticals = {str(v) for v in site.get("verticals") or []}
        if not required.issubset(verticals):
            continue
        if region_class and str(site.get("regionClass") or "") != region_class:
            continue
        out.append(site)
    return out


def validate_creator_source_registry(path: Path | None = None) -> list[str]:
    issues: list[str] = []
    registry_path = path or REGISTRY_PATH
    if not registry_path.is_file():
        return [f"missing creator source registry: {registry_path}"]
    registry = load_creator_source_registry(registry_path)
    if registry.get("schemaVersion") != "quwoquan.creator_source_registry.v1":
        issues.append("schemaVersion must be quwoquan.creator_source_registry.v1")
    sites = registry.get("sites")
    if not isinstance(sites, list) or not sites:
        issues.append("sites must be a non-empty list")
        return issues
    seen: set[str] = set()
    region_counts: defaultdict[str, int] = defaultdict(int)
    vertical_pair_seen = False
    for idx, site in enumerate(s for s in sites if isinstance(s, dict)):
        prefix = f"sites[{idx}]"
        site_id = str(site.get("siteId") or "").strip()
        if not site_id:
            issues.append(f"{prefix}: missing siteId")
        elif site_id in seen:
            issues.append(f"{prefix}: duplicate siteId {site_id}")
        seen.add(site_id)
        for field in REQUIRED_SITE_FIELDS:
            if field not in site:
                issues.append(f"{prefix} {site_id}: missing {field}")
        verticals = site.get("verticals")
        if not isinstance(verticals, list) or not verticals:
            issues.append(f"{prefix} {site_id}: verticals must be non-empty list")
        else:
            vset = {str(v) for v in verticals}
            unknown = sorted(vset - ALLOWED_VERTICALS)
            if unknown:
                issues.append(f"{prefix} {site_id}: unknown verticals {unknown}")
            if {"travel", "photography"}.issubset(vset):
                vertical_pair_seen = True
        for field in ("chinaAnalogLabel", "candidateRole", "rightsPolicy", "sourceKind"):
            if not str(site.get(field) or "").strip():
                issues.append(f"{prefix} {site_id}: {field} must be non-empty")
        if not isinstance(site.get("crawlAllowed"), bool):
            issues.append(f"{prefix} {site_id}: crawlAllowed must be boolean")
        if not isinstance(site.get("validationOnly"), bool):
            issues.append(f"{prefix} {site_id}: validationOnly must be boolean")
        if site.get("crawlAllowed") is False and site.get("validationOnly") is not True:
            issues.append(f"{prefix} {site_id}: crawlAllowed=false requires validationOnly=true")
        if str(site.get("sourceKind") or "") not in ALLOWED_SOURCE_KINDS:
            issues.append(f"{prefix} {site_id}: invalid sourceKind {site.get('sourceKind')!r}")
        rate = site.get("rateLimit")
        if not isinstance(rate, dict) or float(rate.get("requestsPerMinute") or 0) <= 0:
            issues.append(f"{prefix} {site_id}: rateLimit.requestsPerMinute must be > 0")
        domains = site.get("domains")
        if not isinstance(domains, list) or not domains:
            issues.append(f"{prefix} {site_id}: domains must be non-empty list")
        else:
            for domain in domains:
                text = str(domain)
                if "example." in text or text.endswith(".example"):
                    issues.append(f"{prefix} {site_id}: example domain forbidden")
        homepage = str(site.get("homepageUrl") or "")
        if not homepage.startswith("https://"):
            issues.append(f"{prefix} {site_id}: homepageUrl must be https")
        if "example." in homepage:
            issues.append(f"{prefix} {site_id}: example homepage forbidden")
        region_class = str(site.get("regionClass") or "")
        if region_class not in ALLOWED_REGION_CLASSES:
            issues.append(f"{prefix} {site_id}: invalid regionClass {region_class!r}")
        else:
            region_counts[region_class] += 1
    for segment in ("travel_primary", "photography_primary", "travel_photography_cross"):
        if not sites_for_segment(segment):
            issues.append(f"missing usable sites for segment {segment}")
    if not vertical_pair_seen:
        issues.append("at least one site must cover both travel and photography")
    if region_counts["non_china"] < 5 or region_counts["china"] < 5:
        issues.append("registry must include at least 5 non_china and 5 china sites")
    return issues


def _required_verticals_for_segment(segment: str) -> set[str]:
    if segment == "travel_primary":
        return {"travel"}
    if segment == "photography_primary":
        return {"photography"}
    if segment == "travel_photography_cross":
        return {"travel", "photography"}
    return {"travel"}
