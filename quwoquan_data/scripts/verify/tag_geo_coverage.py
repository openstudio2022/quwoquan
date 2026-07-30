"""R5 境外行政区最小覆盖校验。

境外行政区标签的唯一采集通道是 POI picker 与 EXIF GPS：端侧把选点/坐标解析成
`Topic/地理/行政区/<国家>/<一级行政区>/<城市>` 写入 `Post.geoTagRef`。解析器逐段匹配
路径，所以缺一个国家就意味着该国全部内容在地理维度上无标签——既不进地理召回，也
不产生就近交集。这不是覆盖度好坏问题，而是整条链路对该目的地失效。

因此这里是 ERROR 级而非 WARNING：最小集里的国家与城市是出境热度靠前、且已经在
`overseas_regions_*` 里落地的目的地，缺失只可能来自误删或生成器回归。

最小集刻意只列国家和「该国最具代表性的城市」两层，不追认一级行政区名称——一级
行政区归属会随当地区划调整变化，把它写进门禁会让门禁变成需要跟着改的第二真相源。
"""

from __future__ import annotations

from pathlib import Path

# 国家 -> 必须存在的城市（可位于国家的任意层级之下）
OVERSEAS_MIN_COVERAGE: dict[str, tuple[str, ...]] = {
    "日本": ("新宿", "大阪市", "京都市", "札幌市", "那霸市", "横滨市"),
    "韩国": ("明洞", "海云台", "济州市"),
    "泰国": ("曼谷", "清迈市", "普吉镇", "苏梅岛", "芭提雅"),
    "新加坡": ("市中心区", "圣淘沙"),
    "越南": ("还剑区", "会安", "芽庄"),
    "马来西亚": ("吉隆坡", "乔治市", "亚庇"),
    "印度尼西亚": ("库塔", "乌布", "雅加达"),
    "菲律宾": ("宿务", "爱妮岛", "长滩岛"),
    "柬埔寨": ("暹粒",),
    "尼泊尔": ("加德满都", "博卡拉"),
    "马尔代夫": ("马累",),
    "斯里兰卡": ("康提", "科伦坡"),
    "美国": ("洛杉矶", "旧金山", "纽约市", "拉斯维加斯", "大峡谷", "檀香山", "西雅图"),
    "加拿大": ("温哥华", "班夫", "多伦多"),
    "澳大利亚": ("悉尼", "墨尔本", "凯恩斯", "乌鲁鲁"),
    "新西兰": ("奥克兰", "皇后镇", "基督城"),
    "法国": ("巴黎", "尼斯", "里昂"),
    "意大利": ("罗马", "佛罗伦萨", "威尼斯", "米兰"),
    "西班牙": ("马德里", "巴塞罗那", "格拉纳达"),
    "瑞士": ("苏黎世", "因特拉肯", "采尔马特"),
    "德国": ("柏林市", "慕尼黑", "新天鹅堡"),
    "英国": ("伦敦", "爱丁堡"),
    "奥地利": ("维也纳市", "萨尔茨堡", "哈尔施塔特"),
    "捷克": ("布拉格市",),
    "荷兰": ("阿姆斯特丹",),
    "希腊": ("雅典", "圣托里尼"),
    "葡萄牙": ("里斯本", "波尔图"),
    "挪威": ("奥斯陆市", "卑尔根", "特罗姆瑟"),
    "冰岛": ("雷克雅未克",),
    "芬兰": ("赫尔辛基", "罗瓦涅米"),
    "瑞典": ("斯德哥尔摩",),
    "土耳其": ("伊斯坦布尔", "卡帕多奇亚"),
    "阿联酋": ("迪拜市",),
    "埃及": ("开罗", "卢克索"),
    "摩洛哥": ("马拉喀什", "舍夫沙万"),
    "肯尼亚": ("马赛马拉",),
    "南非": ("开普敦",),
    "秘鲁": ("库斯科", "马丘比丘"),
    "阿根廷": ("布宜诺斯艾利斯",),
    "智利": ("圣地亚哥",),
    "巴西": ("里约热内卢",),
    "墨西哥": ("坎昆",),
    "俄罗斯": ("莫斯科", "圣彼得堡"),
    "格鲁吉亚": ("第比利斯市",),
    "乌兹别克斯坦": ("撒马尔罕",),
}

# 港澳台在 pca 数据源里没有下级条目，长期是无子节点的死枝；下级城市另行手工维护，
# 所以这里单独盯住，防止再退化成只有一级行政区节点。
CHINA_SAR_TW_MIN_COVERAGE: dict[str, tuple[str, ...]] = {
    "香港特别行政区": ("香港岛", "九龙", "新界"),
    "澳门特别行政区": ("澳门半岛", "氹仔"),
    "台湾省": ("台北", "台中", "高雄", "花莲"),
}

# 境外国家数下限。远低于最小集条目数，只用于挡住「整块数据被删」这类回归。
MIN_OVERSEAS_COUNTRIES = 40


def _descendant_names(root: Path) -> set[str]:
    return {f.parent.name for f in root.rglob("_definition.json")}


def check_overseas_coverage(tags_root: Path) -> list[str]:
    errors: list[str] = []
    admin_root = tags_root / "Topic" / "地理" / "行政区"
    if not admin_root.exists():
        return ["R5: 行政区目录不存在：Topic/地理/行政区/"]

    countries = {d.name for d in admin_root.iterdir() if d.is_dir()}
    overseas = countries - {"中国"}
    if len(overseas) < MIN_OVERSEAS_COUNTRIES:
        errors.append(
            f"R5: 境外国家数 {len(overseas)} < {MIN_OVERSEAS_COUNTRIES}；"
            f"境外 POI/GPS 选点将解析不到 geoTagRef"
        )

    for country, cities in OVERSEAS_MIN_COVERAGE.items():
        country_dir = admin_root / country
        if not country_dir.exists():
            errors.append(f"R5: 境外最小集缺少国家：{country}")
            continue
        present = _descendant_names(country_dir)
        for city in cities:
            if city not in present:
                errors.append(f"R5: {country} 缺少最小集城市：{city}")

    china_dir = admin_root / "中国"
    for province, cities in CHINA_SAR_TW_MIN_COVERAGE.items():
        prov_dir = china_dir / province
        if not prov_dir.exists():
            errors.append(f"R5: 缺少一级行政区：中国/{province}")
            continue
        present = _descendant_names(prov_dir)
        for city in cities:
            if city not in present:
                errors.append(f"R5: 中国/{province} 缺少下级：{city}")

    return errors
