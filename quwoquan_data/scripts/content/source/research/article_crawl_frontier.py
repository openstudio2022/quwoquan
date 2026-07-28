"""Registry-driven orchestration of the commercial article crawl frontier."""
from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
import json
import urllib.parse

from content.source.research.article_frontier_contract import (
    ArticleFrontierRecord,
    ArticleSiteDiscoveryEvidence,
    ArticleSourceCandidate,
    ArticleSourceDiscoveryOutcome,
    DailyPageBudget,
    FileDailyPageBudget,
    FrontierDecision,
    FrontierItem,
    PublicSearchResult,
)
from content.source.research.article_frontier_profile import (
    SEARCH_PROVIDER,
    article_search_sites,
    canonicalize_article_url,
    formatted_declared_urls,
    template_contexts,
)
from content.source.research.article_frontier_robots import (
    fetch_with_backoff,
    network_issue,
    policy_issue,
    terms_precheck,
)
from content.source.research.article_site_crawl import crawl_article_site
from content.source.research.text_match import _dedupe_terms
from core.data_issue import DataIssue
from core.runtime_policy import active_runtime_policy


BRAVE_SEARCH_URL = "https://search.brave.com/search"


class SearchResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._active_url = ""
        self._active_text: list[str] = []
        self.results: list[PublicSearchResult] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag != "a" or self._active_url:
            return
        href = str(dict(attrs).get("href") or "").strip()
        if href.startswith(("http://", "https://")):
            self._active_url = href
            self._active_text = []

    def handle_data(self, data: str) -> None:
        if self._active_url:
            self._active_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self._active_url:
            return
        title = " ".join(" ".join(self._active_text).split())
        if title:
            self.results.append(
                PublicSearchResult(title=title, url=self._active_url)
            )
        self._active_url = ""
        self._active_text = []


def parse_public_search_results(
    html: str,
) -> tuple[PublicSearchResult, ...]:
    parser = SearchResultParser()
    parser.feed(str(html or ""))
    seen: set[str] = set()
    results: list[PublicSearchResult] = []
    for result in parser.results:
        canonical = canonicalize_article_url(result.url)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        results.append(
            PublicSearchResult(title=result.title, url=canonical)
        )
    return tuple(results)


def _result_title(result: PublicSearchResult) -> str:
    path_name = urllib.parse.urlparse(result.url).path.rsplit("/", 1)[-1]
    marker = f"{path_name} "
    if marker in result.title:
        return result.title.split(marker, 1)[1].strip()
    return result.title


def _search_frontier_items(
    site_id: str,
    *,
    templates: tuple[str, ...],
    aliases: tuple[str, ...],
    topics: tuple[str, ...],
    timeout: int,
    records: list[ArticleFrontierRecord],
    issues: list[DataIssue],
) -> deque[FrontierItem]:
    queue: deque[FrontierItem] = deque()
    seen_queries: set[str] = set()
    for template in templates:
        for context in template_contexts(
            template,
            aliases=aliases,
            topics=topics,
        ):
            try:
                query = " ".join(template.format_map(context).split())
            except (KeyError, ValueError):
                continue
            if not query or query in seen_queries:
                continue
            seen_queries.add(query)
            search_url = (
                f"{BRAVE_SEARCH_URL}?"
                f"{urllib.parse.urlencode({'q': query})}"
            )
            response = fetch_with_backoff(
                search_url,
                timeout=timeout,
                backoff_statuses=frozenset({429}),
            )
            if response.returncode != 0 and response.status_code == 0:
                issue = network_issue(
                    site_id,
                    search_url,
                    message=(
                        "public search unavailable because network transport "
                        "failed"
                    ),
                )
                issues.append(issue)
                records.append(
                    ArticleFrontierRecord(
                        search_url,
                        "",
                        "",
                        0,
                        SEARCH_PROVIDER,
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
                        SEARCH_PROVIDER,
                        query,
                        FrontierDecision.DISCARDED,
                        "search_unreadable",
                        response.status_code,
                    )
                )
                continue
            results = parse_public_search_results(
                response.body.decode("utf-8", errors="replace")
            )
            records.append(
                ArticleFrontierRecord(
                    search_url,
                    canonicalize_article_url(search_url),
                    "",
                    0,
                    SEARCH_PROVIDER,
                    query,
                    FrontierDecision.EXPANDED,
                    f"search_results:{len(results)}",
                    response.status_code,
                )
            )
            for result in results:
                queue.append(
                    FrontierItem(
                        result.url,
                        _result_title(result),
                        search_url,
                        0,
                        SEARCH_PROVIDER,
                        query,
                    )
                )
    return queue


def build_initial_frontier(
    site: Mapping[str, object],
    *,
    aliases: tuple[str, ...],
    topics: tuple[str, ...],
    timeout: int,
    records: list[ArticleFrontierRecord],
    issues: list[DataIssue],
) -> deque[FrontierItem]:
    """Expand only query, seed, sitemap, and pagination declared by registry."""
    profile = site["siteCrawlProfile"]
    assert isinstance(profile, Mapping)
    strategy = profile["discoveryStrategy"]
    assert isinstance(strategy, Mapping)
    site_id = str(site.get("siteId") or "")
    templates = tuple(
        str(value).strip()
        for value in (strategy.get("queryTemplates") or ())
        if str(value).strip()
    )
    queue: deque[FrontierItem] = deque()
    if str(strategy.get("searchProvider") or "") == SEARCH_PROVIDER:
        queue.extend(
            _search_frontier_items(
                site_id,
                templates=templates,
                aliases=aliases,
                topics=topics,
                timeout=timeout,
                records=records,
                issues=issues,
            )
        )
    for seed_url in formatted_declared_urls(
        strategy.get("seedUrls"),
        aliases=aliases,
        topics=topics,
    ):
        queue.append(
            FrontierItem(seed_url, "", "", 0, "declared_seed")
        )
    for sitemap_url in formatted_declared_urls(
        strategy.get("sitemapUrls"),
        aliases=aliases,
        topics=topics,
    ):
        queue.append(
            FrontierItem(
                sitemap_url,
                "",
                "",
                0,
                "declared_sitemap",
                expand_only=True,
                sitemap=True,
            )
        )
    pagination = strategy.get("pagination")
    if isinstance(pagination, Mapping):
        template = str(pagination.get("urlTemplate") or "").strip()
        start_page = max(1, int(pagination.get("startPage") or 1))
        max_pages = max(0, int(pagination.get("maxPages") or 0))
        for page in range(start_page, start_page + max_pages):
            for context in template_contexts(
                template,
                aliases=aliases,
                topics=topics,
            ):
                try:
                    page_url = template.format_map(
                        {**context, "page": str(page)}
                    )
                except (KeyError, ValueError):
                    continue
                canonical = canonicalize_article_url(page_url)
                if canonical:
                    queue.append(
                        FrontierItem(
                            canonical,
                            "",
                            "",
                            0,
                            "declared_pagination",
                            expand_only=True,
                        )
                    )
    if (
        str(strategy.get("mode") or "") == "entity_seeded_scan"
        and str(profile.get("fetchMode") or "") == "mediawiki_api"
    ):
        domains = tuple(
            str(value)
            for value in (site.get("domains") or ())
            if str(value)
        )
        if domains:
            for alias in aliases[:4]:
                title = urllib.parse.quote(
                    alias.replace(" ", "_"),
                    safe="()_-",
                )
                queue.append(
                    FrontierItem(
                        f"https://{domains[0]}/wiki/{title}",
                        alias,
                        "",
                        0,
                        "entity_seeded_scan",
                    )
                )
    if not queue:
        issue = policy_issue(
            site_id,
            "",
            message=(
                "admitted crawl profile has no executable declared frontier "
                "seed"
            ),
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


def _outcome(
    *,
    entity_id: str,
    aliases: tuple[str, ...],
    topics: tuple[str, ...],
    requested_limit: int,
    observed_at: str,
    sites: tuple[ArticleSiteDiscoveryEvidence, ...],
    candidates: tuple[ArticleSourceCandidate, ...],
) -> ArticleSourceDiscoveryOutcome:
    digest_input = {
        "entityId": entity_id,
        "aliases": aliases,
        "topics": topics,
        "requestedLimit": requested_limit,
        "sites": [site.as_dict() for site in sites],
        "sources": [candidate.as_evidence() for candidate in candidates],
    }
    serialized = json.dumps(
        digest_input,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return ArticleSourceDiscoveryOutcome(
        entity_id=entity_id,
        aliases=aliases,
        topics=topics,
        requested_limit=requested_limit,
        observed_at=observed_at,
        frontier_digest=(
            f"sha256:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"
        ),
        sites=sites,
        candidates=candidates,
    )


def _rate_profile(
    profile: Mapping[str, object],
) -> tuple[float, frozenset[int], int]:
    rate_policy = profile.get("rateLimit")
    rate_policy = rate_policy if isinstance(rate_policy, Mapping) else {}
    return (
        float(rate_policy.get("maxRequestsPerSecond") or 0.0),
        frozenset(
            int(value)
            for value in (rate_policy.get("backoffOnStatus") or ())
            if str(value).isdigit()
        ),
        max(0, int(profile.get("maxPagesPerDay") or 0)),
    )


def discover_article_source_frontier(
    entity_id: str,
    *,
    entity_aliases: list[str] | tuple[str, ...] = (),
    topics: list[str] | tuple[str, ...] = (),
    limit: int,
    site_ids: frozenset[str] | None = None,
    daily_budget: DailyPageBudget | None = None,
) -> ArticleSourceDiscoveryOutcome:
    if limit <= 0:
        raise ValueError("article source frontier limit must be positive")
    aliases = tuple(_dedupe_terms([entity_id, *entity_aliases], limit=12))
    topic_terms = tuple(_dedupe_terms(topics, limit=12))
    observed_at = datetime.now(timezone.utc).isoformat()
    timeout = active_runtime_policy().source_fetch_timeout_seconds
    budget = daily_budget or FileDailyPageBudget()
    candidates: list[ArticleSourceCandidate] = []
    site_evidence: list[ArticleSiteDiscoveryEvidence] = []
    seen_canonical_urls: set[str] = set()
    for site in article_search_sites(site_ids=site_ids):
        if len(candidates) >= limit:
            break
        profile = site["siteCrawlProfile"]
        assert isinstance(profile, Mapping)
        (
            max_requests_per_second,
            backoff_statuses,
            max_pages_per_day,
        ) = _rate_profile(profile)
        site_id = str(site.get("siteId") or "")
        records: list[ArticleFrontierRecord] = []
        issues: list[DataIssue] = []
        terms_record, terms_issue = terms_precheck(
            site,
            timeout=timeout,
            backoff_statuses=backoff_statuses,
        )
        records.append(terms_record)
        if terms_issue is not None:
            issues.append(terms_issue)
        if max_requests_per_second <= 0 or max_pages_per_day <= 0:
            issue = policy_issue(
                site_id,
                "",
                message=(
                    "commercial article crawl profile requires positive rate "
                    "and daily page limits"
                ),
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
        queue: deque[FrontierItem] = deque()
        if not issues:
            queue = build_initial_frontier(
                site,
                aliases=aliases,
                topics=topic_terms,
                timeout=timeout,
                records=records,
                issues=issues,
            )
        crawl = crawl_article_site(
            site,
            queue=queue,
            aliases=aliases,
            topics=topic_terms,
            requested_limit=limit,
            candidate_limit=limit - len(candidates),
            timeout=timeout,
            day=observed_at[:10],
            daily_budget=budget,
            initial_records=records,
            initial_issues=issues,
            seen_canonical_urls=seen_canonical_urls,
        )
        candidates.extend(crawl.candidates)
        site_evidence.append(crawl.evidence)
    outcome = _outcome(
        entity_id=entity_id,
        aliases=aliases,
        topics=topic_terms,
        requested_limit=limit,
        observed_at=observed_at,
        sites=tuple(site_evidence),
        candidates=tuple(candidates),
    )
    outcome.as_evidence()
    return outcome


__all__ = [
    "build_initial_frontier",
    "discover_article_source_frontier",
    "parse_public_search_results",
]
