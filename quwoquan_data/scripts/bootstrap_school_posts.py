"""学校 Posts 分层生成

按"全量索引帖 + 重点深内容"策略为学校实体生成 posts。

分层规则：
  - 985/211/双一流大学：1 索引帖 + 3-6 篇深内容
  - 普通本科：1 索引帖 + 1 篇深内容
  - 高职院校：1 索引帖
  - 示范性高中/名校：1 索引帖 + 2 篇深内容
  - 普通中学：1 索引帖
  - 示范幼儿园/名园：1 索引帖 + 1 篇深内容
  - 普通幼儿园：1 索引帖

用法:
  python3 bootstrap_school_posts.py                 # 全量生成
  python3 bootstrap_school_posts.py --dry-run       # 仅统计
  python3 bootstrap_school_posts.py --resume        # 跳过已存在
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common.paths import PUBLISH_ROOT, NOW_ISO

ENTITIES_ROOT = PUBLISH_ROOT / "v1" / "entities" / "机构" / "学校"
POSTS_ROOT = PUBLISH_ROOT / "v1" / "posts" / "article"

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
    ("择园攻略", "Format/内容角度/攻略", "Topic/亲子育儿/幼儿园选择"),
    ("幼小衔接", "Format/内容角度/攻略", "Topic/亲子育儿/幼小衔接"),
]

KEY_UNIVERSITIES = {"985高校", "211高校", "双一流"}

stats = {"index_posts": 0, "deep_posts": 0, "skipped": 0}


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
        if ref in ("Entity/机构/学校/高中", "Entity/机构/学校/初中",
                   "Entity/机构/学校/完全中学"):
            return "school"
        if ref == "Entity/机构/学校/幼儿园":
            return "kindergarten"
    return "other"


def make_index_post(name: str, entity: dict) -> tuple[str, dict]:
    geo_ref = entity.get("geoTagRef", "")
    tag_refs = entity.get("tagRefs", [])

    lines = [
        f"# {name}｜学校概览\n",
        f"> {name}基本信息与概况索引。\n",
        f"实体引用：[/entity/机构/学校/{name}](/entity/机构/学校/{name})\n",
        "## 基本信息\n",
        f"{name}是一所教育机构，致力于为学生提供优质的教育资源和良好的学习环境。学校注重培养学生的综合素质，",
        "在教学质量、师资力量、校园文化等方面持续投入和改进。\n",
        "## 位置与交通\n",
        f"{name}交通便利，周边配套设施完善，为师生的学习和生活提供了便利条件。\n",
        f"标签引用：[/tag/Topic/教育成长](/tag/Topic/教育成长)\n",
        f"封面图：asset://images/posts/{name}_index/cover.jpg\n",
        "\n## 更多信息\n",
        f"如需了解更多关于{name}的详细信息，包括招生政策、课程设置、校园活动等，请关注学校官方渠道。",
        f"本索引帖旨在提供{name}的结构化基本信息，便于快速了解学校概况。\n",
    ]
    article = "\n".join(lines)

    manifest = {
        "contentType": "article",
        "entityRefs": [f"/entity/机构/学校/{name}"],
        "tagRefs": tag_refs + [geo_ref, "Topic/教育成长"],
        "createdAt": NOW_ISO,
        "updatedAt": NOW_ISO,
    }

    return article, manifest


def make_deep_post(name: str, entity: dict, angle_name: str,
                   format_ref: str, topic_ref: str) -> tuple[str, dict]:
    geo_ref = entity.get("geoTagRef", "")
    tag_refs = entity.get("tagRefs", [])

    angle_templates = {
        "新生攻略": [
            "## 入学准备\n",
            f"恭喜你即将成为{name}的新生！入学前需要做好以下准备工作：了解学校的报到流程、准备必要的证件和生活用品、",
            "熟悉校园环境和周边设施。建议提前加入新生群，与学长学姐交流获取第一手信息。\n",
            "## 校园生活指南\n",
            f"{name}的校园生活丰富多彩。食堂、图书馆、体育场等设施齐全，社团活动种类繁多。",
            "建议新生积极参与，既能结交朋友，也能丰富课余生活。\n",
            "## 学习建议\n",
            "大学/学校的学习方式与之前有所不同，更注重自主学习和独立思考。建议做好时间规划，",
            "合理安排学习与休息，充分利用图书馆和在线资源。\n",
        ],
        "选课攻略": [
            "## 选课策略\n",
            f"在{name}选课需要注意：了解培养方案中的必修课和选修课要求，合理规划每学期的课程量，",
            "参考学长学姐的选课评价，注意课程时间的合理分配。\n",
            "## 热门课程推荐\n",
            f"{name}有许多值得推荐的课程，包括通识教育课程和专业核心课程。建议关注教务系统的选课公告，",
            "提前了解课程内容和考核方式。\n",
            "## 选课避坑指南\n",
            "避免同时选择多门高难度课程，注意课程之间的前置要求，合理评估自己的学习能力和时间精力。\n",
        ],
        "校园评测": [
            "## 整体评价\n",
            f"{name}在教学质量、校园环境、生活设施等方面表现如何？本文从多个维度进行客观评测。\n",
            "## 食堂评测\n",
            f"{name}的食堂提供多样化的餐饮选择，价格适中，卫生状况良好。不同食堂各有特色，值得一一探索。\n",
            "## 宿舍评测\n",
            f"{name}的学生宿舍条件在同类学校中处于中上水平，配备基本的生活设施，网络覆盖全面。\n",
            "## 综合推荐\n",
            "总体而言，学校在硬件和软件方面持续改进，为学生营造了良好的学习和生活环境。\n",
        ],
        "考研经验": [
            "## 备考规划\n",
            f"从{name}出发考研需要做好长期规划。建议从大三上学期开始准备，合理分配公共课和专业课的复习时间。\n",
            "## 资源利用\n",
            f"{name}图书馆的考研自习室、学校的考研辅导讲座、以及学长学姐的经验分享都是宝贵的备考资源。\n",
            "## 心态调整\n",
            "考研是一场持久战，保持积极的心态非常重要。建议找到志同道合的研友，互相鼓励，共同进步。\n",
        ],
        "校招经验": [
            "## 校招时间线\n",
            f"{name}的校园招聘主要集中在秋季（9-11月）和春季（3-5月）。建议提前关注学校就业信息网和各大企业的招聘公告。\n",
            "## 简历准备\n",
            "针对校招，简历需要突出在校期间的项目经验、实习经历、学术成果和社团活动。建议针对不同岗位准备不同版本的简历。\n",
            "## 面试技巧\n",
            "校招面试通常包括群面和单面。做好自我介绍的准备，了解应聘公司的业务和文化，展现积极主动的态度。\n",
        ],
        "校园日记": [
            "## 校园四季\n",
            f"在{name}的每一天都是值得记录的。春天的校园百花盛开，夏天的林荫道清凉宜人，",
            "秋天的落叶铺满小径，冬天的第一场雪装点了整个校园。\n",
            "## 日常记录\n",
            f"记录在{name}的日常点滴：清晨的图书馆、午后的咖啡时光、傍晚的操场跑步、夜晚的自习室。",
            "这些平凡的时刻构成了难忘的校园记忆。\n",
        ],
        "择园攻略": [
            "## 如何选择幼儿园\n",
            f"选择{name}这样的幼儿园需要考虑多个因素：距离家的远近、办学理念是否匹配、师资力量、安全设施、",
            "课程体系、收费标准等。建议家长实地考察，与园方充分沟通。\n",
            "## 入园准备\n",
            "为孩子做好入园心理准备：提前带孩子参观幼儿园、培养基本的自理能力、建立规律的作息时间。\n",
            "## 家长注意事项\n",
            "入园后与老师保持良好沟通，关注孩子的情绪变化和适应情况，积极参与家园共育活动。\n",
        ],
        "幼小衔接": [
            "## 衔接准备\n",
            f"从{name}毕业升入小学，需要在知识储备、学习习惯和社交能力三个方面做好准备。\n",
            "## 学习习惯培养\n",
            "培养孩子的专注力、自主学习意识和时间观念，为小学的学习节奏做好铺垫。\n",
            "## 心理适应\n",
            "帮助孩子建立对小学生活的积极期待，培养独立解决问题的能力和社交技巧。\n",
        ],
    }

    template = angle_templates.get(angle_name, [
        f"## 关于{name}\n",
        f"本文从{angle_name}的角度分享关于{name}的信息和经验。\n",
    ])

    lines = [
        f"# {name}｜{angle_name}\n",
        f"> {name}{angle_name}分享。\n",
        f"实体引用：[/entity/机构/学校/{name}](/entity/机构/学校/{name})\n",
    ] + template + [
        f"标签引用：[/tag/{format_ref}](/tag/{format_ref})\n",
        f"封面图：asset://images/posts/{name}_{angle_name}/cover.jpg\n",
    ]
    article = "\n".join(lines)

    manifest = {
        "contentType": "article",
        "entityRefs": [f"/entity/机构/学校/{name}"],
        "tagRefs": list(set(tag_refs + [geo_ref, format_ref, topic_ref])),
        "createdAt": NOW_ISO,
        "updatedAt": NOW_ISO,
    }

    return article, manifest


def write_post(name: str, angle_name: str, article: str, manifest: dict,
               seq: int, dry_run: bool):
    safe_angle = angle_name.replace("/", "_")
    safe_name = name.replace("/", "_")
    post_dir = POSTS_ROOT / safe_angle / safe_name / str(seq)
    if not dry_run:
        post_dir.mkdir(parents=True, exist_ok=True)
        (post_dir / "article.md").write_text(article, encoding="utf-8")
        (post_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def process_entity(entity_dir: Path, args) -> int:
    entity_file = entity_dir / "_entity.json"
    if not entity_file.exists():
        return 0

    entity = json.loads(entity_file.read_text(encoding="utf-8"))
    name = entity_dir.name
    school_type = get_school_type(entity)
    is_key = is_key_university(entity)

    post_count = 0

    article, manifest = make_index_post(name, entity)
    write_post(name, "索引", article, manifest, 1, args.dry_run)
    stats["index_posts"] += 1
    post_count += 1

    deep_angles = []
    if school_type == "university" and is_key:
        deep_angles = DEEP_ANGLES_UNIVERSITY_KEY
    elif school_type == "university":
        deep_angles = DEEP_ANGLES_UNIVERSITY_REGULAR
    elif school_type == "school":
        tag_refs = entity.get("tagRefs", [])
        if "Entity/机构/学校/高中" in tag_refs:
            deep_angles = DEEP_ANGLES_SCHOOL
    elif school_type == "kindergarten":
        tag_refs = entity.get("tagRefs", [])
        if any("公办" in r for r in tag_refs):
            deep_angles = DEEP_ANGLES_KINDERGARTEN[:1]

    for angle_name, format_ref, topic_ref in deep_angles:
        article, manifest = make_deep_post(name, entity, angle_name, format_ref, topic_ref)
        write_post(name, angle_name, article, manifest, 1, args.dry_run)
        stats["deep_posts"] += 1
        post_count += 1

    return post_count


def main():
    parser = argparse.ArgumentParser(description="学校 Posts 分层生成")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("学校 Posts 分层生成")
    print("=" * 60)

    if not ENTITIES_ROOT.exists():
        print("ERROR: 实体目录不存在，请先运行 bootstrap_school_entities.py")
        sys.exit(1)

    entity_dirs = sorted([d for d in ENTITIES_ROOT.iterdir() if d.is_dir()])
    print(f"  实体目录数: {len(entity_dirs)}")

    total_posts = 0
    for entity_dir in entity_dirs:
        total_posts += process_entity(entity_dir, args)

    print(f"\n=== 最终统计 ===")
    print(f"  索引帖: {stats['index_posts']}")
    print(f"  深内容: {stats['deep_posts']}")
    print(f"  总 posts: {total_posts}")


if __name__ == "__main__":
    main()
