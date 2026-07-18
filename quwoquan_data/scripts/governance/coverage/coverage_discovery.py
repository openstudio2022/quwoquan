"""Discover coverage candidates from public source adapters without mutating the master list."""
from __future__ import annotations

import json
import re
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any

from core.runtime_policy import active_runtime_policy
from content.source.research import network_io
from governance.coverage.master_list import admin_children, admin_geo_ref, city_is_district_level
from governance.coverage.coverage_runtime import coverage_workspace_root, now_iso

_WIKI_HOST = "zh.wikipedia.org"
_OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
_RUNTIME_POLICY = active_runtime_policy()
_OVERPASS_HTTP_TIMEOUT_SECONDS = _RUNTIME_POLICY.provider_timeouts.overpass_seconds
_WIKI_RETRY_LIMIT = _RUNTIME_POLICY.coverage_wiki_retry_limit
_WIKI_RETRY_BACKOFF_SECONDS = _RUNTIME_POLICY.coverage_wiki_retry_backoff_seconds
_WIKI_INTER_REQUEST_DELAY_SECONDS = _RUNTIME_POLICY.coverage_wiki_inter_request_delay_seconds
_OVERPASS_RETRY_LIMIT = _RUNTIME_POLICY.coverage_overpass_retry_limit
_OVERPASS_RETRY_BACKOFF_SECONDS = _RUNTIME_POLICY.coverage_overpass_retry_backoff_seconds
_OVERPASS_INTER_REQUEST_DELAY_SECONDS = _RUNTIME_POLICY.coverage_overpass_inter_request_delay_seconds
_OVERPASS_QUERY_TIMEOUT_SECONDS = _RUNTIME_POLICY.coverage_overpass_query_timeout_seconds
_COVERAGE_POLICY = _RUNTIME_POLICY.coverage_discovery
_RETRY_BACKOFF_MULTIPLIER = _COVERAGE_POLICY.retry_backoff_multiplier
_WIKI_CATEGORY_PAGE_LIMIT = _COVERAGE_POLICY.max_pages_per_cell
_WIKI_CATEGORY_DEPTH = _COVERAGE_POLICY.wiki_category_depth
_OVERPASS_RESULT_LIMIT = _COVERAGE_POLICY.overpass_result_limit

# 省 → wiki 种子分类（旅游景点树 + 政府名录镜像分类）。
# 2026-07-09 实测校准：原「{省}全国重点文物保护单位」「{省}古镇」在 zh.wikipedia
# 为空分类；省保单位真名是「Category:{省}文物保护单位」；古镇走全国口径
# 「中国历史文化名镇」（跨省条目由 merge 的区县归属解析过滤，解析失败进缺口清单）。
_WIKI_SEED_CATEGORIES: dict[str, tuple[str, ...]] = {
    "浙江省": (
        "Category:浙江旅游景点",
        "Category:浙江省文物保护单位",
        "Category:浙江省的博物馆",
        "Category:中国历史文化名镇",
    ),
    "四川省": (
        "Category:四川旅游景点",
        "Category:四川省文物保护单位",
        "Category:四川省的博物馆",
        "Category:中国历史文化名镇",
    ),
}

# 分类递归黑名单：命中即不深入（无关领域/人物/机构）。
_WIKI_CATEGORY_STOPWORDS = (
    "人物", "校友", "企业", "公司", "大学", "学院", "中学", "小学",
    "交通", "铁路", "车站", "机场", "地铁", "公路", "桥梁",
    "体育场", "体育馆", "演出", "电影", "电视", "行政区划", "乡镇", "街道",
    "水库", "水电站", "医院", "宾馆", "酒店",
)

# 条目名黑名单：非旅行地点实体。
_TITLE_STOPWORDS = (
    "大学", "学院", "中学", "小学", "公司", "集团", "车站", "站$", "机场",
    "水电站", "医院", "宾馆", "酒店", "列表", "水库",
)

# 名称 → 类型规则（顺序即优先级；(pattern, entityType, typeTagRef)）。
# 保守原则：规则只覆盖结论性后缀；不结论的进缺口清单交 Agent 语义复核。
_NAME_TYPE_RULES: tuple[tuple[str, str, str], ...] = (
    (r"(博物馆|纪念馆|陈列馆|美术馆|科技馆|展览馆)$", "地点/博物馆", "Entity/地点/博物馆"),
    (r"(寺|禅寺|禅院|庙|道观|教堂|清真寺|尼庵|庵)$", "地点/宗教场所", "Entity/地点/宗教场所"),
    (r"(古镇|古城|古街|老街)$", "地点/古镇", "Entity/地点/古镇/历史古镇"),
    (r"(古村|古村落|民族村)$", "地点/古镇", "Entity/地点/古镇/特色古村"),
    (r"(遗址|故居|旧址|古墓|墓|陵园|书院|文庙|会馆|祠|祠堂|牌坊|古塔|塔)$", "地点/遗址", "Entity/地点/遗址/历史建筑"),
    (r"温泉(度假村|度假区)?$", "地点/温泉", "Entity/地点/温泉"),
    (r"(乐园|游乐园|欢乐谷|海洋公园|野生动物园|动物园|水上世界)$", "地点/主题乐园", "Entity/地点/主题乐园/综合主题乐园"),
    (r"(湿地公园)$", "地点/景区", "Entity/地点/景区/湿地公园"),
    (r"(地质公园)$", "地点/景区", "Entity/地点/景区/地质公园"),
    (r"(国家森林公园|自然保护区)$", "地点/景区", "Entity/地点/景区/自然保护区"),
    (r"(公园|植物园)$", "地点/公园", "Entity/地点/公园"),
    (r"(山|峰|岭|崮|岩)$", "地点/自然景观", "Entity/地点/自然景观/山岳"),
    (r"(湖|潭|瀑布|泉|溪|江|河|海滩|沙滩)$", "地点/自然景观", "Entity/地点/自然景观/水体"),
    (r"(岛|列岛|群岛|半岛)$", "地点/自然景观", "Entity/地点/自然景观/海岸海岛"),
    (r"(峡谷|峡|溶洞|洞)$", "地点/自然景观", "Entity/地点/自然景观/山岳"),
    (r"(草原|草甸|森林)$", "地点/自然景观", "Entity/地点/自然景观/森林草原"),
    (r"(湿地)$", "地点/自然景观", "Entity/地点/自然景观/湿地荒漠"),
    (r"(广场|步行街|历史文化街区|文化街|风情街)$", "地点/打卡地", "Entity/地点/打卡地"),
)

# 分类证据 → 景区等级叶子（政府名录镜像：A 级/世界遗产分类是结论性等级证据）。
_CATEGORY_GRADE_RULES: tuple[tuple[str, str, str], ...] = (
    ("国家5A级旅游景区", "地点/景区", "Entity/地点/景区/5A景区"),
    ("国家4A级旅游景区", "地点/景区", "Entity/地点/景区/4A景区"),
    ("国家3A级旅游景区", "地点/景区", "Entity/地点/景区/3A景区"),
    ("世界遗产", "地点/景区", "Entity/地点/景区/世界遗产"),
    ("国家公园", "地点/景区", "Entity/地点/景区/国家公园"),
    ("全国重点文物保护单位", "地点/遗址", "Entity/地点/遗址/文化遗产"),
    # 省保单位名录镜像分类（「浙江省文物保护单位」「四川省文物保护单位」等）：
    # 政府名录结论性证据，映射历史建筑叶子（与主清单存量遗址项惯例一致）；
    # 必须排在「全国重点」之后作兜底（子串匹配顺序敏感）。
    ("文物保护单位", "地点/遗址", "Entity/地点/遗址/历史建筑"),
)

# OSM tag → 类型（结论性映射；attraction 走名称规则）。
_OSM_TAG_TYPE_RULES: tuple[tuple[str, str, str, str], ...] = (
    ("tourism", "museum", "地点/博物馆", "Entity/地点/博物馆"),
    ("tourism", "theme_park", "地点/主题乐园", "Entity/地点/主题乐园/综合主题乐园"),
    ("amenity", "place_of_worship", "地点/宗教场所", "Entity/地点/宗教场所"),
    ("historic", "monastery", "地点/宗教场所", "Entity/地点/宗教场所"),
    ("historic", "archaeological_site", "地点/遗址", "Entity/地点/遗址/考古遗址"),
    ("historic", "*", "地点/遗址", "Entity/地点/遗址/历史建筑"),
    ("leisure", "park", "地点/公园", "Entity/地点/公园"),
    ("natural", "peak", "地点/自然景观", "Entity/地点/自然景观/山岳"),
    ("natural", "water", "地点/自然景观", "Entity/地点/自然景观/水体"),
    ("natural", "beach", "地点/自然景观", "Entity/地点/自然景观/海岸海岛"),
)


def _research_network() -> Any:
    """返回覆盖扩展使用的公共来源网络边界（含 host 断路器）。"""
    return network_io


def _title_blocked(title: str) -> bool:
    return any(re.search(p, title) for p in _TITLE_STOPWORDS)


def _category_blocked(cat_title: str) -> bool:
    return any(word in cat_title for word in _WIKI_CATEGORY_STOPWORDS)


# ─── wiki_category adapter ─────────────────────────────────────────────
def _wiki_api_with_retry(
    bridge: Any,
    host: str,
    params: dict[str, str | int],
    *,
    retries: int = _WIKI_RETRY_LIMIT,
    backoff_seconds: float = _WIKI_RETRY_BACKOFF_SECONDS,
) -> dict[str, Any]:
    """wiki API 带限流退避：空响应（curl 失败/429 HTML 体）按指数退避重试。

    2026-07-09 实测：连续分类请求会触发 zh.wikipedia 限流返回非 JSON 体，
    `_curl_json` 静默返回 {} 导致整棵分类树静默空产。重试仍空才放弃（由
    调用方把该分类记入缺口，不得静默凑数）。
    """
    delay = backoff_seconds
    for attempt in range(max(1, retries)):
        data = bridge.wiki_api(host, params)
        if data:
            return data
        if attempt + 1 < retries:
            time.sleep(delay)
            delay *= _RETRY_BACKOFF_MULTIPLIER
    return {}


def _wiki_category_members(bridge: Any, category: str) -> tuple[list[str], list[str]]:
    """返回 (条目标题, 子分类标题)；带 cmcontinue 翻页。"""
    pages: list[str] = []
    subcats: list[str] = []
    cont: str | None = None
    for _ in range(_WIKI_CATEGORY_PAGE_LIMIT):
        params: dict[str, str | int] = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": category,
            "cmlimit": 500,
            "format": "json",
        }
        if cont:
            params["cmcontinue"] = cont
        data = _wiki_api_with_retry(bridge, _WIKI_HOST, params)
        members = ((data.get("query") or {}).get("categorymembers")) or []
        for m in members:
            # 注意：条目主命名空间 ns=0 是 falsy，禁止用 `or -1` 兜底（会把全部条目丢成 -1）。
            raw_ns = m.get("ns")
            ns = int(raw_ns) if raw_ns is not None else -1
            title = str(m.get("title") or "")
            if ns == 0 and title:
                pages.append(title)
            elif ns == 14 and title:
                subcats.append(title)
        cont = ((data.get("continue") or {}).get("cmcontinue")) or None
        if not cont:
            break
    return pages, subcats


def _wiki_page_details(bridge: Any, titles: list[str]) -> dict[str, dict[str, Any]]:
    """批量取条目 intro extract + categories（50/批）。"""
    details: dict[str, dict[str, Any]] = {}
    for i in range(0, len(titles), 50):
        chunk = titles[i : i + 50]
        data = _wiki_api_with_retry(
            bridge,
            _WIKI_HOST,
            {
                "action": "query",
                "prop": "extracts|categories|pageprops",
                "titles": "|".join(chunk),
                "exintro": 1,
                "explaintext": 1,
                "exlimit": "max",
                "cllimit": "max",
                "redirects": "1",
                "format": "json",
            },
        )
        for page in ((data.get("query") or {}).get("pages") or {}).values():
            if not isinstance(page, dict):
                continue
            title = str(page.get("title") or "")
            if not title or int(page.get("pageid") or -1) <= 0:
                continue
            details[title] = {
                "pageid": int(page.get("pageid") or 0),
                "qid": str((page.get("pageprops") or {}).get("wikibase_item") or ""),
                "extract": str(page.get("extract") or "")[:1200],
                "categories": [
                    str(c.get("title") or "") for c in (page.get("categories") or [])
                ],
            }
    return details


def discover_wiki_candidates(
    province: str,
    *,
    max_depth: int = _WIKI_CATEGORY_DEPTH,
    limit: int | None = None,
    sleep_seconds: float = _WIKI_INTER_REQUEST_DELAY_SECONDS,
    bridge: Any | None = None,
) -> list[dict[str, Any]]:
    """省级 wiki 分类树递归发现（含政府名录镜像分类）。"""
    bridge = bridge or _research_network()
    seeds = _WIKI_SEED_CATEGORIES.get(province)
    if not seeds:
        return []
    seen_cats: set[str] = set()
    seen_pages: set[str] = set()
    page_sources: dict[str, list[str]] = {}
    queue: list[tuple[str, int]] = [(seed, 0) for seed in seeds]
    while queue:
        category, depth = queue.pop(0)
        if category in seen_cats or depth > max_depth:
            continue
        seen_cats.add(category)
        pages, subcats = _wiki_category_members(bridge, category)
        time.sleep(max(0.0, sleep_seconds))
        for title in pages:
            if _title_blocked(title):
                continue
            page_sources.setdefault(title, []).append(category)
            seen_pages.add(title)
        for sub in subcats:
            if not _category_blocked(sub):
                queue.append((sub, depth + 1))
        if limit and len(seen_pages) >= limit:
            break
    titles = sorted(seen_pages)[:limit]
    details = _wiki_page_details(bridge, titles)
    out: list[dict[str, Any]] = []
    for title in titles:
        detail = details.get(title) or {}
        out.append(
            {
                "name": title,
                "province": province,
                "source": "wiki_category",
                "identityRefs": {
                    "qid": str(detail.get("qid") or ""),
                    "wikipediaPageId": int(detail.get("pageid") or 0),
                },
                "sourceCategories": sorted(set(page_sources.get(title) or [])),
                "categories": detail.get("categories") or [],
                "extract": detail.get("extract") or "",
            }
        )
    return out


# ─── osm_poi adapter ──────────────────────────────────────────────────
def _overpass_query(
    bridge: Any,
    query: str,
    *,
    retries: int = _OVERPASS_RETRY_LIMIT,
    backoff_seconds: float = _OVERPASS_RETRY_BACKOFF_SECONDS,
) -> tuple[list[dict[str, Any]], bool]:
    """Overpass 查询带限流退避；返回 (elements, ok)。

    公共 Overpass 端点对连续区县级查询会 429/504（实测 2026-07-09 两省批：
    浙江 90 区县仅少数成功、四川仅 1 区县成功，失败静默空产）。空响应视为
    疑似限流并退避重试；重试后仍失败返回 ok=False，由调用方记入缺口报告。
    """
    encoded = urllib.parse.urlencode({"data": query})
    delay = backoff_seconds
    for attempt in range(max(1, retries)):
        data = bridge.curl_json(
            f"{_OVERPASS_ENDPOINT}?{encoded}",
            timeout=_OVERPASS_HTTP_TIMEOUT_SECONDS,
        )
        elements = data.get("elements") if isinstance(data, dict) else None
        if isinstance(elements, list):
            return [e for e in elements if isinstance(e, dict)], True
        if attempt + 1 < retries:
            time.sleep(delay)
            delay *= _RETRY_BACKOFF_MULTIPLIER
    return [], False


def _osm_strong_signal(element: dict[str, Any]) -> bool:
    """发现层强信号；普通面、generic historic/park 不能因 OSM tag 自动准入。"""
    tags = element.get("tags") or {}
    if "wikipedia" in tags or "wikidata" in tags:
        return True
    return str(tags.get("tourism") or "") in {"museum", "theme_park"} or (
        str(tags.get("natural") or "") in {"peak", "water", "beach"}
        and bool(tags.get("tourism"))
    )


def discover_osm_candidates(
    province: str,
    *,
    cities: list[str] | None = None,
    limit: int | None = None,
    sleep_seconds: float = _OVERPASS_INTER_REQUEST_DELAY_SECONDS,
    bridge: Any | None = None,
    country: str = "中国",
    failed_districts: list[str] | None = None,
) -> list[dict[str, Any]]:
    """逐区县 Overpass POI 发现（区县归属精确）。

    公共端点限流应对：查询间隔缺省 3s + `_overpass_query` 内置退避重试；
    重试仍失败的区县追加进 `failed_districts`（调用方记入缺口报告），
    禁止静默空产假装该区县无 POI。
    """
    bridge = bridge or _research_network()
    out: list[dict[str, Any]] = []
    province_geo = admin_geo_ref(country, province)
    for city in admin_children(province_geo):
        if cities and city not in cities:
            continue
        districts = (
            [city]
            if city_is_district_level(country, province, city)
            else admin_children(f"{province_geo}/{city}")
        )
        for district in districts:
            query = (
                f'[out:json][timeout:{_OVERPASS_QUERY_TIMEOUT_SECONDS}];area["name"="{district}"]["admin_level"~"6|7"]->.a;'
                '(nwr["tourism"~"attraction|museum|theme_park"]["name"](area.a);'
                'nwr["historic"]["name"](area.a);'
                'nwr["leisure"="park"]["name"](area.a);'
                'nwr["natural"~"peak|water|beach"]["tourism"]["name"](area.a););'
                f"out tags {_OVERPASS_RESULT_LIMIT};"
            )
            elements, ok = _overpass_query(bridge, query)
            if not ok and failed_districts is not None:
                failed_districts.append(f"{city}/{district}")
            for element in elements:
                if not _osm_strong_signal(element):
                    continue
                tags = element.get("tags") or {}
                name = str(tags.get("name") or "").strip()
                if not name or len(name) < 2 or _title_blocked(name):
                    continue
                out.append(
                    {
                        "name": name,
                        "province": province,
                        "city": city,
                        "district": district,
                        "source": "osm_poi",
                        "identityRefs": {
                            "qid": str(tags.get("wikidata") or ""),
                            "osmType": str(element.get("type") or ""),
                            "osmId": str(element.get("id") or ""),
                        },
                        "coordinates": {
                            "lat": float(
                                element.get("lat")
                                or (element.get("center") or {}).get("lat")
                                or 0
                            ),
                            "lon": float(
                                element.get("lon")
                                or (element.get("center") or {}).get("lon")
                                or 0
                            ),
                        },
                        "osmTags": {
                            k: str(v)
                            for k, v in tags.items()
                            if k
                            in (
                                "tourism",
                                "historic",
                                "leisure",
                                "natural",
                                "amenity",
                                "shop",
                                "office",
                                "building",
                                "highway",
                                "public_transport",
                                "wikipedia",
                                "wikidata",
                            )
                        },
                        "osmType": str(element.get("type") or ""),
                    }
                )
            time.sleep(max(0.0, sleep_seconds))
            if limit and len(out) >= limit:
                return out[:limit]
    return out


# ─── discover 入口 ─────────────────────────────────────────────────────
def discover_candidates(
    provinces: list[str],
    *,
    sources: list[str],
    cities: list[str] | None = None,
    limit: int | None = None,
    sleep_seconds: float | None = None,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    """发现候选并落 NDJSON；OTA/官方文旅未收口时写 source_gaps（诚实缺口）。"""
    target_dir = out_dir or coverage_workspace_root()
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report: dict[str, Any] = {
        "schema": "quwoquan_data.coverage_discover_report",
        "generatedAt": now_iso(),
        "provinces": provinces,
        "sources": sources,
        "files": [],
        "counts": {},
        "sourceGaps": [],
    }
    for source in sources:
        if source not in ("wiki_category", "osm_poi"):
            report["sourceGaps"].append(
                {
                    "source": source,
                    "status": "not_collected",
                    "reason": "官方文旅/OTA 公共索引的城市 id 映射与反爬未收口（实测 ctrip 返回跨城缓存页），本轮诚实缺口，不产候选",
                }
            )
    for province in provinces:
        candidates: list[dict[str, Any]] = []
        if "wiki_category" in sources:
            candidates.extend(
                discover_wiki_candidates(
                    province,
                    limit=limit,
                    sleep_seconds=(
                        _WIKI_INTER_REQUEST_DELAY_SECONDS
                        if sleep_seconds is None
                        else sleep_seconds
                    ),
                )
            )
        if "osm_poi" in sources:
            osm_failed: list[str] = []
            candidates.extend(
                discover_osm_candidates(
                    province,
                    cities=cities,
                    limit=limit,
                    sleep_seconds=(
                        _OVERPASS_INTER_REQUEST_DELAY_SECONDS
                        if sleep_seconds is None
                        else max(_OVERPASS_INTER_REQUEST_DELAY_SECONDS, sleep_seconds)
                    ),
                    failed_districts=osm_failed,
                )
            )
            if osm_failed:
                report["sourceGaps"].append(
                    {
                        "source": "osm_poi",
                        "province": province,
                        "status": "partial",
                        "reason": "Overpass 公共端点限流/失败（重试后仍空），以下区县未采集",
                        "failedDistricts": osm_failed,
                    }
                )
        path = target_dir / f"candidates_{province}_{stamp}.ndjson"
        with path.open("w", encoding="utf-8") as fh:
            for item in candidates:
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")
        report["files"].append(str(path))
        report["counts"][province] = len(candidates)
    report_path = target_dir / f"discover_report_{stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["reportPath"] = str(report_path)
    return report


# ─── merge（去重 + 打标 + 写回） ────────────────────────────────────────
