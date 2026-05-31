"""川西冷启动 v1 实体 catalog（只读真相源，源自 sichuan_v5 16 实体）。"""
from __future__ import annotations

from sample_data.sichuan_v5 import TYPE_ANGLES, _geo  # noqa: F401

CHUANXI_TASK_ID = "川西冷启动_v1"
CHUANXI_BATCH_ID = "full"
CHUANXI_RELEASE_ID = "chuanxi_cold_start_r1"

# 与 sample_data/sichuan_v5.py rows 对齐
CHUANXI_ENTITIES: list[dict] = [
    {
        "name": "峨眉山",
        "label_en": "Mount Emei",
        "etype": "景区",
        "domain": "地点",
        "city": "乐山市",
        "theme": "Topic/旅行/旅行主题/雪山探险",
        "role": "环线南段",
    },
    {
        "name": "九寨沟",
        "label_en": "Jiuzhaigou",
        "etype": "景区",
        "domain": "地点",
        "city": "阿坝州",
        "theme": "Topic/旅行/玩法/观光游览",
        "role": "高原核心",
        "high_altitude": True,
    },
    {
        "name": "稻城亚丁",
        "label_en": "Daocheng Yading",
        "etype": "景区",
        "domain": "地点",
        "city": "甘孜州",
        "theme": "Topic/旅行/出行方式/徒步穿越",
        "role": "高原核心",
        "high_altitude": True,
    },
    {
        "name": "黄龙",
        "label_en": "Huanglong",
        "etype": "景区",
        "domain": "地点",
        "city": "阿坝州",
        "theme": "Topic/旅行/旅行主题/海滨度假",
        "role": "高原核心",
        "high_altitude": True,
    },
    {
        "name": "海螺沟",
        "label_en": "Hailuogou",
        "etype": "景区",
        "domain": "地点",
        "city": "甘孜州",
        "theme": "Topic/旅行/旅行主题/雪山探险",
        "role": "冰川温泉",
        "high_altitude": True,
    },
    {
        "name": "三星堆遗址",
        "label_en": "Sanxingdui Site",
        "etype": "遗址",
        "domain": "地点",
        "city": "德阳市",
        "theme": "Topic/旅行/旅行主题/文化深度游",
        "role": "文化支线",
    },
    {
        "name": "金沙遗址",
        "label_en": "Jinsha Site",
        "etype": "遗址",
        "domain": "地点",
        "city": "成都市",
        "theme": "Topic/旅行/旅行主题/文化深度游",
        "role": "枢纽文化",
    },
    {
        "name": "阆中古城",
        "label_en": "Langzhong Ancient Town",
        "etype": "古镇",
        "domain": "地点",
        "city": "南充市",
        "theme": "Topic/旅行/玩法/古迹寻访",
        "role": "北线古镇",
    },
    {
        "name": "黄龙溪古镇",
        "label_en": "Huanglongxi Ancient Town",
        "etype": "古镇",
        "domain": "地点",
        "city": "成都市",
        "theme": "Topic/旅行/玩法/古迹寻访",
        "role": "近郊古镇",
    },
    {
        "name": "成都太古里",
        "label_en": "Chengdu Taikoo Li",
        "etype": "打卡地",
        "domain": "地点",
        "city": "成都市",
        "theme": "Topic/旅行/旅行主题/城市漫步",
        "role": "枢纽打卡",
    },
    {
        "name": "宽窄巷子",
        "label_en": "Kuanzhai Alley",
        "etype": "打卡地",
        "domain": "地点",
        "city": "成都市",
        "theme": "Topic/旅行/旅行主题/城市漫步",
        "role": "枢纽打卡",
    },
    {
        "name": "三星堆博物馆",
        "label_en": "Sanxingdui Museum",
        "etype": "博物馆",
        "domain": "地点",
        "city": "德阳市",
        "theme": "Topic/旅行/玩法/博物馆展览",
        "role": "文化支线",
    },
    {
        "name": "成都博物馆",
        "label_en": "Chengdu Museum",
        "etype": "博物馆",
        "domain": "地点",
        "city": "成都市",
        "theme": "Topic/旅行/玩法/博物馆展览",
        "role": "枢纽博物馆",
    },
    {
        "name": "陈麻婆豆腐总店",
        "label_en": "Chen Mapo Tofu Flagship",
        "etype": "餐厅",
        "domain": "地点",
        "city": "成都市",
        "theme": "Topic/旅行/玩法/市集探店",
        "role": "美食节点",
    },
    {
        "name": "峨眉山蓝光己庄温泉度假村",
        "label_en": "Blulight Yizhuang Emei Hot Spring Resort",
        "etype": "住宿",
        "domain": "地点",
        "city": "乐山市",
        "theme": "Topic/旅行/玩法/SPA美容",
        "role": "度假住宿",
    },
    {
        "name": "四川大学",
        "label_en": "Sichuan University",
        "etype": "学校",
        "domain": "机构",
        "city": "成都市",
        "theme": "Topic/旅行/旅行主题/城市漫步",
        "role": "校园参观",
    },
]


def entity_tag_line(domain: str, etype: str) -> str:
    return f"Entity/{domain}/{etype}"


def geo_tag(city: str) -> str:
    return _geo(city)


def angles_for(domain: str, etype: str) -> list[str]:
    return list(TYPE_ANGLES[(domain, etype)])


def entity_ref(domain: str, etype: str, name: str) -> str:
    return f"{domain}/{etype}/{name}"


def build_post_tag_refs(row: dict, angle: str) -> list[str]:
    domain = row["domain"]
    etype = row["etype"]
    theme = row["theme"]
    refs = [
        theme,
        "Topic/旅行/玩法/观光游览",
        "Topic/旅行/出行方式/自驾",
        "Topic/旅行/行程形态/自由行",
        "Topic/旅行/旅行时长/3-5日中线",
        f"Format/内容角度/{angle}",
        entity_tag_line(domain, etype),
        "Topic/旅行",
    ]
    if row.get("high_altitude"):
        refs.extend(
            [
                "Topic/旅行/出行方式/徒步穿越",
                "Topic/旅行/旅行筹备/应急避险",
            ]
        )
    if etype == "住宿":
        refs.append("Topic/旅行/住宿/川西住宿")
    if etype == "学校":
        refs.append("Topic/旅行/玩法/校园参观")
    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for r in refs:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out
