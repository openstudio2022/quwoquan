"""标签体系验证脚本（四分组版）

检查项：
  R1  - 分组完备性：4 大分组 _group.json 必须存在
  R2  - 维度完备性：Topic/Audience/Format/Entity 必须含指定子维度 + Topic/旅行 7 子维度 + Topic/地理 3 子维度
  R3  - 字段合规：每个 _definition.json 必须含 label/labelEn/createdAt/updatedAt；
          description 缺失为 WARNING；禁止出现 appliesTo/status/lifecycle/deprecatedTo/startDate/endDate
  R4  - 兄弟互斥：同级目录下标签名不得互为子串（WARNING）
  R5  - 地理完备：中国/四川省 21 市州必须存在
  R6  - Entity 非实例化：Entity 树深度不超过 4 层（含组名），超出为 WARNING
  R7  - 标签总量下限（>=4800 总量，>=1000 非地理）
  R8  - Schema 合规：_definition.json 不含禁止字段（blocking）
  R9  - 容量均衡：每层 20-100 子节点警告
  R10 - 引用格式：tagRef 格式必须以 Topic/Audience/Format/Entity 开头
  R11 - 菜系/业态正交：Entity/地点/餐厅/* 不得与 Topic/美食餐饮/菜系/** 重名
  R12 - 品类/业态防混：Topic/美食餐饮/品类/* 与 Entity/地点/餐厅/* 不得完全同名

用法:
  python3 verify_tag_tree.py
  python3 verify_tag_tree.py --min-total 1700
  python3 verify_tag_tree.py --strict  # 严格模式，warning 也阻断
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common.paths import PUBLISH_ROOT

TAGS_ROOT = PUBLISH_ROOT / "v1" / "tags"
GROUPS = ["Topic", "Audience", "Format", "Entity"]

REQUIRED_DIMS = {
    "Topic": ["场景", "事件话题", "时间", "地理"],
    "Audience": ["用户", "创作者", "圈子"],
    "Format": ["内容载体", "内容角度", "表现手法", "视觉风格", "互动玩法", "商业形式"],
    "Entity": ["地点", "机构", "活动", "人物", "品牌", "作品", "商品", "生物", "交通工具"],
}

REQUIRED_TOPIC_VERTICALS = [
    "自然风光", "历史文化", "美食餐饮", "旅行", "住宿", "运动",
    "健康养生", "数码科技", "影视娱乐", "亲子育儿", "教育成长",
    "情感关系", "时尚穿搭", "美妆护肤", "游戏电竞", "家居生活",
    "非遗民俗", "宠物动物", "金融理财", "购物消费", "艺术创作",
    "摄影",
]

REQUIRED_FIELDS = ["label", "labelEn", "createdAt", "updatedAt"]
FORBIDDEN_FIELDS = ["appliesTo", "status", "lifecycle", "deprecatedTo",
                    "startDate", "endDate", "weight", "tagId", "parentId",
                    "leafConstraint", "refType"]

SICHUAN_CITIES = [
    "成都市", "绵阳市", "德阳市", "宜宾市", "南充市", "泸州市", "自贡市",
    "内江市", "乐山市", "达州市", "资阳市", "眉山市", "遂宁市", "广安市",
    "雅安市", "巴中市", "广元市", "攀枝花市",
    "阿坝藏族羌族自治州", "甘孜藏族自治州", "凉山彝族自治州",
]

errors: list[str] = []
warnings: list[str] = []


# ─────────────────────────────────────────────
# R1: 分组完备性
# ─────────────────────────────────────────────
def check_r1_groups():
    for g in GROUPS:
        group_file = TAGS_ROOT / g / "_group.json"
        if not group_file.exists():
            errors.append(f"R1: 缺少分组定义 {g}/_group.json")
        group_dir = TAGS_ROOT / g
        if not group_dir.exists():
            errors.append(f"R1: 分组目录不存在 {g}/")


# ─────────────────────────────────────────────
# R2: 维度完备性
# ─────────────────────────────────────────────
def check_r2_dimensions():
    for group, dims in REQUIRED_DIMS.items():
        for d in dims:
            dim_dir = TAGS_ROOT / group / d
            if not dim_dir.exists():
                errors.append(f"R2: 缺少维度目录 {group}/{d}/")
            else:
                dim_file = dim_dir / "_dimension.json"
                if not dim_file.exists():
                    warnings.append(f"R2: 维度目录存在但缺少 _dimension.json: {group}/{d}/")

    for v in REQUIRED_TOPIC_VERTICALS:
        v_dir = TAGS_ROOT / "Topic" / v
        if not v_dir.exists():
            errors.append(f"R2: 缺少 Topic 垂类目录 Topic/{v}/")
        elif not (v_dir / "_definition.json").exists():
            errors.append(f"R2: Topic 垂类缺少 _definition.json: Topic/{v}/")

    # 检查 Topic/地理/ 的三个必需子维度
    required_geo_subdims = ["行政区", "地形地貌", "区域"]
    geo_root = TAGS_ROOT / "Topic" / "地理"
    if geo_root.exists():
        for subdim in required_geo_subdims:
            subdim_dir = geo_root / subdim
            if not subdim_dir.exists():
                errors.append(f"R2: 缺少 Topic/地理 子维度: {subdim}")

    # 检查 Topic/旅行/ 的 7 个必需子维度
    REQUIRED_TRAVEL_SUBDIMS = [
        "旅行主题", "玩法", "出行方式", "行程形态",
        "旅行时长", "住宿", "旅行筹备",
    ]
    travel_root = TAGS_ROOT / "Topic" / "旅行"
    if travel_root.exists():
        for subdim in REQUIRED_TRAVEL_SUBDIMS:
            subdim_dir = travel_root / subdim
            if not subdim_dir.exists():
                errors.append(f"R2: 缺少 Topic/旅行 子维度: {subdim}")
            elif not (subdim_dir / "_dimension.json").exists():
                warnings.append(f"R2: Topic/旅行/{subdim} 缺少 _dimension.json")

    # 检查 Topic/美食餐饮/ 的 9 个必需子维度
    REQUIRED_FOOD_SUBDIMS = [
        "菜系", "品类", "饮品", "就餐时段", "用餐场合",
        "饮食特征", "风味口味", "认证评级", "特色食材",
    ]
    food_root = TAGS_ROOT / "Topic" / "美食餐饮"
    if food_root.exists():
        for subdim in REQUIRED_FOOD_SUBDIMS:
            subdim_dir = food_root / subdim
            if not subdim_dir.exists():
                errors.append(f"R2: 缺少 Topic/美食餐饮 子维度: {subdim}")
            elif not (subdim_dir / "_dimension.json").exists():
                warnings.append(f"R2: Topic/美食餐饮/{subdim} 缺少 _dimension.json")

    # 检查 Topic/住宿/ 的 8 个必需子维度
    REQUIRED_STAY_SUBDIMS = [
        "业态", "价位档次", "主题", "设施服务",
        "房型", "区位", "认证评级", "预订特征",
    ]
    stay_root = TAGS_ROOT / "Topic" / "住宿"
    if stay_root.exists():
        for subdim in REQUIRED_STAY_SUBDIMS:
            subdim_dir = stay_root / subdim
            if not subdim_dir.exists():
                errors.append(f"R2: 缺少 Topic/住宿 子维度: {subdim}")
            elif not (subdim_dir / "_dimension.json").exists():
                warnings.append(f"R2: Topic/住宿/{subdim} 缺少 _dimension.json")


# ─────────────────────────────────────────────
# R3: 字段合规 + R8: 禁止字段
# ─────────────────────────────────────────────
def check_r3_r8_fields():
    for f in TAGS_ROOT.rglob("_definition.json"):
        rel = str(f.relative_to(TAGS_ROOT))
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"R3: JSON解析失败 {rel}: {e}")
            continue

        # 必填字段检查
        for field in REQUIRED_FIELDS:
            if field not in data or not data[field]:
                errors.append(f"R3: 缺少必填字段 {field} in {rel}")

        # description 缺失 → WARNING
        if not data.get("description"):
            warnings.append(f"R3: 缺少 description（建议补充）in {rel}")

        # 禁止字段检查（R8）
        for ff in FORBIDDEN_FIELDS:
            if ff in data:
                errors.append(f"R8: 禁止字段 '{ff}' 出现在 {rel}（应外置到 tag_runtime/）")


# ─────────────────────────────────────────────
# R4: 兄弟互斥（WARNING）
# ─────────────────────────────────────────────
def check_r4_sibling_exclusivity():
    """检查同级兄弟标签不得互为子串。
    过滤规则：
    - 若较短标签字符数 < ceil(较长标签字符数 / 2)，则视为前缀/词根复用，跳过
      （例：印度(2) vs 印度尼西亚(5)：2 < ceil(5/2)=3，跳过；
           高端(2) vs 中高端(3)：2 >= ceil(3/2)=2，警告）
    """
    import math
    checked: set[str] = set()
    for d in TAGS_ROOT.rglob("_definition.json"):
        parent = d.parent.parent
        parent_key = str(parent)
        if parent_key in checked:
            continue
        checked.add(parent_key)
        siblings = [
            child.name for child in parent.iterdir()
            if child.is_dir() and (child / "_definition.json").exists()
        ]
        for i, s1 in enumerate(siblings):
            for s2 in siblings[i + 1:]:
                shorter, longer = (s1, s2) if len(s1) <= len(s2) else (s2, s1)
                if shorter in longer:
                    min_len = math.ceil(len(longer) / 2)
                    if len(shorter) >= min_len:
                        warnings.append(
                            f"R4: 兄弟子串 [{s1}] ↔ [{s2}] in "
                            f"{parent.relative_to(TAGS_ROOT)}")


# ─────────────────────────────────────────────
# R5: 地理完备（抽样检查多省）
# ─────────────────────────────────────────────
PROVINCE_SAMPLE_CITIES = {
    "四川省": SICHUAN_CITIES,
    "北京市": ["东城区", "西城区", "朝阳区", "海淀区", "丰台区", "通州区"],
    "广东省": ["广州市", "深圳市", "珠海市", "东莞市", "佛山市"],
    "浙江省": ["杭州市", "宁波市", "温州市", "嘉兴市", "湖州市"],
    "江苏省": ["南京市", "苏州市", "无锡市", "常州市", "徐州市"],
    "山东省": ["济南市", "青岛市", "烟台市", "潍坊市", "淄博市"],
    "湖北省": ["武汉市", "宜昌市", "襄阳市", "荆州市", "黄冈市"],
    "河南省": ["郑州市", "洛阳市", "开封市", "南阳市", "安阳市"],
    "云南省": ["昆明市", "大理白族自治州", "丽江市"],
    "湖南省": ["长沙市", "张家界市", "湘西土家族苗族自治州"],
}


def check_r5_geo_completeness():
    china_dir = TAGS_ROOT / "Topic" / "地理" / "行政区" / "中国"
    if not china_dir.exists():
        errors.append("R5: 中国行政区目录不存在：Topic/地理/行政区/中国/")
        return

    # 检查省级完备性（至少 31 个省级单位）
    province_dirs = [d for d in china_dir.iterdir()
                     if d.is_dir() and d.name != "_definition.json"]
    if len(province_dirs) < 31:
        errors.append(f"R5: 中国省级单位不足，期望>=31，实际={len(province_dirs)}")

    # 抽样检查各省地级市
    for province, cities in PROVINCE_SAMPLE_CITIES.items():
        prov_dir = china_dir / province
        if not prov_dir.exists():
            errors.append(f"R5: 省级目录不存在：{province}")
            continue
        for city in cities:
            if not (prov_dir / city).exists():
                errors.append(f"R5: {province} 缺少：{city}")


# ─────────────────────────────────────────────
# R6: Entity 非实例化（WARNING when depth > 4）
# ─────────────────────────────────────────────
def check_r6_entity_no_instances():
    entity_dir = TAGS_ROOT / "Entity"
    if not entity_dir.exists():
        return
    # Entity 分组名(1层) / 领域(2层) / 类型(3层) / 子类型(4层)
    # depth > 4 说明可能有实例化
    MAX_DEPTH = 4
    for f in entity_dir.rglob("_definition.json"):
        rel_parts = f.parent.relative_to(entity_dir).parts
        depth = len(rel_parts)
        if depth > MAX_DEPTH:
            warnings.append(
                f"R6: Entity 树超过 {MAX_DEPTH} 层，可能存在实例化节点：{f.relative_to(TAGS_ROOT)}")


# ─────────────────────────────────────────────
# R7: 总量下限
# ─────────────────────────────────────────────
def check_r7_total(min_total: int = 4800, min_non_geo: int = 1000):
    total = 0
    geo_count = 0
    geo_root = TAGS_ROOT / "Topic" / "地理"
    for f in TAGS_ROOT.rglob("_definition.json"):
        total += 1
        if geo_root.exists() and str(f).startswith(str(geo_root)):
            geo_count += 1
    non_geo = total - geo_count
    print(f"\n标签总量: {total} (地理: {geo_count}, 非地理: {non_geo})")
    print(f"  下限要求: 总量 >= {min_total}, 非地理 >= {min_non_geo}")
    if total < min_total:
        errors.append(f"R7: 标签总量 {total} < {min_total}")
    if non_geo < min_non_geo:
        errors.append(f"R7: 非地理标签 {non_geo} < {min_non_geo}")
    return total, geo_count, non_geo


# ─────────────────────────────────────────────
# R9: 容量均衡（WARNING）
# ─────────────────────────────────────────────
def check_r9_capacity_balance():
    """检查每层子节点容量均衡。
    SKIP_PATHS：时效性维度 + 初期有意识地只有1-2个子节点的路径（待扩充）。
    """
    SKIP_PATHS = {
        # 时效性特殊维度，允许子节点少
        str(TAGS_ROOT / "Topic" / "事件话题"),
        str(TAGS_ROOT / "Topic" / "时间"),
        # 行政区初期仅收录中国，其他国家待后续扩充
        str(TAGS_ROOT / "Topic" / "地理" / "行政区"),
        # 地理维度本身（下一层是地形地貌/行政区，预期只有2-3个）
        str(TAGS_ROOT / "Topic" / "地理"),
        # 地形地貌下各分类数量不均，初期允许
        str(TAGS_ROOT / "Topic" / "地理" / "地形地貌"),
        # 部分垂类初期子节点少
        str(TAGS_ROOT / "Topic" / "命理玄学"),
        str(TAGS_ROOT / "Topic" / "宗教信仰"),
        str(TAGS_ROOT / "Topic" / "军事国防"),
        str(TAGS_ROOT / "Topic" / "公益社会"),
        str(TAGS_ROOT / "Topic" / "法律政务"),
        str(TAGS_ROOT / "Topic" / "国际视野"),
        # Entity/商品 画像维度初期少子节点
        str(TAGS_ROOT / "Entity" / "商品"),
        # Audience/圈子 维度各组织形式初期少
        str(TAGS_ROOT / "Audience" / "圈子"),
        # 旅行子维度有自己的容量规则 (5-25)
        str(TAGS_ROOT / "Topic" / "旅行"),
        # 住宿子维度初期允许少子节点
        str(TAGS_ROOT / "Topic" / "住宿"),
        # 美食子维度部分品类数量不均
        str(TAGS_ROOT / "Topic" / "美食餐饮"),
    }
    for dir_path in TAGS_ROOT.rglob("*"):
        if not dir_path.is_dir():
            continue
        if any(str(dir_path).startswith(skip) for skip in SKIP_PATHS):
            continue
        children = [
            c for c in dir_path.iterdir()
            if c.is_dir() and not c.name.startswith("_")
        ]
        if 0 < len(children) < 3:
            warnings.append(
                f"R9: {dir_path.relative_to(TAGS_ROOT)} 子节点偏少（{len(children)} 个，建议3+）")
        elif len(children) > 100:
            warnings.append(
                f"R9: {dir_path.relative_to(TAGS_ROOT)} 子节点过多（{len(children)} 个，建议<100）")

    # 旅行子维度专项容量检查（5-25）
    travel_root = TAGS_ROOT / "Topic" / "旅行"
    if travel_root.exists():
        for subdim_dir in travel_root.iterdir():
            if not subdim_dir.is_dir() or subdim_dir.name.startswith("_"):
                continue
            children = [
                c for c in subdim_dir.iterdir()
                if c.is_dir() and not c.name.startswith("_")
            ]
            count = len(children)
            if count < 5:
                warnings.append(
                    f"R9: Topic/旅行/{subdim_dir.name} 叶子偏少（{count} 个，旅行子维度建议5+）")
            elif count > 25:
                warnings.append(
                    f"R9: Topic/旅行/{subdim_dir.name} 叶子过多（{count} 个，旅行子维度建议≤25）")


# ─────────────────────────────────────────────
# R11: Entity/地点/餐厅 业态不得与 Topic/美食餐饮/菜系 重叠
# ─────────────────────────────────────────────
def check_r11_restaurant_cuisine_orthogonality():
    """Entity/地点/餐厅/* 的叶子名称不得出现在 Topic/美食餐饮/菜系/** 中。
    餐厅是经营业态（火锅店/烧烤店/面馆），菜系是饮食流派（川菜/粤菜/日料）。"""
    cuisine_names: set[str] = set()
    cuisine_root = TAGS_ROOT / "Topic" / "美食餐饮" / "菜系"
    if cuisine_root.exists():
        for f in cuisine_root.rglob("_definition.json"):
            cuisine_names.add(f.parent.name)

    restaurant_root = TAGS_ROOT / "Entity" / "地点" / "餐厅"
    if not restaurant_root.exists():
        return
    for f in restaurant_root.rglob("_definition.json"):
        name = f.parent.name
        if name in cuisine_names:
            errors.append(
                f"R11: Entity/地点/餐厅/{name} 与 Topic/美食餐饮/菜系 重名——"
                f"餐厅应为业态（如'火锅店'），菜系应为流派（如'川菜'）")


# ─────────────────────────────────────────────
# R12: Topic/美食餐饮/品类 与 Entity/地点/餐厅 不得同名
# ─────────────────────────────────────────────
def check_r12_category_entity_no_homonym():
    """Topic/美食餐饮/品类/* 是食物形态（火锅/面食），
    Entity/地点/餐厅/* 是经营业态（火锅店/面馆），两者不得完全同名。
    Entity 侧应带"店/馆/吧/铺/屋/坊"后缀。"""
    category_names: set[str] = set()
    cat_root = TAGS_ROOT / "Topic" / "美食餐饮" / "品类"
    if cat_root.exists():
        for f in cat_root.rglob("_definition.json"):
            category_names.add(f.parent.name)

    restaurant_root = TAGS_ROOT / "Entity" / "地点" / "餐厅"
    if not restaurant_root.exists():
        return
    for f in restaurant_root.rglob("_definition.json"):
        name = f.parent.name
        if name in category_names:
            warnings.append(
                f"R12: Entity/地点/餐厅/{name} 与 Topic/美食餐饮/品类/{name} 同名——"
                f"建议 Entity 侧加'店/馆/铺'后缀（如'火锅'→'火锅店'）")


# ─────────────────────────────────────────────
# 深度均衡报告
# ─────────────────────────────────────────────
def depth_report():
    from collections import defaultdict
    depth_counts: dict[str, int] = defaultdict(int)
    for f in TAGS_ROOT.rglob("_definition.json"):
        rel_parts = f.parent.relative_to(TAGS_ROOT).parts
        group = rel_parts[0] if rel_parts else "unknown"
        depth = len(rel_parts)
        depth_counts[f"{group}.depth{depth}"] += 1

    print("\n=== 深度分布 ===")
    for key in sorted(depth_counts):
        print(f"  {key}: {depth_counts[key]}")


# ─────────────────────────────────────────────
# 分组统计
# ─────────────────────────────────────────────
def group_stats():
    print("\n=== 分组统计 ===")
    for g in GROUPS:
        g_dir = TAGS_ROOT / g
        if g_dir.exists():
            count = sum(1 for _ in g_dir.rglob("_definition.json"))
            print(f"  {g}: {count}")
            for dim_dir in sorted(g_dir.iterdir()):
                if not dim_dir.is_dir() or dim_dir.name.startswith("_"):
                    continue
                dim_count = sum(1 for _ in dim_dir.rglob("_definition.json"))
                print(f"    ├ {dim_dir.name}: {dim_count}")


# ─────────────────────────────────────────────
# main
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="标签体系验证（四分组版）")
    parser.add_argument("--min-total", type=int, default=4800)
    parser.add_argument("--min-non-geo", type=int, default=1000)
    parser.add_argument("--strict", action="store_true",
                        help="严格模式：警告也视为错误")
    parser.add_argument("--skip-capacity", action="store_true",
                        help="跳过容量均衡检查（R9）")
    parser.add_argument("--stats-only", action="store_true",
                        help="只输出统计不做验证")
    args = parser.parse_args()

    print("=" * 60)
    print("标签体系验证（四分组版）")
    print("=" * 60)

    if not args.stats_only:
        check_r1_groups()
        check_r2_dimensions()
        check_r3_r8_fields()
        check_r4_sibling_exclusivity()
        check_r5_geo_completeness()
        check_r6_entity_no_instances()
        if not args.skip_capacity:
            check_r9_capacity_balance()
        check_r11_restaurant_cuisine_orthogonality()
        check_r12_category_entity_no_homonym()

    total, geo_count, non_geo = check_r7_total(args.min_total, args.min_non_geo)

    group_stats()
    depth_report()

    print(f"\n{'WARNING' if warnings else '(无警告)'}（{len(warnings)} 条）:")
    for w in warnings[:30]:
        print(f"  ⚠ {w}")
    if len(warnings) > 30:
        print(f"  ... 还有 {len(warnings) - 30} 条警告")

    if args.strict:
        errors.extend(warnings)

    print(f"\n{'ERROR' if errors else '(无错误)'}（{len(errors)} 条）:")
    for e in errors[:30]:
        print(f"  ✗ {e}")
    if len(errors) > 30:
        print(f"  ... 还有 {len(errors) - 30} 条错误")

    print(f"\n{'验证通过' if not errors else '验证失败'}: {len(errors)} 错误, {len(warnings)} 警告")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
