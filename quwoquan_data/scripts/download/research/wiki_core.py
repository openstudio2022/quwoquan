"""MediaWiki, Wikidata and trusted external-link discovery."""
from __future__ import annotations

import re
import urllib.parse
from typing import Any

from download.research import runtime_bridge
from download.research.runtime_bridge import curl_json as _curl_json, wiki_api as _wiki_api
from download.research.source_quality import _homepage_text_quality_issue
from download.research.text_match import (
    _dedupe_terms,
    _entity_name_variants,
    _normalized_title,
    _text_mentions_entity,
    _title_matches_entity,
    _wiki_resolved_title_matches_entity,
    _wiki_title_matches_entity,
)

def _wiki_title(host: str, entity_id: str) -> str:
    def _usable_title(title: str) -> str:
        if not title or not _wiki_title_matches_entity(title, entity_id):
            return ""
        extract = _wiki_api(
            host,
            {
                "action": "query",
                "titles": title,
                "prop": "extracts",
                "explaintext": "1",
                "format": "json",
            },
        )
        pages = (extract.get("query") or {}).get("pages") or {}
        for page in pages.values():
            if not isinstance(page, dict):
                continue
            extract_text = str(page.get("extract") or "").strip()
            if extract_text and not _homepage_text_quality_issue(
                extract_text,
                entity_id,
                require_fact_ready=False,
            ):
                return str(page.get("title") or title)
        return ""

    exact = _wiki_api(host, {"action": "query", "titles": entity_id, "format": "json"})
    pages = (exact.get("query") or {}).get("pages") or {}
    for page in pages.values():
        if isinstance(page, dict) and int(page.get("pageid") or -1) > 0:
            title = str(page.get("title") or entity_id)
            usable = _usable_title(title)
            if usable:
                return usable
    search = _wiki_api(
        host,
        {
            "action": "query",
            "list": "search",
            "srsearch": entity_id,
            "srlimit": 5,
            "format": "json",
        },
    )
    rows = ((search.get("query") or {}).get("search") or [])
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "")
        usable = _usable_title(title)
        if usable:
            return usable
    return ""

def _wiki_title_for_entity(
    host: str,
    entity_id: str,
    *,
    entity_aliases: list[str] | tuple[str, ...] = (),
    limit: int = 10,
) -> str:
    """Resolve an entity wiki title through canonical name, short names and aliases."""
    terms = _dedupe_terms(
        [*_entity_name_variants(entity_id), *entity_aliases],
        limit=limit,
    )
    validation_aliases = _dedupe_terms([*terms, *entity_aliases], limit=limit + len(entity_aliases))
    for term in terms:
        title = runtime_bridge.call("_wiki_title", _wiki_title, host, term)
        if not title:
            continue
        if _wiki_resolved_title_matches_entity(
            title,
            entity_id,
            entity_aliases=validation_aliases,
        ):
            return title
    return ""

def _wiki_related_titles_for_entity(
    host: str,
    entity_id: str,
    *,
    entity_aliases: list[str] | tuple[str, ...] = (),
    limit: int = 3,
) -> list[str]:
    """Resolve related wiki pages through aliases while preserving entity grounding."""
    found: list[str] = []
    seen: set[str] = set()
    terms = _dedupe_terms(
        [*_entity_name_variants(entity_id), *entity_aliases],
        limit=max(limit * 2, 8),
    )
    for term in terms:
        for title in runtime_bridge.call("_wiki_related_titles", _wiki_related_titles, host, term, limit=limit):
            key = _normalized_title(title)
            if not key or key in seen:
                continue
            if not (
                _text_mentions_entity(title, entity_id, entity_aliases=entity_aliases)
                or _text_mentions_entity(title, term, entity_aliases=entity_aliases)
            ):
                continue
            seen.add(key)
            found.append(title)
            if len(found) >= limit:
                return found
    return found

_RELATED_WIKI_SUFFIXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("博物馆", ("遗址", "文化遗址", "")),
    ("纪念馆", ("故居", "旧址", "")),
)

def _wiki_related_titles(host: str, entity_id: str, *, limit: int = 3) -> list[str]:
    """Find tightly related wiki pages for supporting evidence only.

    Some visitor-facing entities (for example a museum built around an
    archaeological site) have no exact wiki page while the underlying cultural
    object has one. These pages are useful for factual context, but must never
    replace the entity homepage or become article base drafts.
    """
    entity_id = str(entity_id or "").strip()
    if not entity_id:
        return []
    stems: list[str] = []
    for suffix, related_suffixes in _RELATED_WIKI_SUFFIXES:
        if entity_id.endswith(suffix) and len(entity_id) > len(suffix):
            stem = entity_id[: -len(suffix)]
            stems.extend(stem + item for item in related_suffixes)
    if not stems:
        return []
    data = _wiki_api(
        host,
        {
            "action": "query",
            "list": "search",
            "srsearch": entity_id,
            "srlimit": 10,
            "format": "json",
        },
    )
    rows = ((data.get("query") or {}).get("search") or [])
    wanted = {_normalized_title(item) for item in stems if item.strip()}
    found: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip()
        title_key = _normalized_title(title)
        if not title or title_key in seen:
            continue
        if title_key not in wanted:
            continue
        extract = _wiki_api(
            host,
            {
                "action": "query",
                "titles": title,
                "prop": "extracts",
                "explaintext": "1",
                "format": "json",
            },
        )
        pages = (extract.get("query") or {}).get("pages") or {}
        if not any(
            isinstance(page, dict) and str(page.get("extract") or "").strip()
            for page in pages.values()
        ):
            continue
        seen.add(title_key)
        found.append(title)
        if len(found) >= limit:
            break
    return found

def _wiki_url(host: str, title: str) -> str:
    if not title:
        return ""
    return f"https://{host}/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"

def _wikidata_item_for_zhwiki(title: str) -> str:
    data = _wiki_api("zh.wikipedia.org", {
        "action": "query",
        "titles": title,
        "prop": "pageprops",
        "format": "json",
    })
    pages = (data.get("query") or {}).get("pages") or {}
    for page in pages.values():
        if isinstance(page, dict):
            qid = str((page.get("pageprops") or {}).get("wikibase_item") or "")
            if qid:
                return qid
    return ""

def _wikidata_item_for_entity_search(entity_id: str) -> str:
    """Return a strongly matching Wikidata QID without relying on zhwiki.

    Some Chinese scenic areas do not have a zhwiki page but do have a Wikidata
    item with Commons media. We only accept exact/strong label or alias matches;
    weak city/province substitutes stay out of the plan.
    """
    if not entity_id:
        return ""
    for term in _dedupe_terms(_entity_name_variants(entity_id), limit=5):
        data = _curl_json(
            "https://www.wikidata.org/w/api.php?"
            + urllib.parse.urlencode(
                {
                    "action": "wbsearchentities",
                    "search": term,
                    "language": "zh",
                    "uselang": "zh",
                    "limit": 5,
                    "format": "json",
                }
            ),
            timeout=20,
        )
        rows = data.get("search") if isinstance(data.get("search"), list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            labels = [str(row.get("label") or ""), str(row.get("match", {}).get("text") or "")]
            aliases = row.get("aliases") if isinstance(row.get("aliases"), list) else []
            labels.extend(str(item) for item in aliases)
            if any(
                _title_matches_entity(label, entity_id)
                or _title_matches_entity(label, term)
                for label in labels
                if label
            ):
                qid = str(row.get("id") or "")
                if qid.startswith("Q"):
                    return qid
    return ""

def _wikidata_claims(qid: str) -> dict[str, Any]:
    if not qid:
        return {}
    data = _curl_json(
        "https://www.wikidata.org/w/api.php?"
        + urllib.parse.urlencode(
            {
                "action": "wbgetentities",
                "ids": qid,
                "props": "claims",
                "format": "json",
            }
        ),
        timeout=20,
    )
    entity = ((data.get("entities") or {}).get(qid) or {})
    claims = entity.get("claims") if isinstance(entity.get("claims"), dict) else {}
    return claims if isinstance(claims, dict) else {}

def _wikidata_entity_aliases(qid: str) -> list[str]:
    if not qid:
        return []
    data = _curl_json(
        "https://www.wikidata.org/w/api.php?"
        + urllib.parse.urlencode(
            {
                "action": "wbgetentities",
                "ids": qid,
                "props": "labels|aliases",
                "languages": "zh|zh-hans|zh-hant|en",
                "format": "json",
            }
        ),
        timeout=20,
    )
    entity = ((data.get("entities") or {}).get(qid) or {})
    values: list[str] = []
    for bucket_name in ("labels", "aliases"):
        bucket = entity.get(bucket_name) if isinstance(entity.get(bucket_name), dict) else {}
        for rows in bucket.values():
            if isinstance(rows, dict):
                rows = [rows]
            if not isinstance(rows, list):
                continue
            for row in rows:
                if isinstance(row, dict):
                    value = str(row.get("value") or "").strip()
                    if value and value not in values:
                        values.append(value)
    return values

def _claim_string_values(claims: dict[str, Any], pid: str) -> list[str]:
    values: list[str] = []
    for claim in claims.get(pid) or []:
        if not isinstance(claim, dict):
            continue
        shutdown_wait = True
        try:
            value = claim["mainsnak"]["datavalue"]["value"]
        except (KeyError, TypeError):
            continue
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    return values

def _official_website(qid: str) -> str:
    if not qid:
        return ""
    for value in _claim_string_values(_wikidata_claims(qid), "P856"):
        if value.startswith(("http://", "https://")):
            return value
    return ""

_TRUSTED_EXTERNAL_DOMAINS: tuple[str, ...] = (
    "gov.cn",
    "people.com.cn",
    "news.cn",
    "xinhuanet.com",
    "chinanews.com",
    "cctv.com",
    "gmw.cn",
    "scol.com.cn",
    "newssc.org",
    "whc.unesco.org",
    "mnr.gov.cn",
    "dujiangyan.com.cn",
    "yading.cn",
    "yadingtour.com",
    "sxd.cn",
    "ctrip.com",
    "trip.com",
    "mafengwo.cn",
    "mafengwo.com",
    "qyer.com",
    "tripadvisor.cn",
    "tripadvisor.com",
    "lonelyplanet.com",
    "nationalgeographic.com",
)

def _trusted_external_links(title: str, *, limit: int = 4) -> list[str]:
    if not title:
        return []
    data = _wiki_api(
        "zh.wikipedia.org",
        {
            "action": "query",
            "titles": title,
            "prop": "extlinks",
            "ellimit": 50,
            "format": "json",
        },
    )
    pages = (data.get("query") or {}).get("pages") or {}
    links: list[str] = []
    seen: set[str] = set()
    for page in pages.values():
        if not isinstance(page, dict):
            continue
        for row in page.get("extlinks") or []:
            raw = str(row.get("*") or row.get("url") or "").strip()
            if not raw or raw in seen:
                continue
            parsed = urllib.parse.urlparse(raw)
            host = (parsed.hostname or "").lower()
            if not parsed.scheme.startswith("http"):
                continue
            if "web.archive.org" in host or "google." in host or "toolforge.org" in host:
                continue
            if any(host == domain or host.endswith(f".{domain}") for domain in _TRUSTED_EXTERNAL_DOMAINS):
                seen.add(raw)
                links.append(raw)
            if len(links) >= limit:
                return links
    return links

def _external_platform(url: str) -> str:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if "ctrip.com" in host or "trip.com" in host:
        return "携程攻略"
    if "mafengwo." in host:
        return "马蜂窝"
    if "qyer.com" in host:
        return "穷游"
    if "tripadvisor." in host:
        return "Tripadvisor"
    if "lonelyplanet.com" in host:
        return "Lonely Planet"
    if "nationalgeographic.com" in host:
        return "National Geographic"
    if "people.com.cn" in host:
        return "人民网"
    if "news.cn" in host or "xinhuanet.com" in host:
        return "新华网"
    if "chinanews.com" in host:
        return "中国新闻网"
    if "cctv.com" in host:
        return "央视网"
    if "gmw.cn" in host:
        return "光明网"
    if "whc.unesco.org" in host:
        return "UNESCO"
    if host.endswith("gov.cn") or host.endswith("mnr.gov.cn"):
        return "文旅局"
    if "dujiangyan.com.cn" in host or "yading" in host:
        return "景区官网"
    return "权威媒体"

def _url_looks_like_article(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    path = (parsed.path or "").lower()
    if not path or path in {"/", ""}:
        return False
    basename = path.rsplit("/", 1)[-1]
    if basename in {"index.html", "index.htm", "default.html", "default.htm"}:
        return False
    article_patterns = (
        r"/n\d+/\d{4}/\d{4}/",
        r"/\d{4}/\d{2}/\d{2}/",
        r"/\d{4}-\d{2}/\d{2}/",
        r"/c_\d+",
        r"/arti[a-z0-9]+",
        r"userobject\d+ai\d+",
    )
    if any(re.search(pattern, path) for pattern in article_patterns):
        return True
    return bool(re.search(r"\.(shtml|html|htm)$", path) and re.search(r"\d{4,}", path))

def _external_article_category(url: str, platform: str) -> str:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    platform_text = platform.casefold()
    if any(marker in host for marker in ("ctrip.com", "trip.com", "mafengwo.", "qyer.com", "tripadvisor.")):
        return "travelogue"
    if "lonelyplanet.com" in host or "nationalgeographic.com" in host or "whc.unesco.org" in host:
        return "vertical_professional"
    if host.endswith("gov.cn") or host.endswith("mnr.gov.cn") or platform in {"文旅局", "景区官网"}:
        return "official_article" if _url_looks_like_article(url) else "official"
    if any(marker in host for marker in ("people.com.cn", "news.cn", "xinhuanet.com", "chinanews.com", "cctv.com", "gmw.cn")):
        return "media_article" if _url_looks_like_article(url) else "authoritative_reference"
    if any(marker in platform_text for marker in ("人民网", "新华", "中国新闻网", "央视", "光明", "media")):
        return "media_article" if _url_looks_like_article(url) else "authoritative_reference"
    return "authoritative_reference"
