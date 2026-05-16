"""泰国旅行 v5 示例数据：10 实体 + 20 posts。"""
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

TASK_ID = "泰国旅行_v5"
ANGLES = ["攻略", "体验", "叙事", "科普", "探店", "日记"]


def _geo(admin1: str, admin2: str) -> str:
    return f"Topic/地理/行政区/泰国/{admin1}/{admin2}"


def _entity_tag_line(domain: str, etype: str) -> str:
    return f"Entity/{domain}/{etype}"


def build(dry_run: bool = False):
    """生成泰国旅行 v5 全量数据。"""
    root = RUNTIME_ROOT / "tasks" / TASK_ID
    if not dry_run:
        ensure_task_layout(TASK_ID)

    rows: list[dict] = [
        {
            "name": "大皇宫",
            "label_en": "Grand Palace",
            "etype": "景区",
            "domain": "地点",
            "a1": "曼谷府",
            "a2": "曼谷",
            "theme": "Topic/旅行/旅行主题/城市漫步",
        },
        {
            "name": "双龙寺",
            "label_en": "Doi Suthep",
            "etype": "景区",
            "domain": "地点",
            "a1": "清迈府",
            "a2": "清迈",
            "theme": "Topic/旅行/玩法/朝圣观光",
        },
        {
            "name": "皮皮岛",
            "label_en": "Phi Phi Islands",
            "etype": "景区",
            "domain": "地点",
            "a1": "甲米府",
            "a2": "皮皮岛",
            "theme": "Topic/旅行/旅行主题/海岛度假",
        },
        {
            "name": "考山路",
            "label_en": "Khao San Road",
            "etype": "打卡地",
            "domain": "地点",
            "a1": "曼谷府",
            "a2": "曼谷",
            "theme": "Topic/旅行/旅行主题/夜生活",
        },
        {
            "name": "周末集市",
            "label_en": "Weekend Market",
            "etype": "打卡地",
            "domain": "地点",
            "a1": "曼谷府",
            "a2": "曼谷",
            "theme": "Topic/旅行/玩法/市集淘宝",
        },
        {
            "name": "清迈古城",
            "label_en": "Chiang Mai Old City",
            "etype": "古镇",
            "domain": "地点",
            "a1": "清迈府",
            "a2": "清迈",
            "theme": "Topic/旅行/玩法/古迹寻访",
        },
        {
            "name": "苏梅岛度假村",
            "label_en": "Koh Samui Resort",
            "etype": "住宿",
            "domain": "地点",
            "a1": "素叻他尼府",
            "a2": "苏梅岛",
            "theme": "Topic/旅行/玩法/海岛度假",
        },
        {
            "name": "曼谷夜市小吃",
            "label_en": "Bangkok Night Market Food",
            "etype": "餐厅",
            "domain": "地点",
            "a1": "曼谷府",
            "a2": "曼谷",
            "theme": "Topic/旅行/玩法/美食打卡",
        },
        {
            "name": "暹罗海洋世界",
            "label_en": "SEA LIFE Bangkok",
            "etype": "主题乐园",
            "domain": "地点",
            "a1": "曼谷府",
            "a2": "曼谷",
            "theme": "Topic/旅行/玩法/亲子娱乐",
        },
        {
            "name": "素万那普机场",
            "label_en": "Suvarnabhumi Airport",
            "etype": "交通枢纽",
            "domain": "地点",
            "a1": "沙没巴干府",
            "a2": "挽披",
            "theme": "Topic/旅行/出行方式/航空",
        },
    ]

    entity_count = 0
    post_count = 0
    for idx, r in enumerate(rows):
        name = r["name"]
        etype = r["etype"]
        domain = r["domain"]
        geo = _geo(r["a1"], r["a2"])
        desc = (
            f"{name} 位于泰国{r['a1']}{r['a2']}一线，类型为 {etype}，属于泰国旅行 v5 示例数据的结构化样例，"
            "用于验证 geoTagRef 与 post manifest 约束。"
        )
        highlights = [
            "入境与交通：关注签注政策、转机时间与行李直挂规则（示例占位）。",
            "本地支付：提前了解现金比例与移动支付的覆盖范围。",
            "安全与礼仪：寺庙着装、摄影边界与小费文化需要前置沟通。",
            "内容素材：`asset://` 仅占位，正式内容需走版权与授权核验。",
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
        a2 = ANGLES[(idx + 2) % len(ANGLES)]

        if name == "清迈古城":
            posts_spec = [
                (
                    "清迈古城旅拍",
                    "体验",
                    [
                        "Topic/旅行/玩法/摄影旅拍",
                        "Topic/旅行/玩法/古迹寻访",
                        "Topic/旅行/出行方式/慢行",
                        "Format/内容角度/体验",
                    ],
                    [
                        "城墙与寺庙的转角适合用广角收进纵深感；注意阴影与高光平衡。",
                        "午后人流量上升，早点开工能换到更干净的前景。",
                        "傍晚光线偏暖，白平衡可略向冷色收一点避免发黄。",
                    ],
                ),
                (
                    "清迈古城慢行攻略",
                    a2,
                    [
                        "Topic/旅行/玩法/古迹寻访",
                        "Topic/旅行/行程形态/自由行",
                        "Topic/旅行/旅行主题/城市漫步",
                        "Format/内容角度/" + a2,
                    ],
                    [
                        "把古城内外交通拆成「步行圈 + 双条车兜底」两段，心智成本更低。",
                        "午餐后安排室内展馆或咖啡馆，躲开最热时段。",
                        "晚上优先选择Lighting好的路段，注意安全与随身物品。",
                    ],
                ),
            ]
        else:
            posts_spec = [
                (
                    f"{name}{a1}笔记",
                    a1,
                    [
                        "Topic/旅行/玩法/观光游览",
                        "Topic/旅行/行程形态/自由行",
                        "Topic/旅行/出行方式/慢行",
                        "Format/内容角度/" + a1,
                    ],
                    [
                        f"以 {name} 为主线，先把「必须完成的核心段落」写清，再补可选扩展。",
                        "把排队、预约、闭馆与天气变量写进时间表，避免被动改线。",
                        "若是多人同行，提前对齐预算峰值与消费分工，减少现场摩擦。",
                    ],
                ),
                (
                    f"{name}{a2}延展",
                    a2,
                    [
                        r["theme"],
                        "Topic/旅行/玩法/观光游览",
                        "Topic/旅行/旅行时长/3-5日中线",
                        "Format/内容角度/" + a2,
                    ],
                    [
                        f"{name} 的第二条叙事：从体验细节出发，而不是复述百科。",
                        "适当加入「失败样本」与「复盘建议」，比单纯好评更有信息量。",
                        "回程段把行李与交通接驳写成 checklist，降低遗漏概率。",
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
