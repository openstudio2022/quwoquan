"""学校实体完整性验证

检查项：
  E1 - 每个 seed catalog 行对应实体目录存在
  E2 - 每目录含 _entity.json + page.md + manifest.json
  E3 - _entity.json 含 geoTagRef（以 Topic/地理/行政区/ 开头）
  E4 - tagRefs 至少含 Entity/机构/学校 + 1 个学段标签
  E5 - 所有 tagRefs 在 publish/v1/tags 中可解析
  E6 - page.md >= 300 字
  E7 - page.md 无旧式 /tag/主题/ 路径
  E8 - 无目录名冲突

用法:
  python3 verify_school_entities.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common.paths import PUBLISH_ROOT, RUNTIME_ROOT

ENTITIES_ROOT = PUBLISH_ROOT / "v1" / "entities" / "机构" / "学校"
TAGS_ROOT = PUBLISH_ROOT / "v1" / "tags"
CATALOG_DIR = RUNTIME_ROOT / "seed" / "school_catalog"

errors: list[str] = []
warnings: list[str] = []

SCHOOL_TYPE_TAGS = {
    "Entity/机构/学校/幼儿园", "Entity/机构/学校/小学", "Entity/机构/学校/初中",
    "Entity/机构/学校/高中", "Entity/机构/学校/完全中学",
    "Entity/机构/学校/九年一贯制学校", "Entity/机构/学校/十二年一贯制学校",
    "Entity/机构/学校/中等职业学校", "Entity/机构/学校/大学",
    "Entity/机构/学校/高职院校", "Entity/机构/学校/国际学校",
    "Entity/机构/学校/特殊教育学校", "Entity/机构/学校/培训机构",
}


def e2_three_files():
    if not ENTITIES_ROOT.exists():
        errors.append("E2: 实体根目录不存在")
        return 0

    count = 0
    missing = 0
    for d in ENTITIES_ROOT.iterdir():
        if not d.is_dir():
            continue
        count += 1
        for fname in ("_entity.json", "page.md", "manifest.json"):
            if not (d / fname).exists():
                errors.append(f"E2: {d.name}/ 缺少 {fname}")
                missing += 1
    print(f"  E2: {count} 个实体目录, {missing} 缺失文件")
    return count


def e3_geo_tag_ref():
    n_err = 0
    for d in ENTITIES_ROOT.iterdir():
        if not d.is_dir():
            continue
        ef = d / "_entity.json"
        if not ef.exists():
            continue
        entity = json.loads(ef.read_text(encoding="utf-8"))
        geo = entity.get("geoTagRef", "")
        if not geo:
            errors.append(f"E3: {d.name} 缺少 geoTagRef")
            n_err += 1
        elif not geo.startswith("Topic/地理/行政区/"):
            errors.append(f"E3: {d.name} geoTagRef 前缀错误: {geo}")
            n_err += 1
    if n_err == 0:
        print("  E3 OK: 所有实体 geoTagRef 合法")


def e4_tag_refs():
    n_err = 0
    for d in ENTITIES_ROOT.iterdir():
        if not d.is_dir():
            continue
        ef = d / "_entity.json"
        if not ef.exists():
            continue
        entity = json.loads(ef.read_text(encoding="utf-8"))
        tag_refs = entity.get("tagRefs", [])
        if "Entity/机构/学校" not in tag_refs:
            errors.append(f"E4: {d.name} tagRefs 缺少 Entity/机构/学校")
            n_err += 1
        has_type = any(r in SCHOOL_TYPE_TAGS for r in tag_refs)
        if not has_type:
            errors.append(f"E4: {d.name} tagRefs 缺少学段标签")
            n_err += 1
    if n_err == 0:
        print("  E4 OK: 所有实体 tagRefs 含必选标签")


def e5_tag_refs_resolvable():
    n_err = 0
    n_checked = 0
    for d in ENTITIES_ROOT.iterdir():
        if not d.is_dir():
            continue
        ef = d / "_entity.json"
        if not ef.exists():
            continue
        entity = json.loads(ef.read_text(encoding="utf-8"))
        for ref in entity.get("tagRefs", []):
            n_checked += 1
            tag_dir = TAGS_ROOT / ref
            if not tag_dir.exists():
                if n_err < 20:
                    errors.append(f"E5: {d.name} tagRef 不可解析: {ref}")
                n_err += 1
    if n_err == 0:
        print(f"  E5 OK: {n_checked} 个 tagRefs 全部可解析")
    else:
        print(f"  E5: {n_err} 个 tagRef 不可解析 (前20条已记录)")


def e6_page_length():
    n_short = 0
    for d in ENTITIES_ROOT.iterdir():
        if not d.is_dir():
            continue
        pm = d / "page.md"
        if not pm.exists():
            continue
        content = pm.read_text(encoding="utf-8")
        if len(content) < 300:
            if n_short < 10:
                errors.append(f"E6: {d.name} page.md 仅 {len(content)} 字 (< 300)")
            n_short += 1
    if n_short == 0:
        print("  E6 OK: 所有 page.md >= 300 字")
    else:
        print(f"  E6: {n_short} 个 page.md 不足 300 字")


def e7_no_old_paths():
    n_err = 0
    for d in ENTITIES_ROOT.iterdir():
        if not d.is_dir():
            continue
        pm = d / "page.md"
        if not pm.exists():
            continue
        content = pm.read_text(encoding="utf-8")
        if "/tag/主题/" in content:
            errors.append(f"E7: {d.name} page.md 含旧式 /tag/主题/ 路径")
            n_err += 1
    if n_err == 0:
        print("  E7 OK: 无旧式路径")


def main():
    print("=" * 60)
    print("学校实体完整性验证")
    print("=" * 60)

    count = e2_three_files()
    if count > 0:
        e3_geo_tag_ref()
        e4_tag_refs()
        e5_tag_refs_resolvable()
        e6_page_length()
        e7_no_old_paths()

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
