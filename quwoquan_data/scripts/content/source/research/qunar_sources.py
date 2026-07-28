"""Qunar travelogue discovery and entity-anchor policy."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
import time
import urllib.parse
from typing import Any

from content.source.research import network_io
from content.source.research.plan_state import _source
from content.source.research.text_match import (
    _dedupe_terms,
    _entity_name_variants,
    _normalized_title,
    _title_matches_entity,
)
from content.source.research.wiki_common import _QUNAR_SEARCH_API, _strip_html
from core.runtime_policy import active_runtime_policy


_QUNAR_AUTHOR_BOOK_ANCHOR_RE = re.compile(
    r"<a\b[^>]*href=[\"']([^\"']*(?:/youji|/travelbook/note)/(\d+)[^\"']*)[\"'][^>]*>(.*?)</a>",
    re.I | re.S,
)
_QUNAR_ANCHOR_TITLE_RE = re.compile(
    r"<p\b[^>]*class=[\"'][^\"']*tit-text[^\"']*[\"'][^>]*>(.*?)</p>",
    re.I | re.S,
)
_QUNAR_ANCHOR_TIME_RE = re.compile(
    r"<p\b[^>]*class=[\"'][^\"']*tit-time[^\"']*[\"'][^>]*>(.*?)</p>",
    re.I | re.S,
)
_QUNAR_RECENT_YEARS = 3
_QUNAR_HTTP_TIMEOUT_SECONDS = active_runtime_policy().provider_timeouts.qunar_seconds
_QUNAR_ENTITY_SUFFIXES = (
    "长城",
    "攻略",
    "游记",
    "旅行",
    "旅游",
    "自由行",
    "一日游",
    "二日游",
    "三日游",
    "四日游",
    "五日游",
    "夜游",
    "复盘",
    "景区",
    "风景区",
    "风景名胜区",
    "旅游区",
    "文化旅游区",
    "古街",
    "古镇",
    "街区",
    "博物馆",
    "遗址",
    "基地",
    "公园",
)
_QUNAR_ENTITY_SPLIT_RE = re.compile(r"[—－–\-~～/／、,，|]+")
_QUNAR_ENTITY_SEARCH_SUFFIXES = (
    "风景名胜区",
    "文化旅游区",
    "旅游度假区",
    "旅游区",
    "风景区",
    "景区",
)
_QUNAR_FALSE_SUFFIXES = (
    "沟",
    "村",
    "镇",
    "乡",
    "县",
    "市",
    "区",
    "路",
    "站",
)

def _qunar_epoch_to_date(value: Any) -> str:
    try:
        raw = float(value)
    except (TypeError, ValueError):
        return ""
    if raw <= 0:
        return ""
    seconds = raw / 1000.0 if raw > 10_000_000_000 else raw
    try:
        return datetime.fromtimestamp(seconds, tz=timezone(timedelta(hours=8))).date().isoformat()
    except (OSError, OverflowError, ValueError):
        return ""

def _qunar_row_published_at(row: dict[str, Any]) -> str:
    for key in ("startTime", "publishTime", "cTime", "uTime"):
        published = _qunar_epoch_to_date(row.get(key))
        if published:
            return published
    return ""

def _qunar_parse_date(value: Any) -> datetime.date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    for pattern in (
        r"(?P<y>\d{4})-(?P<m>\d{1,2})-(?P<d>\d{1,2})",
        r"(?P<y>\d{4})/(?P<m>\d{1,2})/(?P<d>\d{1,2})",
        r"(?P<y>\d{4})年(?P<m>\d{1,2})月(?P<d>\d{1,2})日?",
    ):
        match = re.search(pattern, raw)
        if not match:
            continue
        try:
            return datetime(
                int(match.group("y")),
                int(match.group("m")),
                int(match.group("d")),
                tzinfo=timezone(timedelta(hours=8)),
            ).date()
        except ValueError:
            return None
    return None

def _qunar_freshness_tier(published_at: str) -> str:
    parsed = _qunar_parse_date(published_at)
    if parsed is None:
        return "unknown"
    today = datetime.now(timezone(timedelta(hours=8))).date()
    cutoff = today.replace(year=today.year - _QUNAR_RECENT_YEARS)
    return "recent_3y" if parsed >= cutoff else "stale_over_3y"

def _qunar_entity_anchor(value: str, entity_id: str) -> bool:
    value_key = _normalized_title(value)
    entity_key = _normalized_title(entity_id)
    if not value_key or not entity_key:
        return False
    if value_key == entity_key:
        return True
    for index in [match.start() for match in re.finditer(re.escape(entity_key), value_key)]:
        before = value_key[:index]
        after = value_key[index + len(entity_key):]
        if not after:
            return True
        if any(after.startswith(_normalized_title(suffix)) for suffix in _QUNAR_ENTITY_SUFFIXES):
            return True
        if len(entity_key) <= 2 and any(after.startswith(_normalized_title(suffix)) for suffix in _QUNAR_FALSE_SUFFIXES):
            continue
        if before.endswith(("游", "逛", "到", "去", "看")) and any(
            marker in after for marker in ("攻略", "游记", "旅行", "旅游")
        ):
            return True
    return False

def _qunar_city_conflicts_entity(
    row: dict[str, Any],
    *,
    entity_id: str,
    match_terms: list[str],
) -> bool:
    """Reject homonymous attractions whose explicit Qunar city differs."""
    city_key = _normalized_title(_strip_html(str(row.get("cityName") or "")))
    entity_key = _normalized_title(entity_id)
    if not city_key or not entity_key:
        return False
    qualifiers: set[str] = set()
    for term in _dedupe_terms(match_terms, limit=12):
        term_key = _normalized_title(term)
        if term_key and term_key != entity_key and entity_key.endswith(term_key):
            qualifier = entity_key[: -len(term_key)]
            if len(qualifier) >= 2:
                qualifiers.add(qualifier)
    return bool(qualifiers) and not any(
        city_key in qualifier or qualifier in city_key
        for qualifier in qualifiers
    )


def _qunar_row_anchor_signals(
    row: dict[str, Any],
    *,
    entity_id: str,
    match_terms: list[str],
) -> tuple[bool, bool]:
    if _qunar_city_conflicts_entity(
        row,
        entity_id=entity_id,
        match_terms=match_terms,
    ):
        return False, False
    title = _strip_html(str(row.get("title") or ""))
    route = [str(item) for item in (row.get("travelRoute") or []) if str(item).strip()]
    anchor_terms = _dedupe_terms([entity_id, *match_terms], limit=12)
    title_hit = any(_qunar_entity_anchor(title, term) for term in anchor_terms)
    route_hit = any(
        _qunar_entity_anchor(item, term)
        for item in route
        for term in anchor_terms
    )
    return title_hit, route_hit

def _qunar_source_from_row(
    *,
    row: dict[str, Any],
    entity_id: str,
    source_index: int,
    source_id_prefix: str,
    discovery_provider: str,
    match_confidence: float,
    evidence_reason: str,
) -> dict[str, Any]:
    raw_id = str(row.get("id") or "").strip()
    title = _strip_html(str(row.get("title") or ""))
    route = [str(item) for item in (row.get("travelRoute") or []) if str(item).strip()]
    city = _strip_html(str(row.get("cityName") or ""))
    source = _source(
        source_id=f"{source_id_prefix}_{source_index}",
        platform="去哪儿攻略",
        url=f"https://touch.travel.qunar.com/youji/{raw_id}",
        category="travelogue",
        discovery_provider=discovery_provider,
        match_confidence=match_confidence,
        evidence_reason=evidence_reason,
        source_role="base",
        images=[],
        image_evidence_mode="",
    )
    source["title"] = title
    author_name = _strip_html(str(row.get("userName") or row.get("authorName") or ""))
    author_id = str(row.get("userId") or row.get("authorId") or row.get("uid") or "").strip()
    if author_name:
        source["authorName"] = author_name
        source["userName"] = author_name
    if author_id:
        source["authorId"] = author_id
        source["userId"] = author_id
        source["authorBooksUrl"] = f"https://touch.travel.qunar.com/{author_id}/books"
        source["userBooksUrl"] = source["authorBooksUrl"]
    published_at = str(row.get("publishedAt") or "").strip() or _qunar_row_published_at(row)
    if published_at:
        source["publishedAt"] = published_at
    source["sourceFreshnessTier"] = _qunar_freshness_tier(published_at)
    source["routeDays"] = row.get("routeDays") or ""
    source["travelRoute"] = route[:20]
    source["viewCount"] = row.get("viewCount") or 0
    source["sourceUseMode"] = "factual_reference_only"
    source["publishMediaMode"] = "text_only"
    if city:
        source["cityName"] = city
    return source

def _qunar_author_books_rows(
    *,
    author_id: str,
    author_name: str,
    entity_id: str,
    match_terms: list[str],
    seen_ids: set[str],
    limit: int,
) -> list[dict[str, Any]]:
    """Read a Qunar author's books page and return additional detail-page rows.

    This is a conservative discovery frontier: it only emits same-author detail
    URLs whose title still anchors the current entity. Same creator context is
    useful, but it must not stitch an author's unrelated routes into this entity.
    """
    if not author_id or limit <= 0:
        return []
    books_url = f"https://touch.travel.qunar.com/{author_id}/books"
    html = network_io.curl_text(books_url, timeout=_QUNAR_HTTP_TIMEOUT_SECONDS)
    if not html:
        return []
    rows: list[dict[str, Any]] = []
    for match in _QUNAR_AUTHOR_BOOK_ANCHOR_RE.finditer(html):
        raw_id = str(match.group(2) or "").strip()
        if not raw_id or raw_id in seen_ids:
            continue
        anchor_html = match.group(3) or ""
        title_match = _QUNAR_ANCHOR_TITLE_RE.search(anchor_html)
        title = _strip_html(title_match.group(1) if title_match else anchor_html)
        time_match = _QUNAR_ANCHOR_TIME_RE.search(anchor_html)
        time_text = _strip_html(time_match.group(1) if time_match else "")
        row = {
            "id": raw_id,
            "title": title,
            "userName": author_name,
            "userId": author_id,
            "publishedAt": time_text,
        }
        title_hit = any(
            _qunar_entity_anchor(title, term) or _title_matches_entity(title, term)
            for term in match_terms
            if term
        )
        if title_hit:
            rows.append(row)
    return rows[:limit]

def _qunar_search_terms(
    entity_id: str,
    *,
    entity_aliases: list[str] | tuple[str, ...] = (),
    limit: int = 8,
) -> list[str]:
    split_terms: list[str] = []
    for part in _QUNAR_ENTITY_SPLIT_RE.split(str(entity_id or "")):
        value = part.strip()
        if len(_normalized_title(value)) < 2:
            continue
        split_terms.append(value)
        for suffix in _QUNAR_ENTITY_SEARCH_SUFFIXES:
            if value.endswith(suffix):
                short = value[: -len(suffix)].strip()
                if len(_normalized_title(short)) >= 2:
                    split_terms.append(short)
                break
    base_terms = _dedupe_terms([*_entity_name_variants(entity_id), *split_terms, *entity_aliases], limit=8)
    primary = str(base_terms[0] if base_terms else entity_id or "").strip()
    primary_intents = [f"{primary}攻略", f"{primary}游记"] if primary else []
    primary_context = [f"{primary}旅游", f"{primary}景区"] if primary else []
    return _dedupe_terms([*primary_intents, *base_terms, *primary_context], limit=limit)

def _qunar_travelogue_sources(
    entity_id: str,
    *,
    entity_aliases: list[str] | tuple[str, ...] = (),
    limit: int = 4,
) -> list[dict[str, Any]]:
    """Discover fetchable Qunar travelogue pages for article text evidence.

    RC4：去哪儿 UGC 游记是 text-only 文章底稿，配图必须同源；不再接受外部「授权图集」
    （已删除 authorized_images 死参），images 恒为空、imageEvidenceMode=""。
    """
    sources: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    # Composite scenic areas often have official operation names while UGC uses
    # sub-site or short destination names. Keep enough alias budget to reach
    # curated registry aliases without lowering the downstream entity gate.
    search_terms = _qunar_search_terms(entity_id, entity_aliases=entity_aliases, limit=8)
    match_terms = _dedupe_terms([*_entity_name_variants(entity_id), *entity_aliases, *search_terms], limit=16)
    source_index = 0
    expanded_author_ids: set[str] = set()
    for term in search_terms:
        for page in (1, 2):
            page_candidate_count_before = len(candidates)
            encoded_q = urllib.parse.quote(term)
            data: dict[str, Any] = {}
            for attempt in range(2):
                for url in (
                    f"{_QUNAR_SEARCH_API}?_json&q={encoded_q}&page={page}",
                    f"{_QUNAR_SEARCH_API}?_json=&q={encoded_q}&page={page}",
                ):
                    data = network_io.curl_json(url, timeout=_QUNAR_HTTP_TIMEOUT_SECONDS)
                    if data.get("ret") is True:
                        break
                if data.get("ret") is True:
                    break
                time.sleep(0.35 * (attempt + 1))
            payload = data.get("data") if isinstance(data.get("data"), dict) else {}
            rows = payload.get("bookList") if isinstance(payload.get("bookList"), list) else []
            if not rows:
                break
            for row in rows:
                if not isinstance(row, dict):
                    continue
                raw_id = str(row.get("id") or "").strip()
                if not raw_id or raw_id in seen_ids:
                    continue
                title = _strip_html(str(row.get("title") or ""))
                route = [str(item) for item in (row.get("travelRoute") or []) if str(item).strip()]
                city = _strip_html(str(row.get("cityName") or ""))
                title_hit, route_hit = _qunar_row_anchor_signals(
                    row,
                    entity_id=entity_id,
                    match_terms=match_terms,
                )
                if not (title_hit or route_hit):
                    continue
                seen_ids.add(raw_id)
                published_at = str(row.get("publishedAt") or "").strip() or _qunar_row_published_at(row)
                freshness = _qunar_freshness_tier(published_at)
                match_confidence = 0.96 if title_hit else 0.88
                if freshness == "stale_over_3y":
                    match_confidence = min(match_confidence, 0.74)
                candidates.append(
                    {
                        "row": row,
                        "term": term,
                        "title": title,
                        "route": route,
                        "city": city,
                        "titleHit": title_hit,
                        "routeHit": route_hit,
                        "freshness": freshness,
                        "matchConfidence": match_confidence,
                    }
                )
                author_name = _strip_html(str(row.get("userName") or ""))
                author_id = str(row.get("userId") or row.get("authorId") or row.get("uid") or "").strip()
                if author_id and author_id not in expanded_author_ids:
                    expanded_author_ids.add(author_id)
                    expansion_budget = 2
                    for author_row in _qunar_author_books_rows(
                        author_id=author_id,
                        author_name=author_name,
                        entity_id=entity_id,
                        match_terms=match_terms,
                        seen_ids=seen_ids,
                        limit=expansion_budget,
                    ):
                        author_raw_id = str(author_row.get("id") or "").strip()
                        if not author_raw_id or author_raw_id in seen_ids:
                            continue
                        seen_ids.add(author_raw_id)
                        author_title = _strip_html(str(author_row.get("title") or ""))
                        author_title_hit, author_route_hit = _qunar_row_anchor_signals(
                            author_row,
                            entity_id=entity_id,
                            match_terms=match_terms,
                        )
                        if not (author_title_hit or author_route_hit):
                            continue
                        author_freshness = _qunar_freshness_tier(
                            str(author_row.get("publishedAt") or "")
                        )
                        candidates.append(
                            {
                                "row": author_row,
                                "term": f"author:{author_name or author_id}",
                                "title": author_title,
                                "route": [],
                                "city": "",
                                "titleHit": author_title_hit,
                                "routeHit": author_route_hit,
                                "freshness": author_freshness,
                                "matchConfidence": 0.86 if author_freshness != "stale_over_3y" else 0.74,
                                "authorExpansion": True,
                                "authorLabel": author_name or author_id,
                        }
                    )
            if not payload.get("more"):
                break
            if len(candidates) >= limit:
                break
            if len(candidates) == page_candidate_count_before:
                break
    def _candidate_sort_key(item: dict[str, Any]) -> tuple[int, int, int, int, int]:
        freshness_rank = {
            "recent_3y": 0,
            "unknown": 1,
            "stale_over_3y": 2,
        }.get(str(item.get("freshness") or ""), 1)
        anchor_rank = 0 if item.get("titleHit") else 1
        route_len = len(item.get("route") or [])
        try:
            views = int(item.get("row", {}).get("viewCount") or 0)
        except (TypeError, ValueError):
            views = 0
        return (
            freshness_rank,
            anchor_rank,
            min(route_len, 20),
            -int(float(item.get("matchConfidence") or 0.0) * 1000),
            -views,
        )

    for item in sorted(candidates, key=_candidate_sort_key):
        if len(sources) >= limit:
            break
        source_index += 1
        row = item["row"]
        provider = (
            "qunar_author_books_page"
            if item.get("authorExpansion")
            else "qunar_touch_search_json"
        )
        reason_prefix = (
            f"去哪儿攻略同作者作品集补源 {entity_id}；author={item.get('authorLabel')};"
            if item.get("authorExpansion")
            else f"去哪儿攻略游记搜索命中 {entity_id}；query={item.get('term')};"
        )
        source = _qunar_source_from_row(
            row=row,
            entity_id=entity_id,
            source_index=source_index,
            source_id_prefix="article_qunar_base",
            discovery_provider=provider,
            match_confidence=float(item.get("matchConfidence") or 0.0),
            evidence_reason=(
                f"{reason_prefix} title={str(item.get('title') or '')[:60]} "
                f"route={','.join((item.get('route') or [])[:6])} city={item.get('city') or ''}; "
                f"freshness={item.get('freshness')}"
            ),
        )
        source["sourceFreshnessTier"] = item.get("freshness") or source.get("sourceFreshnessTier") or "unknown"
        sources.append(source)
    return sources

def _qunar_review_support_source(entity_id: str) -> dict[str, Any]:
    source = _source(
        source_id="article_qunar_review_support",
        platform="去哪儿景点点评",
        url=f"https://touch.travel.qunar.com/search?q={urllib.parse.quote(entity_id)}",
        category="review_note",
        discovery_provider="qunar_touch_search_page",
        match_confidence=0.86,
        evidence_reason=f"去哪儿搜索页提供 {entity_id} 景点标签、游记列表、热度与点评线索，可作多意图事实参考底稿",
        source_role="base",
    )
    source["category"] = "review_note"
    return source
