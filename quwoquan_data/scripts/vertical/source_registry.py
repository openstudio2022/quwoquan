"""Travel vertical source registry loader and lint."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import fnmatch
import urllib.parse

import yaml

_VERTICALS_ROOT = Path(__file__).resolve().parents[2] / "verticals"
from _common.source_catalog import known_category_ids, platform_category

TRAVEL_SOURCE_REGISTRY_PATH = _VERTICALS_ROOT / "travel" / "sources" / "source_registry.yaml"


def load_travel_source_registry() -> dict[str, Any]:
    if not TRAVEL_SOURCE_REGISTRY_PATH.is_file():
        raise FileNotFoundError(f"missing travel source registry: {TRAVEL_SOURCE_REGISTRY_PATH}")
    data = yaml.safe_load(TRAVEL_SOURCE_REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    if data.get("schemaVersion") != "quwoquan.travel_source_registry.v1":
        raise ValueError(f"{TRAVEL_SOURCE_REGISTRY_PATH}: invalid schemaVersion")
    if data.get("vertical") != "travel":
        raise ValueError(f"{TRAVEL_SOURCE_REGISTRY_PATH}: vertical mismatch")
    return data


def verify_travel_source_registry(*, allowed_extractors: set[str] | None = None) -> list[str]:
    issues: list[str] = []
    try:
        data = load_travel_source_registry()
    except Exception as exc:  # noqa: BLE001
        return [f"travel: source registry invalid: {exc}"]

    categories = known_category_ids()
    quality_tiers = {str(x) for x in (data.get("qualityTiers") or []) if str(x)}
    license_policies = {str(x) for x in (data.get("licensePolicies") or []) if str(x)}
    registry_extractors = {str(x) for x in (data.get("extractors") or []) if str(x)}
    if allowed_extractors is not None:
        unknown = sorted(registry_extractors - allowed_extractors)
        if unknown:
            issues.append(f"travel: source registry declares unknown extractors {unknown}")

    sites = data.get("sites") or []
    if not sites:
        issues.append("travel: source registry has no sites")
        return issues

    seen_ids: set[str] = set()
    seen_platforms: set[str] = set()
    for idx, site in enumerate(sites):
        prefix = f"travel: sites[{idx}]"
        if not isinstance(site, dict):
            issues.append(f"{prefix} must be an object")
            continue
        site_id = str(site.get("siteId") or "").strip()
        platform = str(site.get("platform") or "").strip()
        category = str(site.get("category") or "").strip()
        extractor = str(site.get("extractor") or "").strip()
        license_policy = str(site.get("licensePolicy") or "").strip()
        quality_tier = str(site.get("qualityTier") or "").strip()
        patterns = [str(x).strip() for x in (site.get("urlPatterns") or []) if str(x).strip()]
        domains = [str(x).strip() for x in (site.get("domains") or []) if str(x).strip()]
        fetchable = site.get("fetchable")

        if not site_id:
            issues.append(f"{prefix}: missing siteId")
        elif site_id in seen_ids:
            issues.append(f"{prefix}: duplicate siteId {site_id}")
        else:
            seen_ids.add(site_id)

        if not platform:
            issues.append(f"{prefix}: missing platform")
        elif platform in seen_platforms:
            issues.append(f"{prefix}: duplicate platform {platform}")
        else:
            seen_platforms.add(platform)

        if category not in categories:
            issues.append(f"{prefix}: unknown category {category!r}")
        elif platform and platform_category(platform) != category:
            issues.append(
                f"{prefix}: platform/category mismatch ({platform!r} -> {platform_category(platform)!r}, expected {category!r})"
            )

        if extractor not in registry_extractors:
            issues.append(f"{prefix}: extractor {extractor!r} not declared in top-level extractors")
        if license_policy not in license_policies:
            issues.append(f"{prefix}: unknown licensePolicy {license_policy!r}")
        if quality_tier not in quality_tiers:
            issues.append(f"{prefix}: unknown qualityTier {quality_tier!r}")
        if fetchable not in (True, False):
            issues.append(f"{prefix}: fetchable must be boolean")
        if not patterns:
            issues.append(f"{prefix}: urlPatterns must not be empty")
        if fetchable is True and extractor == "generic_html":
            issues.append(f"{prefix}: fetchable=true requires a site-specific extractor, not generic_html")
        if category in {"encyclopedia", "official"} and not fetchable:
            issues.append(f"{prefix}: {category} source should be fetchable=true if pre-approved in registry")
        if category == "map_geo" and fetchable:
            issues.append(f"{prefix}: map_geo source should not be marked fetchable=true for正文抓取")
        if not domains and category in {"encyclopedia", "travelogue", "map_geo"}:
            issues.append(f"{prefix}: domains should not be empty for {category} source")
    return issues


def iter_travel_registry_sites() -> list[dict[str, Any]]:
    sites = load_travel_source_registry().get("sites") or []
    return [site for site in sites if isinstance(site, dict)]


def match_travel_source_site(url: str) -> dict[str, Any] | None:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    normalized_url = urllib.parse.urlunparse(parsed)
    for site in iter_travel_registry_sites():
        domains = [str(x).strip().lower() for x in (site.get("domains") or []) if str(x).strip()]
        patterns = [str(x).strip() for x in (site.get("urlPatterns") or []) if str(x).strip()]
        domain_hit = any(host == domain or host.endswith(f".{domain}") for domain in domains)
        pattern_hit = any(fnmatch.fnmatch(normalized_url, pattern) for pattern in patterns)
        if domain_hit or pattern_hit:
            return site
    return None


def resolve_travel_source_runtime(url: str, *, platform: str = "") -> dict[str, Any]:
    site = match_travel_source_site(url)
    if site is None:
        category = platform_category(platform) if platform else None
        return {
            "siteId": "",
            "platform": platform,
            "category": category or "",
            "fetchable": False,
            "extractor": "generic_html",
            "licensePolicy": "",
            "qualityTier": "",
            "matched": False,
        }
    return {
        "siteId": str(site.get("siteId") or ""),
        "platform": str(site.get("platform") or platform or ""),
        "category": str(site.get("category") or ""),
        "fetchable": bool(site.get("fetchable")),
        "extractor": str(site.get("extractor") or "generic_html"),
        "licensePolicy": str(site.get("licensePolicy") or ""),
        "qualityTier": str(site.get("qualityTier") or ""),
        "matched": True,
    }


def build_travel_source_guidance() -> dict[str, Any]:
    sites = iter_travel_registry_sites()
    fetchable_sites = []
    fallback_sites = []
    for site in sites:
        row = {
            "siteId": str(site.get("siteId") or ""),
            "platform": str(site.get("platform") or ""),
            "category": str(site.get("category") or ""),
            "domains": [str(x) for x in (site.get("domains") or []) if str(x)],
            "extractor": str(site.get("extractor") or ""),
            "licensePolicy": str(site.get("licensePolicy") or ""),
            "qualityTier": str(site.get("qualityTier") or ""),
            "fetchable": bool(site.get("fetchable")),
            "notes": str(site.get("notes") or ""),
        }
        if row["fetchable"]:
            fetchable_sites.append(row)
        else:
            fallback_sites.append(row)
    return {
        "defaultAction": load_travel_source_registry().get("defaultAction") or "block",
        "fetchableSites": fetchable_sites,
        "nonFetchableSites": fallback_sites,
        "instruction": (
            "优先选择 fetchable=true 的预审站点；非白名单或 fetchable=false 的站点只能作为 coverage 候选，"
            "抓不到稳定正文时必须诚实 Reject/skip，不得用 source_plan.body 或脚本拼接替代。"
        ),
    }
