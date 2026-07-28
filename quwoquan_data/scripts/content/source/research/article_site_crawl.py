"""Bounded crawl of one registry-admitted public article site."""
from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
import hashlib
import json
import re
import urllib.parse
import urllib.robotparser

from content.source.research import network_io
from content.source.research.article_frontier_contract import (
    ArticleFrontierRecord,
    ArticleSiteDiscoveryEvidence,
    ArticleSourceCandidate,
    DailyPageBudget,
    FrontierDecision,
    FrontierItem,
    PublicSearchResult,
)
from content.source.research.article_frontier_profile import (
    article_profile_digest,
    article_url_allowed,
    canonicalize_article_url,
)
from content.source.research.article_frontier_robots import (
    SiteRateLimiter,
    fetch_with_backoff,
    network_issue,
    policy_issue,
    robots_for_url,
    shared_rate_limiter,
)
from content.source.research.text_match import (
    _text_mentions_entity,
    _title_matches_entity,
)
from core.data_issue import DataIssue


LOGIN_WALL_MARKERS = (
    "请先登录",
    "登录后查看",
    "登录后继续",
    "需要登录",
    "验证后继续",
    "访问过于频繁",
    "captcha",
    "login required",
)


@dataclass(frozen=True, slots=True)
class SiteCrawlResult:
    evidence: ArticleSiteDiscoveryEvidence
    candidates: tuple[ArticleSourceCandidate, ...]


class PageParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[PublicSearchResult] = []
        self.canonical_url = ""
        self._in_title = False
        self._active_link = ""
        self._active_link_text: list[str] = []
        self._suppressed_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag in {"script", "style", "noscript", "template"}:
            self._suppressed_depth += 1
            return
        if self._suppressed_depth:
            return
        attributes = dict(attrs)
        if tag == "title":
            self._in_title = True
        if tag == "link":
            rel = {
                value.casefold()
                for value in str(attributes.get("rel") or "").split()
            }
            href = str(attributes.get("href") or "").strip()
            if "canonical" in rel and href and not self.canonical_url:
                self.canonical_url = urllib.parse.urljoin(self.base_url, href)
        if tag == "a" and not self._active_link:
            href = str(attributes.get("href") or "").strip()
            if href:
                self._active_link = urllib.parse.urljoin(self.base_url, href)
                self._active_link_text = []

    def handle_data(self, data: str) -> None:
        if self._suppressed_depth:
            return
        value = " ".join(str(data or "").split())
        if not value:
            return
        if self._in_title:
            self.title_parts.append(value)
        if self._active_link:
            self._active_link_text.append(value)
        if len(self.text_parts) < 1200:
            self.text_parts.append(value)

    def handle_endtag(self, tag: str) -> None:
        if (
            tag in {"script", "style", "noscript", "template"}
            and self._suppressed_depth
        ):
            self._suppressed_depth -= 1
            return
        if self._suppressed_depth:
            return
        if tag == "title":
            self._in_title = False
        if tag == "a" and self._active_link:
            title = " ".join(self._active_link_text).strip()
            self.links.append(
                PublicSearchResult(title=title, url=self._active_link)
            )
            self._active_link = ""
            self._active_link_text = []

    @property
    def title(self) -> str:
        return " ".join(self.title_parts).strip()

    @property
    def text(self) -> str:
        return " ".join(self.text_parts)[:30000]


def sitemap_urls(body: bytes) -> tuple[str, ...]:
    text = body.decode("utf-8", errors="replace")
    urls: list[str] = []
    for value in re.findall(r"(?is)<loc>\s*(.*?)\s*</loc>", text):
        canonical = canonicalize_article_url(unescape(value.strip()))
        if canonical and canonical not in urls:
            urls.append(canonical)
    return tuple(urls)


def page_relevance(
    *,
    title: str,
    text: str,
    aliases: tuple[str, ...],
    topics: tuple[str, ...],
) -> tuple[bool, float]:
    entity_hit = any(
        _title_matches_entity(title, alias)
        or _text_mentions_entity(text, alias, entity_aliases=aliases)
        for alias in aliases
    )
    normalized_text = f"{title} {text}".casefold()
    topic_hit = any(
        topic.casefold() in normalized_text for topic in topics if topic
    )
    if not entity_hit:
        return False, 0.2 if topic_hit else 0.0
    return True, 0.99 if topic_hit else 0.94


def _record(
    item: FrontierItem,
    canonical_url: str,
    decision: FrontierDecision,
    reason: str,
    status_code: int = 0,
    relevance_score: float = 0.0,
) -> ArticleFrontierRecord:
    return ArticleFrontierRecord(
        item.url,
        canonical_url,
        item.parent_url,
        item.depth,
        item.discovery_method,
        item.query,
        decision,
        reason,
        status_code,
        relevance_score,
    )


def _site_limits(
    profile: Mapping[str, object],
) -> tuple[float, frozenset[int], int, int]:
    rate_policy = profile.get("rateLimit")
    rate_policy = rate_policy if isinstance(rate_policy, Mapping) else {}
    requests_per_second = float(
        rate_policy.get("maxRequestsPerSecond") or 0.0
    )
    backoff_statuses = frozenset(
        int(value)
        for value in (rate_policy.get("backoffOnStatus") or ())
        if str(value).isdigit()
    )
    return (
        requests_per_second,
        backoff_statuses,
        max(0, int(profile.get("maxDepth") or 0)),
        max(0, int(profile.get("maxPagesPerDay") or 0)),
    )


def crawl_article_site(
    site: Mapping[str, object],
    *,
    queue: deque[FrontierItem],
    aliases: tuple[str, ...],
    topics: tuple[str, ...],
    requested_limit: int,
    candidate_limit: int,
    timeout: int,
    day: str,
    daily_budget: DailyPageBudget,
    initial_records: list[ArticleFrontierRecord],
    initial_issues: list[DataIssue],
    seen_canonical_urls: set[str],
) -> SiteCrawlResult:
    """Crawl one admitted site without retaining source-page body content."""
    profile = site["siteCrawlProfile"]
    assert isinstance(profile, Mapping)
    (
        max_requests_per_second,
        backoff_statuses,
        max_depth,
        max_pages_per_day,
    ) = _site_limits(profile)
    site_id = str(site.get("siteId") or "")
    profile_digest = article_profile_digest(site)
    records = list(initial_records)
    issues = list(initial_issues)
    pages_reserved = 0
    candidates: list[ArticleSourceCandidate] = []
    robots_by_origin: dict[
        str,
        urllib.robotparser.RobotFileParser | None,
    ] = {}
    limiter_by_origin: dict[str, SiteRateLimiter] = {}
    seen_site_urls: set[str] = set()
    run_page_limit = min(
        max_pages_per_day,
        max(4, requested_limit * 4),
    )
    while (
        queue
        and len(candidates) < candidate_limit
        and pages_reserved < run_page_limit
    ):
        item = queue.popleft()
        canonical_url = canonicalize_article_url(item.url)
        if item.depth > max_depth:
            records.append(
                _record(
                    item,
                    canonical_url,
                    FrontierDecision.DISCARDED,
                    "max_depth_exceeded",
                )
            )
            continue
        if not canonical_url or not article_url_allowed(canonical_url, site):
            records.append(
                _record(
                    item,
                    canonical_url,
                    FrontierDecision.DISCARDED,
                    "outside_allowed_paths",
                )
            )
            continue
        if (
            canonical_url in seen_site_urls
            or canonical_url in seen_canonical_urls
        ):
            records.append(
                _record(
                    item,
                    canonical_url,
                    FrontierDecision.DISCARDED,
                    "canonical_duplicate",
                )
            )
            continue
        seen_site_urls.add(canonical_url)
        parsed = urllib.parse.urlsplit(canonical_url)
        origin = f"https://{parsed.netloc}"
        if origin not in robots_by_origin:
            robots, robots_record, robots_issue = robots_for_url(
                canonical_url,
                site_id=site_id,
                timeout=timeout,
                backoff_statuses=backoff_statuses,
            )
            robots_by_origin[origin] = robots
            records.append(robots_record)
            if robots_issue is not None:
                issues.append(robots_issue)
            crawl_delay = (
                (
                    robots.crawl_delay(network_io.USER_AGENT)
                    or robots.crawl_delay("*")
                    or 0
                )
                if robots is not None
                else 0
            )
            limiter_by_origin[origin] = shared_rate_limiter(
                site_id,
                origin,
                max_requests_per_second=max_requests_per_second,
                crawl_delay=float(crawl_delay),
            )
        robots = robots_by_origin[origin]
        if robots is None:
            records.append(
                _record(
                    item,
                    canonical_url,
                    FrontierDecision.BLOCKED,
                    "robots_policy_unavailable",
                )
            )
            continue
        if not robots.can_fetch(network_io.USER_AGENT, canonical_url):
            records.append(
                _record(
                    item,
                    canonical_url,
                    FrontierDecision.DISCARDED,
                    "robots_denied",
                )
            )
            continue
        try:
            reservation = daily_budget.reserve(
                site_id,
                day=day,
                max_pages_per_day=max_pages_per_day,
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            issue = policy_issue(
                site_id,
                canonical_url,
                message=(
                    "daily page budget ledger unavailable: "
                    f"{type(exc).__name__}"
                ),
            )
            issues.append(issue)
            records.append(
                _record(
                    item,
                    canonical_url,
                    FrontierDecision.BLOCKED,
                    issue.code.value,
                )
            )
            break
        if not reservation.allowed:
            records.append(
                _record(
                    item,
                    canonical_url,
                    FrontierDecision.BLOCKED,
                    "max_pages_per_day_exhausted",
                )
            )
            break
        pages_reserved += 1
        response = fetch_with_backoff(
            canonical_url,
            timeout=timeout,
            backoff_statuses=backoff_statuses,
            limiter=limiter_by_origin[origin],
        )
        if response.returncode != 0 and response.status_code == 0:
            issue = network_issue(
                site_id,
                canonical_url,
                message=(
                    "article frontier page unavailable because network "
                    "transport failed"
                ),
            )
            issues.append(issue)
            records.append(
                _record(
                    item,
                    canonical_url,
                    FrontierDecision.BLOCKED,
                    issue.code.value,
                )
            )
            continue
        if not response.ok:
            records.append(
                _record(
                    item,
                    canonical_url,
                    FrontierDecision.DISCARDED,
                    "page_unreadable",
                    response.status_code,
                )
            )
            continue
        final_url = canonicalize_article_url(
            response.final_url or canonical_url
        )
        parser = PageParser(final_url or canonical_url)
        parser.feed(response.body.decode("utf-8", errors="replace"))
        final_url = canonicalize_article_url(
            parser.canonical_url or final_url
        )
        if not final_url or not article_url_allowed(final_url, site):
            records.append(
                _record(
                    item,
                    final_url,
                    FrontierDecision.DISCARDED,
                    "redirect_outside_allowed_paths",
                    response.status_code,
                )
            )
            continue
        if final_url in seen_canonical_urls:
            records.append(
                _record(
                    item,
                    final_url,
                    FrontierDecision.DISCARDED,
                    "canonical_duplicate",
                    response.status_code,
                )
            )
            continue
        if any(
            marker in parser.text.casefold()
            for marker in LOGIN_WALL_MARKERS
        ):
            records.append(
                _record(
                    item,
                    final_url,
                    FrontierDecision.DISCARDED,
                    "login_or_challenge_wall",
                    response.status_code,
                )
            )
            continue
        if item.expand_only:
            links = (
                tuple(
                    PublicSearchResult("", value)
                    for value in sitemap_urls(response.body)
                )
                if item.sitemap
                else tuple(parser.links)
            )
            records.append(
                _record(
                    item,
                    final_url,
                    FrontierDecision.EXPANDED,
                    f"declared_frontier_links:{len(links)}",
                    response.status_code,
                )
            )
            for link in links[: max(16, requested_limit * 8)]:
                queue.append(
                    FrontierItem(
                        link.url,
                        link.title,
                        final_url,
                        item.depth + 1,
                        f"{item.discovery_method}_link",
                    )
                )
            continue
        title = parser.title or item.title_hint
        relevant, relevance_score = page_relevance(
            title=title,
            text=parser.text,
            aliases=aliases,
            topics=topics,
        )
        if not relevant:
            records.append(
                _record(
                    item,
                    final_url,
                    FrontierDecision.DISCARDED,
                    "entity_alias_topic_relevance_failed",
                    response.status_code,
                    relevance_score,
                )
            )
            continue
        seen_canonical_urls.add(final_url)
        source_id = (
            f"article_frontier_{site_id}_"
            f"{hashlib.sha256(final_url.encode('utf-8')).hexdigest()[:12]}"
        )
        candidates.append(
            ArticleSourceCandidate(
                source_id=source_id,
                site_id=site_id,
                platform=str(site.get("platform") or "旅行指南"),
                category=str(site.get("category") or "travelogue"),
                canonical_url=final_url,
                title=title,
                discovery_method=item.discovery_method,
                relevance_score=relevance_score,
                profile_digest=profile_digest,
            )
        )
        records.append(
            _record(
                item,
                final_url,
                FrontierDecision.ACCEPTED,
                "public_factual_reference_only",
                response.status_code,
                relevance_score,
            )
        )
        if item.depth < max_depth:
            for link in parser.links[: max(16, requested_limit * 8)]:
                queue.append(
                    FrontierItem(
                        link.url,
                        link.title,
                        final_url,
                        item.depth + 1,
                        "page_link",
                    )
                )
    if queue and pages_reserved >= run_page_limit:
        pending = queue[0]
        records.append(
            _record(
                pending,
                canonicalize_article_url(pending.url),
                FrontierDecision.BLOCKED,
                (
                    "max_pages_per_day_exhausted"
                    if run_page_limit == max_pages_per_day
                    else "bounded_frontier_run_limit_reached"
                ),
            )
        )
    evidence = ArticleSiteDiscoveryEvidence(
        site_id=site_id,
        rights_policy=str(
            profile.get("rightsPolicy") or site.get("licensePolicy") or ""
        ),
        robots_policy=str(profile.get("robotsPolicy") or ""),
        terms_url=str(profile.get("termsUrl") or ""),
        max_depth=max_depth,
        max_pages_per_day=max_pages_per_day,
        max_requests_per_second=max_requests_per_second,
        profile_digest=profile_digest,
        pages_reserved=pages_reserved,
        frontier=tuple(records),
        issues=tuple(issues),
    )
    return SiteCrawlResult(
        evidence=evidence,
        candidates=tuple(candidates),
    )


__all__ = ["SiteCrawlResult", "crawl_article_site"]
