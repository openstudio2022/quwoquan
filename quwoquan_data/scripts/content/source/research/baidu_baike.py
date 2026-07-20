"""Resolve and decode exact public Baidu Baike entry pages."""
from __future__ import annotations

from dataclasses import dataclass
import html
import re
import urllib.parse

from core.baike_source_contract import BAIDU_BAIKE_CANONICAL_RESOLUTION
from core.runtime_policy import active_runtime_policy
from content.source.html_text import _html_to_plain_text
from content.source.research import network_io
from content.source.research.text_match import (
    _dedupe_terms,
    _geo_context_matches,
    _wiki_resolved_title_matches_entity,
    _wiki_title_matches_entity,
)


@dataclass(frozen=True, slots=True)
class BaiduBaikePage:
    title: str
    text: str


@dataclass(frozen=True, slots=True)
class BaiduBaikeResolution:
    url: str
    title: str
    matched_term: str
    match_confidence: float


def _clean_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def decode_baidu_baike_html(body: bytes, *, url: str) -> BaiduBaikePage | None:
    raw = body.decode("utf-8", errors="replace")
    title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw)
    title = _clean_text(title_match.group(1) if title_match else "")
    title = re.sub(r"[_\-|]\s*百度百科.*$", "", title).strip()
    text = _html_to_plain_text(raw, url).strip()
    if not title or len(text) < 40:
        return None
    return BaiduBaikePage(title=title, text=text)


def baidu_baike_search_url(term: str) -> str:
    return (
        BAIDU_BAIKE_CANONICAL_RESOLUTION.base_url
        + urllib.parse.quote(str(term or "").strip(), safe="")
    )


def _canonical_entry_url(final_url: str) -> str | None:
    parsed = urllib.parse.urlsplit(final_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "baike.baidu.com"
        or not parsed.path.startswith("/item/")
    ):
        return None
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _page_matches_entity(
    page: BaiduBaikePage,
    *,
    entity_id: str,
    aliases: tuple[str, ...],
    geo_context_terms: tuple[str, ...],
) -> bool:
    if not _wiki_resolved_title_matches_entity(
        page.title,
        entity_id,
        entity_aliases=aliases,
    ):
        return False
    if not _geo_context_matches(
        " ".join((page.title, page.text, entity_id)),
        geo_context_terms,
    ):
        return False
    if _wiki_title_matches_entity(page.title, entity_id):
        return True
    return not BAIDU_BAIKE_CANONICAL_RESOLUTION.require_geo_context_for_alias or bool(
        geo_context_terms
    )


def resolve_baidu_baike_page(
    entity_id: str,
    *,
    entity_aliases: tuple[str, ...] = (),
    geo_context_terms: tuple[str, ...] = (),
) -> BaiduBaikeResolution | None:
    policy = BAIDU_BAIKE_CANONICAL_RESOLUTION
    candidates = _dedupe_terms(
        [entity_id, *entity_aliases],
        limit=policy.candidate_limit,
    )
    timeout = active_runtime_policy().provider_timeouts.encyclopedia_seconds
    for candidate in candidates:
        response = network_io.fetch_http(
            baidu_baike_search_url(candidate),
            timeout=timeout,
        )
        if not response.ok or not response.body:
            continue
        canonical_url = _canonical_entry_url(response.final_url)
        if canonical_url is None:
            continue
        page = decode_baidu_baike_html(response.body, url=canonical_url)
        if page is None or not _page_matches_entity(
            page,
            entity_id=entity_id,
            aliases=entity_aliases,
            geo_context_terms=geo_context_terms,
        ):
            continue
        return BaiduBaikeResolution(
            url=canonical_url,
            title=page.title,
            matched_term=candidate,
            match_confidence=(
                policy.canonical_confidence
                if _wiki_title_matches_entity(page.title, entity_id)
                else policy.alias_confidence
            ),
        )
    return None


__all__ = [
    "BaiduBaikePage",
    "BaiduBaikeResolution",
    "baidu_baike_search_url",
    "decode_baidu_baike_html",
    "resolve_baidu_baike_page",
]
