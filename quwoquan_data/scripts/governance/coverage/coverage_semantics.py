"""Coverage 候选名称归一化与确定性语义拒绝规则。"""
from __future__ import annotations

import re
import unicodedata
from typing import Any


GENERIC_OSM_NAMES = frozenset(
    {
        "quarry",
        "tk",
        "park",
        "garden",
        "museum",
        "attraction",
        "scenic spot",
        "公园",
        "广场",
        "景区",
        "景点",
        "博物馆",
        "遗址",
        "古迹",
        "无名",
        "未命名",
    }
)
ORDINARY_FACILITY_PATTERN = re.compile(
    r"(停车场|加油站|充电站|厕所|卫生间|物业|售楼处|小区|住宅|公寓|学校|"
    r"幼儿园|大学|学院|医院|诊所|药店|银行|营业厅|超市|便利店|商店|"
    r"购物中心|商场|公司|工厂|厂区|采石场)$",
    re.IGNORECASE,
)
LODGING_OR_COMMERCE_PATTERN = re.compile(
    r"(酒店|宾馆|旅馆|民宿|客栈|度假村|餐厅|饭店|咖啡馆|酒吧)$",
    re.IGNORECASE,
)
TRANSPORT_OR_ROAD_PATTERN = re.compile(
    r"(道路|公路|高速|大街|路|街|公交站|车站|地铁站|火车站|客运站|机场)$",
    re.IGNORECASE,
)


def normalize_name(value: str) -> str:
    """NFKC + 去空白 + 去常见景区后缀变体。"""
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    text = re.sub(r"\s+", "", text)
    for suffix in ("旅游景区", "风景名胜区", "风景区", "旅游区", "景区"):
        if text.endswith(suffix) and len(text) > len(suffix) + 1:
            text = text[: -len(suffix)]
            break
    return text


def semantic_rejection_reason(item: dict[str, Any]) -> str | None:
    """拒绝有明确证据的非旅行地点；严格设施规则只作用于 OSM 候选。"""
    name = str(item.get("name") or "").strip()
    normalized = normalize_name(name).casefold()
    if not normalized or normalized in GENERIC_OSM_NAMES or len(normalized) < 2:
        return "generic_or_placeholder_name"
    if item.get("source") != "osm_poi":
        return None
    if ORDINARY_FACILITY_PATTERN.search(name):
        return "ordinary_facility"
    if LODGING_OR_COMMERCE_PATTERN.search(name):
        return "ordinary_lodging_or_commerce"
    if TRANSPORT_OR_ROAD_PATTERN.search(name):
        return "transport_or_road"
    tags = item.get("osmTags") if isinstance(item.get("osmTags"), dict) else {}
    if any(
        str(tags.get(key) or "")
        for key in ("shop", "office", "building", "highway", "public_transport")
    ):
        return "ordinary_osm_feature"
    if str(tags.get("tourism") or "") in {
        "hotel",
        "guest_house",
        "hostel",
        "motel",
        "camp_site",
        "information",
    }:
        return "ordinary_lodging_or_commerce"
    return None
