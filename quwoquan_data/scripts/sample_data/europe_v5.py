"""欧洲旅行 v5 示例数据：12 实体 + 24 posts。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _common.paths import RUNTIME_ROOT, ensure_task_layout  # noqa: E402

from sample_data._common import (  # noqa: E402
    make_entity,
    make_entity_manifest,
    make_entity_page,
    make_post_article,
    make_post_manifest,
    validate_travel_post,
    write_entity,
    write_post,
    write_task_manifest,
)

TASK_ID = "欧洲旅行_v5"
ANGLES = ["攻略", "体验", "叙事", "科普", "探店", "日记"]


def _geo(country: str, city: str) -> str:
    return f"Topic/地理/行政区/{country}/{city}"


def _entity_tag_line(domain: str, etype: str) -> str:
    return f"Entity/{domain}/{etype}"


def build(dry_run: bool = False):
    """生成欧洲旅行 v5 全量数据。"""
    root = RUNTIME_ROOT / "tasks" / TASK_ID
    if not dry_run:
        ensure_task_layout(TASK_ID)

    rows: list[dict] = [
        {
            "name": "埃菲尔铁塔",
            "label_en": "Eiffel Tower",
            "etype": "景区",
            "domain": "地点",
            "country": "法国",
            "city": "巴黎",
            "theme": "Topic/旅行/旅行主题/城市地标",
        },
        {
            "name": "斗兽场",
            "label_en": "Colosseum",
            "etype": "景区",
            "domain": "地点",
            "country": "意大利",
            "city": "罗马",
            "theme": "Topic/旅行/旅行主题/世界遗产",
        },
        {
            "name": "圣家堂",
            "label_en": "Sagrada Familia",
            "etype": "景区",
            "domain": "地点",
            "country": "西班牙",
            "city": "巴塞罗那",
            "theme": "Topic/旅行/旅行主题/建筑艺术",
        },
        {
            "name": "CK小镇",
            "label_en": "Cesky Krumlov",
            "etype": "古镇",
            "domain": "地点",
            "country": "捷克",
            "city": "克鲁姆洛夫",
            "theme": "Topic/旅行/玩法/古迹寻访",
        },
        {
            "name": "圣托里尼",
            "label_en": "Santorini",
            "etype": "打卡地",
            "domain": "地点",
            "country": "希腊",
            "city": "圣托里尼",
            "theme": "Topic/旅行/旅行主题/海岛度假",
        },
        {
            "name": "少女峰",
            "label_en": "Jungfrau",
            "etype": "打卡地",
            "domain": "地点",
            "country": "瑞士",
            "city": "因特拉肯",
            "theme": "Topic/旅行/旅行主题/雪山探险",
        },
        {
            "name": "卢浮宫",
            "label_en": "Louvre",
            "etype": "博物馆",
            "domain": "地点",
            "country": "法国",
            "city": "巴黎",
            "theme": "Topic/人文/文博/经典陈列",
        },
        {
            "name": "大英博物馆",
            "label_en": "British Museum",
            "etype": "博物馆",
            "domain": "地点",
            "country": "英国",
            "city": "伦敦",
            "theme": "Topic/人文/文博/通史展",
        },
        {
            "name": "桑托里尼洞穴酒店",
            "label_en": "Santorini Cave Hotel",
            "etype": "住宿",
            "domain": "地点",
            "country": "希腊",
            "city": "圣托里尼",
            "theme": "Topic/旅行/玩法/海岛度假",
        },
        {
            "name": "维也纳国家歌剧院",
            "label_en": "Vienna State Opera",
            "etype": "演艺场馆",
            "domain": "地点",
            "country": "奥地利",
            "city": "维也纳",
            "theme": "Topic/旅行/玩法/演艺观演",
        },
        {
            "name": "里斯本蛋挞店",
            "label_en": "Lisbon Egg Tart Shop",
            "etype": "餐厅",
            "domain": "地点",
            "country": "葡萄牙",
            "city": "里斯本",
            "theme": "Topic/旅行/玩法/美食打卡",
        },
        {
            "name": "伦敦希思罗机场",
            "label_en": "London Heathrow Airport",
            "etype": "交通枢纽",
            "domain": "地点",
            "country": "英国",
            "city": "伦敦",
            "theme": "Topic/旅行/出行方式/航空",
        },
    ]

    entity_count = 0
    post_count = 0
    for idx, r in enumerate(rows):
        name = r["name"]
        etype = r["etype"]
        domain = r["domain"]
        geo = _geo(r["country"], r["city"])
        desc = (
            f"{name} 位于{r['country']}{r['city']}，类型为 {etype}，是欧洲旅行 v5 示例数据的结构化节点，"
            "用于对齐跨国 geoTagRef 与多语种 label 字段。"
        )
        highlights = [
            "跨境行程：关注申根/入境材料、航司行李规则与转机最小连接时间（占位）。",
            "城市内交通：把高峰时段、罢工与临时封路的风险预算写进行程。",
            "票务预订：热门场馆建议提前预约并保存二维码离线副本。",
            "素材合规：`asset://` 仅为路径占位，正式内容需完成授权与出处标注。",
        ]
        ent_tags = [
            r["theme"],
            "Topic/旅行/玩法/观光游览",
            "Topic/旅行/行程形态/自由行",
            "Topic/旅行/旅行时长/3-5日中线",
            "Format/内容角度/攻略",
            _entity_tag_line(domain, etype),
        ]
        entity = make_entity(
            name,
            r["label_en"],
            desc,
            domain,
            etype,
            geo,
            ent_tags,
        )
        page = make_entity_page(name, domain, etype, desc, highlights)
        em = make_entity_manifest(name, domain, etype, ent_tags, entity_refs=[])
        entity_ref = f"{domain}/{etype}/{name}"
        if not dry_run:
            write_entity(root, domain, etype, name, entity, page, em)
        entity_count += 1

        a1 = ANGLES[idx % len(ANGLES)]
        a2 = ANGLES[(idx + 4) % len(ANGLES)]

        if name == "圣托里尼":
            posts_spec = [
                (
                    "圣托里尼旅拍",
                    "体验",
                    [
                        "Topic/旅行/玩法/摄影旅拍",
                        "Topic/旅行/旅行主题/海岛度假",
                        "Topic/旅行/出行方式/慢行",
                        "Format/内容角度/体验",
                    ],
                    [
                        "蓝白对比强，注意过曝与高光溢出；偏振镜要谨慎使用避免.sky 死黑。",
                        "风大时稳定器意义有限，优先提高快门与安全握持。",
                        "日落机位要提前占位，同时关注台阶湿滑与随身物品。",
                    ],
                ),
                (
                    "圣托里尼动线攻略",
                    a2,
                    [
                        "Topic/旅行/旅行主题/海岛度假",
                        "Topic/旅行/行程形态/自由行",
                        "Topic/旅行/玩法/观光游览",
                        "Format/内容角度/" + a2,
                    ],
                    [
                        "把观景点、用餐与回酒店拆成三段，避免把所有事情压在黄金半小时。",
                        "岛上交通以租车/巴士/步行为主，提前对齐体力与行李重量。",
                        "防晒与补水比拍照更重要；出现中暑前兆要立刻降温补水。",
                    ],
                ),
            ]
        else:
            posts_spec = [
                (
                    f"{name}{a1}记录",
                    a1,
                    [
                        "Topic/旅行/玩法/观光游览",
                        "Topic/旅行/行程形态/自由行",
                        "Topic/旅行/出行方式/慢行",
                        "Format/内容角度/" + a1,
                    ],
                    [
                        f"围绕 {name} 的行程，建议先用「可达性最差」的那一段锁定时间窗口。",
                        "城市管理差异大：同一种行为在不同国家可能有不同约束，先查官方口径。",
                        "把紧急联络、保单与证件复印件离线保存，遇到突发状况更从容。",
                    ],
                ),
                (
                    f"{name}{a2}续篇",
                    a2,
                    [
                        r["theme"],
                        "Topic/旅行/玩法/观光游览",
                        "Topic/旅行/旅行时长/3-5日中线",
                        "Format/内容角度/" + a2,
                    ],
                    [
                        f"{name} 的补充视角：用体验密度替换景点数量，旅行质感会更稳。",
                        "欧洲城市昼夜温差与室内外切换频繁，分层穿衣比一件厚外套更实用。",
                        "离开前核对退税材料与海关盖章位置，避免最后一段手忙脚乱。",
                    ],
                ),
            ]

        for seq, (title, angle, tr, paras) in enumerate(posts_spec, start=1):
            pm = make_post_manifest(title, entity_ref, tr, content_type="article")
            validate_travel_post(pm, etype, context=f"{TASK_ID}:{title}")
            art = make_post_article(title, name, domain, etype, angle, paras)
            if not dry_run:
                write_post(root, "article", angle, title, seq, art, pm)
            post_count += 1

    if not dry_run:
        write_task_manifest(root, TASK_ID, entity_count, post_count)
    return entity_count, post_count
