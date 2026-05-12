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

from common import (
    RUNTIME_ROOT,
    TOPIC_ENRICHMENT_SCHEMA_VERSION,
    ensure_runtime_layout,
    read_ndjson,
    read_yaml,
    write_ndjson,
)
from native_fetch import NativeFetchError, fetch_html_page

DEFAULT_MAX_SOURCES = 22
BAIKE_ITEM_LINK_RE = re.compile(r'href="(/item/[^"?#]+)"', re.I)
MW_USER_AGENT = "quwoquan-data-crawl-topic-pool/1.0 (+https://github.com/quwoquan/quwoquan)"

WikiExpandMode = Literal["none", "filtered", "full"]

# 景观类后缀：滑窗前先剥离，否则「风景名胜区」会带来全国同质「XX风景区」假阳性。
_SCENE_TITLE_SUFFIXES: tuple[str, ...] = (
    "国家级风景名胜区",
    "风景名胜区",
    "风景旅游区",
    "旅游景区",
    "旅游区",
    "风景区",
    "国家公园",
    "旅游度假区",
    "文旅度假区",
)

# 二元组黑名单：不写入 relevanceTokens，亦用于 authenticity 的 medium 判定过滤。
GENERIC_SCENE_BIGRAM_BLOCKLIST_FOR_AUTH: frozenset[str] = frozenset(
    {
        "风景",
        "景区",
        "名胜",
        "胜区",
        "旅游",
        "游区",
        "遗产",
        "公园",
        "地质",
        "索道",
        "观景",
        "度假",
        "级景",
    }
)


def _strip_scene_suffixes(title: str) -> str:
    s = str(title or "").strip()
    if not s:
        return ""
    changed = True
    while changed:
        changed = False
        for suf in _SCENE_TITLE_SUFFIXES:
            if s.endswith(suf) and len(s) > len(suf):
                s = s[: -len(suf)].strip()
                changed = True
    return s or str(title or "").strip()


def _dedupe_preserve(seq: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in seq:
        t = str(item).strip()
        if len(t) < 2 or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def derive_strong_tokens(
    *,
    name: str,
    wiki_title: str,
    baike_item: str,
    aliases: list[str],
    core_tokens: list[str],
) -> list[str]:
    """外链标题门禁：须命中强 token（地名/别名/核心词/剥离后缀后的主名），杜绝仅凭「风景区」全国撞车。"""
    chunks: list[str] = []
    for raw in (_strip_scene_suffixes(name), name, _strip_scene_suffixes(wiki_title), wiki_title, _strip_scene_suffixes(baike_item), baike_item):
        raw = str(raw or "").strip()
        if raw:
            chunks.append(raw)
    chunks.extend(str(a).strip() for a in aliases if str(a).strip())
    chunks.extend(str(c).strip() for c in core_tokens if str(c).strip())
    strong = _dedupe_preserve(chunks)
    # 剔除过短且无区别的单字二元组已由长度>=2 保证；去掉与黑名单完全一致的二元短语
    strong = [
        s
        for s in strong
        if s not in GENERIC_SCENE_BIGRAM_BLOCKLIST_FOR_AUTH or len(s) > 2
    ]
    return strong[:24]


def expected_region_keywords_from_catalog_row(raw: dict[str, Any]) -> list[str]:
    """从 catalog NDJSON/YAML 行提取地域核验词（province/prefecture/expected_region_keywords 等）。"""
    acc: list[str] = []
    for key in ("province", "prefecture", "district", "adm1", "region"):
        v = raw.get(key)
        if isinstance(v, str) and v.strip():
            acc.append(v.strip())
    er = raw.get("expected_region_keywords")
    if isinstance(er, list):
        for x in er:
            s = str(x).strip()
            if s:
                acc.append(s)
    return _dedupe_preserve(acc)[:32]


def _derive_relevance_tokens(name: str, aliases: list[str], core_tokens: list[str]) -> list[str]:
    """相关性 token：剥离后缀后再拆二元组；屏蔽景观泛词二元组。"""
    stripped_name = _strip_scene_suffixes(name)
    tokens: list[str] = []
    for chunk in [stripped_name, name, *aliases, *core_tokens]:
        s = str(chunk).strip()
        if not s:
            continue
        if s not in tokens:
            tokens.append(s)
        if len(s) >= 2:
            for i in range(len(s) - 1):
                bi = s[i : i + 2]
                if not bi.strip() or bi.isspace() or bi in GENERIC_SCENE_BIGRAM_BLOCKLIST_FOR_AUTH:
                    continue
                if bi not in tokens:
                    tokens.append(bi)
    return _dedupe_preserve(tokens)[:48]


def _title_matches_strong(title: str, strong_tokens: list[str]) -> bool:
    tnorm = title.strip()
    if not tnorm:
        return False
    for tok in strong_tokens:
        if tok and tok in tnorm:
            return True
    return False


def _title_matches_tokens(title: str, tokens: list[str]) -> bool:
    tnorm = title.strip()
    if not tnorm:
        return False
    for tok in tokens:
        if tok and tok in tnorm:
            return True
    return False


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


def _wiki_links_filtered(
    site: str,
    wiki_title: str,
    *,
    limit: int,
    strong_tokens: list[str],
) -> list[str]:
    raw = _wiki_api_links_raw(site, wiki_title, limit=max(limit * 8, 80))
    out: list[str] = []
    for url in raw:
        title = urllib.parse.unquote(url.split("/wiki/", 1)[-1]).replace("_", " ") if "/wiki/" in url else ""
        if _title_matches_strong(title, strong_tokens):
            out.append(url)
        if len(out) >= limit:
            break
    return out


def _zh_mw_title_from_url(url: str) -> str:
    u = url.strip()
    for host in ("zh.wikipedia.org", "zh.wikivoyage.org", "en.wikipedia.org"):
        if host in u and "/wiki/" in u:
            tail = u.split("/wiki/", 1)[-1].split("#")[0].split("?")[0]
            return urllib.parse.unquote(tail).replace("_", " ")
    return ""


def _outbound_title_allowed_for_travel(
    title: str, *, strong_tokens: list[str], aliases: list[str], core_tokens: list[str]
) -> bool:
    """Wikivoyage 等：强匹配或别名/核心地域词命中标题即保留。"""
    if _title_matches_strong(title, strong_tokens):
        return True
    if _title_matches_tokens(title, aliases):
        return True
    if _title_matches_tokens(title, core_tokens):
        return True
    return False


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
    baike_path_title: str, *, limit: int, strong_tokens: list[str]
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
        if not _title_matches_strong(tail, strong_tokens):
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
    topic_strong_tokens: list[str] | None = None,
    expected_region_keywords: list[str] | None = None,
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
    if topic_strong_tokens:
        row["topicStrongTokens"] = topic_strong_tokens
    if expected_region_keywords:
        row["expectedRegionKeywords"] = expected_region_keywords
    return row


def build_image_source_row(
    *,
    topic_title: str,
    spec_query: str,
    url: str,
    page_title: str,
    snippet: str,
    engagement: int,
    relevance_tokens: list[str],
    topic_strong_tokens: list[str] | None = None,
    expected_region_keywords: list[str] | None = None,
) -> dict[str, Any]:
    """image lane source_pool 行：taskType 固定为 image，后续由 batch 侧做图像质量门禁。"""
    sid = _source_id_for_url(url)
    row: dict[str, Any] = {
        "candidateId": sid,
        "sourceId": sid,
        "taskType": "image",
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
            "contentCompleteness": 18,
            "actionability": 10,
            "sourceCredibility": 16,
            "freshness": 8,
            "richness": 14,
            "engagementSignal": 10,
            "cleanliness": 12,
        },
        "publishabilityBreakdown": {
            "readerValue": 12,
            "routeSpecificity": 10,
            "factDensity": 10,
            "practicality": 10,
            "narrativePotential": 12,
            "encyclopedicPenalty": 8,
        },
    }
    if relevance_tokens:
        row["relevanceTokens"] = relevance_tokens
    if topic_strong_tokens:
        row["topicStrongTokens"] = topic_strong_tokens
    if expected_region_keywords:
        row["expectedRegionKeywords"] = expected_region_keywords
    return row


def commons_file_gallery_urls(display_name: str, *, limit: int = 16) -> list[str]:
    """检索 Wikimedia Commons（File 命名空间），用于影像 lane 的权威种子页。"""
    q = f"{display_name} Sichuan"
    params = {
        "action": "query",
        "list": "search",
        "srsearch": q,
        "srnamespace": "6",
        "srlimit": str(min(max(1, limit), 20)),
        "format": "json",
    }
    api = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        api,
        headers={"User-Agent": "quwoquan-data-pool-bootstrap/1.0 (+https://github.com/quwoquan/quwoquan)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            payload = json.loads(resp.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return []
    items = (payload.get("query") or {}).get("search") or []
    out: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title.startswith("File:"):
            continue
        enc = urllib.parse.quote(title.replace(" ", "_"), safe="/():%")
        out.append("https://commons.wikimedia.org/wiki/" + enc)
        if len(out) >= limit:
            break
    if not out:
        search = "https://commons.wikimedia.org/w/index.php?" + urllib.parse.urlencode(
            {"search": display_name, "title": "Special:Search", "go": "Go"}
        )
        out.append(search)
    return out[:limit]


IMAGE_TOPIC_SUFFIX = "__img"


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
    strong_tokens = derive_strong_tokens(
        name=name,
        wiki_title=wiki_title,
        baike_item=baike_item,
        aliases=aliases,
        core_tokens=core_tokens,
    )
    urls: list[str] = []
    seen: set[str] = set()

    def add(u: str) -> None:
        u = u.strip()
        if not u or u in seen:
            return
        seen.add(u)
        urls.append(u)

    def maybe_add_wikivoyage(u: str) -> None:
        t = _zh_mw_title_from_url(u)
        if t and not _outbound_title_allowed_for_travel(
            t, strong_tokens=strong_tokens, aliases=aliases, core_tokens=core_tokens
        ):
            return
        add(u)

    add("https://baike.baidu.com/item/" + urllib.parse.quote(baike_item))
    if _wiki_title_resolves("zh.wikipedia.org", wiki_title):
        add("https://zh.wikipedia.org/wiki/" + urllib.parse.quote(wiki_title.replace(" ", "_")))

    for u in _wikivoyage_opensearch_urls(f"{name} 四川", limit=wikivoyage_limit):
        maybe_add_wikivoyage(u)
        if len(urls) >= max_sources:
            return urls
    for u in _wikivoyage_opensearch_urls(name, limit=max(1, wikivoyage_limit // 2)):
        maybe_add_wikivoyage(u)
        if len(urls) >= max_sources:
            return urls
    gv = max(1, min(8, wikivoyage_limit // 3))
    for u in _wikivoyage_opensearch_urls(f"{name} 旅游", limit=gv):
        maybe_add_wikivoyage(u)
        if len(urls) >= max_sources:
            return urls
    for u in _wikivoyage_opensearch_urls(f"{name} 攻略", limit=gv):
        maybe_add_wikivoyage(u)
        if len(urls) >= max_sources:
            return urls

    for row in travel_seed_rows:
        u = str(row.get("sourceUrl") or row.get("url") or "").strip()
        if u:
            add(u)

    if expand == "full":
        for u in _wiki_api_links_raw("zh.wikipedia.org", wiki_title, limit=wiki_link_budget):
            wt = urllib.parse.unquote(u.split("/wiki/", 1)[-1]).replace("_", " ") if "/wiki/" in u else ""
            if wt and not _title_matches_strong(wt, strong_tokens):
                continue
            add(u)
            if len(urls) >= max_sources:
                return urls
    elif expand == "filtered":
        for u in _wiki_links_filtered(
            "zh.wikipedia.org",
            wiki_title,
            limit=wiki_link_budget,
            strong_tokens=strong_tokens,
        ):
            add(u)
            if len(urls) >= max_sources:
                return urls

    if not skip_baike_scrape and len(urls) < max_sources:
        for u in _baike_item_links_filtered(
            baike_item,
            limit=baike_link_budget,
            strong_tokens=strong_tokens,
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
        geo_kw = expected_region_keywords_from_catalog_row(raw)
        strong_list = derive_strong_tokens(
            name=name,
            wiki_title=wiki_title,
            baike_item=baike_item,
            aliases=aliases_s,
            core_tokens=core_s,
        )
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
                    topic_strong_tokens=strong_list,
                    expected_region_keywords=geo_kw if geo_kw else None,
                )
            )
        write_topic_pool(spec, topic_id, "article", name, rows, merge=merge)
        print(f"[pool-bootstrap] topic={topic_id} candidates={len(rows)} merge={merge}", file=sys.stderr)

        img_tid = f"{topic_id}{IMAGE_TOPIC_SUFFIX}"
        write_img = topic_filter is None or topic_id in topic_filter or img_tid in topic_filter
        if write_img:
            cap = max(4, min(int(max_sources), 24))
            img_urls = commons_file_gallery_urls(name, limit=cap)
            img_rows: list[dict[str, Any]] = []
            for j, url in enumerate(img_urls):
                eng = max(1, 90 - j * 2 + (index % 5) * 2)
                img_rows.append(
                    build_image_source_row(
                        topic_title=name,
                        spec_query=spec_query,
                        url=url,
                        page_title=name if j == 0 else url,
                        snippet=f"影像候选：{name}（Commons/Wikimedia）",
                        engagement=eng,
                        relevance_tokens=tokens,
                        topic_strong_tokens=strong_list,
                        expected_region_keywords=geo_kw if geo_kw else None,
                    )
                )
            write_topic_pool(spec, img_tid, "image", name, img_rows, merge=merge)
            print(
                f"[pool-bootstrap] topic={img_tid} image_candidates={len(img_rows)} merge={merge}",
                file=sys.stderr,
            )

        time.sleep(sleep_s)
    out: list[str] = []
    for raw in catalog.get("attractions") or []:
        if isinstance(raw, dict):
            tid = str(raw.get("topic_id") or "").strip()
            if tid:
                out.append(tid)
    return out


def load_attractions_catalog(path: Path) -> dict[str, Any]:
    return read_yaml(path)
