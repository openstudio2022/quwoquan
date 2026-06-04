"""校园垂类学校 posts 分层生成能力。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.paths import NOW_ISO, PUBLISH_ROOT  # noqa: E402
from build_publish_lookup_indexes import build_publish_lookup_indexes  # noqa: E402

ENTITIES_ROOT = PUBLISH_ROOT / "entities" / "机构" / "学校"
POSTS_ROOT = PUBLISH_ROOT / "posts" / "article"

KEY_UNIVERSITIES = {"985高校", "211高校", "双一流"}
DEEP_ANGLES_UNIVERSITY_KEY = [
    ("新生攻略", "Format/内容角度/攻略/新生攻略", "Topic/教育成长/校园生活"),
    ("选课攻略", "Format/内容角度/攻略/选课攻略", "Topic/教育成长/学业学术"),
    ("校园评测", "Format/内容角度/测评/校园评测", "Topic/教育成长/校园生活"),
    ("考研经验", "Format/内容角度/经验分享/考研经验", "Topic/教育成长/升学深造"),
    ("校招经验", "Format/内容角度/经验分享/校招经验", "Topic/教育成长/实习求职"),
    ("校园日记", "Format/内容角度/日记/校园日记", "Topic/教育成长/校园生活"),
]
DEEP_ANGLES_UNIVERSITY_REGULAR = [
    ("新生攻略", "Format/内容角度/攻略/新生攻略", "Topic/教育成长/校园生活"),
    ("校园评测", "Format/内容角度/测评/校园评测", "Topic/教育成长/校园生活"),
]
DEEP_ANGLES_SCHOOL = [
    ("新生攻略", "Format/内容角度/攻略/新生攻略", "Topic/教育成长/基础教育"),
    ("校园评测", "Format/内容角度/测评/校园评测", "Topic/教育成长/基础教育"),
]
DEEP_ANGLES_KINDERGARTEN = [
    ("择园攻略", "Format/内容角度/攻略/择园攻略", "Topic/亲子育儿/幼儿园选择"),
    ("幼小衔接", "Format/内容角度/攻略/幼小衔接", "Topic/亲子育儿/幼小衔接"),
]


def is_key_university(entity: dict) -> bool:
    tag_refs = entity.get("tagRefs", [])
    return any(f"Entity/机构/学校/{k}" in tag_refs for k in KEY_UNIVERSITIES)


def get_school_type(entity: dict) -> str:
    tag_refs = entity.get("tagRefs", [])
    for ref in tag_refs:
        if ref == "Entity/机构/学校/大学":
            return "university"
        if ref == "Entity/机构/学校/高职院校":
            return "vocational"
        if ref in ("Entity/机构/学校/高中", "Entity/机构/学校/初中", "Entity/机构/学校/完全中学"):
            return "school"
        if ref == "Entity/机构/学校/幼儿园":
            return "kindergarten"
    return "other"


def make_index_post(name: str, entity: dict) -> tuple[str, dict]:
    tag_refs = entity.get("tagRefs", [])
    geo_ref = entity.get("geoTagRef", "")
    article = "\n".join([
        f"# {name}｜学校概览\n",
        f"> {name}基本信息、位置交通、校园生活与学习交流索引。\n",
        f"实体引用：[/entity/机构/学校/{name}](/entity/机构/学校/{name})\n",
        "## 基本信息\n",
        f"{name}是一所教育机构。当前内容作为校园主页索引，后续应继续接入官网、地图、招生和学生社区事实。\n",
        "## 位置与交通\n",
        "围绕通勤、周边设施、住宿和生活服务建立持续更新的信息入口。\n",
        "## 学习与生活\n",
        "围绕课程、社团、升学、实习就业和校园生活沉淀差异化文章。\n",
        f"封面图：asset://images/posts/{name}_index/cover.jpg\n",
    ])
    manifest = {
        "contentType": "article",
        "entityRefs": [f"/entity/机构/学校/{name}"],
        "tagRefs": list(dict.fromkeys(tag_refs + [geo_ref, "Topic/教育成长"])),
        "createdAt": NOW_ISO,
        "updatedAt": NOW_ISO,
    }
    return article, manifest


def make_deep_post(name: str, entity: dict, angle_name: str, format_ref: str, topic_ref: str) -> tuple[str, dict]:
    tag_refs = entity.get("tagRefs", [])
    geo_ref = entity.get("geoTagRef", "")
    article = "\n".join([
        f"# {name}｜{angle_name}\n",
        f"> {name}{angle_name}内容骨架，用于承载官方事实、学生经验和持续更新的社区信息。\n",
        f"实体引用：[/entity/机构/学校/{name}](/entity/机构/学校/{name})\n",
        "## 事实来源\n",
        "上线前必须补齐学校官网、招生/教务、地图和学生社区等多源证据。\n",
        "## 经验信息\n",
        f"围绕{name}的{angle_name}沉淀可复用经验，并标注信息时效与适用人群。\n",
        "## 待补缺口\n",
        "模板化内容不得直接视为成熟内容，应进入校园垂类质量门抽检和回流重写。\n",
        f"标签引用：[/tag/{format_ref}](/tag/{format_ref})\n",
        f"封面图：asset://images/posts/{name}_{angle_name}/cover.jpg\n",
    ])
    manifest = {
        "contentType": "article",
        "entityRefs": [f"/entity/机构/学校/{name}"],
        "tagRefs": list(dict.fromkeys(tag_refs + [geo_ref, format_ref, topic_ref])),
        "createdAt": NOW_ISO,
        "updatedAt": NOW_ISO,
    }
    return article, manifest


def write_post(name: str, angle_name: str, article: str, manifest: dict, dry_run: bool) -> None:
    post_dir = POSTS_ROOT / angle_name.replace("/", "_") / name.replace("/", "_") / "1"
    if dry_run:
        return
    post_dir.mkdir(parents=True, exist_ok=True)
    (post_dir / "article.md").write_text(article, encoding="utf-8")
    (post_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def deep_angles_for(entity: dict) -> list[tuple[str, str, str]]:
    school_type = get_school_type(entity)
    if school_type == "university" and is_key_university(entity):
        return DEEP_ANGLES_UNIVERSITY_KEY
    if school_type == "university":
        return DEEP_ANGLES_UNIVERSITY_REGULAR
    if school_type == "school" and "Entity/机构/学校/高中" in entity.get("tagRefs", []):
        return DEEP_ANGLES_SCHOOL
    if school_type == "kindergarten" and any("公办" in r for r in entity.get("tagRefs", [])):
        return DEEP_ANGLES_KINDERGARTEN[:1]
    return []


def process_entity(entity_dir: Path, *, dry_run: bool, resume: bool) -> tuple[int, int]:
    entity_file = entity_dir / "_entity.json"
    if not entity_file.exists():
        return 0, 0
    entity = json.loads(entity_file.read_text(encoding="utf-8"))
    name = entity_dir.name
    index_path = POSTS_ROOT / "索引" / name.replace("/", "_") / "1" / "manifest.json"
    if resume and index_path.exists():
        return 0, 0
    article, manifest = make_index_post(name, entity)
    write_post(name, "索引", article, manifest, dry_run)
    index_count, deep_count = 1, 0
    for angle_name, format_ref, topic_ref in deep_angles_for(entity):
        article, manifest = make_deep_post(name, entity, angle_name, format_ref, topic_ref)
        write_post(name, angle_name, article, manifest, dry_run)
        deep_count += 1
    return index_count, deep_count


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="校园垂类学校 Posts 分层生成")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip-reindex", action="store_true")
    args = parser.parse_args(argv)
    if not ENTITIES_ROOT.exists():
        print("ERROR: 实体目录不存在，请先运行 campus bootstrap entities", file=sys.stderr)
        raise SystemExit(1)
    index_posts = 0
    deep_posts = 0
    for entity_dir in sorted(d for d in ENTITIES_ROOT.iterdir() if d.is_dir()):
        i, d = process_entity(entity_dir, dry_run=args.dry_run, resume=args.resume)
        index_posts += i
        deep_posts += d
    print(f"[campus bootstrap posts] index={index_posts} deep={deep_posts} total={index_posts + deep_posts}")
    if not args.dry_run and not args.skip_reindex:
        counts = build_publish_lookup_indexes()
        print(f"[campus bootstrap posts] reindex entities={counts['entities']} posts={counts['posts']}")
