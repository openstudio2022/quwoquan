"""Resolve canonical public baike.com pages for entities without Wikipedia pages."""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import re
import urllib.parse

from core.baike_source_contract import (
    TOUTIAO_BAIKE_CANONICAL_RESOLUTION,
    source_url_matches_contract,
)
from content.source.research import network_io
from content.source.research.text_match import (
    _dedupe_terms,
    _geo_context_matches,
    _normalized_title,
    _wiki_resolved_title_matches_entity,
    _wiki_title_matches_entity,
)


@dataclass(frozen=True, slots=True)
class BaikePageResolution:
    url: str
    title: str
    matched_term: str
    match_confidence: float


class _PageMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_title = False
        self._title_parts: list[str] = []
        self.description = ""

    @property
    def title(self) -> str:
        raw = re.sub(r"\s+", " ", "".join(self._title_parts)).strip()
        return re.sub(r"[-_—]\s*快懂百科\s*$", "", raw).strip()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() == "title":
            self._in_title = True
            return
        if tag.casefold() != "meta":
            return
        values = {key.casefold(): str(value or "") for key, value in attrs}
        if values.get("name", "").casefold() == "description":
            self.description = values.get("content", "").strip()

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)


def geo_context_terms_from_ref(geo_tag_ref: str) -> tuple[str, ...]:
    segments = [
        segment.strip()
        for segment in str(geo_tag_ref or "").split("/")
        if segment.strip()
    ]
    try:
        country_index = segments.index("中国")
    except ValueError:
        return ()
    return tuple(_dedupe_terms(segments[country_index + 1 :], limit=len(segments)))


def _metadata_matches_entity(
    *,
    title: str,
    description: str,
    entity_id: str,
    aliases: tuple[str, ...],
    geo_context_terms: tuple[str, ...],
) -> bool:
    if not _wiki_resolved_title_matches_entity(
        title,
        entity_id,
        entity_aliases=aliases,
    ):
        return False
    if not _geo_context_matches(
        " ".join((title, description, entity_id)),
        geo_context_terms,
    ):
        return False
    if _wiki_title_matches_entity(title, entity_id):
        return True
    if not TOUTIAO_BAIKE_CANONICAL_RESOLUTION.require_geo_context_for_alias:
        return True
    normalized_description = _normalized_title(description)
    return any(
        _normalized_title(term) in normalized_description
        for term in geo_context_terms
        if _normalized_title(term)
    )


def _contextual_search_terms(
    entity_id: str,
    geo_context_terms: tuple[str, ...],
) -> list[str]:
    """为同名词条补城市/省份限定词；限定词只用于查询，不改变身份匹配。"""
    contextual: list[str] = []
    for context in reversed(geo_context_terms):
        normalized = str(context or "").strip()
        if not normalized or normalized in entity_id:
            continue
        short = re.sub(r"(特别行政区|自治区|自治州|地区|省|市|区|县)$", "", normalized)
        if short and short not in entity_id:
            contextual.append(f"{short}{entity_id}")
    return contextual


def resolve_toutiao_baike_page(
    entity_id: str,
    *,
    entity_aliases: tuple[str, ...] = (),
    geo_context_terms: tuple[str, ...] = (),
) -> BaikePageResolution | None:
    policy = TOUTIAO_BAIKE_CANONICAL_RESOLUTION
    candidates = _dedupe_terms(
        [
            entity_id,
            *entity_aliases,
            *_contextual_search_terms(entity_id, geo_context_terms),
        ],
        limit=policy.candidate_limit,
    )
    timeout = 20
    for candidate in candidates:
        response = network_io.fetch_http(
            f"{policy.base_url}{urllib.parse.quote(candidate)}",
            timeout=timeout,
        )
        if not response.ok or not response.body:
            continue
        if not source_url_matches_contract("toutiao_baike", response.final_url):
            continue
        parser = _PageMetadataParser()
        try:
            parser.feed(response.body.decode("utf-8", errors="replace"))
        except ValueError:
            continue
        if not parser.title or not parser.description:
            continue
        if not _metadata_matches_entity(
            title=parser.title,
            description=parser.description,
            entity_id=entity_id,
            aliases=entity_aliases,
            geo_context_terms=geo_context_terms,
        ):
            continue
        return BaikePageResolution(
            url=response.final_url,
            title=parser.title,
            matched_term=candidate,
            match_confidence=(
                policy.canonical_confidence
                if _wiki_title_matches_entity(parser.title, entity_id)
                else policy.alias_confidence
            ),
        )
    return None


__all__ = [
    "BaikePageResolution",
    "geo_context_terms_from_ref",
    "resolve_toutiao_baike_page",
]
