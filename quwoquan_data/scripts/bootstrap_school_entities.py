"""学校实体批量生成

从 runtime/seed/school_catalog/ 的 ndjson 读取学校数据，
按实体事实源（_entity.json）+ page.md + publish manifest 的模式写入 publish/v1/entities/机构/学校/{name}/。

用法:
  python3 bootstrap_school_entities.py                          # 全量生成
  python3 bootstrap_school_entities.py --dry-run                # 仅统计不写入
  python3 bootstrap_school_entities.py --province 北京市         # 只生成北京高校
  python3 bootstrap_school_entities.py --city 上海市             # 只生成上海
  python3 bootstrap_school_entities.py --etype 幼儿园            # 只生成幼儿园
  python3 bootstrap_school_entities.py --resume                 # 跳过已存在目录
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common.paths import PUBLISH_ROOT, RUNTIME_ROOT, NOW_ISO

CATALOG_DIR = RUNTIME_ROOT / "seed" / "school_catalog"
ENTITIES_ROOT = PUBLISH_ROOT / "v1" / "entities" / "机构" / "学校"
ADMIN_REGIONS_PCA_FILE = Path(__file__).resolve().parent.parent / "data" / "admin_regions" / "pca.json"
MUNICIPALITIES = {"北京市", "天津市", "上海市", "重庆市"}

UNIVERSITY_LEVEL_MAP = {
    "985": "985高校", "211": "211高校", "双一流": "双一流",
    "本科": "大学", "专科": "高职院校",
}
UNIVERSITY_TYPE_MAP = {
    "综合": "综合类", "理工": "理工类", "师范": "师范类",
    "农林": "农林类", "医药": "医药类", "财经": "财经类",
    "政法": "政法类", "体育": "体育类", "艺术": "艺术类",
    "军事": "军事类", "民族": "民族类", "语言": "语言类",
}
OWNERSHIP_MAP = {"公办": "公办", "民办": "民办", "中外合作办学": "中外合作办学"}

ETYPE_TAG_MAP = {
    "幼儿园": "幼儿园", "小学": "小学", "初中": "初中", "高中": "高中",
    "完全中学": "完全中学", "九年一贯制学校": "九年一贯制学校",
    "十二年一贯制学校": "十二年一贯制学校", "中等职业学校": "中等职业学校",
}

stats = {"created": 0, "skipped": 0, "errors": 0, "conflict": 0}
error_log: list[dict] = []

CITY_TO_PROVINCE: dict[str, str] = {}
REGION_PATHS_BY_LABEL: dict[str, list[str]] = {}
REGION_ALIAS_TO_CANONICAL = {
    "临夏州": "临夏回族自治州",
}
if ADMIN_REGIONS_PCA_FILE.exists():
    pca_data = json.loads(ADMIN_REGIONS_PCA_FILE.read_text(encoding="utf-8"))
    for province, cities_data in pca_data.items():
        REGION_PATHS_BY_LABEL.setdefault(province, []).append(f"中国/{province}")
        if province in MUNICIPALITIES:
            CITY_TO_PROVINCE[province] = province
            if isinstance(cities_data, dict):
                for _group_name, districts in cities_data.items():
                    if isinstance(districts, list):
                        for district in districts:
                            REGION_PATHS_BY_LABEL.setdefault(district, []).append(
                                f"中国/{province}/{district}"
                            )
                    elif isinstance(districts, dict):
                        for district in districts:
                            REGION_PATHS_BY_LABEL.setdefault(district, []).append(
                                f"中国/{province}/{district}"
                            )
            continue
        if isinstance(cities_data, dict):
            for city in cities_data.keys():
                CITY_TO_PROVINCE[city] = province
            for city, districts in cities_data.items():
                if city in {"省直辖县级行政区划", "自治区直辖县级行政区划"}:
                    if isinstance(districts, list):
                        for county_city in districts:
                            REGION_PATHS_BY_LABEL.setdefault(county_city, []).append(
                                f"中国/{province}/{county_city}"
                            )
                    elif isinstance(districts, dict):
                        for county_city in districts:
                            REGION_PATHS_BY_LABEL.setdefault(county_city, []).append(
                                f"中国/{province}/{county_city}"
                            )
                    continue
                REGION_PATHS_BY_LABEL.setdefault(city, []).append(f"中国/{province}/{city}")
                if isinstance(districts, list):
                    for district in districts:
                        REGION_PATHS_BY_LABEL.setdefault(district, []).append(
                            f"中国/{province}/{city}/{district}"
                        )
                elif isinstance(districts, dict):
                    for district in districts:
                        REGION_PATHS_BY_LABEL.setdefault(district, []).append(
                            f"中国/{province}/{city}/{district}"
                        )


def resolve_geo_tag_ref(row: dict, source_type: str) -> str:
    if source_type == "university":
        province = row.get("province", "")
        city = row.get("city", "")
        canonical_city = REGION_ALIAS_TO_CANONICAL.get(city, city)
        candidate_paths = REGION_PATHS_BY_LABEL.get(canonical_city, [])
        for path in candidate_paths:
            if province and path.startswith(f"中国/{province}/"):
                return f"Topic/地理/行政区/{path}"
            if province and path == f"中国/{province}":
                return f"Topic/地理/行政区/{path}"
        if candidate_paths:
            return f"Topic/地理/行政区/{candidate_paths[0]}"
        mapped_province = CITY_TO_PROVINCE.get(city, "")
        if mapped_province:
            if mapped_province in MUNICIPALITIES:
                return f"Topic/地理/行政区/中国/{mapped_province}"
            return f"Topic/地理/行政区/中国/{mapped_province}/{city}"
        if province in MUNICIPALITIES and city == province:
            return f"Topic/地理/行政区/中国/{province}"
        if province and city:
            return f"Topic/地理/行政区/中国/{province}/{city}"
        elif province:
            return f"Topic/地理/行政区/中国/{province}"
    else:
        district = row.get("district", "")
        if source_type == "beijing":
                return f"Topic/地理/行政区/中国/北京市/{district}" if district else "Topic/地理/行政区/中国/北京市"
        elif source_type == "shanghai":
                return f"Topic/地理/行政区/中国/上海市/{district}" if district else "Topic/地理/行政区/中国/上海市"
    return "Topic/地理/行政区/中国"


def resolve_tag_refs(row: dict, source_type: str) -> list[str]:
    refs = ["Entity/机构/学校"]

    if source_type == "university":
        levels = row.get("level", [])
        for lv in levels:
            mapped = UNIVERSITY_LEVEL_MAP.get(lv)
            if mapped and f"Entity/机构/学校/{mapped}" not in refs:
                refs.append(f"Entity/机构/学校/{mapped}")
        utype = row.get("universityType", "")
        mapped_type = UNIVERSITY_TYPE_MAP.get(utype)
        if mapped_type:
            refs.append(f"Entity/机构/学校/{mapped_type}")
    else:
        etype = row.get("etype", "")
        mapped = ETYPE_TAG_MAP.get(etype)
        if mapped:
            refs.append(f"Entity/机构/学校/{mapped}")

    ownership = row.get("ownership", "")
    own_mapped = OWNERSHIP_MAP.get(ownership)
    if own_mapped:
        refs.append(f"Entity/机构/学校/{own_mapped}")

    return refs


def make_school_page(name: str, row: dict, source_type: str) -> str:
    if source_type == "university":
        return _make_university_page(name, row)
    etype = row.get("etype", "")
    if etype == "幼儿园":
        return _make_kindergarten_page(name, row)
    return _make_school_page(name, row)


def _make_university_page(name: str, row: dict) -> str:
    levels = ", ".join(row.get("level", []))
    utype = row.get("universityType", "综合")
    province = row.get("province", "")
    city = row.get("city", "")
    ownership = row.get("ownership", "公办")

    lines = [
        f"# {name}\n",
        f"> {name}是一所位于{province}{city}的{ownership}{utype}类高等院校。\n",
        f"类型：[/entity/机构/学校/{name}](/entity/机构/学校/{name})\n",
        "## 基本信息\n",
        f"| 项目 | 信息 |",
        f"|------|------|",
        f"| 学校名称 | {name} |",
        f"| 所在地 | {province}{city} |",
        f"| 办学层次 | {levels} |",
        f"| 学校类型 | {utype}类 |",
        f"| 办学性质 | {ownership} |",
        "",
        "## 院系设置\n",
        f"{name}设有多个学院和院系，覆盖文、理、工、医、管等多个学科门类。学校注重学科交叉融合，积极推进\"双一流\"建设和特色学科发展。\n",
        "## 校园风光\n",
        f"{name}校园环境优美，建筑风格兼具历史底蕴与现代气息。四季景色各异，春有繁花、夏有浓荫、秋有红叶、冬有银装。\n",
        f"封面图：asset://images/机构/学校/{name}/cover.jpg\n",
        "## 就业与深造\n",
        f"{name}毕业生就业率和深造率在同类院校中表现优异。学校与众多知名企业和科研机构建立了合作关系，为学生提供丰富的实习和就业机会。\n",
        "## 校园生活\n",
        f"{name}拥有完善的食堂、宿舍和体育设施，学生社团活动丰富多彩。校园文化氛围浓厚，是求学深造的理想之地。\n",
        f"相关标签：[/tag/Topic/教育成长](/tag/Topic/教育成长) [/tag/Entity/机构/学校](/tag/Entity/机构/学校)\n",
    ]
    return "\n".join(lines)


def _make_school_page(name: str, row: dict) -> str:
    district = row.get("district", "")
    etype = row.get("etype", "中学")
    ownership = row.get("ownership", "公办")

    lines = [
        f"# {name}\n",
        f"> {name}是一所位于{district}的{ownership}{etype}。\n",
        f"类型：[/entity/机构/学校/{name}](/entity/机构/学校/{name})\n",
        "## 学校概况\n",
        f"{name}位于{district}，是一所{ownership}性质的{etype}。学校秉承\"全面发展、追求卓越\"的办学理念，致力于培养德智体美劳全面发展的优秀人才。\n",
        "## 师资力量\n",
        f"{name}拥有一支高素质的教师队伍，其中高级教师和骨干教师占比较高。学校注重教师专业发展，定期组织教研活动和培训交流。\n",
        "## 校园环境\n",
        f"{name}校园环境整洁优美，教学设施完善，配备现代化的实验室、图书馆和体育场馆。\n",
        f"封面图：asset://images/机构/学校/{name}/cover.jpg\n",
        f"相关标签：[/tag/Topic/教育成长](/tag/Topic/教育成长) [/tag/Entity/机构/学校](/tag/Entity/机构/学校)\n",
    ]
    return "\n".join(lines)


def _make_kindergarten_page(name: str, row: dict) -> str:
    district = row.get("district", "")
    ownership = row.get("ownership", "公办")

    lines = [
        f"# {name}\n",
        f"> {name}是一所位于{district}的{ownership}幼儿园。\n",
        f"类型：[/entity/机构/学校/{name}](/entity/机构/学校/{name})\n",
        "## 园所概况\n",
        f"{name}位于{district}，是一所{ownership}性质的幼儿园。园所秉承\"快乐成长、全面发展\"的教育理念，为幼儿提供安全、温馨的成长环境。\n",
        "## 师资与班额\n",
        f"{name}配备专业的学前教育师资团队，师生比符合国家标准。每班配备主班教师、配班教师和保育员，确保每位幼儿得到充分关注。\n",
        "## 课程体系\n",
        f"{name}根据《3-6岁儿童学习与发展指南》设计课程，涵盖健康、语言、社会、科学、艺术五大领域，注重游戏化教学和实践体验。\n",
        f"封面图：asset://images/机构/学校/{name}/cover.jpg\n",
        f"相关标签：[/tag/Topic/亲子育儿](/tag/Topic/亲子育儿) [/tag/Entity/机构/学校](/tag/Entity/机构/学校)\n",
    ]
    return "\n".join(lines)


def resolve_dir_name(name: str, row: dict, source_type: str, seen_names: dict) -> str:
    if name not in seen_names:
        seen_names[name] = []
    seen_names[name].append(row)
    if len(seen_names[name]) == 1:
        return name
    if source_type == "university":
        city = row.get("city", "")
        return f"{name}_{city}" if city else name
    else:
        district = row.get("district", "")
        return f"{name}_{district}" if district else name


def process_row(row: dict, source_type: str, args, seen_names: dict) -> bool:
    name = row.get("name", "").strip()
    if not name:
        stats["errors"] += 1
        error_log.append({"row": row, "error": "missing name"})
        return False

    if source_type == "university":
        if args.province and row.get("province") != args.province:
            return False
        if args.city and row.get("city") != args.city:
            return False
    else:
        if args.etype and row.get("etype") != args.etype:
            return False

    dir_name = resolve_dir_name(name, row, source_type, seen_names)
    entity_dir = ENTITIES_ROOT / dir_name

    if args.resume and entity_dir.exists():
        stats["skipped"] += 1
        return False

    if entity_dir.exists() and not args.resume:
        stats["conflict"] += 1
        # 既有目录视为可重写的历史输出，继续写入新版本以便回填。

    geo_ref = resolve_geo_tag_ref(row, source_type)
    tag_refs = resolve_tag_refs(row, source_type)

    entity_json = {
        "label": name,
        "labelEn": name,
        "description": f"{name}",
        "geoTagRef": geo_ref,
        "tagRefs": tag_refs,
        "sourceRef": f"{source_type}:{name}",
        "createdAt": NOW_ISO,
        "updatedAt": NOW_ISO,
    }

    page_md = make_school_page(name, row, source_type)
    manifest_json = {
        "entityRefs": [],
        "assets": [f"{name}_cover.jpg"],
        "createdAt": NOW_ISO,
        "updatedAt": NOW_ISO,
    }

    if not args.dry_run:
        entity_dir.mkdir(parents=True, exist_ok=True)
        (entity_dir / "_entity.json").write_text(
            json.dumps(entity_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (entity_dir / "page.md").write_text(page_md, encoding="utf-8")
        (entity_dir / "manifest.json").write_text(
            json.dumps(manifest_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    stats["created"] += 1
    return True


def process_file(fpath: Path, source_type: str, args, seen_names: dict):
    with open(fpath, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                stats["errors"] += 1
                error_log.append({"file": fpath.name, "line": i, "error": str(e)})
                continue
            process_row(row, source_type, args, seen_names)


def main():
    parser = argparse.ArgumentParser(description="学校实体批量生成")
    parser.add_argument("--dry-run", action="store_true", help="仅统计不写入")
    parser.add_argument("--resume", action="store_true", help="跳过已存在目录")
    parser.add_argument("--province", help="只生成指定省份高校")
    parser.add_argument("--city", help="只生成指定城市")
    parser.add_argument("--etype", help="只生成指定学段类型")
    args = parser.parse_args()

    print("=" * 60)
    print("学校实体批量生成")
    print("=" * 60)
    print(f"  输出目录: {ENTITIES_ROOT}")
    print(f"  dry-run: {args.dry_run}")
    print(f"  resume: {args.resume}")

    if not args.dry_run:
        ENTITIES_ROOT.mkdir(parents=True, exist_ok=True)

    seen_names: dict[str, list] = {}

    uni_file = CATALOG_DIR / "universities_national.ndjson"
    if uni_file.exists():
        print(f"\n处理: {uni_file.name}")
        process_file(uni_file, "university", args, seen_names)
        print(f"  累计: created={stats['created']}, skipped={stats['skipped']}, errors={stats['errors']}")

    bj_file = CATALOG_DIR / "schools_beijing.ndjson"
    if bj_file.exists():
        print(f"\n处理: {bj_file.name}")
        process_file(bj_file, "beijing", args, seen_names)
        print(f"  累计: created={stats['created']}, skipped={stats['skipped']}, errors={stats['errors']}")

    sh_file = CATALOG_DIR / "schools_shanghai.ndjson"
    if sh_file.exists():
        print(f"\n处理: {sh_file.name}")
        process_file(sh_file, "shanghai", args, seen_names)
        print(f"  累计: created={stats['created']}, skipped={stats['skipped']}, errors={stats['errors']}")

    print(f"\n=== 最终统计 ===")
    print(f"  新增: {stats['created']}")
    print(f"  跳过: {stats['skipped']}")
    print(f"  冲突: {stats['conflict']}")
    print(f"  错误: {stats['errors']}")

    if error_log:
        print(f"\n错误详情（前10条）:")
        for e in error_log[:10]:
            print(f"  {e}")

    if stats["errors"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
