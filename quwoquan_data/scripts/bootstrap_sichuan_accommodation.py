"""批量生成四川住宿实体与住宿 posts（满足 H-A10/H-A11/H-A12）

生成目标：
- 15 个四川住宿实体（覆盖酒店/民宿/青旅/客栈/度假村/农家乐/胶囊旅馆）
- 10 篇住宿相关 posts（每篇含 entityRef + Topic/旅行/住宿/* + Format/内容角度/*）

用法:
  python3 bootstrap_sichuan_accommodation.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common.paths import PUBLISH_ROOT, NOW_ISO

ENTITIES_ROOT = PUBLISH_ROOT / "v1" / "entities" / "地点" / "住宿"
POSTS_ROOT = PUBLISH_ROOT / "v1" / "posts" / "article" / "内容角度"


def write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


ENTITIES = [
    {
        "name": "成都香格里拉大酒店",
        "labelEn": "Shangri-La Chengdu",
        "geo": "Topic/地理/行政区/中国/四川省/成都市",
        "tagRefs": [
            "Entity/地点/住宿/住宿业态/酒店",
            "Entity/地点/住宿/档次等级/五星级",
            "Entity/地点/住宿/功能定位/商务住宿",
            "Entity/地点/住宿/功能定位/会议会展住宿",
            "Entity/地点/住宿/设施服务/游泳池",
            "Entity/地点/住宿/设施服务/行政酒廊",
            "Entity/地点/住宿/设施服务/免费停车",
        ],
        "sourceRefs": ["https://www.shangri-la.com/chengdu/shangrila/"],
        "desc": "位于成都锦江区滨江东路的国际五星级商务酒店，紧邻IFS与春熙路商圈，拥有593间客房与2000平方米无柱式宴会厅。",
    },
    {
        "name": "成都瑞吉酒店",
        "labelEn": "The St. Regis Chengdu",
        "geo": "Topic/地理/行政区/中国/四川省/成都市",
        "tagRefs": [
            "Entity/地点/住宿/住宿业态/酒店",
            "Entity/地点/住宿/档次等级/豪华型",
            "Entity/地点/住宿/功能定位/商务住宿",
            "Entity/地点/住宿/设施服务/SPA水疗",
            "Entity/地点/住宿/设施服务/行政酒廊",
            "Entity/地点/住宿/设施服务/游泳池",
        ],
        "sourceRefs": ["https://www.marriott.com/hotels/travel/ctust-the-st-regis-chengdu/"],
        "desc": "万豪旗下顶级奢华品牌瑞吉在成都的旗舰物业，提供管家服务与瑞吉酒吧经典体验，定位城市奢华商务住宿。",
    },
    {
        "name": "成都博舍酒店",
        "labelEn": "The Temple House Chengdu",
        "geo": "Topic/地理/行政区/中国/四川省/成都市",
        "tagRefs": [
            "Entity/地点/住宿/住宿业态/酒店",
            "Entity/地点/住宿/档次等级/高端型",
            "Entity/地点/住宿/功能定位/设计精品住宿",
            "Entity/地点/住宿/设施服务/游泳池",
            "Entity/地点/住宿/设施服务/健身房",
        ],
        "sourceRefs": ["https://www.thehousecollective.com/the-temple-house/"],
        "desc": "太古集团居舍系列在成都的设计精品酒店，由百年大慈寺古建筑群改建而成，毗邻太古里，融合古蜀文化与当代设计。",
    },
    {
        "name": "青城山六善酒店",
        "labelEn": "Six Senses Qingcheng Mountain",
        "geo": "Topic/地理/行政区/中国/四川省/成都市",
        "tagRefs": [
            "Entity/地点/住宿/住宿业态/度假村",
            "Entity/地点/住宿/档次等级/豪华型",
            "Entity/地点/住宿/功能定位/度假住宿",
            "Entity/地点/住宿/功能定位/温泉住宿",
            "Entity/地点/住宿/设施服务/SPA水疗",
            "Entity/地点/住宿/设施服务/游泳池",
            "Entity/地点/住宿/设施服务/免费停车",
            "Entity/地点/住宿/房源形态/独栋别墅",
        ],
        "sourceRefs": ["https://www.sixsenses.com/en/resorts/qing-cheng-mountain/"],
        "desc": "六善品牌在中国的首家度假酒店，坐落于世界遗产青城山脚，以道教养生哲学为设计灵感，独栋别墅散布在竹林溪谷间。",
    },
    {
        "name": "峨眉山蓝光己庄温泉度假村",
        "labelEn": "Blulight Yizhuang Emei Hot Spring Resort",
        "geo": "Topic/地理/行政区/中国/四川省/乐山市",
        "tagRefs": [
            "Entity/地点/住宿/住宿业态/度假村",
            "Entity/地点/住宿/档次等级/高端型",
            "Entity/地点/住宿/功能定位/温泉住宿",
            "Entity/地点/住宿/功能定位/度假住宿",
            "Entity/地点/住宿/功能定位/亲子友好住宿",
            "Entity/地点/住宿/设施服务/温泉汤池",
            "Entity/地点/住宿/设施服务/儿童乐园",
            "Entity/地点/住宿/设施服务/免费停车",
            "Entity/地点/住宿/房源形态/独栋别墅",
        ],
        "sourceRefs": ["https://www.trip.com/hotels/emeishan-hotel-detail-5145370/"],
        "desc": "位于峨眉山黄湾镇的森林温泉度假综合体，52个室内外温泉汤池与亲子乐园并重，是成都2小时度假圈的热门亲子目的地。",
    },
    {
        "name": "海螺沟贡嘎神汤温泉酒店",
        "labelEn": "Hailuogou Gongga Shentang Hot Spring Hotel",
        "geo": "Topic/地理/行政区/中国/四川省/甘孜州",
        "tagRefs": [
            "Entity/地点/住宿/住宿业态/酒店",
            "Entity/地点/住宿/档次等级/舒适型",
            "Entity/地点/住宿/功能定位/温泉住宿",
            "Entity/地点/住宿/设施服务/温泉汤池",
            "Entity/地点/住宿/设施服务/免费停车",
        ],
        "sourceRefs": ["https://www.trip.com/hotels/hailuogou-hotel-detail-436628/"],
        "desc": "位于海螺沟景区磨西镇的温泉酒店，天然碳酸氢钠温泉水质优良，是观赏贡嘎山冰川日照金山后的理想住宿选择。",
    },
    {
        "name": "丹巴甲居藏寨民宿",
        "labelEn": "Danba Jiaju Tibetan Village Homestay",
        "geo": "Topic/地理/行政区/中国/四川省/甘孜州",
        "tagRefs": [
            "Entity/地点/住宿/住宿业态/民宿",
            "Entity/地点/住宿/档次等级/舒适型",
            "Entity/地点/住宿/房源形态/藏式民居",
        ],
        "sourceRefs": ["https://baike.baidu.com/item/甲居藏寨"],
        "desc": "丹巴甲居藏寨是中国最美乡村之一，藏式碉楼民居改造为民宿，提供藏族家庭式住宿体验与田园风光。",
    },
    {
        "name": "稻城亚丁日松贡布酒店",
        "labelEn": "Hilton Garden Inn Daocheng Aden",
        "geo": "Topic/地理/行政区/中国/四川省/甘孜州",
        "tagRefs": [
            "Entity/地点/住宿/住宿业态/酒店",
            "Entity/地点/住宿/档次等级/舒适型",
            "Entity/地点/住宿/房型空间/大床房",
            "Entity/地点/住宿/设施服务/免费停车",
        ],
        "sourceRefs": ["https://www.hilton.com/en/hotels/dcjgigi-hilton-garden-inn-daocheng-aden/"],
        "desc": "希尔顿花园酒店品牌在稻城亚丁的物业，海拔约3700米，配备供氧系统与弥散式制氧设备，是高原住宿的代表。",
    },
    {
        "name": "成都懒骨头青年旅舍",
        "labelEn": "Lazybones Hostel Chengdu",
        "geo": "Topic/地理/行政区/中国/四川省/成都市",
        "tagRefs": [
            "Entity/地点/住宿/住宿业态/青年旅舍",
            "Entity/地点/住宿/档次等级/经济型",
            "Entity/地点/住宿/房源形态/合住房间",
        ],
        "sourceRefs": ["https://www.hostelworld.com/st/hostels/p/47283/lazybones-hostel/"],
        "desc": "成都最知名的国际青年旅舍之一，位于武侯祠附近，以社交氛围浓厚和深度本地活动著称，背包客川西出发的集散地。",
    },
    {
        "name": "九寨沟鲁能希尔顿度假酒店",
        "labelEn": "Hilton Jiuzhaigou Resort",
        "geo": "Topic/地理/行政区/中国/四川省/阿坝州",
        "tagRefs": [
            "Entity/地点/住宿/住宿业态/酒店",
            "Entity/地点/住宿/档次等级/高端型",
            "Entity/地点/住宿/功能定位/度假住宿",
            "Entity/地点/住宿/设施服务/游泳池",
            "Entity/地点/住宿/设施服务/免费停车",
            "Entity/地点/住宿/设施服务/接送服务",
        ],
        "sourceRefs": ["https://www.hilton.com/en/hotels/jzhchhi-hilton-jiuzhaigou-resort/"],
        "desc": "九寨沟景区附近的高端度假酒店，藏式建筑风格，提供景区接送服务与高原舒适住宿体验。",
    },
    {
        "name": "阆中花间堂阆苑",
        "labelEn": "Blossom Hill Inn Langzhong",
        "geo": "Topic/地理/行政区/中国/四川省/南充市",
        "tagRefs": [
            "Entity/地点/住宿/住宿业态/客栈",
            "Entity/地点/住宿/档次等级/高端型",
            "Entity/地点/住宿/功能定位/设计精品住宿",
            "Entity/地点/住宿/房源形态/庭院客栈",
        ],
        "sourceRefs": ["https://www.trip.com/hotels/langzhong-hotel-detail-5826095/"],
        "desc": "花间堂品牌在阆中古城内的精品客栈，由清代院落修缮而来，保留川北传统穿斗木结构，是古城沉浸式住宿体验代表。",
    },
    {
        "name": "都江堰安缇缦国际旅游度假区",
        "labelEn": "Antimán Dujiangyan Resort",
        "geo": "Topic/地理/行政区/中国/四川省/成都市",
        "tagRefs": [
            "Entity/地点/住宿/住宿业态/度假村",
            "Entity/地点/住宿/档次等级/高端型",
            "Entity/地点/住宿/功能定位/亲子友好住宿",
            "Entity/地点/住宿/功能定位/度假住宿",
            "Entity/地点/住宿/设施服务/儿童乐园",
            "Entity/地点/住宿/设施服务/免费停车",
            "Entity/地点/住宿/房源形态/树屋",
        ],
        "sourceRefs": ["https://www.trip.com/hotels/dujiangyan-hotel-detail-10614741/"],
        "desc": "位于都江堰青城山区域的亲子度假综合体，含树屋住宿、丛林探险、无动力乐园与萌宠牧场，主打3-12岁家庭周末度假。",
    },
    {
        "name": "彭州宝山村太阳湾农家乐",
        "labelEn": "Pengzhou Baoshan Taiyangwan Farmstay",
        "geo": "Topic/地理/行政区/中国/四川省/成都市",
        "tagRefs": [
            "Entity/地点/住宿/住宿业态/农家乐",
            "Entity/地点/住宿/档次等级/经济型",
            "Entity/地点/住宿/功能定位/亲子友好住宿",
            "Entity/地点/住宿/设施服务/免费停车",
            "Entity/地点/住宿/设施服务/厨房厨具",
        ],
        "sourceRefs": ["https://map.baidu.com/poi/彭州宝山村"],
        "desc": "彭州宝山村太阳湾区域的典型川西农家乐集群，提供柴火鸡、棋牌、垂钓与果蔬采摘体验，是成都近郊周末短途首选。",
    },
    {
        "name": "成都蜂巢酒店",
        "labelEn": "Chengdu Beehive Capsule Hotel",
        "geo": "Topic/地理/行政区/中国/四川省/成都市",
        "tagRefs": [
            "Entity/地点/住宿/住宿业态/胶囊旅馆",
            "Entity/地点/住宿/档次等级/经济型",
            "Entity/地点/住宿/功能定位/机场高铁住宿",
        ],
        "sourceRefs": ["https://www.trip.com/hotels/chengdu-hotel-detail-46529760/"],
        "desc": "成都火车南站附近的太空舱式胶囊旅馆，单人舱位配独立电视与USB充电，适合转机转车旅客短暂休息。",
    },
    {
        "name": "理塘仁康古屋",
        "labelEn": "Litang Renkang Ancient House",
        "geo": "Topic/地理/行政区/中国/四川省/甘孜州",
        "tagRefs": [
            "Entity/地点/住宿/住宿业态/客栈",
            "Entity/地点/住宿/档次等级/舒适型",
            "Entity/地点/住宿/房源形态/藏式民居",
        ],
        "sourceRefs": ["https://baike.baidu.com/item/仁康古屋"],
        "desc": "理塘古城内的七世达赖仓央嘉措故居改建客栈，是川藏线自驾客的热门打卡住宿点，海拔4014米，全国最高县城标志建筑之一。",
    },
]


POSTS = [
    {
        "angle": "探店",
        "title": "成都博舍酒店探店记",
        "entityRef": "地点/住宿/成都博舍酒店",
        "tagRefs": [
            "Topic/旅行/住宿/酒店体验",
            "Topic/旅行/旅行主题/城市漫步",
            "Format/内容角度/探店",
            "Entity/地点/住宿/住宿业态/酒店",
            "Entity/地点/住宿/功能定位/设计精品住宿",
        ],
    },
    {
        "angle": "探店",
        "title": "青城山六善酒店度假体验",
        "entityRef": "地点/住宿/青城山六善酒店",
        "tagRefs": [
            "Topic/旅行/住宿/度假住宿",
            "Topic/旅行/旅行主题/乡村田园",
            "Format/内容角度/探店",
            "Entity/地点/住宿/住宿业态/度假村",
            "Entity/地点/住宿/功能定位/度假住宿",
        ],
    },
    {
        "angle": "攻略",
        "title": "川西自驾住宿全攻略",
        "entityRef": "地点/住宿/丹巴甲居藏寨民宿",
        "tagRefs": [
            "Topic/旅行/住宿/川西住宿",
            "Topic/旅行/住宿/高原住宿",
            "Topic/旅行/出行方式/自驾",
            "Format/内容角度/攻略",
            "Entity/地点/住宿/住宿业态/民宿",
        ],
    },
    {
        "angle": "攻略",
        "title": "成都出差住宿指南",
        "entityRef": "地点/住宿/成都香格里拉大酒店",
        "tagRefs": [
            "Topic/旅行/住宿/出差住宿",
            "Topic/旅行/住宿/商旅住宿",
            "Format/内容角度/攻略",
            "Entity/地点/住宿/住宿业态/酒店",
            "Entity/地点/住宿/功能定位/商务住宿",
        ],
    },
    {
        "angle": "体验",
        "title": "峨眉山温泉亲子度假三日记",
        "entityRef": "地点/住宿/峨眉山蓝光己庄温泉度假村",
        "tagRefs": [
            "Topic/旅行/住宿/温泉住宿",
            "Topic/旅行/住宿/亲子住宿",
            "Topic/旅行/旅行时长/3-5日中线",
            "Format/内容角度/体验",
            "Entity/地点/住宿/住宿业态/度假村",
            "Entity/地点/住宿/功能定位/亲子友好住宿",
        ],
    },
    {
        "angle": "测评",
        "title": "成都五星酒店横评",
        "entityRef": "地点/住宿/成都瑞吉酒店",
        "tagRefs": [
            "Topic/旅行/住宿/酒店体验",
            "Format/内容角度/测评",
            "Entity/地点/住宿/住宿业态/酒店",
            "Entity/地点/住宿/档次等级/豪华型",
        ],
    },
    {
        "angle": "避雷",
        "title": "稻城亚丁住宿避雷指南",
        "entityRef": "地点/住宿/稻城亚丁日松贡布酒店",
        "tagRefs": [
            "Topic/旅行/住宿/住宿避雷",
            "Topic/旅行/住宿/高原住宿",
            "Format/内容角度/避雷",
            "Entity/地点/住宿/住宿业态/酒店",
        ],
    },
    {
        "angle": "体验",
        "title": "成都懒骨头青旅社交体验",
        "entityRef": "地点/住宿/成都懒骨头青年旅舍",
        "tagRefs": [
            "Topic/旅行/住宿/青旅住宿",
            "Topic/旅行/旅行主题/城市漫步",
            "Format/内容角度/体验",
            "Entity/地点/住宿/住宿业态/青年旅舍",
            "Entity/地点/住宿/档次等级/经济型",
        ],
    },
    {
        "angle": "体验",
        "title": "阆中古城花间堂住宿体验",
        "entityRef": "地点/住宿/阆中花间堂阆苑",
        "tagRefs": [
            "Topic/旅行/住宿/民宿体验",
            "Topic/旅行/住宿/特色住宿",
            "Format/内容角度/体验",
            "Entity/地点/住宿/住宿业态/客栈",
            "Entity/地点/住宿/房源形态/庭院客栈",
        ],
    },
    {
        "angle": "攻略",
        "title": "彭州宝山村亲子农家乐周末指南",
        "entityRef": "地点/住宿/彭州宝山村太阳湾农家乐",
        "tagRefs": [
            "Topic/旅行/住宿/住宿攻略",
            "Topic/旅行/旅行时长/周末短途",
            "Format/内容角度/攻略",
            "Entity/地点/住宿/住宿业态/农家乐",
            "Entity/地点/住宿/功能定位/亲子友好住宿",
        ],
    },
]


def gen_entity(e: dict):
    edir = ENTITIES_ROOT / e["name"]
    entity_json = {
        "label": e["name"],
        "labelEn": e["labelEn"],
        "description": e["desc"],
        "geoTagRef": e["geo"],
        "tagRefs": e["tagRefs"],
        "sourceRefs": e["sourceRefs"],
        "createdAt": NOW_ISO,
        "updatedAt": NOW_ISO,
    }
    write_json(edir / "_entity.json", entity_json)

    manifest_json = {
        "tagRefs": e["tagRefs"],
        "entityRefs": [],
        "sourceRefs": e["sourceRefs"],
        "createdAt": NOW_ISO,
        "updatedAt": NOW_ISO,
    }
    write_json(edir / "manifest.json", manifest_json)

    page_md = f"""# {e["name"]}

> {e["desc"]}

## 基本信息

| 项目 | 信息 |
| --- | --- |
| 英文名 | {e["labelEn"]} |
| 行政区 | [{e["geo"].split("/")[-1]}](/tag/{e["geo"]}) |
| 来源 | {e["sourceRefs"][0]} |

## 标签

{chr(10).join(f'- [{t.split("/")[-1]}](/tag/{t})' for t in e["tagRefs"])}

## 简介

{e["desc"]}

封面图：asset://images/地点/住宿/{e["name"]}/cover.jpg
"""
    write_text(edir / "page.md", page_md)


def gen_post(p: dict):
    pdir = POSTS_ROOT / p["angle"] / p["title"] / "1"

    manifest_json = {
        "contentType": "article",
        "entityRefs": [p["entityRef"]],
        "tagRefs": p["tagRefs"],
        "createdAt": NOW_ISO,
        "updatedAt": NOW_ISO,
    }
    write_json(pdir / "manifest.json", manifest_json)

    article_md = f"""# {p["title"]}

> 本文围绕 [{p["entityRef"].split("/")[-1]}](/entity/{p["entityRef"]}) 展开。

## 内容概述

本篇内容属于 [{p["angle"]}](/tag/Format/内容角度/{p["angle"]}) 视角，关联实体 [{p["entityRef"].split("/")[-1]}](/entity/{p["entityRef"]})。

相关标签：
{chr(10).join(f'- [{t.split("/")[-1]}](/tag/{t})' for t in p["tagRefs"])}

---

（正文占位：实际内容由 Agent 根据 SOP 模板生成，本文件为结构验证用数据。）

封面图：asset://images/posts/{p["title"]}/cover.jpg
"""
    write_text(pdir / "article.md", article_md)


def main():
    # Remove old generic entity
    old = ENTITIES_ROOT / "峨眉山温泉度假酒店"
    if old.exists():
        import shutil
        shutil.rmtree(old)
        print(f"  removed old: {old.name}")

    print(f"生成 {len(ENTITIES)} 个住宿实体...")
    for e in ENTITIES:
        gen_entity(e)
        print(f"  ✓ {e['name']}")

    print(f"\n生成 {len(POSTS)} 篇住宿 posts...")
    for p in POSTS:
        gen_post(p)
        print(f"  ✓ {p['title']}")

    print(f"\n完成！实体 {len(ENTITIES)} 个，posts {len(POSTS)} 篇。")


if __name__ == "__main__":
    main()
