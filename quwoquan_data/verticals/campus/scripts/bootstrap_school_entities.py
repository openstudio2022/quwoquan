"""校园垂类学校实体批量生成能力。"""
from __future__ import annotations

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
from pathlib import Path

from _common.paths import NOW_ISO, PUBLISH_ROOT, RUNTIME_ROOT

CATALOG_DIR = RUNTIME_ROOT / "seed" / "school_catalog"
ENTITIES_ROOT = PUBLISH_ROOT / "entities" / "机构" / "学校"
ADMIN_REGIONS_PCA_FILE = DATA_ROOT / "reference" / "admin_regions" / "pca.json"
MUNICIPALITIES = {"北京市", "天津市", "上海市", "重庆市"}

UNIVERSITY_LEVEL_MAP = {"985": "985高校", "211": "211高校", "双一流": "双一流", "本科": "大学", "专科": "高职院校"}
UNIVERSITY_TYPE_MAP = {
    "综合": "综合类", "理工": "理工类", "师范": "师范类", "农林": "农林类",
    "医药": "医药类", "财经": "财经类", "政法": "政法类", "体育": "体育类",
    "艺术": "艺术类", "军事": "军事类", "民族": "民族类", "语言": "语言类",
}
OWNERSHIP_MAP = {"公办": "公办", "民办": "民办", "中外合作办学": "中外合作办学"}
ETYPE_TAG_MAP = {
    "幼儿园": "幼儿园", "小学": "小学", "初中": "初中", "高中": "高中",
    "完全中学": "完全中学", "九年一贯制学校": "九年一贯制学校",
    "十二年一贯制学校": "十二年一贯制学校", "中等职业学校": "中等职业学校",
}


def _region_indexes() -> tuple[dict[str, str], dict[str, list[str]]]:
    city_to_province: dict[str, str] = {}
    paths_by_label: dict[str, list[str]] = {}
    if not ADMIN_REGIONS_PCA_FILE.exists():
        return city_to_province, paths_by_label
    pca_data = json.loads(ADMIN_REGIONS_PCA_FILE.read_text(encoding="utf-8"))
    for province, cities_data in pca_data.items():
        paths_by_label.setdefault(province, []).append(f"中国/{province}")
        if province in MUNICIPALITIES:
            city_to_province[province] = province
            continue
        if isinstance(cities_data, dict):
            for city, districts in cities_data.items():
                city_to_province[city] = province
                paths_by_label.setdefault(city, []).append(f"中国/{province}/{city}")
                if isinstance(districts, list):
                    for district in districts:
                        paths_by_label.setdefault(district, []).append(f"中国/{province}/{city}/{district}")
    return city_to_province, paths_by_label


CITY_TO_PROVINCE, REGION_PATHS_BY_LABEL = _region_indexes()


def resolve_geo_tag_ref(row: dict, source_type: str) -> str:
    if source_type == "university":
        province = row.get("province", "")
        city = row.get("city", "")
        for path in REGION_PATHS_BY_LABEL.get(city, []):
            if not province or path.startswith(f"中国/{province}/") or path == f"中国/{province}":
                return f"Topic/地理/行政区/{path}"
        mapped_province = CITY_TO_PROVINCE.get(city, province)
        if mapped_province:
            if mapped_province in MUNICIPALITIES:
                return f"Topic/地理/行政区/中国/{mapped_province}"
            if city:
                return f"Topic/地理/行政区/中国/{mapped_province}/{city}"
        if province:
            return f"Topic/地理/行政区/中国/{province}"
    district = row.get("district", "")
    if source_type == "beijing":
        return f"Topic/地理/行政区/中国/北京市/{district}" if district else "Topic/地理/行政区/中国/北京市"
    if source_type == "shanghai":
        return f"Topic/地理/行政区/中国/上海市/{district}" if district else "Topic/地理/行政区/中国/上海市"
    return "Topic/地理/行政区/中国"


def resolve_tag_refs(row: dict, source_type: str) -> list[str]:
    refs = ["Entity/机构/学校"]
    if source_type == "university":
        for level in row.get("level", []):
            mapped = UNIVERSITY_LEVEL_MAP.get(level)
            if mapped:
                refs.append(f"Entity/机构/学校/{mapped}")
        mapped_type = UNIVERSITY_TYPE_MAP.get(row.get("universityType", ""))
        if mapped_type:
            refs.append(f"Entity/机构/学校/{mapped_type}")
    else:
        mapped = ETYPE_TAG_MAP.get(row.get("etype", ""))
        if mapped:
            refs.append(f"Entity/机构/学校/{mapped}")
    ownership = OWNERSHIP_MAP.get(row.get("ownership", ""))
    if ownership:
        refs.append(f"Entity/机构/学校/{ownership}")
    return list(dict.fromkeys(refs))


def make_school_page(name: str, row: dict, source_type: str) -> str:
    if source_type == "university":
        location = f"{row.get('province', '')}{row.get('city', '')}"
        kind = f"{row.get('ownership', '公办')}{row.get('universityType', '综合')}类高等院校"
        sections = [
            "## 基本信息", f"{name}位于{location}，是一所{kind}。",
            "## 院系与学科", "学校设有多个学院和专业方向，适合结合官方招生章程继续补充细分事实。",
            "## 校园生活", "后续内容应以学校官网、教务处、学生社区和地图信息补齐食堂、宿舍、交通与社团差异。",
        ]
    else:
        location = row.get("district", "")
        kind = f"{row.get('ownership', '公办')}{row.get('etype', '学校')}"
        sections = [
            "## 学校概况", f"{name}位于{location}，是一所{kind}。",
            "## 教学与校园", "后续内容应以学校官方、区教委公开信息、家长学生社区和地图信息补齐差异化事实。",
            "## 生活与升学", "围绕通勤、课后服务、社团、升学路径和家校沟通建立持续更新的话题内容。",
        ]
    return "\n".join([
        f"# {name}\n",
        f"> {name}校园主页，用于承载官方事实、学生生活与学习交流内容。\n",
        f"类型：[/entity/机构/学校/{name}](/entity/机构/学校/{name})\n",
        *sections,
        f"封面图：asset://images/机构/学校/{name}/cover.jpg\n",
        "相关标签：[/tag/Topic/教育成长](/tag/Topic/教育成长) [/tag/Entity/机构/学校](/tag/Entity/机构/学校)\n",
    ])


def _iter_catalog_rows(args: argparse.Namespace):
    sources = [
        ("universities_national.ndjson", "university"),
        ("schools_beijing.ndjson", "beijing"),
        ("schools_shanghai.ndjson", "shanghai"),
    ]
    for filename, source_type in sources:
        path = CATALOG_DIR / filename
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if source_type == "university":
                    if args.province and row.get("province") != args.province:
                        continue
                    if args.city and row.get("city") != args.city:
                        continue
                elif args.etype and row.get("etype") != args.etype:
                    continue
                yield filename, line_no, source_type, row


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="校园垂类学校实体批量生成")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--province")
    parser.add_argument("--city")
    parser.add_argument("--etype")
    args = parser.parse_args(argv)

    stats = {"created": 0, "skipped": 0, "errors": 0}
    seen_names: dict[str, int] = {}
    if not args.dry_run:
        ENTITIES_ROOT.mkdir(parents=True, exist_ok=True)
    for _filename, _line_no, source_type, row in _iter_catalog_rows(args):
        name = str(row.get("name") or "").strip()
        if not name:
            stats["errors"] += 1
            continue
        seen_names[name] = seen_names.get(name, 0) + 1
        dir_name = name if seen_names[name] == 1 else f"{name}_{row.get('city') or row.get('district') or seen_names[name]}"
        entity_dir = ENTITIES_ROOT / dir_name
        if args.resume and entity_dir.exists():
            stats["skipped"] += 1
            continue
        entity_json = {
            "label": name,
            "labelEn": name,
            "description": name,
            "geoTagRef": resolve_geo_tag_ref(row, source_type),
            "tagRefs": resolve_tag_refs(row, source_type),
            "sourceRef": f"{source_type}:{name}",
            "createdAt": NOW_ISO,
            "updatedAt": NOW_ISO,
        }
        if not args.dry_run:
            entity_dir.mkdir(parents=True, exist_ok=True)
            (entity_dir / "_entity.json").write_text(json.dumps(entity_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (entity_dir / "page.md").write_text(make_school_page(name, row, source_type), encoding="utf-8")
        stats["created"] += 1
    print(f"[campus bootstrap entities] created={stats['created']} skipped={stats['skipped']} errors={stats['errors']}")
    if stats["errors"]:
        raise SystemExit(1)
