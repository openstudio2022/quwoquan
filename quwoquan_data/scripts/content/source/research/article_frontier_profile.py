"""Registry admission and declarative profile expansion for article crawling."""
from __future__ import annotations

from collections.abc import Mapping
import fnmatch
import hashlib
import json
import urllib.parse

from content.source.research.article_frontier_contract import ALLOWED_ADMISSION
from governance.coverage.source_registry import iter_travel_registry_sites


TRACKING_QUERY_KEYS = frozenset(
    {"from", "ref", "spm", "source", "src", "tracking_id"}
)
SEARCH_PROVIDER = "brave_public"


def canonicalize_article_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(str(url or "").strip())
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        return ""
    host = parsed.hostname.casefold()
    port = f":{parsed.port}" if parsed.port and parsed.port != 443 else ""
    query = [
        (key, value)
        for key, value in urllib.parse.parse_qsl(
            parsed.query,
            keep_blank_values=True,
        )
        if not key.casefold().startswith("utm_")
        and key.casefold() not in TRACKING_QUERY_KEYS
    ]
    path = parsed.path or "/"
    return urllib.parse.urlunsplit(
        ("https", f"{host}{port}", path, urllib.parse.urlencode(sorted(query)), "")
    )


def article_profile_digest(site: Mapping[str, object]) -> str:
    payload = {
        "siteId": site.get("siteId"),
        "fetchable": site.get("fetchable"),
        "domains": site.get("domains"),
        "urlPatterns": site.get("urlPatterns"),
        "licensePolicy": site.get("licensePolicy"),
        "siteCrawlProfile": site.get("siteCrawlProfile"),
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"sha256:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"


def article_search_sites(
    *,
    site_ids: frozenset[str] | None = None,
) -> tuple[dict[str, object], ...]:
    """Return only fail-closed registry profiles admitted to article crawling."""
    sites: list[dict[str, object]] = []
    for site in iter_travel_registry_sites():
        site_id = str(site.get("siteId") or "").strip()
        if site_ids is not None and site_id not in site_ids:
            continue
        profile = site.get("siteCrawlProfile")
        if not isinstance(profile, dict):
            continue
        lanes = {str(value) for value in (profile.get("contentLanes") or ())}
        if (
            site.get("fetchable") is not True
            or profile.get("crawlAllowed") is not True
            or "article" not in lanes
            or str(profile.get("articleCommercialAdmission") or "")
            != ALLOWED_ADMISSION
            or str(profile.get("robotsPolicy") or "") != "respect_robots_txt"
            or str(profile.get("loginPolicy") or "") != "public_only"
            or not str(profile.get("termsUrl") or "").startswith("https://")
            or not isinstance(profile.get("discoveryStrategy"), dict)
        ):
            continue
        rights_policy = str(
            profile.get("rightsPolicy") or site.get("licensePolicy") or ""
        )
        if rights_policy in {
            "reference_only",
            "discovery_only",
            "licensed_candidate",
            "",
        }:
            continue
        sites.append(site)
    return tuple(sites)


def article_url_allowed(url: str, site: Mapping[str, object]) -> bool:
    canonical = canonicalize_article_url(url)
    if not canonical:
        return False
    profile = site.get("siteCrawlProfile")
    if not isinstance(profile, Mapping):
        return False
    patterns = tuple(
        str(value).strip()
        for value in (profile.get("allowedPaths") or ())
        if str(value).strip()
    )
    return bool(patterns) and any(
        fnmatch.fnmatch(canonical, pattern) for pattern in patterns
    )


def resolve_article_source_binding(
    url: str,
    *,
    site_id: str,
    profile_digest: str,
) -> dict[str, object]:
    """Revalidate a frozen article candidate before its body is fetched.

    A crawler discovery record is only reusable while it remains bound to the
    same registry-admitted site profile.  URL host matching alone is not enough:
    a broader registry entry could otherwise silently replace the site whose
    robots, terms, allowed-path and rate policy admitted the candidate.
    """
    normalized_site_id = str(site_id or "").strip()
    expected_digest = str(profile_digest or "").strip()
    if not normalized_site_id or not expected_digest:
        raise ValueError(
            "commercial article source requires articleSiteId and "
            "sourceDiscoveryProfileDigest"
        )
    admitted = {
        str(site.get("siteId") or "").strip(): site
        for site in article_search_sites(site_ids=frozenset({normalized_site_id}))
    }
    site = admitted.get(normalized_site_id)
    if site is None:
        raise ValueError(
            f"article site is not currently admitted for commercial crawl: "
            f"{normalized_site_id}"
        )
    if article_profile_digest(site) != expected_digest:
        raise ValueError(
            f"article site crawl profile drift: {normalized_site_id}"
        )
    if not article_url_allowed(url, site):
        raise ValueError(
            f"article source URL is outside the frozen site's allowed paths: "
            f"{normalized_site_id}"
        )
    return site


def template_contexts(
    template: str,
    *,
    aliases: tuple[str, ...],
    topics: tuple[str, ...],
) -> tuple[dict[str, str], ...]:
    entity_terms = (
        aliases[:4]
        if any(token in template for token in ("{entity}", "{alias}"))
        else aliases[:1]
    )
    topic_terms = (
        topics[:4]
        if any(token in template for token in ("{topic}", "{geo}", "{theme}"))
        else ("",)
    )
    contexts: list[dict[str, str]] = []
    for entity in entity_terms or ("",):
        for topic in topic_terms or ("",):
            contexts.append(
                {
                    "entity": entity,
                    "alias": entity,
                    "topic": topic,
                    "geo": topic,
                    "theme": topic,
                }
            )
    return tuple(contexts)


def formatted_declared_urls(
    values: object,
    *,
    aliases: tuple[str, ...],
    topics: tuple[str, ...],
) -> tuple[str, ...]:
    urls: list[str] = []
    for raw in values if isinstance(values, list) else []:
        template = str(raw or "").strip()
        if not template:
            continue
        for context in template_contexts(
            template,
            aliases=aliases,
            topics=topics,
        ):
            try:
                url = template.format_map(context)
            except (KeyError, ValueError):
                continue
            canonical = canonicalize_article_url(url)
            if canonical and canonical not in urls:
                urls.append(canonical)
    return tuple(urls)


__all__ = [
    "SEARCH_PROVIDER",
    "article_profile_digest",
    "article_search_sites",
    "article_url_allowed",
    "canonicalize_article_url",
    "formatted_declared_urls",
    "resolve_article_source_binding",
    "template_contexts",
]
