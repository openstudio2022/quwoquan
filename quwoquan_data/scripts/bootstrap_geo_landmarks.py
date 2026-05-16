"""生成地形地貌分类标签到 Topic/地理/地形地貌/

原则：
- 只生成地理科学的地表形态 TYPE 分类，不含任何具体地物实例
- 具体自然景观实例（珠峰/青海湖等）归入 Entity/地点/自然景观
- 此处只关注"是什么地貌"，不回答"具体哪个"

分类逻辑：按地貌成因和形态科学分类
- 山地地貌：高山/丘陵/山脊/火山
- 平坦地貌：平原/盆地/高原/台地
- 水系地貌：河流/湖泊/三角洲/冰川
- 海洋地貌：海岸/岛屿/海湾/海沟
- 干旱地貌：沙漠/戈壁/雅丹
- 特殊地貌：喀斯特/丹霞/冰川/火山/峡谷
- 生态地貌：草原/湿地/森林/冻土

用法:
  python3 bootstrap_geo_landmarks.py              # 全量生成
  python3 bootstrap_geo_landmarks.py --dry-run    # 仅统计不写盘
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common.paths import PUBLISH_ROOT, NOW_ISO

TAGS_ROOT = PUBLISH_ROOT / "v1" / "tags" / "Topic" / "地理" / "地形地貌"

DRY_RUN = False
created = 0


def tag(rel_path: str, label: str, label_en: str, desc: str,
        aliases: list[str] | None = None):
    global created
    p = TAGS_ROOT / rel_path / "_definition.json"
    if p.exists() and not DRY_RUN:
        return
    data: dict = {
        "label": label, "labelEn": label_en,
        "description": desc,
        "createdAt": NOW_ISO, "updatedAt": NOW_ISO,
    }
    if aliases:
        data["aliases"] = aliases
    if not DRY_RUN:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    created += 1


def tags_list(prefix: str, items: list):
    for item in items:
        cn, en, desc = item[0], item[1], item[2]
        aliases = item[3] if len(item) > 3 else None
        tag(f"{prefix}/{cn}", cn, en, desc, aliases)


def gen_landforms():
    # ── 山地地貌 ──────────────────────────────────────────
    tag("山地地貌", "山地地貌", "Mountain Landform", "以山体为主的地表隆起形态")
    tags_list("山地地貌", [
        ("极高山", "Ultra-high Mountain", "海拔5000m以上的极高山地貌"),
        ("高山", "High Mountain", "海拔3500-5000m的高山地貌"),
        ("中山", "Medium Mountain", "海拔1000-3500m的中山地貌"),
        ("低山", "Low Mountain", "海拔500-1000m的低山地貌"),
        ("丘陵", "Hill", "海拔500m以下的缓坡起伏地貌"),
        ("山脊", "Ridge", "山体顶部延伸的线状隆起"),
        ("山谷", "Valley", "山体之间的狭长低地"),
        ("山口", "Mountain Pass", "山脊上相对低矮的鞍部通道"),
    ])

    # ── 平坦地貌 ──────────────────────────────────────────
    tag("平坦地貌", "平坦地貌", "Flat Landform", "地势平坦或起伏和缓的大面积地表形态")
    tags_list("平坦地貌", [
        ("平原", "Plain", "海拔较低、地形平坦的大面积陆地"),
        ("盆地", "Basin", "四周高中间低的封闭或半封闭地形"),
        ("高原", "Plateau", "海拔高但相对平坦的大面积台状地形"),
        ("台地", "Tableland", "顶面平坦四周陡峭的台状高地"),
        ("谷地", "Lowland", "地势较低的凹陷带状地带"),
    ])

    # ── 水系地貌 ──────────────────────────────────────────
    tag("水系地貌", "水系地貌", "Fluvial Landform", "由水流作用形成的地表形态")
    tags_list("水系地貌", [
        ("河流", "River", "地表径流形成的线状水体及其河道"),
        ("湖泊", "Lake", "陆地封闭或半封闭的天然水域"),
        ("三角洲", "Delta", "河流入海/入湖处的扇形沉积地貌"),
        ("峡谷", "Canyon", "深切狭窄的河流侵蚀谷地"),
        ("瀑布", "Waterfall", "河流跌落形成的垂直水流景观"),
        ("堰塞湖", "Barrier Lake", "滑坡泥石流堵塞河道形成的湖泊"),
        ("冲积扇", "Alluvial Fan", "山前河流沉积形成的扇形平地"),
        ("溶洞暗河", "Underground River", "地下水侵蚀形成的暗河系统"),
    ])

    # ── 海洋地貌 ──────────────────────────────────────────
    tag("海洋地貌", "海洋地貌", "Coastal & Marine Landform", "海岸线及海洋区域的地表形态")
    tags_list("海洋地貌", [
        ("海岸", "Coast", "陆地与海洋交接的带状地貌"),
        ("海湾", "Bay", "海岸线向陆地凹入的水域"),
        ("岛屿", "Island", "四面环水的陆地区域"),
        ("群岛", "Archipelago", "多个岛屿组成的岛链"),
        ("半岛", "Peninsula", "三面环水一面连陆的地形"),
        ("海崖", "Sea Cliff", "海岸侵蚀形成的陡壁"),
        ("沙滩", "Beach", "海浪沉积形成的沙质海岸"),
        ("珊瑚礁", "Coral Reef", "生物堆积形成的海底隆起"),
    ])

    # ── 干旱地貌 ──────────────────────────────────────────
    tag("干旱地貌", "干旱地貌", "Arid Landform", "干旱环境下形成的地表形态")
    tags_list("干旱地貌", [
        ("沙漠", "Desert", "植被稀少的大面积沙质地表"),
        ("戈壁", "Gobi", "砾石覆盖的干旱荒漠地表"),
        ("雅丹", "Yardang", "风蚀形成的垄槽相间地貌"),
        ("沙丘", "Sand Dune", "风力堆积形成的流动沙堆"),
        ("盐湖", "Salt Lake", "内流区蒸发浓缩形成的咸水湖"),
        ("盐碱滩", "Salt Flat", "盐分集聚的平坦低洼地"),
    ])

    # ── 特殊地貌 ──────────────────────────────────────────
    tag("特殊地貌", "特殊地貌", "Special Landform", "特殊成因或罕见类型的地表形态")
    tags_list("特殊地貌", [
        ("喀斯特", "Karst", "�ite溶蚀形成的石灰岩地貌", ["溶蚀地貌", "岩溶"]),
        ("丹霞", "Danxia", "红色砂砾岩侵蚀形成的赤壁丹崖地貌"),
        ("冰川", "Glacier", "高寒区积雪压缩形成的流动冰体"),
        ("火山", "Volcano", "岩浆喷发形成的锥状隆起"),
        ("温泉", "Hot Spring", "地热加热的天然泉水出露"),
        ("间歇泉", "Geyser", "周期性喷发的地热喷泉"),
        ("石林", "Stone Forest", "溶蚀残余形成的密集石柱群"),
        ("土林", "Earth Forest", "流水侵蚀软质地层形成的柱状地貌"),
        ("冰碛", "Moraine", "冰川搬运堆积的碎屑地貌"),
    ])

    # ── 生态地貌 ──────────────────────────────────────────
    tag("生态地貌", "生态地貌", "Ecological Landform", "以植被或水文生态为主要特征的地表形态")
    tags_list("生态地貌", [
        ("草原", "Grassland", "温带半干旱区以草本植物为主的地表"),
        ("湿地", "Wetland", "水陆过渡带的生态系统"),
        ("森林", "Forest", "以乔木为主的大面积植被覆盖区"),
        ("冻土", "Permafrost", "永久或季节性冻结的土壤层"),
        ("红树林", "Mangrove", "热带亚热带海岸潮间带森林"),
        ("高山草甸", "Alpine Meadow", "高海拔山地的草甸植被带"),
    ])


def main():
    parser = argparse.ArgumentParser(description="生成地形地貌分类标签")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    global DRY_RUN
    DRY_RUN = args.dry_run

    gen_landforms()

    print(f"\n地形地貌分类生成完成：{created} 个标签")
    if DRY_RUN:
        print("[dry-run 模式，未写盘]")


if __name__ == "__main__":
    main()
