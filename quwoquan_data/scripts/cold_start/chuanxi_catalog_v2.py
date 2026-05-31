"""川西冷启动 v2 任务 catalog：实体扩展 + 122 篇 P0 文章规格。"""
from __future__ import annotations

from dataclasses import dataclass

from cold_start.chuanxi_catalog import (
    CHUANXI_ENTITIES,
    build_post_tag_refs,
    entity_ref,
    geo_tag,
)

CHUANXI_V2_TASK_ID = "川西冷启动_v2"
CHUANXI_V2_RELEASE_ID = "chuanxi_cold_start_r2"
P0_SEASON = "夏"

# P0 新增 10 个标杆景区（与 v1 核心 5 合计 15）
CHUANXI_V2_NEW_SCENIC: list[dict] = [
    {
        "name": "四姑娘山",
        "label_en": "Mount Siguniang",
        "etype": "景区",
        "domain": "地点",
        "city": "阿坝州",
        "theme": "Topic/旅行/旅行主题/雪山探险",
        "role": "户外核心",
        "high_altitude": True,
    },
    {
        "name": "丹巴甲居藏寨",
        "label_en": "Jiaju Tibetan Village",
        "etype": "景区",
        "domain": "地点",
        "city": "甘孜州",
        "theme": "Topic/旅行/旅行主题/文化深度游",
        "role": "藏寨人文",
        "high_altitude": True,
    },
    {
        "name": "墨石公园",
        "label_en": "Moshi Park",
        "etype": "景区",
        "domain": "地点",
        "city": "甘孜州",
        "theme": "Topic/旅行/玩法/观光游览",
        "role": "高原奇观",
        "high_altitude": True,
    },
    {
        "name": "色达",
        "label_en": "Sertar",
        "etype": "景区",
        "domain": "地点",
        "city": "甘孜州",
        "theme": "Topic/旅行/旅行主题/朝圣礼佛",
        "role": "人文高地",
        "high_altitude": True,
    },
    {
        "name": "新都桥",
        "label_en": "Xinduqiao",
        "etype": "景区",
        "domain": "地点",
        "city": "甘孜州",
        "theme": "Topic/旅行/玩法/摄影旅拍",
        "role": "摄影走廊",
        "high_altitude": True,
    },
    {
        "name": "毕棚沟",
        "label_en": "Bipeng Valley",
        "etype": "景区",
        "domain": "地点",
        "city": "阿坝州",
        "theme": "Topic/旅行/玩法/观光游览",
        "role": "彩林沟谷",
        "high_altitude": True,
    },
    {
        "name": "若尔盖花湖",
        "label_en": "Ruoergai Flower Lake",
        "etype": "景区",
        "domain": "地点",
        "city": "阿坝州",
        "theme": "Topic/旅行/玩法/观光游览",
        "role": "草原湿地",
        "high_altitude": True,
    },
    {
        "name": "康定木格措",
        "label_en": "Kangding Mugecuo",
        "etype": "景区",
        "domain": "地点",
        "city": "甘孜州",
        "theme": "Topic/旅行/旅行主题/雪山探险",
        "role": "康定门户",
        "high_altitude": True,
    },
    {
        "name": "理塘",
        "label_en": "Litang",
        "etype": "景区",
        "domain": "地点",
        "city": "甘孜州",
        "theme": "Topic/旅行/旅行主题/文化深度游",
        "role": "高城驿站",
        "high_altitude": True,
    },
    {
        "name": "甲根坝",
        "label_en": "Jiagenba",
        "etype": "景区",
        "domain": "地点",
        "city": "甘孜州",
        "theme": "Topic/旅行/玩法/摄影旅拍",
        "role": "藏乡秘境",
        "high_altitude": True,
    },
]

CHUANXI_V2_SCENIC: list[dict] = [
    row for row in CHUANXI_ENTITIES if row["etype"] == "景区"
] + CHUANXI_V2_NEW_SCENIC

CHUANXI_V2_ALL_ENTITIES: list[dict] = list(CHUANXI_ENTITIES) + CHUANXI_V2_NEW_SCENIC


@dataclass(frozen=True)
class ArticleSpec:
    batch: str
    ref: str
    title: str
    content_type: str  # article | image
    subject_kind: str
    subject_type: str
    intent: str
    audience: str | None
    region: str | None
    season: str | None
    entity_refs: tuple[str, ...]
    transport: str | None = None  # 自驾 | 公共交通 | None
    origin_city: str | None = None


def _entity_intro_specs() -> list[ArticleSpec]:
    specs: list[ArticleSpec] = []
    for row in CHUANXI_V2_SCENIC:
        name = row["name"]
        ref_base = entity_ref(row["domain"], row["etype"], name)
        region = "高原" if row.get("high_altitude") else "山地森林"
        for angle in ("攻略", "体验"):
            specs.append(
                ArticleSpec(
                    batch="entity_intro",
                    ref=f"{name}_{angle}",
                    title=f"{name}{angle}指南",
                    content_type="article",
                    subject_kind="entity",
                    subject_type=row["etype"] if row["etype"] != "景区" else "地点/景区",
                    intent=angle if angle != "日记" else "叙事",
                    audience="leisureTraveler",
                    region=region,
                    season=P0_SEASON,
                    entity_refs=(ref_base,),
                )
            )
    other: list[tuple[dict, str]] = [
        (next(r for r in CHUANXI_ENTITIES if r["name"] == "三星堆遗址"), "科普"),
        (next(r for r in CHUANXI_ENTITIES if r["name"] == "三星堆遗址"), "体验"),
        (next(r for r in CHUANXI_ENTITIES if r["name"] == "阆中古城"), "攻略"),
        (next(r for r in CHUANXI_ENTITIES if r["name"] == "阆中古城"), "叙事"),
        (next(r for r in CHUANXI_ENTITIES if r["name"] == "黄龙溪古镇"), "攻略"),
        (next(r for r in CHUANXI_ENTITIES if r["name"] == "三星堆博物馆"), "科普"),
        (next(r for r in CHUANXI_ENTITIES if r["name"] == "三星堆博物馆"), "体验"),
        (next(r for r in CHUANXI_ENTITIES if r["name"] == "成都博物馆"), "体验"),
    ]
    for row, angle in other:
        etype_map = {
            "遗址": "地点/遗址",
            "古镇": "地点/古镇",
            "博物馆": "地点/博物馆",
        }
        intent = "叙事" if angle == "叙事" else angle
        specs.append(
            ArticleSpec(
                batch="entity_intro",
                ref=f"{row['name']}_{angle}",
                title=f"{row['name']}{angle}指南",
                content_type="article",
                subject_kind="entity",
                subject_type=etype_map.get(row["etype"], f"地点/{row['etype']}"),
                intent=intent,
                audience="leisureTraveler",
                region="平原都市" if row["city"] == "成都市" else "山地森林",
                season=P0_SEASON,
                entity_refs=(entity_ref(row["domain"], row["etype"], row["name"]),),
            )
        )
    hub: list[tuple[dict, str, str]] = [
        (next(r for r in CHUANXI_ENTITIES if r["name"] == "成都太古里"), "攻略", "攻略"),
        (next(r for r in CHUANXI_ENTITIES if r["name"] == "成都太古里"), "体验", "体验"),
        (next(r for r in CHUANXI_ENTITIES if r["name"] == "宽窄巷子"), "攻略", "攻略"),
        (next(r for r in CHUANXI_ENTITIES if r["name"] == "宽窄巷子"), "日记", "叙事"),
    ]
    for row, angle, intent in hub:
        specs.append(
            ArticleSpec(
                batch="entity_intro",
                ref=f"{row['name']}_{angle}",
                title=f"{row['name']}{'指南' if angle != '日记' else '漫步'}",
                content_type="article",
                subject_kind="entity",
                subject_type="地点/打卡地",
                intent=intent,
                audience="leisureTraveler",
                region="平原都市",
                season=P0_SEASON,
                entity_refs=(entity_ref(row["domain"], row["etype"], row["name"]),),
            )
        )
    return specs


def _weekend_specs() -> list[ArticleSpec]:
    destinations = [
        ("青城山都江堰", "山地森林", ()),
        ("峨眉山周末", "山地森林", ("地点/景区/峨眉山",)),
        ("黄龙溪古镇周末", "平原都市", ("地点/古镇/黄龙溪古镇",)),
        ("西岭雪山周末", "雪山", ()),
        ("毕棚沟周末", "高原", ("地点/景区/毕棚沟",)),
        ("四姑娘山双桥沟周末", "高原", ("地点/景区/四姑娘山",)),
        ("三星堆博物馆周末", "平原都市", ("地点/博物馆/三星堆博物馆",)),
        ("都江堰南桥夜景", "平原都市", ()),
    ]
    specs: list[ArticleSpec] = []
    for dest, region, refs in destinations:
        for transport in ("自驾", "公共交通"):
            ref = f"{dest}_{transport}"
            specs.append(
                ArticleSpec(
                    batch="weekend_chengdu",
                    ref=ref,
                    title=f"成都出发{dest}{transport}周末短途（{P0_SEASON}季）",
                    content_type="article",
                    subject_kind="topic",
                    subject_type="旅行/线路",
                    intent="攻略",
                    audience="weekendLocalTraveler",
                    region=region,
                    season=P0_SEASON,
                    entity_refs=refs,
                    transport=transport,
                )
            )
    return specs


LOOPS: list[dict] = [
    {
        "id": "九寨黄龙环线",
        "entities": ("地点/景区/九寨沟", "地点/景区/黄龙"),
        "region": "高原",
    },
    {
        "id": "四姑娘山丹巴新都桥",
        "entities": ("地点/景区/四姑娘山", "地点/景区/丹巴甲居藏寨", "地点/景区/新都桥"),
        "region": "高原",
    },
    {
        "id": "稻城亚丁经典线",
        "entities": ("地点/景区/稻城亚丁", "地点/景区/理塘", "地点/景区/新都桥"),
        "region": "高原",
    },
    {
        "id": "海螺沟贡嘎东线",
        "entities": ("地点/景区/海螺沟", "地点/景区/新都桥"),
        "region": "雪山",
    },
    {
        "id": "色达炉霍人文线",
        "entities": ("地点/景区/色达", "地点/景区/墨石公园"),
        "region": "高原",
    },
    {
        "id": "若尔盖花湖线",
        "entities": ("地点/景区/若尔盖花湖",),
        "region": "高原",
    },
]

MODES: list[tuple[str, str, str]] = [
    ("自驾", "selfDriveTraveler", "路线推荐"),
    ("跟团", "groupTourTraveler", "跟团指南"),
    ("散团", "leisureTraveler", "攻略"),
]


def _loop_specs() -> list[ArticleSpec]:
    specs: list[ArticleSpec] = []
    for loop in LOOPS:
        for mode_name, audience, intent in MODES:
            ref = f"{loop['id']}_{mode_name}_{P0_SEASON}"
            specs.append(
                ArticleSpec(
                    batch="loop_3_5d",
                    ref=ref,
                    title=f"{loop['id']}{mode_name}攻略（{P0_SEASON}季）",
                    content_type="article",
                    subject_kind="topic",
                    subject_type="旅行/线路",
                    intent=intent,
                    audience=audience,
                    region=loop["region"],
                    season=P0_SEASON,
                    entity_refs=loop["entities"],
                    transport=mode_name,
                )
            )
    return specs


DEEP_THEMES: list[dict] = [
    {
        "id": "稻城亚丁深度秘境",
        "entities": ("地点/景区/稻城亚丁", "地点/景区/理塘", "地点/景区/新都桥"),
        "region": "高原",
        "deep_intent": False,
    },
    {
        "id": "格聂徒步穿越",
        "entities": ("地点/景区/理塘",),
        "region": "高原",
        "deep_intent": True,
    },
    {
        "id": "洛克线木里徒步",
        "entities": ("地点/景区/稻城亚丁",),
        "region": "雨林秘境",
        "deep_intent": True,
    },
    {
        "id": "川西大环线慢游",
        "entities": (
            "地点/景区/九寨沟",
            "地点/景区/稻城亚丁",
            "地点/景区/色达",
            "地点/景区/新都桥",
        ),
        "region": "高原",
        "deep_intent": False,
    },
]


def _deep_specs() -> list[ArticleSpec]:
    specs: list[ArticleSpec] = []
    for theme in DEEP_THEMES:
        for mode_name, audience, intent_base in MODES:
            intent = "深度探险" if theme["deep_intent"] and mode_name == "自驾" else (
                "跟团指南" if mode_name == "跟团" else ("路线推荐" if mode_name == "自驾" else "攻略")
            )
            ref = f"{theme['id']}_{mode_name}_{P0_SEASON}"
            specs.append(
                ArticleSpec(
                    batch="deep_7_14d",
                    ref=ref,
                    title=f"{theme['id']}{mode_name}深度攻略（{P0_SEASON}季）",
                    content_type="article",
                    subject_kind="topic",
                    subject_type="旅行/线路",
                    intent=intent,
                    audience=audience if mode_name != "自驾" or not theme["deep_intent"] else "selfDriveTraveler",
                    region=theme["region"],
                    season=P0_SEASON,
                    entity_refs=theme["entities"],
                    transport=mode_name,
                )
            )
    return specs


INBOUND_CITIES = ("北京", "上海", "深圳")
INBOUND_ROUTES: list[dict] = [
    {"id": "九寨黄龙环线", "kind": "loop", "entities": ("地点/景区/九寨沟", "地点/景区/黄龙"), "region": "高原"},
    {"id": "稻城亚丁经典线", "kind": "loop", "entities": ("地点/景区/稻城亚丁", "地点/景区/新都桥"), "region": "高原"},
    {"id": "川西大环线慢游", "kind": "deep", "entities": ("地点/景区/九寨沟", "地点/景区/稻城亚丁"), "region": "高原"},
]


def _inbound_specs() -> list[ArticleSpec]:
    specs: list[ArticleSpec] = []
    for city in INBOUND_CITIES:
        for route in INBOUND_ROUTES:
            for mode_name, audience, intent_base in MODES:
                intent = intent_base
                if route["kind"] == "deep" and mode_name == "自驾":
                    intent = "攻略"
                elif route["kind"] == "deep" and mode_name == "跟团":
                    intent = "跟团指南"
                ref = f"{city}出发_{route['id']}_{mode_name}_{P0_SEASON}"
                specs.append(
                    ArticleSpec(
                        batch="inbound_hub",
                        ref=ref,
                        title=f"{city}出发{route['id']}{mode_name}（经成都·{P0_SEASON}季）",
                        content_type="article",
                        subject_kind="topic",
                        subject_type="旅行/线路",
                        intent="攻略",
                        audience="hubInboundTraveler",
                        region="平原都市",
                        season=P0_SEASON,
                        entity_refs=("地点/打卡地/成都太古里",) + route["entities"],
                        transport=mode_name,
                        origin_city=city,
                    )
                )
    return specs


def _image_specs() -> list[ArticleSpec]:
    scenic = ["九寨沟", "稻城亚丁", "四姑娘山", "海螺沟", "色达"]
    specs: list[ArticleSpec] = []
    for name in scenic:
        ref = f"{name}_图文画报"
        specs.append(
            ArticleSpec(
                batch="images_p0",
                ref=ref,
                title=f"{name}摄影图集",
                content_type="image",
                subject_kind="topic",
                subject_type="旅行/主题",
                intent="美图",
                audience="photoTraveler",
                region="高原" if name != "海螺沟" else "雪山",
                season=P0_SEASON,
                entity_refs=(f"地点/景区/{name}",),
            )
        )
    for loop_id in ("九寨黄龙环线", "四姑娘山丹巴新都桥"):
        ref = f"{loop_id}_图集"
        specs.append(
            ArticleSpec(
                batch="images_p0",
                ref=ref,
                title=f"{loop_id}节点图集",
                content_type="image",
                subject_kind="topic",
                subject_type="旅行/主题",
                intent="美图",
                audience="photoTraveler",
                region="高原",
                season=P0_SEASON,
                entity_refs=(),
            )
        )
    return specs


def build_all_article_specs() -> list[ArticleSpec]:
    specs: list[ArticleSpec] = []
    specs.extend(_entity_intro_specs())
    specs.extend(_weekend_specs())
    specs.extend(_loop_specs())
    specs.extend(_deep_specs())
    specs.extend(_inbound_specs())
    specs.extend(_image_specs())
    return specs


def spec_to_plan_dict(spec: ArticleSpec) -> dict:
    return {
        "batch": spec.batch,
        "ref": spec.ref,
        "title": spec.title,
        "contentType": spec.content_type,
        "vertical": "travel",
        "subjectKind": spec.subject_kind,
        "subjectType": spec.subject_type,
        "intent": spec.intent,
        "audience": spec.audience,
        "region": spec.region,
        "season": spec.season,
        "entityRefs": list(spec.entity_refs),
        "transport": spec.transport,
        "originCity": spec.origin_city,
    }


def build_batch_manifest_rows() -> list[dict]:
    return [spec_to_plan_dict(s) for s in build_all_article_specs()]


__all__ = [
    "CHUANXI_V2_TASK_ID",
    "CHUANXI_V2_RELEASE_ID",
    "CHUANXI_V2_ALL_ENTITIES",
    "CHUANXI_V2_SCENIC",
    "ArticleSpec",
    "build_all_article_specs",
    "build_batch_manifest_rows",
    "build_post_tag_refs",
    "entity_ref",
    "geo_tag",
    "spec_to_plan_dict",
]
