"""主清单扩容管线（WP7 Phase 2）：发现候选 → 去重 → 类型/地理打标 → 写回市州 YAML。

CLI-first 三段式：
- [CLI prepare]  `qwq-data vertical coverage-discover`：从公开来源发现候选，落
  NDJSON（QWQ_OUTPUT_ROOT/data/local/runtime/coverage_expand/），只发现不写回。
- [Agent semantic] 类型/区县不结论的候选进缺口清单，由 Agent 会话语义复核后
  以补充 NDJSON 重新走 merge（本模块不做拍脑袋补全）。
- [CLI validate + gate] `qwq-data vertical coverage-merge`：去重（对主清单
  canonicalName/aliases 全局唯一）→ 规则打标（保守：无证据不结论）→ 写回
  （--apply）→ `qwq-data verify coverage-master-list` 门禁收口。

来源 adapter（五路口径）：
- wiki_category  zh.wikipedia 分类树递归（旅游景点/文保单位/博物馆等），同时承载
  「政府名录」镜像证据（全国重点文物保护单位、A 级景区等分类源于官方名录）。
- osm_poi        OSM Overpass 逐区县 POI（tourism/historic/leisure/natural），
  区县归属精确；只收强信号 POI（wikipedia/wikidata tag、面状对象或结论性类型）。
- ota / official 官方文旅与 OTA 公共索引：城市 id 映射与反爬未收口，本轮输出
  缺口报告（source_gaps），不产候选（诚实缺口，不凑数）。

主清单唯一真相源仍是市州 YAML 目录树；本模块写回走 dump_master_list_file
（保留文件头注释），全局唯一性与 schema 由 verify coverage-master-list 门禁承担。
"""
from __future__ import annotations

import json
import os
import re
import time
import unicodedata
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from _common.coverage_master_list import (
    COVERAGE_MASTER_ROOT,
    admin_children,
    admin_geo_ref,
    city_is_district_level,
    dump_master_list_file,
    iter_master_leaves,
    load_master_list_file,
    master_list_files,
)
from _common import paths as _paths

EXPAND_RUNTIME_DIR = _paths.OUTPUT_ROOT / "data" / "local" / "runtime" / "coverage_expand"


def _expand_runtime_dir() -> Path:
    if os.environ.get("QWQ_OUTPUT_ROOT"):
        output_root = Path(os.environ["QWQ_OUTPUT_ROOT"])
        return output_root / "data" / "local" / "runtime" / "coverage_expand"
    if os.environ.get("QWQ_DATA_ROOT"):
        output_root = Path(os.environ["QWQ_DATA_ROOT"])
        return output_root / "data" / "local" / "runtime" / "coverage_expand"
    return EXPAND_RUNTIME_DIR

_WIKI_HOST = "zh.wikipedia.org"
_OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"

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


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _research_bridge() -> Any:
    """复用 download.research_plan 的 curl/wiki API 层（含 host 断路器）。"""
    import download.research_plan as research_plan  # noqa: PLC0415

    return research_plan


def normalize_name(value: str) -> str:
    """去重归一化：NFKC + 去空白 + 去常见景区后缀变体。"""
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    text = re.sub(r"\s+", "", text)
    for suffix in ("旅游景区", "风景名胜区", "风景区", "旅游区", "景区"):
        if text.endswith(suffix) and len(text) > len(suffix) + 1:
            text = text[: -len(suffix)]
            break
    return text


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
    retries: int = 3,
    backoff_seconds: float = 5.0,
) -> dict[str, Any]:
    """wiki API 带限流退避：空响应（curl 失败/429 HTML 体）按指数退避重试。

    2026-07-09 实测：连续分类请求会触发 zh.wikipedia 限流返回非 JSON 体，
    `_curl_json` 静默返回 {} 导致整棵分类树静默空产。重试仍空才放弃（由
    调用方把该分类记入缺口，不得静默凑数）。
    """
    delay = backoff_seconds
    for attempt in range(max(1, retries)):
        data = bridge._wiki_api(host, params)
        if data:
            return data
        if attempt + 1 < retries:
            time.sleep(delay)
            delay *= 2
    return {}


def _wiki_category_members(bridge: Any, category: str) -> tuple[list[str], list[str]]:
    """返回 (条目标题, 子分类标题)；带 cmcontinue 翻页。"""
    pages: list[str] = []
    subcats: list[str] = []
    cont: str | None = None
    for _ in range(20):  # 翻页护栏
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
                "prop": "extracts|categories",
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
                "extract": str(page.get("extract") or "")[:1200],
                "categories": [
                    str(c.get("title") or "") for c in (page.get("categories") or [])
                ],
            }
    return details


def discover_wiki_candidates(
    province: str,
    *,
    max_depth: int = 4,
    limit: int = 0,
    sleep_seconds: float = 0.3,
    bridge: Any | None = None,
) -> list[dict[str, Any]]:
    """省级 wiki 分类树递归发现（含政府名录镜像分类）。"""
    bridge = bridge or _research_bridge()
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
    titles = sorted(seen_pages)[: limit or None]
    details = _wiki_page_details(bridge, titles)
    out: list[dict[str, Any]] = []
    for title in titles:
        detail = details.get(title) or {}
        out.append(
            {
                "name": title,
                "province": province,
                "source": "wiki_category",
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
    retries: int = 3,
    backoff_seconds: float = 8.0,
) -> tuple[list[dict[str, Any]], bool]:
    """Overpass 查询带限流退避；返回 (elements, ok)。

    公共 Overpass 端点对连续区县级查询会 429/504（实测 2026-07-09 两省批：
    浙江 90 区县仅少数成功、四川仅 1 区县成功，失败静默空产）。空响应视为
    疑似限流并退避重试；重试后仍失败返回 ok=False，由调用方记入缺口报告。
    """
    encoded = urllib.parse.urlencode({"data": query})
    delay = backoff_seconds
    for attempt in range(max(1, retries)):
        data = bridge._curl_json(f"{_OVERPASS_ENDPOINT}?{encoded}", timeout=90)
        elements = data.get("elements") if isinstance(data, dict) else None
        if isinstance(elements, list):
            return [e for e in elements if isinstance(e, dict)], True
        if attempt + 1 < retries:
            time.sleep(delay)
            delay *= 2
    return [], False


def _osm_strong_signal(element: dict[str, Any]) -> bool:
    """强信号过滤：wiki tag / 面状对象 / 结论性类型 tag，否则丢弃（防 POI 噪声）。"""
    tags = element.get("tags") or {}
    if "wikipedia" in tags or "wikidata" in tags:
        return True
    if element.get("type") in ("way", "relation"):
        return True
    for key, value, _etype, _ref in _OSM_TAG_TYPE_RULES:
        actual = str(tags.get(key) or "")
        if actual and (value == "*" or actual == value):
            return True
    return False


def discover_osm_candidates(
    province: str,
    *,
    cities: list[str] | None = None,
    limit: int = 0,
    sleep_seconds: float = 3.0,
    bridge: Any | None = None,
    country: str = "中国",
    failed_districts: list[str] | None = None,
) -> list[dict[str, Any]]:
    """逐区县 Overpass POI 发现（区县归属精确）。

    公共端点限流应对：查询间隔缺省 3s + `_overpass_query` 内置退避重试；
    重试仍失败的区县追加进 `failed_districts`（调用方记入缺口报告），
    禁止静默空产假装该区县无 POI。
    """
    bridge = bridge or _research_bridge()
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
                f'[out:json][timeout:45];area["name"="{district}"]["admin_level"~"6|7"]->.a;'
                '(nwr["tourism"~"attraction|museum|theme_park"]["name"](area.a);'
                'nwr["historic"]["name"](area.a);'
                'nwr["leisure"="park"]["name"](area.a);'
                'nwr["natural"~"peak|water|beach"]["tourism"]["name"](area.a););'
                "out tags 200;"
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
                        "osmTags": {
                            k: str(v)
                            for k, v in tags.items()
                            if k in ("tourism", "historic", "leisure", "natural", "wikipedia", "wikidata")
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
    limit: int = 0,
    sleep_seconds: float = 0.5,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    """发现候选并落 NDJSON；OTA/官方文旅未收口时写 source_gaps（诚实缺口）。"""
    target_dir = out_dir or _expand_runtime_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report: dict[str, Any] = {
        "schemaVersion": "quwoquan_data.coverage_discover_report/1",
        "generatedAt": _now_iso(),
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
                    province, limit=limit, sleep_seconds=sleep_seconds
                )
            )
        if "osm_poi" in sources:
            osm_failed: list[str] = []
            candidates.extend(
                discover_osm_candidates(
                    province,
                    cities=cities,
                    limit=limit,
                    sleep_seconds=max(3.0, sleep_seconds),
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
def _existing_name_index(country: str = "中国") -> dict[str, str]:
    """全国主清单 canonicalName/name/aliases 归一化索引 → 归属文件。"""
    index: dict[str, str] = {}
    for path in master_list_files():
        data = load_master_list_file(path)
        rel = path.as_posix()
        for _district, leaf in iter_master_leaves(data):
            for value in (
                leaf.get("canonicalName"),
                leaf.get("name"),
                *(leaf.get("aliases") or []),
            ):
                key = normalize_name(str(value or ""))
                if key:
                    index.setdefault(key, rel)
    return index


def _classify_by_category(categories: list[str]) -> tuple[str, str] | None:
    for marker, etype, ref in _CATEGORY_GRADE_RULES:
        if any(marker in cat for cat in categories):
            return etype, ref
    return None


def _classify_by_name(name: str) -> tuple[str, str] | None:
    for pattern, etype, ref in _NAME_TYPE_RULES:
        if re.search(pattern, name):
            return etype, ref
    return None


def _classify_by_osm(tags: dict[str, str]) -> tuple[str, str] | None:
    for key, value, etype, ref in _OSM_TAG_TYPE_RULES:
        actual = str(tags.get(key) or "")
        if actual and (value == "*" or actual == value):
            return etype, ref
    return None


def _resolve_district_from_text(
    text: str,
    *,
    province: str,
    country: str = "中国",
) -> tuple[str, str] | None:
    """从 wiki extract/categories 文本解析 (city, district)。

    先锁市州（文本含市州名），再在该市州区县中匹配；跨市州同名区县
    （如四川两个市中区）靠市州先锁避免误归。仅当唯一命中才结论。
    """
    province_geo = admin_geo_ref(country, province)
    matched: list[tuple[str, str]] = []
    for city in admin_children(province_geo):
        if city_is_district_level(country, province, city):
            if city in text:
                matched.append((city, city))
            continue
        for district in admin_children(f"{province_geo}/{city}"):
            if district in text:
                # 区县名命中先记录；同市州多区县或跨市州多命中时由下方裁决
                matched.append((city, district))
    unique = sorted(set(matched))
    if len(unique) == 1:
        return unique[0]
    # 多命中：若唯一一个市州命中了区县且文本明确含该市州名，取之
    cities_hit = {c for c, _ in unique}
    if len(cities_hit) > 1:
        text_cities = [c for c in cities_hit if c in text]
        if len(text_cities) == 1:
            city_districts = sorted({d for c, d in unique if c == text_cities[0]})
            if len(city_districts) == 1:
                return text_cities[0], city_districts[0]
    return None


def merge_candidates(
    provinces: list[str],
    *,
    candidate_files: list[Path],
    apply: bool = False,
    country: str = "中国",
) -> dict[str, Any]:
    """去重 + 打标 + （--apply）写回；不结论候选进缺口清单。"""
    existing = _existing_name_index(country)
    wanted = set(provinces)
    merged: dict[str, dict[str, Any]] = {}
    for path in candidate_files:
        with Path(path).open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                item = json.loads(line)
                if str(item.get("province") or "") not in wanted:
                    continue
                key = normalize_name(str(item.get("name") or ""))
                if not key:
                    continue
                slot = merged.setdefault(key, {"name": item["name"], "items": []})
                slot["items"].append(item)

    appended: list[dict[str, Any]] = []
    duplicates = 0
    gaps: list[dict[str, Any]] = []
    patches: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = {}

    for key, slot in sorted(merged.items()):
        if key in existing:
            duplicates += 1
            continue
        items = slot["items"]
        name = str(slot["name"])
        province = str(items[0].get("province"))
        # 类型打标：分类等级证据 > OSM tag > 名称规则；全不结论 → 缺口。
        classified: tuple[str, str] | None = None
        for item in items:
            if item.get("source") == "wiki_category":
                classified = _classify_by_category(
                    [*(item.get("categories") or []), *(item.get("sourceCategories") or [])]
                )
                if classified:
                    break
        if not classified:
            for item in items:
                if item.get("source") == "osm_poi":
                    classified = _classify_by_osm(item.get("osmTags") or {})
                    if classified:
                        break
        if not classified:
            classified = _classify_by_name(name)
        # 区县归属：OSM 自带 > wiki 文本解析；不结论 → 缺口。
        located: tuple[str, str] | None = None
        for item in items:
            if item.get("district") and item.get("city"):
                located = (str(item["city"]), str(item["district"]))
                break
        if not located:
            for item in items:
                text = " ".join(
                    [str(item.get("extract") or ""), *(item.get("categories") or [])]
                )
                located = _resolve_district_from_text(text, province=province, country=country)
                if located:
                    break
        if not classified or not located:
            gaps.append(
                {
                    "name": name,
                    "province": province,
                    "missing": [
                        *(["entityType"] if not classified else []),
                        *(["district"] if not located else []),
                    ],
                    "evidence": items[:2],
                }
            )
            continue
        etype, type_ref = classified
        city, district = located
        entry = {
            "name": name,
            "canonicalName": name,
            "entityType": etype,
            "typeTagRefs": [type_ref],
            "geoTagRef": (
                admin_geo_ref(country, province, city)
                if city == district and city_is_district_level(country, province, city)
                else admin_geo_ref(country, province, city, district)
            ),
            "sourceReadiness": "pending",
        }
        patches.setdefault((province, city), {}).setdefault(district, []).append(entry)
        appended.append({"name": name, "province": province, "city": city, "district": district, "entityType": etype})

    written_files: list[str] = []
    if apply:
        for (province, city), district_map in sorted(patches.items()):
            path = COVERAGE_MASTER_ROOT / province / f"{city}.yaml"
            if not path.is_file():
                gaps.append(
                    {"name": f"<市州文件缺失: {province}/{city}>", "province": province, "missing": ["cityFile"], "evidence": []}
                )
                continue
            data = load_master_list_file(path)
            districts = data.setdefault("districts", [])
            by_district = {str(g.get("district") or ""): g for g in districts if isinstance(g, dict)}
            for district, entries in sorted(district_map.items()):
                group = by_district.get(district)
                if group is None:
                    group = {"district": district, "leaves": []}
                    districts.append(group)
                    by_district[district] = group
                leaves = group.setdefault("leaves", [])
                next_priority = max(
                    [int(l.get("selectionPriority") or 0) for l in leaves if isinstance(l, dict)] or [0]
                ) + 1
                for entry in entries:
                    leaf = dict(entry)
                    leaf["selectionPriority"] = next_priority
                    next_priority += 1
                    leaves.append(leaf)
            dump_master_list_file(path, data)
            written_files.append(path.as_posix())

    expand_runtime_dir = _expand_runtime_dir()
    expand_runtime_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = {
        "schemaVersion": "quwoquan_data.coverage_merge_report/1",
        "generatedAt": _now_iso(),
        "provinces": provinces,
        "apply": apply,
        "candidatesUnique": len(merged),
        "duplicatesAgainstMaster": duplicates,
        "appended": len(appended),
        "appendedItems": appended,
        "gaps": len(gaps),
        "gapItems": gaps,
        "writtenFiles": written_files,
    }
    report_path = expand_runtime_dir / f"merge_report_{stamp}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["reportPath"] = str(report_path)
    return report
