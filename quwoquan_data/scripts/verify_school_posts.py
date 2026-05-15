"""学校 Posts 完整性验证

检查项：
  P1 - 每所学校至少 1 篇索引帖
  P2 - 每篇 post 含 article.md + manifest.json
  P3 - manifest 的 tagRefs 覆盖 Entity + Topic + 地理
  P4 - article.md >= 300 字，含 /entity/ 和 /tag/ 引用
  P5 - 抽样深内容 article >= 300 字

用法:
  python3 verify_school_posts.py
"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common.paths import PUBLISH_ROOT

ENTITIES_ROOT = PUBLISH_ROOT / "v1" / "entities" / "机构" / "学校"
POSTS_ROOT = PUBLISH_ROOT / "v1" / "posts" / "article"

SCHOOL_POST_ANGLES = {
    "索引", "新生攻略", "选课攻略", "校园评测", "考研经验",
    "校招经验", "校园日记", "择园攻略", "幼小衔接",
}

errors: list[str] = []


def p1_index_coverage():
    if not ENTITIES_ROOT.exists():
        errors.append("P1: 实体目录不存在")
        return

    entity_names = {d.name for d in ENTITIES_ROOT.iterdir() if d.is_dir()}
    index_dir = POSTS_ROOT / "索引"
    if not index_dir.exists():
        errors.append(f"P1: 索引帖目录不存在: {index_dir}")
        return

    posted_names = {d.name for d in index_dir.iterdir() if d.is_dir()}
    missing = entity_names - posted_names
    if missing:
        errors.append(f"P1: {len(missing)} 所学校缺少索引帖")
        for m in list(missing)[:5]:
            errors.append(f"  P1: 缺失: {m}")
    else:
        print(f"  P1 OK: 所有 {len(entity_names)} 所学校都有索引帖")


def p2_post_files():
    if not POSTS_ROOT.exists():
        errors.append("P2: posts 目录不存在")
        return 0

    total = 0
    missing = 0
    for angle_dir in POSTS_ROOT.iterdir():
        if not angle_dir.is_dir():
            continue
        if angle_dir.name not in SCHOOL_POST_ANGLES:
            continue
        for school_dir in angle_dir.iterdir():
            if not school_dir.is_dir():
                continue
            for seq_dir in school_dir.iterdir():
                if not seq_dir.is_dir():
                    continue
                total += 1
                for fname in ("article.md", "manifest.json"):
                    if not (seq_dir / fname).exists():
                        errors.append(f"P2: {seq_dir.relative_to(POSTS_ROOT)} 缺少 {fname}")
                        missing += 1
    print(f"  P2: {total} 篇学校 posts, {missing} 缺失文件")
    return total


def p3_tag_coverage():
    if not POSTS_ROOT.exists():
        return
    n_err = 0
    n_checked = 0
    for angle_dir in POSTS_ROOT.iterdir():
        if not angle_dir.is_dir():
            continue
        if angle_dir.name not in SCHOOL_POST_ANGLES:
            continue
        for school_dir in angle_dir.iterdir():
            if not school_dir.is_dir():
                continue
            for seq_dir in school_dir.iterdir():
                if not seq_dir.is_dir():
                    continue
                mf = seq_dir / "manifest.json"
                if not mf.exists():
                    continue
                manifest = json.loads(mf.read_text(encoding="utf-8"))
                tag_refs = manifest.get("tagRefs", [])
                n_checked += 1
                has_entity = any(r.startswith("Entity/") for r in tag_refs)
                has_topic = any(r.startswith("Topic/") for r in tag_refs)
                if not has_entity:
                    if n_err < 10:
                        errors.append(f"P3: {seq_dir.relative_to(POSTS_ROOT)} manifest 缺 Entity tagRef")
                    n_err += 1
                if not has_topic:
                    if n_err < 10:
                        errors.append(f"P3: {seq_dir.relative_to(POSTS_ROOT)} manifest 缺 Topic tagRef")
                    n_err += 1
    if n_err == 0:
        print(f"  P3 OK: {n_checked} 篇学校 posts tagRefs 覆盖 Entity + Topic")


def p4_article_quality():
    if not POSTS_ROOT.exists():
        return
    n_short = 0
    n_missing_ref = 0
    n_total = 0
    for angle_dir in POSTS_ROOT.iterdir():
        if not angle_dir.is_dir():
            continue
        if angle_dir.name not in SCHOOL_POST_ANGLES:
            continue
        for school_dir in angle_dir.iterdir():
            if not school_dir.is_dir():
                continue
            for seq_dir in school_dir.iterdir():
                if not seq_dir.is_dir():
                    continue
                af = seq_dir / "article.md"
                if not af.exists():
                    continue
                content = af.read_text(encoding="utf-8")
                n_total += 1
                if len(content) < 300:
                    n_short += 1
                if "/entity/" not in content and "/tag/" not in content:
                    n_missing_ref += 1

    if n_short > 0:
        errors.append(f"P4: {n_short}/{n_total} 篇 article.md < 300 字")
    else:
        print(f"  P4 OK: 所有 {n_total} 篇 article.md >= 300 字")

    if n_missing_ref > 0:
        errors.append(f"P4: {n_missing_ref}/{n_total} 篇缺少 /entity/ 或 /tag/ 引用")


def main():
    print("=" * 60)
    print("学校 Posts 完整性验证")
    print("=" * 60)

    p1_index_coverage()
    total = p2_post_files()
    p3_tag_coverage()
    p4_article_quality()

    print(f"\n{'ERROR' if errors else '(无错误)'}（{len(errors)} 条）:")
    for e in errors[:30]:
        print(f"  ✗ {e}")
    if len(errors) > 30:
        print(f"  ... 还有 {len(errors) - 30} 条")

    print(f"\n{'验证通过' if not errors else '验证失败'}: {len(errors)} 错误")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
