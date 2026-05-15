"""生成行政区标签到 Topic/地理/行政区/

数据源：
  - 中国大陆 31 省级：quwoquan_data/data/admin_regions/pca.json（民政部数据）
  - 港澳台 3 个省级：脚本内手工定义（暂无下级数据）
  - 泰国/欧洲：脚本内手工定义（量小、变化少）

层级：行政区/国家/省级/市级/区县级（最多4层路径）
路径示例：Topic/地理/行政区/中国/四川省/成都市/武侯区

用法:
  python3 bootstrap_admin_regions.py                      # 全量生成
  python3 bootstrap_admin_regions.py --country 中国        # 只生成中国
  python3 bootstrap_admin_regions.py --province 四川省     # 只补全四川省
  python3 bootstrap_admin_regions.py --dry-run             # 仅统计
  python3 bootstrap_admin_regions.py --stats               # 只打印数据源统计

幂等执行：已存在节点跳过。
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common.paths import PUBLISH_ROOT, NOW_ISO

TAGS_ROOT = PUBLISH_ROOT / "v1" / "tags" / "Topic" / "地理" / "行政区"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "admin_regions"

DRY_RUN = False
created = 0
skipped = 0


def ensure_tag(rel_path: str, label: str, label_en: str, desc: str):
    global created, skipped
    p = TAGS_ROOT / rel_path / "_definition.json"
    if p.exists():
        skipped += 1
        return
    if not DRY_RUN:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({
            "label": label, "labelEn": label_en,
            "description": desc,
            "createdAt": NOW_ISO, "updatedAt": NOW_ISO,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    created += 1


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

    # 港澳台（pca.json 不含，手动补充）
    if not filter_province or filter_province == "香港特别行政区":
        ensure_tag("中国/香港特别行政区", "香港特别行政区",
                   PROVINCE_EN["香港特别行政区"], PROVINCE_DESC["香港特别行政区"])
    if not filter_province or filter_province == "澳门特别行政区":
        ensure_tag("中国/澳门特别行政区", "澳门特别行政区",
                   PROVINCE_EN["澳门特别行政区"], PROVINCE_DESC["澳门特别行政区"])
    if not filter_province or filter_province == "台湾省":
        ensure_tag("中国/台湾省", "台湾省",
                   PROVINCE_EN["台湾省"], PROVINCE_DESC["台湾省"])


# ─────────────────────────────────────────────
# 泰国（手工定义，量小）
# ─────────────────────────────────────────────

THAILAND_PROVINCES: dict[str, tuple[str, str, dict]] = {
    "曼谷府": ("Bangkok", "泰国首都府，政治与经济核心", {
        "曼谷": ("Bangkok", "首都与最大都市"),
    }),
    "清迈府": ("Chiang Mai Province", "泰北文化与旅游重镇所在府", {
        "清迈市": ("Chiang Mai", "泰北中心城市与门户"),
    }),
    "普吉府": ("Phuket Province", "泰国最大海岛旅游目的地所在府", {
        "普吉镇": ("Phuket Town", "府城与老城文化中心"),
        "芭东海滩": ("Patong Beach", "著名海滩度假区"),
    }),
    "素叻他尼府": ("Surat Thani Province", "泰国湾南岸枢纽，著名离岛门户", {
        "苏梅岛": ("Koh Samui", "南部热门海岛度假地"),
        "帕岸岛": ("Koh Phangan", "生态旅游与满月派对知名岛"),
    }),
    "清莱府": ("Chiang Rai Province", "泰北边境与文化三角所在府", {
        "清莱市": ("Chiang Rai", "府治与区域中心"),
    }),
    "春武里府": ("Chonburi Province", "东部经济走廊与海滨旅游区", {
        "芭提雅": ("Pattaya", "著名滨海旅游城市"),
    }),
    "巴蜀府": ("Prachuap Khiri Khan Province", "泰国湾西岸，皇家海滨传统胜地", {
        "华欣": ("Hua Hin", "皇家海滨度假城"),
    }),
}


def gen_thailand():
    ensure_tag("泰国", "泰国", "Thailand", "泰国（TH）行政区域")
    for province, (prov_en, prov_desc, cities) in THAILAND_PROVINCES.items():
        ensure_tag(f"泰国/{province}", province, prov_en, prov_desc)
        for city, (city_en, city_desc) in cities.items():
            ensure_tag(f"泰国/{province}/{city}", city, city_en, city_desc)


# ─────────────────────────────────────────────
# 欧洲（手工定义，量小）
# ─────────────────────────────────────────────

EUROPE_CITIES: dict[str, tuple[str, str, dict[str, tuple[str, str]]]] = {
    "法国": ("France", "法国（FR）行政区域", {
        "巴黎": ("Paris", "首都，政治文化中心"),
        "尼斯": ("Nice", "地中海滨海与度假名城"),
        "马赛": ("Marseille", "第一大港，区域经济中心"),
    }),
    "意大利": ("Italy", "意大利（IT）行政区域", {
        "罗马": ("Rome", "首都，历史与政治中心"),
        "佛罗伦萨": ("Florence", "文艺复兴艺术与旅游重镇"),
        "威尼斯": ("Venice", "水城与文化遗产名城"),
    }),
    "西班牙": ("Spain", "西班牙（ES）行政区域", {
        "巴塞罗那": ("Barcelona", "加泰罗尼亚经济与国际旅游中心"),
        "马德里": ("Madrid", "首都，政治与经济中心"),
        "塞维利亚": ("Seville", "安达卢西亚文化与历史中心"),
    }),
    "瑞士": ("Switzerland", "瑞士（CH）行政区域", {
        "苏黎世": ("Zurich", "最大城市与国际金融中心"),
        "日内瓦": ("Geneva", "国际组织与高端服务中心"),
        "因特拉肯": ("Interlaken", "阿尔卑斯山门户旅游城市"),
    }),
    "奥地利": ("Austria", "奥地利（AT）行政区域", {
        "维也纳": ("Vienna", "首都，音乐与文化中心"),
        "萨尔茨堡": ("Salzburg", "巴洛克古城与莫扎特故乡"),
    }),
    "捷克": ("Czech Republic", "捷克（CZ）行政区域", {
        "布拉格": ("Prague", "首都，历史文化名城"),
        "CK小镇": ("Český Krumlov", "世界遗产小镇"),
    }),
    "荷兰": ("Netherlands", "荷兰（NL）行政区域", {
        "阿姆斯特丹": ("Amsterdam", "法定首都与最大城市"),
    }),
    "英国": ("United Kingdom", "英国（GB）行政区域", {
        "伦敦": ("London", "首都与全球金融中心"),
        "爱丁堡": ("Edinburgh", "苏格兰首府与文化古都"),
    }),
    "希腊": ("Greece", "希腊（GR）行政区域", {
        "雅典": ("Athens", "首都，古希腊文明中心"),
        "圣托里尼": ("Santorini", "爱琴海度假与火山岛名片"),
    }),
    "葡萄牙": ("Portugal", "葡萄牙（PT）行政区域", {
        "里斯本": ("Lisbon", "首都与大西洋门户"),
        "波尔图": ("Porto", "北部港口与文化酒乡名城"),
    }),
    "挪威": ("Norway", "挪威（NO）行政区域", {
        "奥斯陆": ("Oslo", "首都与政治中心"),
        "卑尔根": ("Bergen", "西海岸港口与峡湾门户"),
        "特罗姆瑟": ("Tromsø", "北极圈门户与极光旅游重镇"),
    }),
}


def gen_europe():
    for country, (country_en, country_desc, cities) in EUROPE_CITIES.items():
        ensure_tag(country, country, country_en, country_desc)
        for city, (city_en, city_desc) in cities.items():
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

    # 泰国/欧洲
    thai_nodes = 1  # 泰国
    for _p, (_pe, _pd, cities) in THAILAND_PROVINCES.items():
        thai_nodes += 1 + len(cities)
    euro_nodes = 0
    for _c, (_ce, _cd, cities) in EUROPE_CITIES.items():
        euro_nodes += 1 + len(cities)

    total_china = 1 + province_count + city_count + district_count
    total = total_china + thai_nodes + euro_nodes

    print(f"=== 行政区数据源统计 ===")
    print(f"中国省级: {province_count}（含港澳台）")
    print(f"中国地级: {city_count}")
    print(f"中国县级: {district_count}")
    print(f"中国总计: {total_china}（含根节点）")
    print(f"泰国: {thai_nodes}")
    print(f"欧洲: {euro_nodes}")
    print(f"全部总计: {total}")


# ─────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="生成行政区标签到 Topic/地理/行政区/")
    parser.add_argument("--country", default=None, help="国家名（如 中国、泰国）")
    parser.add_argument("--province", default=None, help="省份名（如 四川省），仅生成该省")
    parser.add_argument("--dry-run", action="store_true", help="仅统计不写盘")
    parser.add_argument("--stats", action="store_true", help="打印数据源统计后退出")
    args = parser.parse_args()

    if args.stats:
        print_stats()
        return

    global DRY_RUN
    DRY_RUN = args.dry_run

    # 中国
    if args.country in (None, "中国"):
        gen_china(filter_province=args.province)

    # 泰国
    if args.country in (None, "泰国") and args.province is None:
        gen_thailand()

    # 欧洲
    if args.country is None and args.province is None:
        gen_europe()

    print(f"\n行政区生成完成：新增 {created}，跳过（已存在）{skipped}")
    total = created + skipped
    print(f"总节点数：{total}")
    if DRY_RUN:
        print("[dry-run 模式，未写盘]")


if __name__ == "__main__":
    main()
