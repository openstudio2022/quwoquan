"""生成完整标签体系到 control_plane/governance/taxonomy/

四大分组：Topic / Audience / Format / Entity
- Topic: 主题垂类与场景/事件/话题/时间/地理（行政区由 bootstrap_admin_regions.py 生成；垂类无 Topic/主题 中间层）
- Audience: 用户/创作者/圈子（商品画像并入 Entity/商品）
- Format: 内容载体/内容角度/表现手法/视觉风格/互动玩法/商业形式
- Entity: 9 领域类型骨架（不实例化具体对象）

原则：
- _definition.json 只含 label/labelEn/aliases/description/sourceRefs/notes/createdAt/updatedAt
- tagId 由目录路径推导，不写入文件
- 不含 appliesTo/leafConstraint/status/lifecycle/weight/deprecatedTo/startDate/endDate

用法:
  python3 quwoquan_data/scripts/cli.py governance taxonomy bootstrap-tags
  python3 quwoquan_data/scripts/cli.py governance taxonomy bootstrap-tags --dry-run
  python3 quwoquan_data/scripts/cli.py governance taxonomy bootstrap-tags --group Topic
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
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core.paths import CONTROL_PLANE_TAXONOMY_ROOT, NOW_ISO

TAGS_ROOT = CONTROL_PLANE_TAXONOMY_ROOT

DRY_RUN = False
_stats: dict[str, int] = {}


def write_json(path: Path, data: dict):
    if DRY_RUN:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _group_file(group: str) -> Path:
    return TAGS_ROOT / group / "_group.json"


def _dim_file(path: str) -> Path:
    return TAGS_ROOT / path / "_dimension.json"


def _def_file(path: str) -> Path:
    return TAGS_ROOT / path / "_definition.json"


def group(group_id: str, label: str, label_en: str, semantics: str, dimensions: list[str]):
    write_json(_group_file(group_id), {
        "id": group_id, "label": label, "labelEn": label_en,
        "semantics": semantics,
        "expectedDimensions": dimensions,
        "createdAt": NOW_ISO, "updatedAt": NOW_ISO,
    })


def dim(path: str, label: str, label_en: str, desc: str,
        max_depth: int = 3, expected_size: int = 0,
        path_policy: str = "any-depth", ref_hint: str = ""):
    data = {
        "label": label, "labelEn": label_en,
        "description": desc,
        "maxDepth": max_depth,
        "pathPolicy": path_policy,
        "createdAt": NOW_ISO, "updatedAt": NOW_ISO,
    }
    if expected_size:
        data["expectedSize"] = expected_size
    if ref_hint:
        data["refHint"] = ref_hint
    write_json(_dim_file(path), data)


def tag(path: str, label: str, label_en: str, desc: str,
        aliases: list[str] | None = None):
    group_key = path.split("/")[0]
    _stats[group_key] = _stats.get(group_key, 0) + 1
    data: dict = {
        "label": label, "labelEn": label_en,
        "description": desc,
        "createdAt": NOW_ISO, "updatedAt": NOW_ISO,
    }
    if aliases:
        data["aliases"] = aliases
    write_json(_def_file(path), data)


def tags_list(prefix: str, items: list[tuple]):
    """批量生成叶子标签。items = [(中文名, 英文名, 描述[, aliases])]"""
    for item in items:
        cn, en, desc = item[0], item[1], item[2]
        aliases = item[3] if len(item) > 3 else None
        tag(f"{prefix}/{cn}", cn, en, desc, aliases)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# T O P I C
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from governance.taxonomy.bootstrap_tags_topic import configure_writers as _configure_topic_writers, gen_topic
from governance.taxonomy.bootstrap_tags_audience import configure_writers as _configure_audience_writers, gen_audience
from governance.taxonomy.bootstrap_tags_format import configure_writers as _configure_format_writers, gen_format
from governance.taxonomy.bootstrap_tags_entity import configure_writers as _configure_entity_writers, gen_entity


def configure_taxonomy_section_writers() -> None:
    writers = {"group": group, "dim": dim, "tag": tag, "tags_list": tags_list}
    _configure_topic_writers(**writers)
    _configure_audience_writers(**writers)
    _configure_format_writers(**writers)
    _configure_entity_writers(**writers)


# 全局 taxonomy 快照
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def write_taxonomy():
    dimensions = []
    for group_id in ["Topic", "Audience", "Format", "Entity"]:
        group_dir = TAGS_ROOT / group_id
        if not group_dir.exists():
            continue
        for dim_path in group_dir.iterdir():
            if not dim_path.is_dir():
                continue
            count = sum(1 for _ in dim_path.rglob("_definition.json"))
            dimensions.append({
                "id": f"{group_id}/{dim_path.name}",
                "group": group_id,
                "label": dim_path.name,
                "count": count,
            })

    total = sum(d["count"] for d in dimensions)
    by_group: dict[str, int] = {}
    for d in dimensions:
        by_group[d["group"]] = by_group.get(d["group"], 0) + d["count"]

    write_json(TAGS_ROOT / "_taxonomy.json", {
        "version": "v4",
        "schemaVersion": "1.0",
        "groups": ["Topic", "Audience", "Format", "Entity"],
        "dimensions": dimensions,
        "totalCount": total,
        "stats": {"byGroup": by_group},
        "generatedAt": NOW_ISO,
    })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# main
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GENERATORS: dict[str, callable] = {
    "Topic": gen_topic,
    "Audience": gen_audience,
    "Format": gen_format,
    "Entity": gen_entity,
}


def main(argv: list[str] | None = None):
    global DRY_RUN

    configure_taxonomy_section_writers()
    parser = argparse.ArgumentParser(description="生成四分组标签体系")
    parser.add_argument("--dry-run", action="store_true", help="仅统计不写盘")
    parser.add_argument("--group", choices=["Topic", "Audience", "Format", "Entity"],
                        help="只生成指定分组")
    args = parser.parse_args(argv)
    DRY_RUN = args.dry_run

    if args.group:
        GENERATORS[args.group]()
    else:
        for g, fn in GENERATORS.items():
            print(f"  生成 {g} ...")
            fn()

    if not DRY_RUN:
        write_taxonomy()

    print("\n=== bootstrap_tags 统计 ===")
    total = 0
    for k, v in sorted(_stats.items()):
        print(f"  {k}: {v}")
        total += v
    print(f"  合计: {total}")
    if DRY_RUN:
        print("  [dry-run 模式，未写盘]")
