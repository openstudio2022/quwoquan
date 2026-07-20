"""Discover coverage candidates from public source adapters without mutating the master list."""
from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from core.runtime_policy import active_runtime_policy
from content.source.research import network_io
from governance.coverage.coverage_corroboration import (
    candidate_corroboration_key as _candidate_corroboration_key,
    discover_baike_corroborations,
)
from governance.coverage.master_list import admin_children, admin_geo_ref, city_is_district_level
from governance.coverage.coverage_runtime import coverage_workspace_root, now_iso

_ShardProgress = Callable[
    [str, str, str, str, list[dict[str, Any]], str | None],
    None,
]

_WIKI_HOST = "zh.wikipedia.org"
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
_WIKIDATA_SPARQL_ENDPOINT = _COVERAGE_POLICY.wikidata_sparql_endpoint
_WIKIDATA_RESULT_LIMIT = _COVERAGE_POLICY.wikidata_result_limit
_OVERPASS_CONCURRENCY = _COVERAGE_POLICY.overpass_concurrency
_OVERPASS_RESULT_LIMIT = _COVERAGE_POLICY.overpass_result_limit
_OVERPASS_ENDPOINTS = _COVERAGE_POLICY.overpass_endpoints

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

# Wikidata 旅行对象根类 → 本仓实体标签。查询以 P31/P279* 取得根类证据，
# 不依赖名称猜测；同一对象命中多个根类时保留全部标签，由 merge 统一选主类型。
_WIKIDATA_ROOT_TYPE_REFS: dict[str, str] = {
    "Q570116": "Entity/地点/打卡地",  # tourist attraction
    "Q33506": "Entity/地点/博物馆",
    "Q22698": "Entity/地点/公园",
    "Q1107656": "Entity/地点/公园",  # garden
    "Q8502": "Entity/地点/自然景观/山岳",
    "Q15324": "Entity/地点/自然景观/水体",
    "Q23442": "Entity/地点/自然景观/海岸海岛",
    "Q35509": "Entity/地点/自然景观/山岳",  # cave
    "Q473972": "Entity/地点/景区/自然保护区",
    "Q24398318": "Entity/地点/宗教场所",
    "Q839954": "Entity/地点/遗址/考古遗址",
    "Q1081138": "Entity/地点/遗址/历史建筑",
    "Q4989906": "Entity/地点/遗址/文化遗产",  # monument
}

# OSM tag → 类型（结论性映射；attraction 走名称规则）。
_OSM_TAG_TYPE_RULES: tuple[tuple[str, str, str, str], ...] = (
    ("tourism", "attraction", "地点/打卡地", "Entity/地点/打卡地"),
    ("tourism", "museum", "地点/博物馆", "Entity/地点/博物馆"),
    ("tourism", "gallery", "地点/博物馆", "Entity/地点/博物馆"),
    ("tourism", "theme_park", "地点/主题乐园", "Entity/地点/主题乐园/综合主题乐园"),
    ("tourism", "zoo", "地点/主题乐园", "Entity/地点/主题乐园/综合主题乐园"),
    ("tourism", "aquarium", "地点/主题乐园", "Entity/地点/主题乐园/综合主题乐园"),
    ("tourism", "viewpoint", "地点/打卡地", "Entity/地点/打卡地"),
    ("amenity", "place_of_worship", "地点/宗教场所", "Entity/地点/宗教场所"),
    ("historic", "monastery", "地点/宗教场所", "Entity/地点/宗教场所"),
    ("historic", "archaeological_site", "地点/遗址", "Entity/地点/遗址/考古遗址"),
    ("historic", "*", "地点/遗址", "Entity/地点/遗址/历史建筑"),
    ("leisure", "park", "地点/公园", "Entity/地点/公园"),
    ("leisure", "garden", "地点/公园", "Entity/地点/公园"),
    ("leisure", "nature_reserve", "地点/景区", "Entity/地点/景区/自然保护区"),
    ("natural", "peak", "地点/自然景观", "Entity/地点/自然景观/山岳"),
    ("natural", "water", "地点/自然景观", "Entity/地点/自然景观/水体"),
    ("natural", "beach", "地点/自然景观", "Entity/地点/自然景观/海岸海岛"),
    ("natural", "cave_entrance", "地点/自然景观", "Entity/地点/自然景观/山岳"),
    ("natural", "bay", "地点/自然景观", "Entity/地点/自然景观/海岸海岛"),
    ("natural", "spring", "地点/自然景观", "Entity/地点/自然景观/水体"),
    ("natural", "wetland", "地点/自然景观", "Entity/地点/自然景观/湿地荒漠"),
    ("natural", "wood", "地点/自然景观", "Entity/地点/自然景观/森林草原"),
)

_OSM_QUERY_GROUPS: tuple[tuple[str, str], ...] = (
    (
        "tourism",
        'nwr["tourism"~"attraction|museum|theme_park|gallery|viewpoint|zoo|aquarium"]["name"](area.a);',
    ),
    ("historic", 'nwr["historic"]["name"](area.a);'),
    (
        "leisure",
        'nwr["leisure"~"park|garden|nature_reserve"]["name"](area.a);',
    ),
    (
        "natural",
        'nwr["natural"~"peak|water|beach|cave_entrance|bay|spring|wetland|wood"]["name"](area.a);',
    ),
    ("worship", 'nwr["amenity"="place_of_worship"]["name"](area.a);'),
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


def _wiki_category_members(
    bridge: Any,
    category: str,
) -> tuple[list[str], list[str], bool]:
    """返回 (条目标题, 子分类标题, 请求是否完整)；带 cmcontinue 翻页。"""
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
        if not data:
            return pages, subcats, False
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
    return pages, subcats, True


def _wiki_page_details(
    bridge: Any,
    titles: list[str],
    *,
    failed_batches: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
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
        if not data:
            if failed_batches is not None:
                failed_batches.append("|".join(chunk))
            continue
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
    failed_units: list[str] | None = None,
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
        pages, subcats, ok = _wiki_category_members(bridge, category)
        if not ok:
            if failed_units is not None:
                failed_units.append(category)
            continue
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
    details = _wiki_page_details(
        bridge,
        titles,
        failed_batches=failed_units,
    )
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


# ─── wikidata_geo adapter ─────────────────────────────────────────────
def _sparql_literal(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _wikidata_district_query(
    *,
    province: str,
    district: str,
    limit: int,
    offset: int,
) -> str:
    roots = " ".join(f"wd:{qid}" for qid in _WIKIDATA_ROOT_TYPE_REFS)
    return f"""
PREFIX bd: <http://www.bigdata.com/rdf#>
PREFIX geo: <http://www.opengis.net/ont/geosparql#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX schema: <http://schema.org/>
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
SELECT DISTINCT ?item ?itemLabel ?itemDescription ?coord ?travelRoot WHERE {{
  ?province rdfs:label "{_sparql_literal(province)}"@zh.
  ?district rdfs:label "{_sparql_literal(district)}"@zh;
            wdt:P131* ?province.
  ?item wdt:P131* ?district;
        wdt:P625 ?coord;
        wdt:P31 ?kind;
        rdfs:label ?itemLabel.
  FILTER(LANG(?itemLabel) = "zh")
  VALUES ?travelRoot {{ {roots} }}
  ?kind wdt:P279* ?travelRoot.
  OPTIONAL {{
    ?item schema:description ?itemDescription.
    FILTER(LANG(?itemDescription) = "zh")
  }}
}}
ORDER BY ?item ?travelRoot
LIMIT {max(1, int(limit))}
OFFSET {max(0, int(offset))}
""".strip()


def _wikidata_bindings(
    bridge: Any,
    query: str,
    *,
    retries: int = _WIKI_RETRY_LIMIT,
    backoff_seconds: float = _WIKI_RETRY_BACKOFF_SECONDS,
) -> tuple[list[dict[str, Any]], bool]:
    """执行一次逻辑 SPARQL 请求；网络重试由本 adapter 显式控制。"""
    delay = backoff_seconds
    for attempt in range(max(1, retries)):
        payload = bridge.post_form_json(
            _WIKIDATA_SPARQL_ENDPOINT,
            fields={"query": query, "format": "json"},
            timeout=_COVERAGE_POLICY.request_timeout_seconds,
        )
        results = payload.get("results") if isinstance(payload, dict) else None
        bindings = results.get("bindings") if isinstance(results, dict) else None
        if isinstance(bindings, list):
            return [row for row in bindings if isinstance(row, dict)], True
        if attempt + 1 < retries:
            time.sleep(delay)
            delay *= _RETRY_BACKOFF_MULTIPLIER
    return [], False


def _binding_value(binding: dict[str, Any], key: str) -> str:
    value = binding.get(key)
    return str(value.get("value") or "").strip() if isinstance(value, dict) else ""


def _wikidata_candidates_from_bindings(
    bindings: list[dict[str, Any]],
    *,
    province: str,
    city: str,
    district: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for binding in bindings:
        item_url = _binding_value(binding, "item")
        qid = item_url.rsplit("/", 1)[-1]
        name = _binding_value(binding, "itemLabel")
        root_qid = _binding_value(binding, "travelRoot").rsplit("/", 1)[-1]
        type_ref = _WIKIDATA_ROOT_TYPE_REFS.get(root_qid)
        coord_match = re.fullmatch(
            r"Point\(([-+]?\d+(?:\.\d+)?) ([-+]?\d+(?:\.\d+)?)\)",
            _binding_value(binding, "coord"),
        )
        if (
            not re.fullmatch(r"Q[1-9]\d*", qid)
            or not name
            or len(name) < 2
            or _title_blocked(name)
            or type_ref is None
            or coord_match is None
        ):
            continue
        slot = grouped.setdefault(
            qid,
            {
                "name": name,
                "province": province,
                "city": city,
                "district": district,
                "source": "wikidata_geo",
                "identityRefs": {"qid": qid},
                "coordinates": {
                    "lat": float(coord_match.group(2)),
                    "lon": float(coord_match.group(1)),
                },
                "typeTagRefs": [],
                "extract": _binding_value(binding, "itemDescription"),
            },
        )
        if type_ref not in slot["typeTagRefs"]:
            slot["typeTagRefs"].append(type_ref)
    for candidate in grouped.values():
        candidate["typeTagRefs"].sort()
    return list(grouped.values())


def discover_wikidata_candidates(
    province: str,
    *,
    cities: list[str] | None = None,
    limit: int | None = None,
    sleep_seconds: float = _WIKI_INTER_REQUEST_DELAY_SECONDS,
    bridge: Any | None = None,
    country: str = "中国",
    failed_districts: list[str] | None = None,
) -> list[dict[str, Any]]:
    """按行政区分页发现具稳定 QID、坐标和旅行根类证据的对象。"""
    bridge = bridge or _research_network()
    out: list[dict[str, Any]] = []
    seen_qids: set[str] = set()
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
            exhausted = False
            for page in range(_WIKI_CATEGORY_PAGE_LIMIT):
                bindings, ok = _wikidata_bindings(
                    bridge,
                    _wikidata_district_query(
                        province=province,
                        district=district,
                        limit=_WIKIDATA_RESULT_LIMIT,
                        offset=page * _WIKIDATA_RESULT_LIMIT,
                    ),
                )
                if not ok:
                    if failed_districts is not None:
                        failed_districts.append(f"{city}/{district}")
                    break
                candidates = _wikidata_candidates_from_bindings(
                    bindings,
                    province=province,
                    city=city,
                    district=district,
                )
                for candidate in candidates:
                    qid = str((candidate.get("identityRefs") or {}).get("qid") or "")
                    if not qid or qid in seen_qids:
                        continue
                    seen_qids.add(qid)
                    out.append(candidate)
                    if limit and len(out) >= limit:
                        return out[:limit]
                if len(bindings) < _WIKIDATA_RESULT_LIMIT:
                    exhausted = True
                    break
                time.sleep(max(0.0, sleep_seconds))
            if not exhausted and ok and failed_districts is not None:
                failed_districts.append(
                    f"{city}/{district}:page_limit_{_WIKI_CATEGORY_PAGE_LIMIT}_reached"
                )
            time.sleep(max(0.0, sleep_seconds))
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
    delay = backoff_seconds
    for attempt in range(max(1, retries)):
        endpoint = _OVERPASS_ENDPOINTS[attempt % len(_OVERPASS_ENDPOINTS)]
        data = bridge.post_form_json(
            endpoint,
            fields={"data": query},
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
    """发现层旅行相关信号；是否进入主清单仍需非 OSM 来源交叉确认。"""
    tags = element.get("tags") or {}
    if "wikipedia" in tags or "wikidata" in tags:
        return True
    return (
        str(tags.get("tourism") or "")
        in {
            "attraction",
            "museum",
            "theme_park",
            "gallery",
            "viewpoint",
            "zoo",
            "aquarium",
        }
        or bool(str(tags.get("historic") or "").strip())
        or str(tags.get("leisure") or "") in {"park", "garden", "nature_reserve"}
        or str(tags.get("natural") or "")
        in {
            "peak",
            "water",
            "beach",
            "cave_entrance",
            "bay",
            "spring",
            "wetland",
            "wood",
        }
        or str(tags.get("amenity") or "") == "place_of_worship"
    )


def _osm_type_tag_refs(tags: dict[str, Any], name: str) -> list[str]:
    refs: list[str] = []
    for key, expected, _entity_type, type_ref in _OSM_TAG_TYPE_RULES:
        actual = str(tags.get(key) or "")
        if actual and (expected == "*" or actual == expected):
            refs.append(type_ref)
    if not refs:
        for pattern, _entity_type, type_ref in _NAME_TYPE_RULES:
            if re.search(pattern, name):
                refs.append(type_ref)
                break
    return sorted(set(refs))


def _overpass_literal(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _osm_group_queries(
    *, province: str, city: str, district: str
) -> list[tuple[str, str]]:
    """生成省→市州→区县唯一定位的轻量查询，避免同名区县串省。"""
    province_name = _overpass_literal(province)
    city_name = _overpass_literal(city)
    district_name = _overpass_literal(district)
    prelude = (
        f'[out:json][timeout:{_OVERPASS_QUERY_TIMEOUT_SECONDS}];'
        f'area["name"="{province_name}"]["boundary"="administrative"]->.p;'
        f'area(area.p)["name"="{city_name}"]["boundary"="administrative"]->.c;'
    )
    if city == district:
        prelude += ".c->.a;"
    else:
        prelude += (
            f'area(area.c)["name"="{district_name}"]'
            '["boundary"="administrative"]->.a;'
        )
    return [
        (
            group,
            f"{prelude}{selector}out tags center {_OVERPASS_RESULT_LIMIT};",
        )
        for group, selector in _OSM_QUERY_GROUPS
    ]


def discover_osm_candidates(
    province: str,
    *,
    cities: list[str] | None = None,
    limit: int | None = None,
    sleep_seconds: float = _OVERPASS_INTER_REQUEST_DELAY_SECONDS,
    bridge: Any | None = None,
    country: str = "中国",
    failed_districts: list[str] | None = None,
    skip_shards: set[tuple[str, str, str, str]] | None = None,
    shard_progress: _ShardProgress | None = None,
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
            shard_key = (province, city, district, "osm_poi")
            if skip_shards is not None and shard_key in skip_shards:
                continue
            district_start = len(out)
            elements_by_identity: dict[tuple[str, str], dict[str, Any]] = {}
            failed_groups: list[str] = []
            truncated_groups: list[str] = []
            elements_by_group: dict[str, list[dict[str, Any]]] = {}
            group_queries = _osm_group_queries(
                province=province,
                city=city,
                district=district,
            )
            workers = max(1, min(_OVERPASS_CONCURRENCY, len(group_queries)))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(_overpass_query, bridge, query): group
                    for group, query in group_queries
                }
                for future in as_completed(futures):
                    group = futures[future]
                    group_elements, ok = future.result()
                    if not ok:
                        failed_groups.append(group)
                    elif len(group_elements) >= _OVERPASS_RESULT_LIMIT:
                        truncated_groups.append(group)
                    elements_by_group[group] = group_elements
            for group, _query in group_queries:
                for element in sorted(
                    elements_by_group.get(group, []),
                    key=lambda item: (
                        str(item.get("type") or ""),
                        str(item.get("id") or ""),
                    ),
                ):
                    identity = (
                        str(element.get("type") or ""),
                        str(element.get("id") or ""),
                    )
                    if all(identity):
                        elements_by_identity.setdefault(identity, element)
            time.sleep(max(0.0, sleep_seconds))
            failure_reason: str | None = None
            if failed_groups or truncated_groups:
                details = [
                    *(f"failed_{group}" for group in sorted(failed_groups)),
                    *(
                        f"truncated_{group}_{_OVERPASS_RESULT_LIMIT}"
                        for group in sorted(truncated_groups)
                    ),
                ]
                failure_reason = ",".join(details)
                if failed_districts is not None:
                    failed_districts.append(
                        f"{city}/{district}:{failure_reason}"
                    )
            elements = list(elements_by_identity.values())
            for element in elements:
                if not _osm_strong_signal(element):
                    continue
                tags = element.get("tags") or {}
                name = str(tags.get("name") or "").strip()
                if not name or len(name) < 2 or _title_blocked(name):
                    continue
                type_tag_refs = _osm_type_tag_refs(tags, name)
                if not type_tag_refs:
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
                        "typeTagRefs": type_tag_refs,
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
            if shard_progress is not None:
                shard_progress(
                    "osm_poi",
                    province,
                    city,
                    district,
                    out[district_start:],
                    failure_reason,
                )
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
    seed_candidates: list[dict[str, Any]] | None = None,
    skip_shards: set[tuple[str, str, str, str]] | None = None,
    shard_progress: _ShardProgress | None = None,
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
        "uniqueCounts": {},
        "sourceGaps": [],
    }
    for source in sources:
        if source not in (
            "wiki_category",
            "wikidata_geo",
            "osm_poi",
            "baidu_baike_search",
            "toutiao_baike_search",
        ):
            report["sourceGaps"].append(
                {
                    "source": source,
                    "status": "not_collected",
                    "reason": "官方文旅/OTA 公共索引的城市 id 映射与反爬未收口（实测 ctrip 返回跨城缓存页），本轮诚实缺口，不产候选",
                }
            )
    for province in provinces:
        candidates: list[dict[str, Any]] = [
            dict(candidate)
            for candidate in (seed_candidates or [])
            if str(candidate.get("province") or "") == province
        ]
        if "wiki_category" in sources:
            wiki_failed: list[str] = []
            candidates.extend(
                discover_wiki_candidates(
                    province,
                    limit=limit,
                    sleep_seconds=(
                        _WIKI_INTER_REQUEST_DELAY_SECONDS
                        if sleep_seconds is None
                        else sleep_seconds
                    ),
                    failed_units=wiki_failed,
                )
            )
            if wiki_failed:
                report["sourceGaps"].append(
                    {
                        "source": "wiki_category",
                        "province": province,
                        "status": "partial",
                        "reason": "MediaWiki 分类或详情请求在重试后仍失败",
                        "failedUnits": wiki_failed,
                    }
                )
        if "wikidata_geo" in sources:
            wikidata_failed: list[str] = []
            candidates.extend(
                discover_wikidata_candidates(
                    province,
                    cities=cities,
                    limit=limit,
                    sleep_seconds=(
                        _WIKI_INTER_REQUEST_DELAY_SECONDS
                        if sleep_seconds is None
                        else sleep_seconds
                    ),
                    failed_districts=wikidata_failed,
                )
            )
            if wikidata_failed:
                report["sourceGaps"].append(
                    {
                        "source": "wikidata_geo",
                        "province": province,
                        "status": "partial",
                        "reason": "Wikidata SPARQL 失败或分页护栏触顶，以下区县未完整采集",
                        "failedDistricts": wikidata_failed,
                    }
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
                    skip_shards=skip_shards,
                    shard_progress=shard_progress,
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
        for baike_source in ("baidu_baike_search", "toutiao_baike_search"):
            if baike_source in sources:
                candidates.extend(
                    discover_baike_corroborations(
                        candidates,
                        source=baike_source,
                        limit=limit,
                    )
                )
                report["sourceGaps"].append(
                    {
                        "source": baike_source,
                        "province": province,
                        "status": "typed_blocked",
                        "reason": (
                            "当前 adapter 只对既有稳定候选做精确词条核验，"
                            "不具备可证明耗尽的公开搜索索引；核验结果已保留，"
                            "不得冒充该来源 discovery cell 饱和"
                        ),
                    }
                )
        path = target_dir / f"candidates_{province}_{stamp}.ndjson"
        with path.open("w", encoding="utf-8") as fh:
            for item in candidates:
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")
        report["files"].append(str(path))
        report["counts"][province] = len(candidates)
        report["uniqueCounts"][province] = len(
            {_candidate_corroboration_key(item) for item in candidates}
        )
    report_path = target_dir / f"discover_report_{stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["reportPath"] = str(report_path)
    return report


# ─── merge（去重 + 打标 + 写回） ────────────────────────────────────────
