"""Coverage discovery policy, classifier tables, and shared source helpers."""
from __future__ import annotations

import re
from typing import Any

from content.source.research import network_io
from core.runtime_policy import active_runtime_policy


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
_OVERPASS_RESULT_LIMIT = _COVERAGE_POLICY.overpass_result_limit
_OVERPASS_ENDPOINTS = _COVERAGE_POLICY.overpass_endpoints

# The execution request supplies ``region``. These generic MediaWiki category
# templates are provider behavior, not a committed rollout target list.
_WIKI_SEED_CATEGORY_TEMPLATES: tuple[str, ...] = (
    "Category:{region}旅游景点",
    "Category:{region}文物保护单位",
    "Category:{region}的博物馆",
    "Category:中国历史文化名镇",
)


def wiki_category_seeds(region: str) -> tuple[str, ...]:
    normalized_region = str(region or "").strip()
    if not normalized_region:
        raise ValueError("region is required for MediaWiki category discovery")
    return tuple(
        template.format(region=normalized_region)
        for template in _WIKI_SEED_CATEGORY_TEMPLATES
    )

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
    return any(re.search(pattern, title) for pattern in _TITLE_STOPWORDS)


def _category_blocked(cat_title: str) -> bool:
    return any(word in cat_title for word in _WIKI_CATEGORY_STOPWORDS)
