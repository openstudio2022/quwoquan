"""生成事件话题分类到 Topic/事件话题/

原则：
- 只生成稳定的话题类型骨架，不写具体赛事/活动实例
- 不写生命周期字段（热度/startDate/endDate）
- 时效性热点由 tag_runtime/topic_hotness.ndjson 在运行时管理
- 季节节日已统一归入 Topic/时间/，此处不重复

分类：社会热点 / 赛事话题 / 文娱话题 / 地区话题

用法:
  python3 bootstrap_event_topics.py          # 生成（幂等）
  python3 bootstrap_event_topics.py --dry-run
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common.paths import PUBLISH_ROOT, NOW_ISO

TAGS_ROOT = PUBLISH_ROOT / "v1" / "tags" / "Topic" / "事件话题"

DRY_RUN = False
created = 0


def tag(rel_path: str, label: str, label_en: str, desc: str,
        aliases: list[str] | None = None):
    global created
    p = TAGS_ROOT / rel_path / "_definition.json"
    if p.exists():
        return
    data: dict = {
        "label": label, "labelEn": label_en,
        "description": desc,
        "createdAt": NOW_ISO, "updatedAt": NOW_ISO,
    }
    if aliases:
        data["aliases"] = aliases
    if not DRY_RUN:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    created += 1


def tags_list(prefix: str, items: list):
    for item in items:
        cn, en, desc = item[0], item[1], item[2]
        aliases = item[3] if len(item) > 3 else None
        tag(f"{prefix}/{cn}", cn, en, desc, aliases)


def gen():
    # ── 社会热点 ──────────────────────────────────────────
    tag("社会热点", "社会热点", "Social Trending", "时效性社会话题热点分类")
    tags_list("社会热点", [
        ("网络热梗", "Internet Memes", "网络流行语与表情包话题"),
        ("社会事件", "Social Events", "引发公众关注的重大公共事件"),
        ("消费热点", "Consumer Hotspot", "消费品与消费话题热点"),
        ("教育热点", "Education Hotspot", "教育改革与政策热点"),
        ("就业话题", "Employment Topics", "求职就业市场话题"),
        ("健康热点", "Health Hotspot", "公共卫生与健康热点"),
        ("环境话题", "Environmental Topics", "环保与气候变化话题"),
        ("科技热点", "Tech Hotspot", "科技领域突破性进展话题"),
        ("经济热点", "Economic Hotspot", "宏观经济与市场波动话题"),
        ("政策热点", "Policy Hotspot", "重要政策法规动态话题"),
    ])

    # ── 赛事话题（F-11：类型骨架，无具体赛事实例）──────────
    tag("赛事话题", "赛事话题", "Sports & Event Topics", "体育赛事与大型活动的话题类型分类")
    tags_list("赛事话题", [
        ("综合运动会", "Multi-sport Games", "奥运会/亚运会/全运会等综合性运动会话题"),
        ("职业联赛", "Professional League", "足球/篮球/网球等职业联赛话题"),
        ("马拉松赛事", "Marathon Events", "各地马拉松长跑赛事话题"),
        ("电竞赛事", "Esports Events", "电子竞技锦标赛话题"),
        ("文化节庆", "Cultural Festival", "音乐节/电影节/艺术展等文化节庆话题"),
        ("商业展会", "Trade Exhibition", "车展/科技展/博览会等行业展会话题"),
        ("学术论坛", "Academic Forum", "高峰论坛/学术研讨会话题"),
    ])

    # ── 文娱话题 ──────────────────────────────────────────
    tag("文娱话题", "文娱话题", "Entertainment Topics", "影视娱乐热点话题")
    tags_list("文娱话题", [
        ("影视新作", "New Release", "新上映电影电视剧话题"),
        ("明星动态", "Celebrity News", "艺人明星相关热点话题"),
        ("综艺话题", "Variety Show Topics", "热播综艺节目话题"),
        ("打榜应援", "Fan Support", "粉丝偶像应援话题"),
        ("书影音热搜", "Media Hot Search", "图书影视音乐热搜话题"),
        ("游戏话题", "Game Topics", "游戏新作与版本更新话题"),
    ])

    # ── 地区话题 ──────────────────────────────────────────
    tag("地区话题", "地区话题", "Regional Topics", "特定地区热点话题")
    tags_list("地区话题", [
        ("四川热点", "Sichuan Hotspot", "四川本地热点话题"),
        ("成都话题", "Chengdu Topics", "成都城市话题"),
        ("北京话题", "Beijing Topics", "首都城市话题"),
        ("上海话题", "Shanghai Topics", "上海城市话题"),
        ("港澳台话题", "HK/Macao/TW Topics", "港澳台地区热点话题"),
    ])


def main():
    parser = argparse.ArgumentParser(description="生成事件话题分类骨架")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    global DRY_RUN
    DRY_RUN = args.dry_run

    gen()

    print(f"\n事件话题分类生成完成：{created} 个标签")
    if DRY_RUN:
        print("[dry-run 模式，未写盘]")


if __name__ == "__main__":
    main()
