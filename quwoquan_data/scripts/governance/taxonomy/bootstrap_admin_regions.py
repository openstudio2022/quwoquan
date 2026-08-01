"""生成行政区标签到 Topic/地理/行政区/

数据源：
  - 中国大陆 31 省级：quwoquan_data/reference/admin_regions/pca.json（民政部数据）
  - 港澳台 3 个省级及其下级：overseas_regions_asia.CHINA_SAR_TW_CITIES
  - 境外：overseas_regions_{asia,americas,europe}（量小、变化少，手工维护）

层级：行政区/国家/省级/市级/区县级（最多4层路径）
路径示例：Topic/地理/行政区/中国/四川省/成都市/武侯区

用法:
  python3 quwoquan_data/scripts/cli.py governance taxonomy bootstrap-admin-regions
  python3 quwoquan_data/scripts/cli.py governance taxonomy bootstrap-admin-regions --country 中国
  python3 quwoquan_data/scripts/cli.py governance taxonomy bootstrap-admin-regions --province 四川省
  python3 quwoquan_data/scripts/cli.py governance taxonomy bootstrap-admin-regions --dry-run
  python3 quwoquan_data/scripts/cli.py governance taxonomy bootstrap-admin-regions --stats

幂等执行：已存在节点跳过。
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core.paths import CONTROL_PLANE_TAXONOMY_ROOT, NOW_ISO
from governance.taxonomy.overseas_regions_asia import (
    ASIA_REGIONS,
    CHINA_SAR_TW_CITIES,
    CITY_STATE_CITIES,
)
from governance.taxonomy.overseas_regions_americas import AMERICAS_OCEANIA_REGIONS
from governance.taxonomy.overseas_regions_europe import EUROPE_MIDEAST_REGIONS

ALL_OVERSEAS_REGIONS = {
    **ASIA_REGIONS,
    **AMERICAS_OCEANIA_REGIONS,
    **EUROPE_MIDEAST_REGIONS,
}

TAGS_ROOT = CONTROL_PLANE_TAXONOMY_ROOT / "Topic" / "地理" / "行政区"
DATA_DIR = DATA_ROOT / "reference" / "admin_regions"

DRY_RUN = False
created = 0
skipped = 0


# 行政区标签的采集通道是 POI picker 与 EXIF GPS（见 Post.geoTagRef），消费方是地理召回
# 与就近交集。两个字段对整棵子树是常量，所以在这里统一写入而不是逐条声明。
GEO_COLLECTION_CHANNEL = "poi"
GEO_CONSUMED_BY = ["recall", "intersection"]


def ensure_tag(rel_path: str, label: str, label_en: str, desc: str):
    """写入或补全一个行政区标签。

    已存在的节点只补 collectionChannel / consumedBy 两个治理字段，不覆盖人工维护过的
    label / description，也不刷新 createdAt——否则每次 bootstrap 都会产生全树 diff。
    """
    global created, skipped
    p = TAGS_ROOT / rel_path / "_definition.json"
    if p.exists():
        skipped += 1
        _backfill_governance_fields(p)
        return
    if not DRY_RUN:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({
            "label": label, "labelEn": label_en,
            "description": desc,
            "collectionChannel": GEO_COLLECTION_CHANNEL,
            "consumedBy": GEO_CONSUMED_BY,
            "createdAt": NOW_ISO, "updatedAt": NOW_ISO,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    created += 1


def _backfill_governance_fields(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("collectionChannel") == GEO_COLLECTION_CHANNEL \
            and data.get("consumedBy") == GEO_CONSUMED_BY:
        return
    data["collectionChannel"] = GEO_COLLECTION_CHANNEL
    data["consumedBy"] = GEO_CONSUMED_BY
    data["updatedAt"] = NOW_ISO
    if not DRY_RUN:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ─────────────────────────────────────────────
# 省级英文名映射（34 个）
# ─────────────────────────────────────────────

PROVINCE_EN = {
    "北京市": "Beijing Municipality",
    "天津市": "Tianjin Municipality",
    "河北省": "Hebei Province",
    "山西省": "Shanxi Province",
    "内蒙古自治区": "Inner Mongolia Autonomous Region",
    "辽宁省": "Liaoning Province",
    "吉林省": "Jilin Province",
    "黑龙江省": "Heilongjiang Province",
    "上海市": "Shanghai Municipality",
    "江苏省": "Jiangsu Province",
    "浙江省": "Zhejiang Province",
    "安徽省": "Anhui Province",
    "福建省": "Fujian Province",
    "江西省": "Jiangxi Province",
    "山东省": "Shandong Province",
    "河南省": "Henan Province",
    "湖北省": "Hubei Province",
    "湖南省": "Hunan Province",
    "广东省": "Guangdong Province",
    "广西壮族自治区": "Guangxi Zhuang Autonomous Region",
    "海南省": "Hainan Province",
    "重庆市": "Chongqing Municipality",
    "四川省": "Sichuan Province",
    "贵州省": "Guizhou Province",
    "云南省": "Yunnan Province",
    "西藏自治区": "Tibet Autonomous Region",
    "陕西省": "Shaanxi Province",
    "甘肃省": "Gansu Province",
    "青海省": "Qinghai Province",
    "宁夏回族自治区": "Ningxia Hui Autonomous Region",
    "新疆维吾尔自治区": "Xinjiang Uyghur Autonomous Region",
    "香港特别行政区": "Hong Kong SAR",
    "澳门特别行政区": "Macao SAR",
    "台湾省": "Taiwan Province",
}

PROVINCE_DESC = {
    "北京市": "中国首都，政治文化中心",
    "天津市": "北方重要港口与工业城市",
    "河北省": "环绕京津，燕赵文化",
    "山西省": "三晋大地，煤炭资源大省",
    "内蒙古自治区": "草原牧区，蒙古族聚居区",
    "辽宁省": "东北老工业基地，辽沈文化",
    "吉林省": "东北腹地，长白山所在地",
    "黑龙江省": "中国最北省份，冰雪文化",
    "上海市": "中国最大经济城市，国际金融中心",
    "江苏省": "经济强省，吴越文化",
    "浙江省": "江南鱼米之乡，民营经济强省",
    "安徽省": "徽文化发源地，黄山所在地",
    "福建省": "闽南文化，海上丝绸之路起点",
    "江西省": "鄱阳湖畔，红色摇篮",
    "山东省": "儒家文化发源地，经济大省",
    "河南省": "中原文化，华夏文明发源地",
    "湖北省": "九省通衢，长江中游",
    "湖南省": "湘菜故乡，伟人辈出",
    "广东省": "改革开放前沿，粤港澳大湾区",
    "广西壮族自治区": "山水甲天下，壮族聚居区",
    "海南省": "中国最大经济特区，热带海岛",
    "重庆市": "山城火锅，长江上游经济中心",
    "四川省": "天府之国，西南重镇",
    "贵州省": "多彩贵州，喀斯特地貌",
    "云南省": "彩云之南，多民族省份",
    "西藏自治区": "世界屋脊，藏传佛教文化",
    "陕西省": "十三朝古都，丝绸之路起点",
    "甘肃省": "河西走廊，丝路重镇",
    "青海省": "三江源头，青藏高原东北部",
    "宁夏回族自治区": "塞上江南，回族聚居区",
    "新疆维吾尔自治区": "西域文化，维吾尔族聚居区",
    "香港特别行政区": "国际金融中心，一国两制",
    "澳门特别行政区": "东方蒙特卡洛，一国两制",
    "台湾省": "宝岛台湾",
}

# 直辖市列表（pca.json 中直辖市有 "市辖区" 中间层需跳过）
MUNICIPALITIES = {"北京市", "天津市", "上海市", "重庆市"}
DIRECT_COUNTY_GROUPS = {"省直辖县级行政区划", "自治区直辖县级行政区划"}


# ─────────────────────────────────────────────
# 中国行政区生成（数据驱动）
# ─────────────────────────────────────────────

def gen_china(filter_province: str | None = None):
    """从 pca.json 生成中国全部行政区标签"""
    pca_file = DATA_DIR / "pca.json"
    if not pca_file.exists():
        print(f"ERROR: 数据文件不存在: {pca_file}", file=sys.stderr)
        print("请先运行数据下载步骤", file=sys.stderr)
        sys.exit(1)

    pca = json.loads(pca_file.read_text("utf-8"))

    ensure_tag("中国", "中国", "China", "中华人民共和国行政区域")

    for province, cities_data in pca.items():
        if filter_province and province != filter_province:
            continue

        p_en = PROVINCE_EN.get(province, province)
        p_desc = PROVINCE_DESC.get(province, f"{province}行政区域")
        ensure_tag(f"中国/{province}", province, p_en, p_desc)

        if province in MUNICIPALITIES:
            # 直辖市：pca.json 中结构为 {省: {"市辖区": [区列表], "县": [县列表]}}
            # 直辖市下的 "市辖区"/"县" 是虚拟中间层，跳过直接取区县
            if isinstance(cities_data, dict):
                for _group_name, districts in cities_data.items():
                    if isinstance(districts, list):
                        for district in districts:
                            ensure_tag(
                                f"中国/{province}/{district}",
                                district, district, f"{province}{district}"
                            )
                    elif isinstance(districts, dict):
                        for district in districts:
                            ensure_tag(
                                f"中国/{province}/{district}",
                                district, district, f"{province}{district}"
                            )
        else:
            # 普通省/自治区：{省: {市: [区县列表]}}
            if isinstance(cities_data, dict):
                for city, districts in cities_data.items():
                    if city in DIRECT_COUNTY_GROUPS:
                        if isinstance(districts, list):
                            for county_city in districts:
                                ensure_tag(
                                    f"中国/{province}/{county_city}",
                                    county_city, county_city, f"{province}{county_city}"
                                )
                        elif isinstance(districts, dict):
                            for county_city in districts:
                                ensure_tag(
                                    f"中国/{province}/{county_city}",
                                    county_city, county_city, f"{province}{county_city}"
                                )
                        continue
                    ensure_tag(
                        f"中国/{province}/{city}",
                        city, city, f"{province}{city}"
                    )
                    if isinstance(districts, list):
                        for district in districts:
                            ensure_tag(
                                f"中国/{province}/{city}/{district}",
                                district, district, f"{city}{district}"
                            )
                    elif isinstance(districts, dict):
                        for district in districts:
                            ensure_tag(
                                f"中国/{province}/{city}/{district}",
                                district, district, f"{city}{district}"
                            )

    # 港澳台（pca.json 不含，手动补充；下级城市见 CHINA_SAR_TW_CITIES）
    for province in ("香港特别行政区", "澳门特别行政区", "台湾省"):
        if filter_province and filter_province != province:
            continue
        ensure_tag(f"中国/{province}", province,
                   PROVINCE_EN[province], PROVINCE_DESC[province])
        for city, (city_en, city_desc) in CHINA_SAR_TW_CITIES[province].items():
            ensure_tag(f"中国/{province}/{city}", city, city_en, city_desc)


# ─────────────────────────────────────────────
# 境外行政区（手工定义，量小、变化少）
# ─────────────────────────────────────────────

def gen_overseas(filter_country: str | None = None):
    """生成境外三层行政区标签：国家 / 一级行政区 / 城市。

    城邦与岛国（新加坡、马尔代夫）没有有意义的一级行政区，城市直接挂在国家下，
    表里以空的一级行政区表表达。
    """
    for country, (country_en, country_desc, regions) in ALL_OVERSEAS_REGIONS.items():
        if filter_country and filter_country != country:
            continue
        ensure_tag(country, country, country_en, country_desc)
        for region, (region_en, region_desc, cities) in regions.items():
            ensure_tag(f"{country}/{region}", region, region_en, region_desc)
            for city, (city_en, city_desc) in cities.items():
                ensure_tag(f"{country}/{region}/{city}", city, city_en, city_desc)
        for city, (city_en, city_desc) in CITY_STATE_CITIES.get(country, {}).items():
            ensure_tag(f"{country}/{city}", city, city_en, city_desc)


# ─────────────────────────────────────────────
# 数据统计
# ─────────────────────────────────────────────

def print_stats():
    pca_file = DATA_DIR / "pca.json"
    if not pca_file.exists():
        print(f"ERROR: {pca_file} 不存在", file=sys.stderr)
        sys.exit(1)

    pca = json.loads(pca_file.read_text("utf-8"))
    province_count = len(pca) + 3  # +港澳台
    city_count = 0
    district_count = 0

    for province, cities_data in pca.items():
        if province in MUNICIPALITIES:
            if isinstance(cities_data, dict):
                for _group, districts in cities_data.items():
                    if isinstance(districts, (list, dict)):
                        district_count += len(districts)
        else:
            if isinstance(cities_data, dict):
                city_count += len(cities_data)
                for _city, districts in cities_data.items():
                    if isinstance(districts, (list, dict)):
                        district_count += len(districts)

    sar_tw_cities = sum(len(cities) for cities in CHINA_SAR_TW_CITIES.values())
    overseas_nodes = 0
    for country, (_en, _desc, regions) in ALL_OVERSEAS_REGIONS.items():
        overseas_nodes += 1 + len(regions)
        overseas_nodes += sum(len(cities) for _r, (_re, _rd, cities) in regions.items())
        overseas_nodes += len(CITY_STATE_CITIES.get(country, {}))

    total_china = 1 + province_count + city_count + district_count + sar_tw_cities
    total = total_china + overseas_nodes

    print("=== 行政区数据源统计 ===")
    print(f"中国省级: {province_count}（含港澳台）")
    print(f"中国地级: {city_count}")
    print(f"中国县级: {district_count}")
    print(f"港澳台下级: {sar_tw_cities}")
    print(f"中国总计: {total_china}（含根节点）")
    print(f"境外国家: {len(ALL_OVERSEAS_REGIONS)}")
    print(f"境外节点: {overseas_nodes}")
    print(f"全部总计: {total}")
    print(f"境外占比: {overseas_nodes / total:.1%}")


# ─────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────

def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="生成行政区标签到 Topic/地理/行政区/")
    parser.add_argument("--country", default=None, help="国家名（如 中国、日本、泰国）")
    parser.add_argument("--province", default=None, help="省份名（如 四川省），仅生成该省")
    parser.add_argument("--dry-run", action="store_true", help="仅统计不写盘")
    parser.add_argument("--stats", action="store_true", help="打印数据源统计后退出")
    args = parser.parse_args(argv)

    if args.stats:
        print_stats()
        return

    global DRY_RUN
    DRY_RUN = args.dry_run

    if args.country in (None, "中国"):
        gen_china(filter_province=args.province)

    # --province 只对中国有意义；指定它时不触碰境外子树。
    if args.province is None and args.country != "中国":
        gen_overseas(filter_country=args.country)

    print(f"\n行政区生成完成：新增 {created}，跳过（已存在）{skipped}")
    total = created + skipped
    print(f"总节点数：{total}")
    if DRY_RUN:
        print("[dry-run 模式，未写盘]")
