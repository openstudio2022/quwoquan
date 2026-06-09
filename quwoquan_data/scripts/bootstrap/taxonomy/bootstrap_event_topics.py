"""生成事件与话题分类骨架到 Topic/事件 / Topic/话题

原则：
- 只生成稳定的话题类型骨架，不写具体赛事/活动实例
- 不写生命周期字段（热度/startDate/endDate）
- 时效性热点、热搜、新闻事件实例见 `docs/dynamic_topic_event_model.md`
  与 `tag_runtime/` 运行时层，不在静态标签树里扩展新叶
- 季节节日已统一归入 Topic/时间/，此处不重复

分类：社会热点 / 赛事话题 / 文娱话题 / 地区话题

用法:
  python3 scripts/bootstrap/taxonomy/bootstrap_event_topics.py          # 生成（幂等）
  python3 scripts/bootstrap/taxonomy/bootstrap_event_topics.py --dry-run
"""

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common.paths import PUBLISH_ROOT, NOW_ISO

EVENT_CANONICAL_ROOT = PUBLISH_ROOT / "tags" / "Topic" / "事件"
TOPIC_CANONICAL_ROOT = PUBLISH_ROOT / "tags" / "Topic" / "话题"

DRY_RUN = False
created = 0


def tag_at(root: Path, rel_path: str, label: str, label_en: str, desc: str,
           aliases: list[str] | None = None):
    global created
    p = root / rel_path / "_definition.json"
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


def tag(rel_path: str, label: str, label_en: str, desc: str,
        aliases: list[str] | None = None):
    tag_at(TAGS_ROOT, rel_path, label, label_en, desc, aliases)


def tags_list_at(root: Path, prefix: str, items: list):
    for item in items:
        cn, en, desc = item[0], item[1], item[2]
        aliases = item[3] if len(item) > 3 else None
        rel_path = f"{prefix}/{cn}" if prefix else cn
        tag_at(root, rel_path, cn, en, desc, aliases)


def tags_list(prefix: str, items: list):
    tags_list_at(TAGS_ROOT, prefix, items)


def gen():
    # ── 新 canonical 根：事件 / 话题 ───────────────────────────
    tag_at(EVENT_CANONICAL_ROOT, "", "事件", "Event", "可指称事实事件")
    tags_list_at(EVENT_CANONICAL_ROOT, "", [
        ("新闻事件", "News Event", "新闻报道中的可指称事实事件"),
        ("史实事件", "Historical Event", "已发生且可考证的史实事实事件"),
        ("社会事件", "Social Event", "社会公共领域中的事实事件"),
        ("赛事事件", "Competition Event", "体育与大型赛事事实事件"),
        ("地区事件", "Regional Event", "区域性事实事件"),
        ("政策事件", "Policy Event", "重要政策发布与施行事件"),
    ])

    tag_at(TOPIC_CANONICAL_ROOT, "", "话题", "Topic", "稳定议题语义")
    tags_list_at(TOPIC_CANONICAL_ROOT, "", [
        ("社会议题", "Social Issue", "公共讨论中的稳定社会议题"),
        ("公共议题", "Public Issue", "公共政策、治理与社会议题"),
        ("文娱话题", "Entertainment Topic", "影视、音乐、综艺等文娱议题"),
        ("地区话题", "Regional Topic", "城市与地区讨论议题"),
        ("科技话题", "Tech Topic", "科技趋势与技术讨论议题"),
        ("教育议题", "Education Topic", "教育政策与学习讨论议题"),
    ])


def main():
    parser = argparse.ArgumentParser(description="生成事件 / 话题分类骨架")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    global DRY_RUN
    DRY_RUN = args.dry_run

    gen()

    print(f"\n事件 / 话题分类生成完成：{created} 个标签")
    if DRY_RUN:
        print("[dry-run 模式，未写盘]")


if __name__ == "__main__":
    main()
