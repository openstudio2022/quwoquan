"""Resolve and decode exact Baidu Baike card API pages."""
from __future__ import annotations

from dataclasses import dataclass
import html
import json
import re
import urllib.parse

from core.baike_source_contract import BAIDU_BAIKE_API_POLICY
from core.runtime_policy import active_runtime_policy
from content.source.research import network_io
from content.source.research.text_match import (
    _dedupe_terms,
    _normalized_title,
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


def decode_baidu_baike_payload(body: bytes) -> BaiduBaikePage | None:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    title = _clean_text(payload.get("title"))
    abstract = _clean_text(payload.get("abstract"))
    if not title or not abstract:
        return None
    facts: list[str] = []
    for row in payload.get("card") or []:
        if not isinstance(row, dict):
            continue
        name = _clean_text(row.get("name"))
        raw_values = row.get("value")
        values = raw_values if isinstance(raw_values, list) else [raw_values]
        value = "、".join(filter(None, (_clean_text(item) for item in values)))
        if name and value:
            facts.append(f"{name}：{value}")
    text = "\n\n".join([f"# {title}", abstract, *facts])
    return BaiduBaikePage(title=title, text=text)


def baidu_baike_api_url(term: str) -> str:
    policy = BAIDU_BAIKE_API_POLICY
    query = dict(policy.fixed_query)
    query["bk_key"] = term
    return f"{policy.base_url}?{urllib.parse.urlencode(query)}"


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
    if _wiki_title_matches_entity(page.title, entity_id):
        return True
    if not BAIDU_BAIKE_API_POLICY.require_geo_context_for_alias:
        return True
    normalized_text = _normalized_title(page.text)
    return any(
        _normalized_title(term) in normalized_text
        for term in geo_context_terms
        if _normalized_title(term)
    )


def resolve_baidu_baike_page(
    entity_id: str,
    *,
    entity_aliases: tuple[str, ...] = (),
    geo_context_terms: tuple[str, ...] = (),
) -> BaiduBaikeResolution | None:
    policy = BAIDU_BAIKE_API_POLICY
    candidates = _dedupe_terms(
        [entity_id, *entity_aliases],
        limit=policy.candidate_limit,
    )
    timeout = active_runtime_policy().provider_timeouts.encyclopedia_seconds
    for candidate in candidates:
        url = baidu_baike_api_url(candidate)
        response = network_io.fetch_http(url, timeout=timeout)
        if not response.ok or not response.body:
            continue
        page = decode_baidu_baike_payload(response.body)
        if page is None or not _page_matches_entity(
            page,
            entity_id=entity_id,
            aliases=entity_aliases,
            geo_context_terms=geo_context_terms,
        ):
            continue
        return BaiduBaikeResolution(
            url=f"https://baike.baidu.com/item/{urllib.parse.quote(page.title)}",
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
    "baidu_baike_api_url",
    "decode_baidu_baike_payload",
    "resolve_baidu_baike_page",
]
