"""校园标签体系专项正交门禁

检查项：
  C1  - Entity/机构/学校/** 叶子数 >= 30
  C2  - Entity/机构/学校/** 无超过 R6 深度约束(4)的路径
  C3  - Entity/机构/学校/** 无具体学校实例名
  C4  - Topic/教育成长 叶子数 >= 40
  C5  - Audience/圈子/校园圈 子标签数 >= 6
  C6  - Audience/用户/教育/教育经历/在读学生 目录不存在
  C7  - Topic/旅行/玩法/校园参观 存在
  C8  - Topic/场景/生活场景/校园场景 存在
  C9  - Topic/亲子育儿/幼儿园选择 存在
  C10 - Format/内容角度/经验分享 子标签数 >= 5

用法:
  python3 verify_campus_taxonomy.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common.paths import PUBLISH_ROOT

TAGS_ROOT = PUBLISH_ROOT / "v1" / "tags"
errors: list[str] = []

SCHOOL_INSTANCE_PATTERN = re.compile(
    r"^(北京|清华|复旦|上海交通|浙江|南京|武汉|中山|华中科技|华东师范|华南理工|"
    r"四川|重庆|天津|吉林|厦门|兰州|山东|东北|西北工业|西南|东南|中南|"
    r"同济|南开|中国人民|中国科学技术|中央民族|对外经济贸易|外交学院|国防科技|解放军|"
    r".{2,20}(大学|学院)$|"
    r".{2,20}(附属中学|附属小学|附中|附小|实验学校|外国语学校)$|"
    r".{2,10}(第.{1,3}中学|第.{1,3}小学|第.{1,3}幼儿园)$)"
)

SCHOOL_TYPE_ALLOWLIST = {
    "幼儿园", "小学", "初中", "高中", "完全中学",
    "九年一贯制学校", "十二年一贯制学校", "中等职业学校",
    "大学", "高职院校", "国际学校", "特殊教育学校", "培训机构",
    "985高校", "211高校", "双一流", "普通本科", "独立学院",
    "民办本科", "中外合作办学", "军事院校",
    "综合类", "理工类", "师范类", "农林类", "医药类",
    "财经类", "政法类", "体育类", "艺术类", "军事类",
    "民族类", "语言类", "公办", "民办",
}


def count_leaves(root: Path) -> int:
    return sum(1 for f in root.rglob("_definition.json")
               if f.parent != root)


def c1_school_leaf_count():
    school_root = TAGS_ROOT / "Entity" / "机构" / "学校"
    if not school_root.exists():
        errors.append("C1: Entity/机构/学校/ 目录不存在")
        return
    n = count_leaves(school_root)
    if n < 30:
        errors.append(f"C1: Entity/机构/学校 叶子数 {n} < 30")
    else:
        print(f"  C1 OK: Entity/机构/学校 叶子数 = {n}")


def c2_school_depth():
    school_root = TAGS_ROOT / "Entity" / "机构" / "学校"
    if not school_root.exists():
        return
    for f in school_root.rglob("_definition.json"):
        rel = f.parent.relative_to(TAGS_ROOT)
        depth = len(rel.parts)
        if depth > 4:
            errors.append(f"C2: Entity 深度超限 ({depth}>4): {rel}")


def c3_no_school_instances():
    school_root = TAGS_ROOT / "Entity" / "机构" / "学校"
    if not school_root.exists():
        return
    for d in school_root.iterdir():
        if not d.is_dir() or d.name.startswith("_"):
            continue
        if d.name in SCHOOL_TYPE_ALLOWLIST:
            continue
        if SCHOOL_INSTANCE_PATTERN.match(d.name):
            errors.append(f"C3: 疑似学校实例名进入标签树: Entity/机构/学校/{d.name}")


def c4_education_leaf_count():
    edu_root = TAGS_ROOT / "Topic" / "教育成长"
    if not edu_root.exists():
        errors.append("C4: Topic/教育成长/ 目录不存在")
        return
    n = count_leaves(edu_root)
    if n < 40:
        errors.append(f"C4: Topic/教育成长 叶子数 {n} < 40")
    else:
        print(f"  C4 OK: Topic/教育成长 叶子数 = {n}")


def c5_campus_circle_count():
    cc_root = TAGS_ROOT / "Audience" / "圈子" / "校园圈"
    if not cc_root.exists():
        errors.append("C5: Audience/圈子/校园圈/ 目录不存在")
        return
    n = sum(1 for d in cc_root.iterdir()
            if d.is_dir() and (d / "_definition.json").exists())
    if n < 6:
        errors.append(f"C5: Audience/圈子/校园圈 子标签数 {n} < 6")
    else:
        print(f"  C5 OK: Audience/圈子/校园圈 子标签数 = {n}")


def c6_no_current_student():
    path = TAGS_ROOT / "Audience" / "用户" / "教育" / "教育经历" / "在读学生"
    if path.exists():
        errors.append("C6: Audience/用户/教育/教育经历/在读学生 仍然存在，应已删除")
    else:
        print("  C6 OK: 在读学生 已删除")


def c7_campus_tour():
    path = TAGS_ROOT / "Topic" / "旅行" / "玩法" / "校园参观" / "_definition.json"
    if not path.exists():
        errors.append("C7: Topic/旅行/玩法/校园参观 不存在")
    else:
        print("  C7 OK: Topic/旅行/玩法/校园参观 存在")


def c8_campus_scene():
    path = TAGS_ROOT / "Topic" / "场景" / "生活场景" / "校园场景" / "_definition.json"
    if not path.exists():
        errors.append("C8: Topic/场景/生活场景/校园场景 不存在")
    else:
        print("  C8 OK: Topic/场景/生活场景/校园场景 存在")


def c9_kindergarten_selection():
    path = TAGS_ROOT / "Topic" / "亲子育儿" / "幼儿园选择" / "_definition.json"
    if not path.exists():
        errors.append("C9: Topic/亲子育儿/幼儿园选择 不存在")
    else:
        print("  C9 OK: Topic/亲子育儿/幼儿园选择 存在")


def c10_experience_sharing():
    es_root = TAGS_ROOT / "Format" / "内容角度" / "经验分享"
    if not es_root.exists():
        errors.append("C10: Format/内容角度/经验分享/ 目录不存在")
        return
    n = sum(1 for d in es_root.iterdir()
            if d.is_dir() and (d / "_definition.json").exists())
    if n < 5:
        errors.append(f"C10: Format/内容角度/经验分享 子标签数 {n} < 5")
    else:
        print(f"  C10 OK: Format/内容角度/经验分享 子标签数 = {n}")


def main():
    print("=" * 60)
    print("校园标签体系专项正交门禁")
    print("=" * 60)

    c1_school_leaf_count()
    c2_school_depth()
    c3_no_school_instances()
    c4_education_leaf_count()
    c5_campus_circle_count()
    c6_no_current_student()
    c7_campus_tour()
    c8_campus_scene()
    c9_kindergarten_selection()
    c10_experience_sharing()

    print(f"\n{'ERROR' if errors else '(无错误)'}（{len(errors)} 条）:")
    for e in errors:
        print(f"  ✗ {e}")

    print(f"\n{'验证通过' if not errors else '验证失败'}: {len(errors)} 错误")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
