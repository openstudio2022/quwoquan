"""Public-search discovery for provider-approved article detail pages."""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import fnmatch
import urllib.parse

from content.source.research import network_io
from content.source.research.plan_state import _source
from content.source.research.text_match import _dedupe_terms, _title_matches_entity
from core.runtime_policy import active_runtime_policy
from governance.coverage.source_registry import iter_travel_registry_sites


_BRAVE_SEARCH_URL = "https://search.brave.com/search"
_SEARCH_PROVIDER = "brave_public"


@dataclass(frozen=True, slots=True)
class PublicSearchResult:
    title: str
    url: str


class _SearchResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._active_url = ""
        self._active_text: list[str] = []
        self.results: list[PublicSearchResult] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
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
            self.results.append(PublicSearchResult(title=title, url=self._active_url))
        self._active_url = ""
        self._active_text = []


def parse_public_search_results(html: str) -> tuple[PublicSearchResult, ...]:
    parser = _SearchResultParser()
    parser.feed(str(html or ""))
    seen: set[str] = set()
    results: list[PublicSearchResult] = []
    for result in parser.results:
        if result.url in seen:
            continue
        seen.add(result.url)
        results.append(result)
    return tuple(results)


def _article_search_sites() -> tuple[dict[str, object], ...]:
    sites: list[dict[str, object]] = []
    for site in iter_travel_registry_sites():
        profile = site.get("siteCrawlProfile")
        if not isinstance(profile, dict) or not bool(profile.get("crawlAllowed")):
            continue
        lanes = {str(value) for value in (profile.get("contentLanes") or ())}
        strategy = profile.get("discoveryStrategy")
        if "article" not in lanes or not isinstance(strategy, dict):
            continue
        if str(strategy.get("searchProvider") or "") != _SEARCH_PROVIDER:
            continue
        sites.append(site)
    return tuple(sites)


def _result_title(result: PublicSearchResult) -> str:
    path_name = urllib.parse.urlparse(result.url).path.rsplit("/", 1)[-1]
    marker = f"{path_name} "
    if marker in result.title:
        return result.title.split(marker, 1)[1].strip()
    return result.title


def public_search_article_sources(
    entity_id: str,
    *,
    entity_aliases: list[str] | tuple[str, ...] = (),
    limit: int,
) -> list[dict[str, object]]:
    if limit <= 0:
        return []
    aliases = _dedupe_terms([entity_id, *entity_aliases], limit=12)
    sources: list[dict[str, object]] = []
    seen_urls: set[str] = set()
    timeout = active_runtime_policy().source_fetch_timeout_seconds
    for site in _article_search_sites():
        profile = site["siteCrawlProfile"]
        strategy = profile["discoveryStrategy"]
        patterns = tuple(str(value) for value in (site.get("urlPatterns") or ()) if str(value))
        templates = tuple(
            str(value) for value in (strategy.get("queryTemplates") or ()) if str(value)
        )
        for template in templates:
            query = template.format(entity=entity_id)
            search_url = f"{_BRAVE_SEARCH_URL}?{urllib.parse.urlencode({'q': query})}"
            html = network_io.curl_text(search_url, timeout=timeout)
            for result in parse_public_search_results(html):
                if result.url in seen_urls:
                    continue
                if patterns and not any(fnmatch.fnmatch(result.url, pattern) for pattern in patterns):
                    continue
                title = _result_title(result)
                if not any(_title_matches_entity(title, alias) for alias in aliases):
                    continue
                seen_urls.add(result.url)
                source = _source(
                    source_id=f"article_{str(site.get('siteId') or 'public_search')}_base_{len(sources) + 1}",
                    platform=str(site.get("platform") or "旅行指南"),
                    url=result.url,
                    category=str(site.get("category") or "travelogue"),
                    discovery_provider=_SEARCH_PROVIDER,
                    match_confidence=0.94,
                    evidence_reason=(
                        f"公开搜索发现与 {entity_id} 标题匹配的实体旅行详情页；"
                        f"site={site.get('siteId')}"
                    ),
                    source_role="base",
                    images=[],
                    image_evidence_mode="",
                )
                source["title"] = title
                source["publishMediaMode"] = "text_only"
                sources.append(source)
                if len(sources) >= limit:
                    return sources
    return sources


__all__ = [
    "PublicSearchResult",
    "parse_public_search_results",
    "public_search_article_sources",
]
