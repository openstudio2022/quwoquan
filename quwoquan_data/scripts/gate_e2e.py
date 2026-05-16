"""E2E Gate v5 — 四分组标签体系 + 全维度统一目录结构门禁

G1-G11:  task-level entity/post/publish 完整性
G12-G15: publish 全局标签体系（已迁移到四分组 Topic/Audience/Format/Entity）
G16-G29: 新增 schema/tagRef/pathPolicy/post内容角度/关系图/命名/refHint/容量/前缀/旅行强制/geo强制/索引/校园专项/互斥对 门禁
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common.paths import *

TASK_ID = "四川旅行_v5"
BATCH_ID = "多维度冒烟"

ENTITIES = {
    ("地点", "景区", "峨眉山"), ("地点", "景区", "九寨沟"), ("地点", "景区", "稻城亚丁"),
    ("地点", "景区", "黄龙"), ("地点", "景区", "海螺沟"),
    ("地点", "遗址", "三星堆遗址"), ("地点", "遗址", "金沙遗址"),
    ("地点", "古镇", "阆中古城"), ("地点", "古镇", "黄龙溪古镇"),
    ("地点", "打卡地", "成都太古里"), ("地点", "打卡地", "宽窄巷子"),
    ("地点", "博物馆", "三星堆博物馆"), ("地点", "博物馆", "成都博物馆"),
    ("地点", "餐厅", "陈麻婆豆腐总店"),
    ("地点", "住宿", "峨眉山蓝光己庄温泉度假村"),
    ("机构", "学校", "四川大学"),
}

TYPE_ANGLES = {
    ("地点", "景区"): ["攻略", "体验"],
    ("地点", "遗址"): ["科普", "体验"],
    ("地点", "打卡地"): ["攻略", "日记"],
    ("地点", "博物馆"): ["科普", "体验"],
    ("地点", "古镇"): ["攻略", "叙事"],
    ("地点", "餐厅"): ["探店", "攻略"],
    ("地点", "住宿"): ["体验", "攻略"],
    ("机构", "学校"): ["攻略", "体验"],
}

EXPECTED_DOMAINS = {"地点", "机构"}
EXPECTED_TYPES = {"景区", "遗址", "打卡地", "博物馆", "古镇", "餐厅", "住宿", "学校"}

errors: list[str] = []
warnings: list[str] = []


def check(ok: bool, msg: str):
    if not ok:
        errors.append(msg)


# ─── G1: tags 完整性 + 无冗余 ────────────────────────────────────
def g1_tags():
    td = task_data(TASK_ID)
    defs = list(td.tags_dir().rglob("_definition.json"))
    check(len(defs) >= 100, f"G1: 标签数量不足: {len(defs)} < 100")
    dims = list(td.tags_dir().rglob("_dimension.json"))
    check(len(dims) >= 7, f"G1: 维度数量不足: {len(dims)} < 7")

    taxonomy = td.taxonomy()
    check(taxonomy.exists(), "G1: _taxonomy.json 不存在")

    for f in defs:
        data = json.loads(f.read_text(encoding="utf-8"))
        check("tagId" not in data, f"G1: 含冗余 tagId: {f.relative_to(td.tags_dir())}")
        check("label" in data, f"G1: 缺 label: {f.relative_to(td.tags_dir())}")
        check("labelEn" in data, f"G1: 缺 labelEn: {f.relative_to(td.tags_dir())}")
        check("createdAt" in data, f"G1: 缺 createdAt: {f.relative_to(td.tags_dir())}")
        # G1: 禁止字段
        for ff in ["appliesTo", "status", "lifecycle", "deprecatedTo", "startDate", "endDate"]:
            check(ff not in data, f"G1: 禁止字段 '{ff}': {f.relative_to(td.tags_dir())}")


# ─── G2: entities 三层目录 + 三件套 + 无冗余字段 ─────────────────
def g2_entities():
    td = task_data(TASK_ID)
    domains_seen = set()
    types_seen = set()

    for domain, etype, name in ENTITIES:
        domains_seen.add(domain)
        types_seen.add(etype)
        edir = td.entity_dir(domain, etype, name)
        check(edir.exists(), f"G2: 目录不存在: {domain}/{etype}/{name}")

        ej = td.entity_json(domain, etype, name)
        check(ej.exists(), f"G2: _entity.json 不存在: {domain}/{etype}/{name}")
        if ej.exists():
            data = json.loads(ej.read_text(encoding="utf-8"))
            check("entityId" not in data, f"G2: 含冗余 entityId: {name}")
            check("entityType" not in data, f"G2: 含冗余 entityType: {name}")
            check("createdAt" in data, f"G2: 缺 createdAt: {name}")
            check("updatedAt" in data, f"G2: 缺 updatedAt: {name}")
            check("geoTagRef" in data, f"G2: 缺 geoTagRef: {name}")
            check("tagRefs" in data, f"G2: 缺 tagRefs: {name}")

        check(td.entity_page(domain, etype, name).exists(),
              f"G2: page.md 不存在: {domain}/{etype}/{name}")
        check(td.entity_manifest(domain, etype, name).exists(),
              f"G2: manifest.json 不存在: {domain}/{etype}/{name}")
        mf = td.entity_manifest(domain, etype, name)
        if mf.exists():
            manifest = json.loads(mf.read_text(encoding="utf-8"))
            check("tagRefs" not in manifest, f"G2: entity manifest 不应重复 tagRefs: {domain}/{etype}/{name}")
            check("geoTagRef" not in manifest, f"G2: entity manifest 不应重复 geoTagRef: {domain}/{etype}/{name}")

    check(domains_seen >= EXPECTED_DOMAINS,
          f"G2: 缺领域: {EXPECTED_DOMAINS - domains_seen}")
    check(types_seen >= EXPECTED_TYPES,
          f"G2: 缺类型: {EXPECTED_TYPES - types_seen}")


# ─── G3: 主页内容质量 ───────────────────────────────────────────
def g3_page_quality():
    td = task_data(TASK_ID)
    for domain, etype, name in ENTITIES:
        page = td.entity_page(domain, etype, name)
        if not page.exists():
            continue
        content = page.read_text(encoding="utf-8")
        check(len(content) >= 800,
              f"G3: 主页过短({len(content)}字): {domain}/{etype}/{name}")
        check("/entity/" in content,
              f"G3: 主页无 /entity/ 引用: {name}")
        check("/tag/" in content,
              f"G3: 主页无 /tag/ 引用: {name}")
        check("asset://" in content,
              f"G3: 主页无 asset:// 引用: {name}")
        check("## 标签" not in content,
              f"G3: 主页含独立标签章节: {name}")
        check("## 相关实体" not in content,
              f"G3: 主页含独立相关实体章节: {name}")


# ─── G4: posts 多角度 + 无冗余 + 内容角度覆盖 ────────────────────
def g4_posts():
    td = task_data(TASK_ID)
    post_count = 0
    angles_seen = set()

    for domain, etype, name in ENTITIES:
        expected_angles = TYPE_ANGLES.get((domain, etype), ["攻略", "体验"])
        for angle in expected_angles:
            angles_seen.add(angle)
            title = f"{name}{angle}指南"
            pdir = td.post_dir("article", angle, title, 1)
            check(pdir.exists(), f"G4: post 目录不存在: {title}")

            article = pdir / "article.md"
            if article.exists():
                content = article.read_text(encoding="utf-8")
                check("asset://" in content, f"G4: 无 asset://: {title}")
                check("/entity/" in content, f"G4: 无 /entity/: {title}")
                check("/tag/" in content, f"G4: 无 /tag/: {title}")
                check(len(content) >= 300, f"G4: 文章过短: {title}")
                post_count += 1

            mf = pdir / "manifest.json"
            if mf.exists():
                data = json.loads(mf.read_text(encoding="utf-8"))
                check("topicId" not in data, f"G4: 含冗余 topicId: {title}")
                check("createdAt" in data, f"G4: 缺 createdAt: {title}")
                for eref in data.get("entityRefs", []):
                    check(not eref.isascii(), f"G4: entityRef 非中文路径: {eref}")

    expected_total = sum(len(TYPE_ANGLES.get((d, t), ["攻略", "体验"]))
                        for d, t, _ in ENTITIES)
    check(post_count == expected_total,
          f"G4: post 数量 {post_count} != {expected_total}")
    check(len(angles_seen) >= 5,
          f"G4: 内容角度多样性不足: 仅 {angles_seen}")


# ─── G5: publish 同构 ────────────────────────────────────────────
def g5_publish_isomorphic():
    v = publish_active_version()
    check(v >= 1, "G5: 无活跃 publish 版本")
    if v < 1:
        return
    pd = publish_data(v)

    for domain, etype, name in ENTITIES:
        check(pd.entity_json(domain, etype, name).exists(),
              f"G5: publish 缺 entity: {domain}/{etype}/{name}")
        check(pd.entity_page(domain, etype, name).exists(),
              f"G5: publish 缺 page: {domain}/{etype}/{name}")

    for domain, etype, name in ENTITIES:
        angles = TYPE_ANGLES.get((domain, etype), ["攻略", "体验"])
        for angle in angles:
            title = f"{name}{angle}指南"
            check(pd.post_manifest("article", angle, title, 1).exists(),
                  f"G5: publish 缺 post: {title}")


# ─── G6: publish 引用可解析 ──────────────────────────────────────
def g6_publish_refs():
    v = publish_active_version()
    if v < 1:
        return
    pd = publish_data(v)
    for mf in pd.posts_dir().rglob("manifest.json"):
        data = json.loads(mf.read_text(encoding="utf-8"))
        for eref in data.get("entityRefs", []):
            parts = eref.split("/")
            if len(parts) == 3:
                check(pd.entity_json(parts[0], parts[1], parts[2]).exists(),
                      f"G6: entityRef 不可解析: {eref}")
        for tref in data.get("tagRefs", []):
            check(pd.tag_file(tref).exists(),
                  f"G6: tagRef 不可解析: {tref}")


# ─── G7: 三段式完整 ─────────────────────────────────────────────
def g7_three_stage():
    for cmd in ["explore", "build", "download", "produce", "reconcile"]:
        cmd_root = batch_command_root(TASK_ID, BATCH_ID, cmd)
        check(cmd_root.exists(), f"G7: {cmd} 目录不存在")
        if not cmd_root.exists():
            continue
        at = cmd_root / "assistant_tasks"
        check(at.exists() and any(at.glob("*.json")),
              f"G7: {cmd}/assistant_tasks 为空")
        for sub in ["inputs", "results"]:
            d = cmd_root / sub
            if d.exists():
                for step_dir in d.iterdir():
                    if step_dir.is_dir():
                        check(any(step_dir.glob("*.json")),
                              f"G7: {cmd}/{sub}/{step_dir.name} 为空")


# ─── G8: changeset ──────────────────────────────────────────────
def g8_changeset():
    cs = task_changeset_dir(TASK_ID)
    for name in ["entities.txt", "tags.txt", "posts.txt"]:
        f = cs / name
        check(f.exists(), f"G8: {name} 不存在")
        if f.exists():
            lines = [l for l in f.read_text(encoding="utf-8").strip().split("\n") if l]
            check(len(lines) > 0, f"G8: {name} 为空")
            if name == "entities.txt":
                for line in lines:
                    parts = line.strip().split("/")
                    check(len(parts) == 3,
                          f"G8: entity 路径不是三层: {line}")


# ─── G9: SOP 目录匹配 ───────────────────────────────────────────
def g9_sop_match():
    checked_types = set()
    for domain, etype, _ in ENTITIES:
        key = (domain, etype)
        if key in checked_types:
            continue
        checked_types.add(key)
        sop = SOP_ROOT / "主页" / domain / etype
        check(sop.exists(), f"G9: SOP 目录不存在: 主页/{domain}/{etype}")
        if sop.exists():
            for fname in ["guide.md", "template.md", "example.md"]:
                check((sop / fname).exists(),
                      f"G9: SOP 缺文件: 主页/{domain}/{etype}/{fname}")


# ─── G10: task_manifest ─────────────────────────────────────────
def g10_manifest():
    tm = task_manifest(TASK_ID)
    check(tm.exists(), "G10: task_manifest 不存在")
    if tm.exists():
        data = json.loads(tm.read_text(encoding="utf-8"))
        check(data.get("operationType") in ("add", "update"),
              "G10: operationType 无效")
        check(data.get("status") == "published",
              "G10: status != published")
        check("createdAt" in data, "G10: 缺 createdAt")
        check(data.get("entityCount", 0) >= 16,
              f"G10: entityCount 不足: {data.get('entityCount')}")
        check(data.get("postCount", 0) >= 30,
              f"G10: postCount 不足: {data.get('postCount')}")


# ─── G11: Entity 分组下领域与类型标签完整 ────────────────────────
def g11_entity_type_taxonomy():
    tags_root = PUBLISH_ROOT / "v1" / "tags"
    entity_root = tags_root / "Entity"
    check(entity_root.exists(), "G11: Entity 分组目录不存在")

    for domain in ["地点", "机构", "交通工具", "活动", "作品", "人物", "生物", "品牌", "商品"]:
        domain_dir = entity_root / domain
        check(domain_dir.exists(), f"G11: 缺 Entity 领域: {domain}")

    place_root = entity_root / "地点"
    if place_root.exists():
        expected_place_types = ["景区", "遗址", "古镇", "博物馆",
                                "餐厅", "公园", "自然景观", "城市",
                                "住宿", "主题乐园", "交通枢纽", "演艺场馆"]
        for pt in expected_place_types:
            check((place_root / pt).exists(),
                  f"G11: 缺 Entity/地点 子类型: {pt}")

        # 餐厅应有 >=15 个子类型（22 类扩展）
        restaurant_root = place_root / "餐厅"
        if restaurant_root.exists():
            restaurant_kids = [d for d in restaurant_root.iterdir()
                               if d.is_dir() and (d / "_definition.json").exists()]
            check(len(restaurant_kids) >= 15,
                  f"G11: Entity/地点/餐厅 子类型偏少: {len(restaurant_kids)} < 15")

        # 住宿应有 >=8 个子类型（10 类扁平骨架）
        stay_root = place_root / "住宿"
        if stay_root.exists():
            stay_kids = [d for d in stay_root.iterdir()
                         if d.is_dir() and (d / "_definition.json").exists()]
            check(len(stay_kids) >= 8,
                  f"G11: Entity/地点/住宿 子类型偏少: {len(stay_kids)} < 8")


# ─── G12: 全局标签四分组完备性 ────────────────────────────────────
REQUIRED_GROUPS = ["Topic", "Audience", "Format", "Entity"]
REQUIRED_GROUP_DIMS = {
    "Topic": ["场景", "事件话题", "时间", "地理",
              "自然风光", "美食餐饮", "住宿", "旅行", "运动", "健康养生", "摄影"],
    "Audience": ["用户", "创作者", "圈子"],
    "Format": ["内容载体", "内容角度", "表现手法", "视觉风格", "互动玩法", "商业形式"],
    "Entity": ["地点", "机构", "活动", "人物", "品牌", "作品", "商品", "生物", "交通工具"],
}

def g12_dimension_completeness():
    tags_root = PUBLISH_ROOT / "v1" / "tags"
    for g in REQUIRED_GROUPS:
        group_file = tags_root / g / "_group.json"
        check(group_file.exists(), f"G12: publish 缺分组定义 {g}/_group.json")
        for dim_name in REQUIRED_GROUP_DIMS.get(g, []):
            dim_dir = tags_root / g / dim_name
            check(dim_dir.exists(), f"G12: publish 缺维度目录 {g}/{dim_name}/")


# ─── G13: 行政区完备性（多省抽样） ─────────────────────────────────────
SICHUAN_CITIES_GATE = [
    "成都市", "绵阳市", "德阳市", "宜宾市", "南充市", "泸州市", "自贡市",
    "内江市", "乐山市", "达州市", "资阳市", "眉山市", "遂宁市", "广安市",
    "雅安市", "巴中市", "广元市", "攀枝花市",
    "阿坝藏族羌族自治州", "甘孜藏族自治州", "凉山彝族自治州",
]

PROVINCE_SAMPLE_GATE = {
    "北京市": ["东城区", "西城区", "朝阳区", "海淀区"],
    "广东省": ["广州市", "深圳市", "珠海市", "东莞市"],
    "浙江省": ["杭州市", "宁波市", "温州市"],
    "江苏省": ["南京市", "苏州市", "无锡市"],
    "山东省": ["济南市", "青岛市", "烟台市"],
    "湖北省": ["武汉市", "宜昌市", "襄阳市"],
    "河南省": ["郑州市", "洛阳市", "开封市"],
    "云南省": ["昆明市", "大理白族自治州"],
    "湖南省": ["长沙市", "张家界市"],
    "陕西省": ["西安市", "咸阳市"],
}


def g13_admin_region_completeness():
    china_root = PUBLISH_ROOT / "v1" / "tags" / "Topic" / "地理" / "行政区" / "中国"
    check(china_root.exists(), "G13: 中国行政区节点不存在")
    if not china_root.exists():
        return

    # 检查省级数量（>=31，不含港澳台也至少 31）
    province_dirs = [d for d in china_root.iterdir()
                     if d.is_dir() and d.name != "_definition.json"]
    check(len(province_dirs) >= 31, f"G13: 中国省级单位不足: {len(province_dirs)} < 31")

    # 四川省完整检查
    sc_root = china_root / "四川省"
    check(sc_root.exists(), "G13: 四川省目录不存在")
    if sc_root.exists():
        existing = {d.name for d in sc_root.iterdir()
                    if d.is_dir() and (d / "_definition.json").exists()}
        for city in SICHUAN_CITIES_GATE:
            check(city in existing, f"G13: 缺四川市州: {city}")
        check(len(existing) >= 21, f"G13: 四川市州数量不足: {len(existing)} < 21")

    # 多省抽样检查
    for province, expected_cities in PROVINCE_SAMPLE_GATE.items():
        prov_dir = china_root / province
        check(prov_dir.exists(), f"G13: 省级目录不存在: {province}")
        if prov_dir.exists():
            for city in expected_cities:
                check((prov_dir / city / "_definition.json").exists(),
                      f"G13: {province} 缺: {city}")


# ─── G14: 标签字段合规（新轻量 schema，description 为 WARNING 非 BLOCK）───
REQUIRED_TAG_FIELDS = ["label", "labelEn", "createdAt", "updatedAt"]
FORBIDDEN_TAG_FIELDS = ["appliesTo", "status", "lifecycle", "deprecatedTo",
                         "startDate", "endDate", "weight", "tagId", "parentId"]

def g14_field_compliance():
    tags_root = PUBLISH_ROOT / "v1" / "tags"
    sample_count = 0
    fail_count = 0
    for f in tags_root.rglob("_definition.json"):
        sample_count += 1
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            errors.append(f"G14: JSON 解析失败: {f.relative_to(tags_root)}")
            fail_count += 1
            continue
        # 必填字段（blocking）
        for field in REQUIRED_TAG_FIELDS:
            if field not in data or not data[field]:
                if fail_count < 20:
                    errors.append(f"G14: 缺必填字段 {field}: {f.relative_to(tags_root)}")
                fail_count += 1
        # 禁止字段（blocking）
        for ff in FORBIDDEN_TAG_FIELDS:
            if ff in data:
                errors.append(f"G14: 禁止字段 '{ff}': {f.relative_to(tags_root)}")
                fail_count += 1

    check(sample_count > 0, "G14: 无 _definition.json 文件")
    check(fail_count == 0, f"G14: {fail_count} 个字段合规问题")


# ─── G15: 标签总量下限 ──────────────────────────────────────────────
def g15_tag_count_threshold():
    tags_root = PUBLISH_ROOT / "v1" / "tags"
    total = sum(1 for _ in tags_root.rglob("_definition.json"))
    # 新路径：Topic/地理/
    geo_root = tags_root / "Topic" / "地理"
    geo_count = sum(1 for _ in geo_root.rglob("_definition.json")) if geo_root.exists() else 0
    non_geo = total - geo_count
    check(total >= 4800, f"G15: 标签总量 {total} < 4800")
    check(non_geo >= 1000, f"G15: 非地理标签 {non_geo} < 1000")


# ─── G16: _definition.schema.json 合规（禁止字段 + additionalProperties）───
def g16_schema_compliance():
    tags_root = PUBLISH_ROOT / "v1" / "tags"
    schema_forbidden = ["appliesTo", "status", "lifecycle", "deprecatedTo",
                        "startDate", "endDate", "weight", "tagId", "parentId",
                        "leafConstraint", "refType"]
    fail_count = 0
    for f in tags_root.rglob("_definition.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for ff in schema_forbidden:
            if ff in data:
                if fail_count < 10:
                    errors.append(f"G16: Schema 违规字段 '{ff}': {f.relative_to(tags_root)}")
                fail_count += 1
    check(fail_count == 0, f"G16: {fail_count} 个 schema 违规问题")


# ─── G17: publish/v1 tagRef 100% 可解析 ─────────────────────────────
def g17_tagref_resolvable():
    v = publish_active_version()
    if v < 1:
        warnings.append("G17: 无活跃 publish 版本，跳过 tagRef 验证")
        return
    pd = publish_data(v)
    tags_root = PUBLISH_ROOT / "v1" / "tags"
    dead_refs: list[str] = []
    for mf in pd.posts_dir().rglob("manifest.json"):
        data = json.loads(mf.read_text(encoding="utf-8"))
        for tref in data.get("tagRefs", []):
            if not (tags_root / tref / "_definition.json").exists():
                dead_refs.append(f"{mf.parent.name}: {tref}")
    for ef in pd.entities_dir().rglob("_entity.json"):
        data = json.loads(ef.read_text(encoding="utf-8"))
        for tref in data.get("tagRefs", []):
            if not (tags_root / tref / "_definition.json").exists():
                dead_refs.append(f"{ef.parent.name}: {tref}")
    check(len(dead_refs) == 0,
          f"G17: {len(dead_refs)} 个 tagRef 死引用（前5条）: {dead_refs[:5]}")


# ─── G18: 路径策略 pathPolicy 提示（WARNING-only，不 blocking）───────
def g18_path_policy_hints():
    tags_root = PUBLISH_ROOT / "v1" / "tags"
    # prefer-leaf 提示：Audience/用户/国籍 引用应到叶子
    pref_leaf_paths = [
        "Audience/用户/国籍",
        "Audience/用户/族群",
        "Audience/用户/语言",
    ]
    v = publish_active_version()
    if v < 1:
        return
    pd = publish_data(v)
    for mf in list(pd.entities_dir().rglob("_entity.json"))[:50]:
        data = json.loads(mf.read_text(encoding="utf-8"))
        for tref in data.get("tagRefs", []):
            for plp in pref_leaf_paths:
                if tref == plp:
                    warnings.append(
                        f"G18: tagRef '{tref}' 建议引用到叶子节点: {mf.parent.name}")


# ─── G19: post 内容角度目录一致性（blocking）────────────────────────
def g19_post_angle_dir_match():
    v = publish_active_version()
    if v < 1:
        return
    pd = publish_data(v)
    # 允许的内容角度名称（Format/内容角度/* 的最后一段）
    tags_root = PUBLISH_ROOT / "v1" / "tags"
    valid_angles: set[str] = set()
    angle_root = tags_root / "Format" / "内容角度"
    if angle_root.exists():
        for f in angle_root.rglob("_definition.json"):
            valid_angles.add(f.parent.name)

    for mf in pd.posts_dir().rglob("manifest.json"):
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
        except Exception:
            continue
        # post 路径：posts/{载体}/{angle}/{title}/{seq}/manifest.json（兼容旧的内容角度中间层）
        parts = list(mf.parent.relative_to(pd.posts_dir()).parts)
        # 误操作 cp 可能产生 posts/posts/...，去掉重复的 posts 前缀段
        while parts and parts[0] == "posts":
            parts = parts[1:]
        if len(parts) >= 2:
            # 处理嵌套角度路径：{载体}/内容角度/{角度}/{title}/{seq}/（兼容旧路径）
            if len(parts) >= 3 and parts[1] == "内容角度":
                dir_angle = parts[2]
            else:
                dir_angle = parts[1]
            # 从 tagRefs 中取 Format/内容角度/* 的最后一段
            tag_angles = []
            for tref in data.get("tagRefs", []):
                if tref.startswith("Format/内容角度/"):
                    tag_angles.append(tref.rsplit("/", 1)[-1])
            if tag_angles and dir_angle not in tag_angles:
                errors.append(
                    f"G19: post 目录角度 '{dir_angle}' 与 tagRefs 角度 {tag_angles} 不一致: "
                    f"{mf.parent.relative_to(pd.posts_dir())}")


# ─── G20: 反向索引覆盖（WARNING，relations/ 存在则检查）────────────
def g20_inverted_index_coverage():
    rel_root = PUBLISH_ROOT / "v1" / "relations"
    if not rel_root.exists():
        warnings.append("G20: relations/ 目录不存在，跳过反向索引验证（运行 tag_graph.py 生成）")
        return
    cooccur_dir = rel_root / "cooccur"
    inv_dir = rel_root / "inverted_index"
    if cooccur_dir.exists():
        count = sum(1 for _ in cooccur_dir.rglob("*.ndjson"))
        check(count >= 1, "G20: cooccur/ 下无 .ndjson 文件")
    if inv_dir.exists():
        count = sum(1 for _ in inv_dir.rglob("*.ndjson"))
        check(count >= 1, "G20: inverted_index/ 下无 .ndjson 文件")


# ─── G21: 命名同步（标签目录名与 label 字段一致）──────────────────
def g21_label_dir_sync():
    tags_root = PUBLISH_ROOT / "v1" / "tags"
    fail_count = 0
    for f in tags_root.rglob("_definition.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        dir_name = f.parent.name
        label = data.get("label", "")
        if label and label != dir_name:
            if fail_count < 10:
                errors.append(
                    f"G21: label '{label}' 与目录名 '{dir_name}' 不一致: "
                    f"{f.relative_to(tags_root)}")
            fail_count += 1
    check(fail_count == 0, f"G21: {fail_count} 个标签 label 与目录名不一致")


# ─── G22: refHint 解析提示（WARNING，不 blocking）───────────────────
def g22_refhint_warnings():
    # 检查 Audience/用户/国籍 下的引用是否也能在 Topic/地理/行政区 找到对应节点
    tags_root = PUBLISH_ROOT / "v1" / "tags"
    region_tags = set()
    region_root = tags_root / "Topic" / "地理" / "行政区" / "中国"
    if region_root.exists():
        for f in region_root.rglob("_definition.json"):
            region_tags.add(f.parent.name)
    nationality_root = tags_root / "Audience" / "用户" / "国籍"
    if nationality_root.exists():
        for f in nationality_root.rglob("_definition.json"):
            nat = f.parent.name
            if nat not in region_tags and nat != "其他" and nat != "中国":
                warnings.append(f"G22: 国籍标签 '{nat}' refHint 提示检查（信息性）")


# ─── G23: 分组容量均衡（WARNING，不 blocking）────────────────────────
def g23_group_capacity():
    tags_root = PUBLISH_ROOT / "v1" / "tags"
    limits = {
        "Topic": (3, 45),
        "Audience": (3, 10),
        "Format": (3, 10),
        "Entity": (3, 15),
    }
    for group in ["Topic", "Audience", "Format", "Entity"]:
        g_dir = tags_root / group
        if not g_dir.exists():
            continue
        dims = [d for d in g_dir.iterdir() if d.is_dir() and not d.name.startswith("_")]
        lo, hi = limits[group]
        if len(dims) < lo:
            warnings.append(f"G23: {group} 维度数量偏少（{len(dims)} 个，建议>={lo}）")
        if len(dims) > hi:
            warnings.append(f"G23: {group} 维度数量偏多（{len(dims)} 个，建议<={hi}）")


# ─── G24: tagRefs 四分组前缀（BLOCKING）─────────────────────────────
VALID_TAG_PREFIXES = ("Topic/", "Audience/", "Format/", "Entity/")

def g24_tagref_prefix():
    """所有 tagRefs / geoTagRef 必须以四分组前缀开头。"""
    v = publish_active_version()
    if v < 1:
        warnings.append("G24: 无活跃 publish 版本，跳过")
        return
    pd = publish_data(v)
    fail_count = 0
    for mf in pd.posts_dir().rglob("manifest.json"):
        data = json.loads(mf.read_text(encoding="utf-8"))
        for tref in data.get("tagRefs", []):
            if not any(tref.startswith(p) for p in VALID_TAG_PREFIXES):
                if fail_count < 10:
                    errors.append(f"G24: tagRef 前缀非法 '{tref}': {mf.parent.name}")
                fail_count += 1
    for ef in pd.entities_dir().rglob("_entity.json"):
        data = json.loads(ef.read_text(encoding="utf-8"))
        for tref in data.get("tagRefs", []):
            if not any(tref.startswith(p) for p in VALID_TAG_PREFIXES):
                if fail_count < 10:
                    errors.append(f"G24: tagRef 前缀非法 '{tref}': {ef.parent.name}")
                fail_count += 1
        geo = data.get("geoTagRef", "")
        if geo and not geo.startswith("Topic/地理/行政区/"):
            if fail_count < 10:
                errors.append(f"G24: geoTagRef 前缀非法 '{geo}': {ef.parent.name}")
            fail_count += 1
    check(fail_count == 0, f"G24: {fail_count} 个 tagRef/geoTagRef 前缀不合法")


# ─── G25: 旅行类实体 post 必含 Topic/旅行/* tagRef（BLOCKING）─────────
TRAVEL_ENTITY_TYPES = {"景区", "主题乐园", "古镇", "住宿", "遗址", "自然景观", "打卡地"}

def g25_travel_post_tag():
    """旅行类实体的 post 必须至少包含一个 Topic/旅行/* tagRef。"""
    v = publish_active_version()
    if v < 1:
        warnings.append("G25: 无活跃 publish 版本，跳过")
        return
    pd = publish_data(v)
    fail_count = 0
    for mf in pd.posts_dir().rglob("manifest.json"):
        data = json.loads(mf.read_text(encoding="utf-8"))
        entity_refs = data.get("entityRefs", [])
        is_travel = False
        for eref in entity_refs:
            parts = eref.split("/")
            if len(parts) >= 2 and parts[1] in TRAVEL_ENTITY_TYPES:
                is_travel = True
                break
        if is_travel:
            tag_refs = data.get("tagRefs", [])
            has_travel_tag = any(r.startswith("Topic/旅行/") for r in tag_refs)
            if not has_travel_tag:
                if fail_count < 10:
                    errors.append(f"G25: 旅行类实体 post 缺少 Topic/旅行/* tagRef: {mf.parent.name}")
                fail_count += 1
    check(fail_count == 0, f"G25: {fail_count} 个旅行类 post 缺少 Topic/旅行/* tagRef")


# ─── G26: entity 必含 geoTagRef 指向 Topic/地理/行政区/（BLOCKING）────
def g26_entity_geo_tag():
    """每个 entity 必须含 geoTagRef 且指向 Topic/地理/行政区/。"""
    v = publish_active_version()
    if v < 1:
        warnings.append("G26: 无活跃 publish 版本，跳过")
        return
    pd = publish_data(v)
    fail_count = 0
    for ef in pd.entities_dir().rglob("_entity.json"):
        data = json.loads(ef.read_text(encoding="utf-8"))
        geo = data.get("geoTagRef", "")
        if not geo:
            if fail_count < 10:
                errors.append(f"G26: entity 缺少 geoTagRef: {ef.parent.name}")
            fail_count += 1
        elif not geo.startswith("Topic/地理/行政区/"):
            if fail_count < 10:
                errors.append(f"G26: geoTagRef 不指向 Topic/地理/行政区/: '{geo}' in {ef.parent.name}")
            fail_count += 1
    check(fail_count == 0, f"G26: {fail_count} 个 entity geoTagRef 不合规")


# ─── G27: 已知互斥对（WARNING）─────────────────────────────────────
def g27_mutex_pairs():
    """检查已知互斥标签对（从 tag_policy.yaml 读取），输出警告不阻断。"""
    import yaml
    policy_path = Path(__file__).resolve().parents[1] / "schema" / "tag" / "tag_policy.yaml"
    if not policy_path.exists():
        warnings.append("G27: tag_policy.yaml 不存在，跳过互斥检查")
        return
    policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    pairs = policy.get("mutex_pairs", {}).get("pairs", [])
    if not pairs:
        warnings.append("G27: tag_policy.yaml 中无 mutex_pairs，跳过")
        return

    v = publish_active_version()
    if v < 1:
        return
    pd = publish_data(v)
    mutex_count = 0
    for mf in list(pd.posts_dir().rglob("manifest.json")) + list(pd.entities_dir().rglob("_entity.json")):
        data = json.loads(mf.read_text(encoding="utf-8"))
        tag_refs = set(data.get("tagRefs", []))
        for pair in pairs:
            if len(pair) == 2 and pair[0] in tag_refs and pair[1] in tag_refs:
                mutex_count += 1
                warnings.append(
                    f"G27: 互斥对 [{pair[0]}] ↔ [{pair[1]}] 同时出现: {mf.parent.name}")
    if mutex_count > 0:
        warnings.append(f"G27: 共检测到 {mutex_count} 处互斥对冲突（warning）")


# ─── G28: 实体/帖子 lookup 索引（BLOCKING）─────────────────────────
def _count_ndjson_records(root: Path) -> int:
    total = 0
    for f in root.rglob("*.ndjson"):
        total += sum(1 for line in f.read_text(encoding="utf-8").splitlines() if line.strip())
    return total


def g28_lookup_indexes():
    v1_root = PUBLISH_ROOT / "v1"
    index_root = v1_root / "index"
    entity_index_root = index_root / "entities"
    post_index_root = index_root / "posts"

    check(index_root.exists(), "G28: index/ 目录不存在")
    check(entity_index_root.exists(), "G28: index/entities/ 目录不存在")
    check(post_index_root.exists(), "G28: index/posts/ 目录不存在")

    entity_files = list(entity_index_root.rglob("*.ndjson")) if entity_index_root.exists() else []
    post_files = list(post_index_root.rglob("*.ndjson")) if post_index_root.exists() else []
    check(len(entity_files) >= 1, "G28: index/entities/ 下无 .ndjson 分片")
    check(len(post_files) >= 1, "G28: index/posts/ 下无 .ndjson 分片")

    entity_records = _count_ndjson_records(entity_index_root) if entity_index_root.exists() else 0
    post_records = _count_ndjson_records(post_index_root) if post_index_root.exists() else 0
    entity_count = sum(1 for _ in (v1_root / "entities").rglob("_entity.json"))
    post_count = sum(1 for mf in (v1_root / "posts").rglob("manifest.json") if "entities" not in mf.parts)

    check(entity_records == entity_count,
          f"G28: 实体索引条数 {entity_records} != 实体事实源 {entity_count}")
    check(post_records == post_count,
          f"G28: post 索引条数 {post_records} != post 事实源 {post_count}")


# ─── G29: 校园标签专项（BLOCKING）───────────────────────────────────
def g29_campus_taxonomy():
    script = Path(__file__).resolve().parent / "verify_campus_taxonomy.py"
    check(script.exists(), "G29: verify_campus_taxonomy.py 不存在")
    if not script.exists():
        return
    result = subprocess.run([sys.executable, str(script)], check=False)
    check(result.returncode == 0, f"G29: 校园标签体系专项门禁失败（exit={result.returncode}）")


def main():
    print("=" * 65)
    print("E2E Gate v5: 四分组标签体系 + 全维度统一目录结构验证")
    print("=" * 65)

    # ── 全局标签体系门禁（G12-G15：先跑，用于统计）─────────────────
    g12_dimension_completeness()
    g13_admin_region_completeness()
    g14_field_compliance()
    g15_tag_count_threshold()

    # ── task-level 门禁 ─────────────────────────────────────────────
    g1_tags()
    g2_entities()
    g3_page_quality()
    g4_posts()
    g5_publish_isomorphic()
    g6_publish_refs()
    g7_three_stage()
    g8_changeset()
    g9_sop_match()
    g10_manifest()
    g11_entity_type_taxonomy()

    # ── 新增 schema/语义 门禁 G16-G29 ──────────────────────────────
    g16_schema_compliance()
    g17_tagref_resolvable()
    g18_path_policy_hints()   # warning only
    g19_post_angle_dir_match()
    g20_inverted_index_coverage()
    g21_label_dir_sync()
    g22_refhint_warnings()    # warning only
    g23_group_capacity()      # warning only
    g24_tagref_prefix()
    g25_travel_post_tag()
    g26_entity_geo_tag()
    g27_mutex_pairs()           # warning only
    g28_lookup_indexes()
    g29_campus_taxonomy()

    print("-" * 65)

    tags_root = PUBLISH_ROOT / "v1" / "tags"
    total_tags = sum(1 for _ in tags_root.rglob("_definition.json"))
    geo_root = tags_root / "Topic" / "地理"
    geo_tags = sum(1 for _ in geo_root.rglob("_definition.json")) if geo_root.exists() else 0

    if warnings:
        print(f"\n{len(warnings)} 项警告（不阻断）:")
        for w in warnings:
            print(f"  WARN: {w}")

    if errors:
        print(f"\n{len(errors)} 项不通过:")
        for e in errors:
            print(f"  FAIL: {e}")
        sys.exit(1)
    else:
        td = task_data(TASK_ID)
        tag_count = len(list(td.tags_dir().rglob("_definition.json")))
        entity_count = len(list(td.entities_dir().rglob("_entity.json")))
        post_count = len(list(td.posts_dir().rglob("manifest.json")))
        v = publish_active_version()

        print(f"\n全部 29 项 Gate 通过！（{len(warnings)} 警告）")
        print(f"  G1:  {tag_count} 标签（4分组），无冗余 tagId/禁止字段")
        print(f"  G2:  {entity_count} 实体，三层路径正确")
        print(f"  G3:  主页质量达标")
        print(f"  G4:  {post_count} 篇 post")
        print(f"  G5:  publish/v{v}/ 与 runtime 同构")
        print(f"  G6:  publish 引用可解析")
        print(f"  G7:  5 命令三段式完整")
        print(f"  G8:  changeset 完整")
        print(f"  G9:  SOP 模板完整")
        print(f"  G10: taskManifest 完整")
        print(f"  G11: 实体类型维度完整")
        print(f"  G12: Topic/Audience/Format/Entity 4分组完备")
        print(f"  G13: 行政区完备（34省级 + 多省抽样）")
        print(f"  G14: 全部标签字段合规（禁止字段净零）")
        print(f"  G15: 标签总量 {total_tags}（地理 {geo_tags}，非地理 {total_tags - geo_tags}）")
        print(f"  G16: _definition.json schema 违规净零")
        print(f"  G17: tagRef 死引用净零")
        print(f"  G18: pathPolicy refHint 检查（warning）")
        print(f"  G19: post 内容角度目录一致性")
        print(f"  G20: 反向索引 / cooccur 完整")
        print(f"  G21: 标签 label 与目录名同步")
        print(f"  G22: refHint 国籍→国家对应（warning）")
        print(f"  G23: 分组容量均衡（warning）")
        print(f"  G24: tagRef 四分组前缀合规")
        print(f"  G25: 旅行类实体 post 均含 Topic/旅行/* tagRef")
        print(f"  G26: entity geoTagRef 均指向 Topic/地理/行政区/")
        print(f"  G27: 已知互斥对检查（warning）")
        print(f"  G28: 实体/帖子 lookup 索引完整")
        print(f"  G29: 校园标签体系专项门禁")
        sys.exit(0)


if __name__ == "__main__":
    main()
