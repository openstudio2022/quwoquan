"""Travel vertical source registry loader and lint."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any
import fnmatch
import urllib.parse

import yaml

_VERTICALS_ROOT = Path(__file__).resolve().parents[2] / "verticals"
from _common.source_catalog import known_category_ids, platform_category
from _common.content_source_registry import (
    build_content_source_guidance,
    load_content_source_registry,
    verify_content_source_registry,
)

TRAVEL_SOURCE_REGISTRY_PATH = _VERTICALS_ROOT / "travel" / "sources" / "source_registry.yaml"
DISCOVERY_STRATEGY_MODES = {
    "entity_seeded_scan",
    "content_search",
    "site_listing_scan",
    "photo_collection_scan",
    "licensed_asset_manifest",
}
VALID_ARTICLE_COMMERCIAL_ADMISSIONS = {
    "commercial_release",
    "controlled_trial",
    "reference_only",
    "blocked",
}


def load_travel_source_registry() -> dict[str, Any]:
    if not TRAVEL_SOURCE_REGISTRY_PATH.is_file():
        raise FileNotFoundError(f"missing travel source registry: {TRAVEL_SOURCE_REGISTRY_PATH}")
    data = yaml.safe_load(TRAVEL_SOURCE_REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    if data.get("schemaVersion") != "quwoquan.travel_source_registry":
        raise ValueError(f"{TRAVEL_SOURCE_REGISTRY_PATH}: invalid schemaVersion")
    if data.get("vertical") != "travel":
        raise ValueError(f"{TRAVEL_SOURCE_REGISTRY_PATH}: vertical mismatch")
    return data


def verify_travel_source_registry(*, allowed_extractors: set[str] | None = None) -> list[str]:
    issues: list[str] = verify_content_source_registry()
    try:
        data = load_travel_source_registry()
    except Exception as exc:  # noqa: BLE001
        return [f"travel: source registry invalid: {exc}"]

    categories = known_category_ids()
    quality_tiers = {str(x) for x in (data.get("qualityTiers") or []) if str(x)}
    license_policies = {str(x) for x in (data.get("licensePolicies") or []) if str(x)}
    registry_extractors = {str(x) for x in (data.get("extractors") or []) if str(x)}
    article_admissions = {str(x) for x in (data.get("articleCommercialAdmissions") or []) if str(x)}
    if allowed_extractors is not None:
        unknown = sorted(registry_extractors - allowed_extractors)
        if unknown:
            issues.append(f"travel: source registry declares unknown extractors {unknown}")
    if not article_admissions:
        issues.append("travel: articleCommercialAdmissions must not be empty")
    else:
        unknown_admissions = sorted(article_admissions - VALID_ARTICLE_COMMERCIAL_ADMISSIONS)
        if unknown_admissions:
            issues.append(f"travel: articleCommercialAdmissions declares unknown values {unknown_admissions}")
        missing_admissions = sorted(VALID_ARTICLE_COMMERCIAL_ADMISSIONS - article_admissions)
        if missing_admissions:
            issues.append(f"travel: articleCommercialAdmissions missing values {missing_admissions}")

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
        site_crawl_profile = site.get("siteCrawlProfile")

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
        if site_crawl_profile is not None:
            if not isinstance(site_crawl_profile, dict):
                issues.append(f"{prefix}: siteCrawlProfile must be an object")
            else:
                crawl_allowed = site_crawl_profile.get("crawlAllowed")
                allowed_paths = [str(x).strip() for x in (site_crawl_profile.get("allowedPaths") or []) if str(x).strip()]
                content_lanes = [str(x).strip() for x in (site_crawl_profile.get("contentLanes") or []) if str(x).strip()]
                rights_policy = str(site_crawl_profile.get("rightsPolicy") or license_policy or "").strip()
                robots_policy = str(site_crawl_profile.get("robotsPolicy") or "").strip()
                login_policy = str(site_crawl_profile.get("loginPolicy") or "").strip()
                controlled_trial = site_crawl_profile.get("controlledTrial")
                article_admission = str(site_crawl_profile.get("articleCommercialAdmission") or "").strip()
                if crawl_allowed not in (True, False):
                    issues.append(f"{prefix}: siteCrawlProfile.crawlAllowed must be boolean")
                if crawl_allowed is True and fetchable is not True:
                    issues.append(f"{prefix}: siteCrawlProfile.crawlAllowed=true requires fetchable=true")
                if crawl_allowed is True and not allowed_paths:
                    issues.append(f"{prefix}: siteCrawlProfile.allowedPaths must not be empty when crawlAllowed=true")
                if crawl_allowed is True and not content_lanes:
                    issues.append(f"{prefix}: siteCrawlProfile.contentLanes must not be empty when crawlAllowed=true")
                if rights_policy and rights_policy not in license_policies:
                    issues.append(f"{prefix}: siteCrawlProfile.rightsPolicy {rights_policy!r} not declared in licensePolicies")
                if robots_policy in {"ignore", "bypass"}:
                    issues.append(f"{prefix}: siteCrawlProfile.robotsPolicy cannot bypass robots/terms")
                if login_policy and login_policy not in {"public_only", "manual_authorization_required"}:
                    issues.append(f"{prefix}: siteCrawlProfile.loginPolicy must be public_only or manual_authorization_required")
                if "article" in content_lanes:
                    if article_admission not in article_admissions:
                        issues.append(
                            f"{prefix}: siteCrawlProfile.articleCommercialAdmission {article_admission!r} "
                            "must be declared in articleCommercialAdmissions"
                        )
                    elif article_admission == "commercial_release":
                        if crawl_allowed is not True or fetchable is not True:
                            issues.append(
                                f"{prefix}: commercial_release article source must keep fetchable=true and crawlAllowed=true"
                            )
                        if rights_policy in {"reference_only", "discovery_only", "licensed_candidate"}:
                            issues.append(
                                f"{prefix}: commercial_release article source cannot use rightsPolicy {rights_policy!r}"
                            )
                    elif article_admission == "controlled_trial":
                        if not isinstance(controlled_trial, dict) or controlled_trial.get("allowed") is not True:
                            issues.append(
                                f"{prefix}: controlled_trial article source requires controlledTrial.allowed=true"
                            )
                elif article_admission:
                    issues.append(
                        f"{prefix}: siteCrawlProfile.articleCommercialAdmission is only allowed when contentLanes include article"
                    )
                discovery_strategy = site_crawl_profile.get("discoveryStrategy")
                if discovery_strategy is not None:
                    if not isinstance(discovery_strategy, dict):
                        issues.append(f"{prefix}: siteCrawlProfile.discoveryStrategy must be an object")
                    else:
                        mode = str(discovery_strategy.get("mode") or "").strip()
                        seed_axes = [
                            str(x).strip() for x in (discovery_strategy.get("seedAxes") or [])
                            if str(x).strip()
                        ]
                        precheck_gates = [
                            str(x).strip() for x in (discovery_strategy.get("precheckGates") or [])
                            if str(x).strip()
                        ]
                        if mode not in DISCOVERY_STRATEGY_MODES:
                            issues.append(f"{prefix}: siteCrawlProfile.discoveryStrategy.mode {mode!r} is invalid")
                        if not seed_axes:
                            issues.append(f"{prefix}: siteCrawlProfile.discoveryStrategy.seedAxes must not be empty")
                        blocked_axes = {
                            axis for axis in seed_axes
                            if axis.lower() in {"author", "creator", "photographer", "creator_profile"}
                        }
                        if blocked_axes:
                            issues.append(
                                f"{prefix}: siteCrawlProfile.discoveryStrategy must be content-first, "
                                f"not author/creator-first: {sorted(blocked_axes)}"
                            )
                        if mode == "content_search":
                            query_templates = [
                                str(x).strip() for x in (discovery_strategy.get("queryTemplates") or [])
                                if str(x).strip()
                            ]
                            if not query_templates:
                                issues.append(
                                    f"{prefix}: siteCrawlProfile.discoveryStrategy.queryTemplates must not be empty "
                                    "for content_search"
                                )
                        if mode in {"site_listing_scan", "photo_collection_scan"}:
                            if "light_fetch" not in precheck_gates:
                                issues.append(
                                    f"{prefix}: siteCrawlProfile.discoveryStrategy.precheckGates must include light_fetch "
                                    f"for {mode}"
                                )
                if controlled_trial is not None:
                    if not isinstance(controlled_trial, dict):
                        issues.append(f"{prefix}: siteCrawlProfile.controlledTrial must be an object")
                    else:
                        if controlled_trial.get("allowed") not in (True, False):
                            issues.append(f"{prefix}: siteCrawlProfile.controlledTrial.allowed must be boolean")
                        if controlled_trial.get("allowed") is True:
                            if controlled_trial.get("validationOnly") is not True:
                                issues.append(f"{prefix}: controlledTrial.validationOnly must be true")
                            if controlled_trial.get("rawFetchAllowed") is True:
                                issues.append(f"{prefix}: controlledTrial.rawFetchAllowed cannot be true")
                            if controlled_trial.get("publishableAssetsAllowed") is True:
                                issues.append(f"{prefix}: controlledTrial.publishableAssetsAllowed cannot be true")
                            lane_minimums = controlled_trial.get("minimumLaneCounts") or {}
                            if not isinstance(lane_minimums, dict):
                                issues.append(f"{prefix}: controlledTrial.minimumLaneCounts must be an object")
                            else:
                                for lane in content_lanes:
                                    if int(lane_minimums.get(lane) or 0) <= 0:
                                        issues.append(f"{prefix}: controlledTrial.minimumLaneCounts.{lane} must be > 0")
                                for lane in lane_minimums:
                                    if lane not in content_lanes:
                                        issues.append(f"{prefix}: controlledTrial lane {lane!r} must be listed in contentLanes")
    return issues


def load_unified_content_source_registry() -> dict[str, Any]:
    return load_content_source_registry()


def build_unified_content_source_guidance(vertical: str = "travel") -> dict[str, Any]:
    return build_content_source_guidance(vertical)


def iter_travel_registry_sites() -> list[dict[str, Any]]:
    sites = load_travel_source_registry().get("sites") or []
    return [site for site in sites if isinstance(site, dict)]


def site_article_commercial_admission(site: Mapping[str, Any]) -> str:
    profile = site.get("siteCrawlProfile") if isinstance(site.get("siteCrawlProfile"), Mapping) else {}
    lanes = {str(x).strip() for x in (profile.get("contentLanes") or []) if str(x).strip()}
    if "article" not in lanes:
        return ""
    return str(profile.get("articleCommercialAdmission") or "").strip()


def iter_article_onboarding_sites() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for site in iter_travel_registry_sites():
        admission = site_article_commercial_admission(site)
        if not admission:
            continue
        profile = site.get("siteCrawlProfile") if isinstance(site.get("siteCrawlProfile"), Mapping) else {}
        rows.append(
            {
                "siteId": str(site.get("siteId") or ""),
                "platform": str(site.get("platform") or ""),
                "articleCommercialAdmission": admission,
                "sharedCommercialPoolEligible": admission == "commercial_release",
                "fetchable": bool(site.get("fetchable")),
                "crawlAllowed": bool(profile.get("crawlAllowed")),
                "rightsPolicy": str(profile.get("rightsPolicy") or site.get("licensePolicy") or ""),
                "qualityTier": str(site.get("qualityTier") or ""),
                "contentLanes": [str(x) for x in (profile.get("contentLanes") or []) if str(x)],
            }
        )
    return rows


def build_article_commercial_onboarding_summary() -> dict[str, Any]:
    sites = iter_article_onboarding_sites()
    counts = {
        admission: sum(1 for site in sites if site["articleCommercialAdmission"] == admission)
        for admission in sorted(VALID_ARTICLE_COMMERCIAL_ADMISSIONS)
    }
    return {
        "siteCount": len(sites),
        "sharedCommercialPoolSites": [
            site["siteId"] for site in sites if bool(site.get("sharedCommercialPoolEligible"))
        ],
        "admissionCounts": counts,
        "sites": sites,
    }


def match_travel_source_site(url: str) -> dict[str, Any] | None:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    normalized_url = urllib.parse.urlunparse(parsed)
    matches: list[tuple[int, int, dict[str, Any]]] = []
    for site in iter_travel_registry_sites():
        domains = [str(x).strip().lower() for x in (site.get("domains") or []) if str(x).strip()]
        patterns = [str(x).strip() for x in (site.get("urlPatterns") or []) if str(x).strip()]
        domain_hits = [domain for domain in domains if host == domain or host.endswith(f".{domain}")]
        pattern_hits = [pattern for pattern in patterns if fnmatch.fnmatch(normalized_url, pattern)]
        domain_hit = bool(domain_hits)
        pattern_hit = bool(pattern_hits)
        if domain_hit or pattern_hit:
            specificity = max([len(item) for item in domain_hits + pattern_hits] or [0])
            matches.append((specificity, -len(matches), site))
    if matches:
        return max(matches, key=lambda item: (item[0], item[1]))[2]
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
        "articleCommercialAdmission": site_article_commercial_admission(site),
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
            "articleCommercialAdmission": site_article_commercial_admission(site),
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
