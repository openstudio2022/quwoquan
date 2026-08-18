"""Registry-declared MediaWiki API search seeds for article discovery."""

from __future__ import annotations

import json
import urllib.parse
from collections import deque
from collections.abc import Mapping

from core.data_issue import DataIssue

from content.source.research.article_frontier_contract import (
    ArticleFrontierRecord,
    FrontierDecision,
    FrontierItem,
)
from content.source.research.article_frontier_profile import (
    canonicalize_article_url,
)
from content.source.research.article_frontier_robots import (
    fetch_with_backoff,
    network_issue,
    policy_issue,
)
from core.rate_limit import shared_rate_limiter

_MEDIAWIKI_SEARCH_METHOD = "mediawiki_api_search"


def _mediawiki_search_url(
    host: str,
    *,
    query: str,
    result_limit: int,
) -> str:
    params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srnamespace": "0",
        "srlimit": str(result_limit),
        "srsearch": query,
        "utf8": "1",
    }
    return f"https://{host}/w/api.php?{urllib.parse.urlencode(params)}"


def _mediawiki_page_seeds(
    host: str,
    payload: object,
    *,
    search_url: str,
    query: str,
) -> tuple[FrontierItem, ...] | None:
    if not isinstance(payload, Mapping):
        return None
    query_payload = payload.get("query")
    rows = query_payload.get("search") if isinstance(query_payload, Mapping) else None
    if not isinstance(rows, list):
        return None
    seeds: list[FrontierItem] = []
    seen_urls: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping) or row.get("ns") not in (0, "0"):
            continue
        title = str(row.get("title") or "").strip()
        if not title:
            continue
        encoded_title = urllib.parse.quote(
            title.replace(" ", "_"),
            safe="()_-",
        )
        canonical_url = canonicalize_article_url(f"https://{host}/wiki/{encoded_title}")
        if not canonical_url or canonical_url in seen_urls:
            continue
        seen_urls.add(canonical_url)
        seeds.append(
            FrontierItem(
                canonical_url,
                title,
                search_url,
                0,
                _MEDIAWIKI_SEARCH_METHOD,
                query,
            )
        )
    return tuple(seeds)


def mediawiki_search_frontier_items(
    site: Mapping[str, object],
    *,
    aliases: tuple[str, ...],
    requested_limit: int,
    timeout: int,
    records: list[ArticleFrontierRecord],
    issues: list[DataIssue],
) -> deque[FrontierItem]:
    """Search one registry-declared public MediaWiki origin for page seeds.

    Search results are discovery seeds only.  The normal robots, page fetch,
    entity-anchor and source-quality gates still decide whether a page enters
    the admitted article frontier.
    """
    queue: deque[FrontierItem] = deque()
    profile = site.get("siteCrawlProfile")
    if not isinstance(profile, Mapping):
        return queue
    strategy = profile.get("discoveryStrategy")
    if not isinstance(strategy, Mapping):
        return queue
    if (
        str(strategy.get("mode") or "") != "entity_seeded_scan"
        or str(profile.get("fetchMode") or "") != "mediawiki_api"
    ):
        return queue
    site_id = str(site.get("siteId") or "")
    domains = tuple(
        str(value).strip().casefold()
        for value in (site.get("domains") or ())
        if str(value).strip()
    )
    if not domains:
        issue = policy_issue(
            site_id,
            "",
            message="MediaWiki API search requires a registry-declared domain",
        )
        issues.append(issue)
        records.append(
            ArticleFrontierRecord(
                "",
                "",
                "",
                0,
                "provider_registry",
                "",
                FrontierDecision.BLOCKED,
                issue.code.value,
            )
        )
        return queue
    rate_policy = profile.get("rateLimit")
    rate_policy = rate_policy if isinstance(rate_policy, Mapping) else {}
    max_requests_per_second = float(rate_policy.get("maxRequestsPerSecond") or 0.0)
    backoff_statuses = frozenset(
        int(value)
        for value in (rate_policy.get("backoffOnStatus") or ())
        if str(value).isdigit()
    )
    host = domains[0]
    limiter = shared_rate_limiter(
        site_id,
        f"https://{host}",
        max_requests_per_second=max_requests_per_second,
        crawl_delay=0.0,
    )
    result_limit = min(20, max(4, requested_limit * 4))
    seen_queries: set[str] = set()
    for alias in aliases[:4]:
        query = " ".join(str(alias or "").split())
        if not query or query in seen_queries:
            continue
        seen_queries.add(query)
        search_url = _mediawiki_search_url(
            host,
            query=query,
            result_limit=result_limit,
        )
        response = fetch_with_backoff(
            search_url,
            timeout=timeout,
            backoff_statuses=backoff_statuses,
            limiter=limiter,
        )
        if response.returncode != 0 and response.status_code == 0:
            issue = network_issue(
                site_id,
                search_url,
                message=(
                    "MediaWiki public search unavailable because network "
                    "transport failed"
                ),
            )
            issues.append(issue)
            records.append(
                ArticleFrontierRecord(
                    search_url,
                    "",
                    "",
                    0,
                    _MEDIAWIKI_SEARCH_METHOD,
                    query,
                    FrontierDecision.BLOCKED,
                    issue.code.value,
                )
            )
            continue
        if not response.ok:
            records.append(
                ArticleFrontierRecord(
                    search_url,
                    canonicalize_article_url(search_url),
                    "",
                    0,
                    _MEDIAWIKI_SEARCH_METHOD,
                    query,
                    FrontierDecision.DISCARDED,
                    "mediawiki_search_unreadable",
                    response.status_code,
                )
            )
            continue
        try:
            payload = json.loads(response.body.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            payload = None
        seeds = _mediawiki_page_seeds(
            host,
            payload,
            search_url=search_url,
            query=query,
        )
        if seeds is None:
            records.append(
                ArticleFrontierRecord(
                    search_url,
                    canonicalize_article_url(search_url),
                    "",
                    0,
                    _MEDIAWIKI_SEARCH_METHOD,
                    query,
                    FrontierDecision.DISCARDED,
                    "mediawiki_search_payload_invalid",
                    response.status_code,
                )
            )
            continue
        records.append(
            ArticleFrontierRecord(
                search_url,
                canonicalize_article_url(search_url),
                "",
                0,
                _MEDIAWIKI_SEARCH_METHOD,
                query,
                FrontierDecision.EXPANDED,
                f"mediawiki_search_results:{len(seeds)}",
                response.status_code,
            )
        )
        queue.extend(seeds)
    return queue


__all__ = ["mediawiki_search_frontier_items"]
