"""
可复用的 crawl topic source_pool 生成与合并（不绑定「川西」业务名）。

策略要点：
- 默认不再使用无过滤的 zh.wikipedia prop=links（易产生与景点无关的百科互链）。
- 可选 filtered / full 维基扩链；中文维基主条与百度百科主条始终可写入。
- Wikivoyage opensearch（MediaWiki 官方 API）补充旅行向条目 URL。
- 百度百科 HTML 内链经路径/词表过滤。
- 支持 merge 去重追加、按 topic 切片、从 NDJSON 合并人工旅游 URL。
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Literal, cast

from common import RUNTIME_ROOT, ensure_runtime_layout, read_ndjson, read_yaml, write_ndjson
from native_fetch import NativeFetchError, fetch_html_page

TOPIC_ENRICHMENT_SCHEMA_VERSION = "quwoquan_data.topic_enrichment"
DEFAULT_MAX_SOURCES = 22
BAIKE_ITEM_LINK_RE = re.compile(r'href="(/item/[^"?#]+)"', re.I)
MW_USER_AGENT = "quwoquan-data-crawl-topic-pool/1.0 (+https://github.com/quwoquan/quwoquan)"

WikiExpandMode = Literal["none", "filtered", "full"]


def _normalize_wiki_expand(mode: str) -> WikiExpandMode:
    m = (mode or "filtered").strip().lower()
    if m in ("none", "filtered", "full"):
        return cast(WikiExpandMode, m)
    return "filtered"


def _http_json(url: str, timeout: int = 25) -> dict[str, Any] | list[Any] | None:
    req = urllib.request.Request(url, headers={"User-Agent": MW_USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return None


def _wiki_title_resolves(site: str, wiki_title: str) -> bool:
    api = f"https://{site}/w/api.php"
    params = {"action": "query", "format": "json", "titles": wiki_title, "prop": "info", "redirects": "1"}
    url = api + "?" + urllib.parse.urlencode(params)
    payload = _http_json(url, 20)
    if not isinstance(payload, dict):
        return False
    for page in (payload.get("query") or {}).get("pages", {}).values():
        if isinstance(page, dict) and page.get("missing"):
            return False
    return True


def _wiki_api_links_raw(site: str, wiki_title: str, *, limit: int) -> list[str]:
    base = f"https://{site}/w/api.php"
    params: dict[str, str] = {
        "action": "query",
        "format": "json",
        "titles": wiki_title,
        "redirects": "1",
        "prop": "links",
        "plnamespace": "0",
        "pllimit": str(min(500, max(limit, 1))),
    }
    out: list[str] = []
    seen_titles: set[str] = set()
    for _ in range(12):
        url = base + "?" + urllib.parse.urlencode(params)
        payload = _http_json(url, 25)
        if not isinstance(payload, dict):
            break
        pages = (payload.get("query") or {}).get("pages") or {}
        for page in pages.values():
            if not isinstance(page, dict) or page.get("missing"):
                continue
            if int(str(page.get("ns", 0) or 0)) != 0:
                continue
            for row in page.get("links") or []:
                if not isinstance(row, dict):
                    continue
                title = str(row.get("title") or "").strip()
                if not title or ":" in title or title in seen_titles:
                    continue
                seen_titles.add(title)
                encoded = urllib.parse.quote(title.replace(" ", "_"))
                out.append(f"https://{site}/wiki/{encoded}")
                if len(out) >= limit:
                    return out
        cont = payload.get("continue")
        if isinstance(cont, dict):
            for key, value in cont.items():
                params[str(key)] = str(value)
            continue
        break
    return out


def _derive_relevance_tokens(name: str, aliases: list[str], core_tokens: list[str]) -> list[str]:
    tokens: list[str] = []
    for chunk in [name, *aliases, *core_tokens]:
        s = str(chunk).strip()
        if not s:
            continue
        if s not in tokens:
            tokens.append(s)
        if len(s) >= 2:
            for i in range(len(s) - 1):
                bi = s[i : i + 2]
                if bi.strip() and bi not in tokens and not bi.isspace():
                    tokens.append(bi)
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        t = t.strip()
        if len(t) < 2 or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out[:48]


def _title_matches_tokens(title: str, tokens: list[str]) -> bool:
    tnorm = title.strip()
    if not tnorm:
        return False
    for tok in tokens:
        if tok and tok in tnorm:
            return True
    return False


def _wiki_links_filtered(
    site: str,
    wiki_title: str,
    *,
    limit: int,
    tokens: list[str],
) -> list[str]:
    raw = _wiki_api_links_raw(site, wiki_title, limit=max(limit * 8, 80))
    out: list[str] = []
    for url in raw:
        title = urllib.parse.unquote(url.split("/wiki/", 1)[-1]).replace("_", " ") if "/wiki/" in url else ""
        if _title_matches_tokens(title, tokens):
            out.append(url)
        if len(out) >= limit:
            break
    return out


def _wikivoyage_opensearch_urls(query: str, *, limit: int) -> list[str]:
    params = {
        "action": "opensearch",
        "search": query,
        "limit": str(max(1, min(limit, 20))),
        "namespace": "0",
        "format": "json",
    }
    url = "https://zh.wikivoyage.org/w/api.php?" + urllib.parse.urlencode(params)
    payload = _http_json(url, 25)
    if not isinstance(payload, list) or len(payload) < 4:
        return []
    urls = payload[3]
    if not isinstance(urls, list):
        return []
    out: list[str] = []
    for u in urls:
        if isinstance(u, str) and u.startswith("http") and "zh.wikivoyage.org" in u:
            out.append(u)
    return out[:limit]


def _baike_item_links_filtered(
    baike_path_title: str, *, limit: int, tokens: list[str]
) -> list[str]:
    url = "https://baike.baidu.com/item/" + urllib.parse.quote(baike_path_title)
    try:
        page = fetch_html_page(url, timeout_seconds=25)
    except NativeFetchError:
        return []
    found = BAIKE_ITEM_LINK_RE.findall(page.html)
    out: list[str] = []
    seen: set[str] = set()
    for path in found:
        full = "https://baike.baidu.com" + path.split("?")[0]
        tail = urllib.parse.unquote(full.split("/item/", 1)[-1]) if "/item/" in full else ""
        if not _title_matches_tokens(tail, tokens):
            continue
        if full in seen:
            continue
        seen.add(full)
        out.append(full)
        if len(out) >= limit:
            break
    return out


def _source_id_for_url(url: str) -> str:
    return "src_" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def build_article_row(
    *,
    topic_title: str,
    spec_query: str,
    url: str,
    page_title: str,
    snippet: str,
    engagement: int,
    relevance_tokens: list[str],
) -> dict[str, Any]:
    sid = _source_id_for_url(url)
    row: dict[str, Any] = {
        "candidateId": sid,
        "sourceId": sid,
        "taskType": "article",
        "topicTitle": topic_title,
        "query": spec_query,
        "title": page_title[:200] if page_title else sid,
        "sourceUrl": url,
        "snippet": snippet[:800] if snippet else "",
        "sourceRole": "publish_candidate",
        "rightsStatus": "clear",
        "watermarkStatus": "clean",
        "duplicateStatus": "unique",
        "adSignal": False,
        "likes": engagement,
        "shares": max(0, engagement // 4),
        "comments": max(0, engagement // 5),
        "qualityBreakdown": {
            "contentCompleteness": 22,
            "actionability": 16,
            "sourceCredibility": 14,
            "freshness": 8,
            "richness": 9,
            "engagementSignal": 8,
            "cleanliness": 9,
        },
        "publishabilityBreakdown": {
            "readerValue": 16,
            "routeSpecificity": 14,
            "factDensity": 14,
            "practicality": 12,
            "narrativePotential": 14,
            "encyclopedicPenalty": 6,
        },
    }
    if relevance_tokens:
        row["relevanceTokens"] = relevance_tokens
    return row


def default_enrichment_row(spec: dict[str, Any], topic_id: str, task_type: str, title: str) -> dict[str, Any]:
    return {
        "schemaVersion": TOPIC_ENRICHMENT_SCHEMA_VERSION,
        "specId": spec["spec_id"],
        "topicId": topic_id,
        "taskType": task_type,
        "publishReady": False,
        "title": title,
        "summary": "",
        "entityRefs": list(spec.get("entity_refs", [])),
        "tagRefs": list(spec.get("tag_refs", [])),
        "selectedCandidateIds": [],
        "sourceUrls": [],
    }


def load_travel_url_seed_ndjson(path: Path) -> dict[str, list[dict[str, Any]]]:
    """按 topicId 分组 seed 行：每行 topicId + sourceUrl + 可选 title/snippet。"""
    by_topic: dict[str, list[dict[str, Any]]] = {}
    if not path.exists():
        return by_topic
    for row in read_ndjson(path):
        if not isinstance(row, dict):
            continue
        tid = str(row.get("topicId") or row.get("topic_id") or "").strip()
        surl = str(row.get("sourceUrl") or row.get("url") or "").strip()
        if not tid or not surl:
            continue
        by_topic.setdefault(tid, []).append(row)
    return by_topic


def collect_urls_for_attraction(
    *,
    name: str,
    wiki_title: str,
    baike_item: str,
    aliases: list[str],
    core_tokens: list[str],
    max_sources: int,
    wiki_expand: str,
    wiki_link_budget: int,
    baike_link_budget: int,
    wikivoyage_limit: int,
    skip_baike_scrape: bool,
    travel_seed_rows: list[dict[str, Any]],
) -> list[str]:
    expand = _normalize_wiki_expand(wiki_expand)
    tokens = _derive_relevance_tokens(name, aliases, core_tokens)
    urls: list[str] = []
    seen: set[str] = set()

    def add(u: str) -> None:
        u = u.strip()
        if not u or u in seen:
            return
        seen.add(u)
        urls.append(u)

    add("https://baike.baidu.com/item/" + urllib.parse.quote(baike_item))
    if _wiki_title_resolves("zh.wikipedia.org", wiki_title):
        add("https://zh.wikipedia.org/wiki/" + urllib.parse.quote(wiki_title.replace(" ", "_")))

    for u in _wikivoyage_opensearch_urls(f"{name} 四川", limit=wikivoyage_limit):
        add(u)
        if len(urls) >= max_sources:
            return urls
    for u in _wikivoyage_opensearch_urls(name, limit=max(1, wikivoyage_limit // 2)):
        add(u)
        if len(urls) >= max_sources:
            return urls

    for row in travel_seed_rows:
        u = str(row.get("sourceUrl") or row.get("url") or "").strip()
        if u:
            add(u)

    if expand == "full":
        for u in _wiki_api_links_raw("zh.wikipedia.org", wiki_title, limit=wiki_link_budget):
            add(u)
            if len(urls) >= max_sources:
                return urls
    elif expand == "filtered":
        for u in _wiki_links_filtered(
            "zh.wikipedia.org",
            wiki_title,
            limit=wiki_link_budget,
            tokens=tokens,
        ):
            add(u)
            if len(urls) >= max_sources:
                return urls

    if not skip_baike_scrape and len(urls) < max_sources:
        for u in _baike_item_links_filtered(
            baike_item,
            limit=baike_link_budget,
            tokens=tokens,
        ):
            add(u)
            if len(urls) >= max_sources:
                break
    return urls[:max_sources]


def write_topic_pool(
    spec: dict[str, Any],
    topic_id: str,
    task_type: str,
    display_title: str,
    rows: list[dict[str, Any]],
    *,
    merge: bool,
) -> None:
    spec_id = spec["spec_id"]
    topic_dir = RUNTIME_ROOT / "runs" / spec_id / "topics" / topic_id
    (topic_dir / "pages").mkdir(parents=True, exist_ok=True)
    sp = topic_dir / "source_pool.ndjson"
    en = topic_dir / "enrichment.ndjson"
    if merge and sp.exists():
        existing = read_ndjson(sp)
        seen = {str(r.get("sourceUrl") or "").strip() for r in existing if isinstance(r, dict)}
        for row in rows:
            u = str(row.get("sourceUrl") or "").strip()
            if u and u not in seen:
                existing.append(row)
                seen.add(u)
        rows = existing
    write_ndjson(sp, rows)
    if not en.exists():
        write_ndjson(en, [default_enrichment_row(spec, topic_id, task_type, display_title)])


def bootstrap_from_attractions_yaml(
    spec: dict[str, Any],
    catalog: dict[str, Any],
    *,
    max_sources: int,
    wiki_expand: str,
    wiki_link_budget: int,
    baike_link_budget: int,
    wikivoyage_limit: int,
    sleep_s: float,
    skip_baike_scrape: bool,
    merge: bool,
    topic_filter: set[str] | None,
    travel_seed_by_topic: dict[str, list[dict[str, Any]]],
) -> None:
    ensure_runtime_layout()
    spec_query = str(spec.get("query", "")).strip()
    attractions = catalog.get("attractions") or []
    if not isinstance(attractions, list):
        raise SystemExit("catalog.attractions 必须是列表")

    for index, raw in enumerate(attractions):
        if not isinstance(raw, dict):
            continue
        topic_id = str(raw.get("topic_id") or "").strip()
        name = str(raw.get("name") or "").strip()
        wiki_title = str(raw.get("wiki_title") or name).strip()
        baike_item = str(raw.get("baike_item") or name).strip()
        aliases = raw.get("aliases") if isinstance(raw.get("aliases"), list) else []
        aliases_s = [str(a).strip() for a in aliases if str(a).strip()]
        core_tokens = raw.get("core_tokens") if isinstance(raw.get("core_tokens"), list) else []
        core_s = [str(a).strip() for a in core_tokens if str(a).strip()]
        if not topic_id or not name:
            continue
        if topic_filter is not None and topic_id not in topic_filter:
            continue

        seed_rows = list(travel_seed_by_topic.get(topic_id, []))
        url_list = collect_urls_for_attraction(
            name=name,
            wiki_title=wiki_title,
            baike_item=baike_item,
            aliases=aliases_s,
            core_tokens=core_s,
            max_sources=max_sources,
            wiki_expand=wiki_expand,
            wiki_link_budget=wiki_link_budget,
            baike_link_budget=baike_link_budget,
            wikivoyage_limit=wikivoyage_limit,
            skip_baike_scrape=skip_baike_scrape,
            travel_seed_rows=seed_rows,
        )
        tokens = _derive_relevance_tokens(name, aliases_s, core_s)
        seed_by_url = {
            str(r.get("sourceUrl") or r.get("url") or "").strip(): r for r in seed_rows if isinstance(r, dict)
        }
        rows: list[dict[str, Any]] = []
        for j, url in enumerate(url_list):
            eng = max(1, 120 - j * 2 + (index % 7) * 3)
            meta = seed_by_url.get(url.strip(), {})
            title_hint = str(meta.get("title", "")).strip()
            snip = str(meta.get("snippet", "")).strip()
            if not title_hint:
                title_hint = name if j < 2 else url
            if not snip:
                snip = f"景点「{name}」相关来源：{url}"
            rows.append(
                build_article_row(
                    topic_title=name,
                    spec_query=spec_query,
                    url=url,
                    page_title=title_hint,
                    snippet=snip,
                    engagement=eng,
                    relevance_tokens=tokens,
                )
            )
        write_topic_pool(spec, topic_id, "article", name, rows, merge=merge)
        print(f"[pool-bootstrap] topic={topic_id} candidates={len(rows)} merge={merge}", file=sys.stderr)
        time.sleep(sleep_s)

    image_topics = (spec.get("sample_topics") or {}).get("image") or []
    image_topic = str(image_topics[0]).strip() if image_topics else "cdcx_image_commons_sample_001"
    if topic_filter is None or image_topic in topic_filter:
        write_topic_pool(spec, image_topic, "image", "川西影像样例", [], merge=False)


def catalog_topic_ids_from_yaml(catalog: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for raw in catalog.get("attractions") or []:
        if isinstance(raw, dict):
            tid = str(raw.get("topic_id") or "").strip()
            if tid:
                out.append(tid)
    return out


def load_attractions_catalog(path: Path) -> dict[str, Any]:
    return read_yaml(path)
