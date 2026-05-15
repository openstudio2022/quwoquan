"""E2E Smoke v4 — 全维度四川省验证

覆盖 7 类实体 x 多内容角度 = 全链路 explore->publish
实体三层路径：entities/{领域}/{类型}/{名称}/
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common.paths import *

TASK_ID = "四川省全域_v5"
BATCH_ID = "多维度冒烟"

# ━━━━━ 实体定义：(领域, 类型, 名称, geoTagRef, tagRefs, description, aliases) ━━━

ENTITIES = [
    ("地点", "景区", "峨眉山", "Topic/地理/行政区/四川省/乐山市/峨眉山市",
     ["Topic/主题/佛教文化", "Topic/主题/世界遗产", "Topic/主题/自然风光"],
     "中国四大佛教名山之一，世界文化与自然双遗产", ["峨眉"]),
    ("地点", "景区", "九寨沟", "Topic/地理/行政区/四川省/阿坝藏族羌族自治州/九寨沟县",
     ["Topic/主题/自然风光/湖泊", "Topic/主题/世界遗产"],
     "以翠海叠瀑彩林雪峰著称的世界自然遗产", ["九寨"]),
    ("地点", "景区", "稻城亚丁", "Topic/地理/行政区/四川省/甘孜藏族自治州/稻城县",
     ["Topic/主题/自然风光/雪山", "Topic/主题/自然风光/高原风光"],
     "被誉为蓝色星球上最后一片净土的高原神山", ["亚丁"]),
    ("地点", "遗址", "三星堆遗址", "Topic/地理/行政区/四川省/德阳市/广汉市",
     ["Topic/主题/古蜀文明", "Topic/主题/世界遗产"],
     "距今3000-5000年的古蜀文明祭祀遗址群", ["三星堆"]),
    ("地点", "遗址", "东风堰", "Topic/地理/行政区/四川省/乐山市/夹江县",
     ["Topic/主题/水利工程", "Topic/主题/世界遗产"],
     "始建于清康熙元年的世界灌溉工程遗产", ["毛滩堰"]),
    ("地点", "打卡地", "成都太古里", "Topic/地理/行政区/四川省/成都市/锦江区",
     ["Topic/主题/建筑艺术"],
     "开放式低密度商业街区，国际大牌与成都烟火气交融", ["太古里", "IFS"]),
    ("地点", "打卡地", "宽窄巷子", "Topic/地理/行政区/四川省/成都市/青羊区",
     ["Topic/主题/建筑艺术", "Topic/主题/美食文化/小吃"],
     "清代少城遗留的三条平行老街，成都慢生活地标", ["宽巷子", "窄巷子"]),
    ("地点", "博物馆", "三星堆博物馆", "Topic/地理/行政区/四川省/德阳市/广汉市",
     ["Topic/主题/古蜀文明", "Topic/主题/石刻艺术"],
     "揭开古蜀文明面纱的世界级考古博物馆", []),
    ("地点", "博物馆", "成都博物馆", "Topic/地理/行政区/四川省/成都市/青羊区",
     ["Topic/主题/古蜀文明", "Topic/主题/建筑艺术"],
     "展示成都4500年城市文明的综合性博物馆", []),
    ("地点", "美食街", "锦里小吃街", "Topic/地理/行政区/四川省/成都市/武侯区",
     ["Topic/主题/美食文化/川菜", "Topic/主题/美食文化/小吃", "Topic/主题/三国文化"],
     "成都最具人气的传统小吃聚集地", ["锦里"]),
    ("地点", "美食街", "建设路小吃街", "Topic/地理/行政区/四川省/成都市/成华区",
     ["Topic/主题/美食文化/小吃"],
     "成都本地人最爱的平民夜市小吃街", ["建设路"]),
    ("地点", "古镇", "阆中古城", "Topic/地理/行政区/四川省/南充市/阆中市",
     ["Topic/主题/三国文化", "Topic/主题/建筑艺术", "Topic/主题/非遗传承"],
     "中国四大古城之一，春节文化发祥地", ["阆中"]),
    ("地点", "古镇", "黄龙溪古镇", "Topic/地理/行政区/四川省/成都市/龙泉驿区",
     ["Topic/主题/建筑艺术"],
     "拥有1700年历史的川西水乡古镇", ["黄龙溪"]),
    ("地点", "餐厅", "陈麻婆豆腐", "Topic/地理/行政区/四川省/成都市/青羊区",
     ["Topic/主题/美食文化/川菜"],
     "麻婆豆腐发源地，百年老字号川菜名店", []),
    ("机构", "学校", "四川大学", "Topic/地理/行政区/四川省/成都市",
     ["Topic/主题/红色文化"],
     "百年名校，西南学府之冠", ["川大"]),
    ("活动", "赛事", "成都马拉松", "Topic/地理/行政区/四川省/成都市",
     ["Topic/主题/古蜀文明"],
     "世界田联金标赛事，跑过千年蜀都的城市马拉松", ["成马"]),
]

# 每类实体对应的内容角度
TYPE_ANGLES = {
    ("地点", "景区"): ["攻略", "体验", "叙事"],
    ("地点", "遗址"): ["科普", "体验"],
    ("地点", "打卡地"): ["攻略", "日记"],
    ("地点", "博物馆"): ["科普", "体验"],
    ("地点", "美食街"): ["探店", "攻略"],
    ("地点", "古镇"): ["攻略", "叙事"],
    ("地点", "餐厅"): ["探店", "攻略"],
    ("机构", "学校"): ["攻略", "体验"],
    ("活动", "赛事"): ["体验", "攻略"],
}


def w(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, dict):
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        path.write_text(data, encoding="utf-8")


def gen_page_content(domain: str, etype: str, name: str, desc: str, geo: str, tags: list[str]) -> str:
    city = geo.split("/")[-1] if "/" in geo else geo
    tag_links = " | ".join(f"[{t.split('/')[-1]}](/tag/{t})" for t in tags[:3])
    geo_link = f"[{city}](/tag/{geo})"

    # 为每个实体找一个同类型的关联实体做嵌入引用
    related = None
    for d2, t2, n2, *_ in ENTITIES:
        if d2 == domain and t2 == etype and n2 != name:
            related = (d2, t2, n2)
            break
    if not related:
        for d2, t2, n2, *_ in ENTITIES:
            if d2 == domain and n2 != name:
                related = (d2, t2, n2)
                break
    if not related:
        related = (domain, etype, name)
    rel_link = f"[{related[2]}](/entity/{related[0]}/{related[1]}/{related[2]})"

    sections = {
        "景区": f"""# {name}

> {desc}

{{asset://{name}_panorama.jpg|wrapRight|{name}全景|width=45%}}

## 概况

{name}位于{geo_link}，是四川省最具代表性的旅游景区之一。作为{tag_links}的典型代表，{name}以其独特的自然景观和深厚的文化底蕴吸引着海内外游客。景区年接待游客超过300万人次，是[自驾游](/tag/Topic/场景/自驾游)和[登山](/tag/Topic/场景/登山)爱好者的热门目的地。景区内生态资源丰富，植被覆盖率高，气候垂直分布明显，从亚热带到高山寒带一山尽览。周边配套设施完善，住宿餐饮选择丰富，适合[家庭](/tag/Audience/用户/家庭)和[情侣](/tag/Audience/用户/情侣)出行。

## 历史沿革

- **古代**：{name}自古即为名胜，历代文人墨客留下了大量诗词歌赋，见证了千年沧桑变迁。
- **近代**：清末民初，{name}开始被西方探险家关注，陆续有科考队深入调查其地质和生物资源。
- **现代**：新中国成立后，{name}被列为重点风景名胜区。改革开放以来基础设施不断完善，1996年后陆续获得世界级荣誉。

## 核心景点

{{asset://{name}_highlight.jpg|wrapRight|核心景观|width=40%}}

- **{name}主峰**：海拔高耸，云海翻涌，是观日出的绝佳位置。清晨的光线将山峦染成金色，吸引了无数[摄影打卡](/tag/Topic/场景/摄影打卡)爱好者。建议提前一天住在山顶附近的客栈。
- **核心步道**：沿途古木参天，溪水潺潺，步道平均海拔变化500米，[徒步](/tag/Topic/场景/徒步)全程约4小时。途中设有多处休息亭和观景平台。
- **文化遗存**：保留有始建于唐宋时期的古建筑群，[建筑艺术](/tag/Topic/主题/建筑艺术)融合了当地特色与中原风格，是[文化研学](/tag/Topic/场景/文化研学)的重要基地。

## 实用信息

| 项目 | 信息 |
| ---- | ---- |
| 门票 | 旺季160元/人，淡季80元/人 |
| 开放时间 | 全天开放，索道6:00-18:00 |
| 最佳季节 | [春](/tag/季节/春)末[秋](/tag/季节/秋)初（4-5月、9-11月） |
| 交通 | 成都出发高铁或[自驾游](/tag/Topic/场景/自驾游)均可到达 |
| 周边住宿 | 景区内外均有，建议提前预订 |

## 文化特色

{name}承载着丰富的{tag_links}遗产。千百年来，这里不仅是自然奇观，更是精神信仰的载体。当地的[民族文化](/tag/Topic/主题/民族文化)与自然景观交相辉映，形成了独特的文化景观。每年的传统节庆活动吸引大量信众和游客，是体验[非遗传承](/tag/Topic/主题/非遗传承)的绝佳场所。""",

        "遗址": f"""# {name}

> {desc}

{{asset://{name}_panorama.jpg|wrapRight|{name}全景|width=45%}}

## 概况

{name}位于{geo_link}，是四川省最重要的文化遗存之一。该遗址见证了数千年的历史变迁，是研究{tag_links}的关键实物资料。遗址保护面积可观，出土文物丰富多样，对于理解中华文明的起源和发展具有不可替代的学术价值。周边交通便利，配套有专业的展陈设施，适合[文化研学](/tag/Topic/场景/文化研学)和[学生](/tag/Audience/用户/学生)研学旅行。

## 历史沿革

- **始建期**：{name}的历史可追溯到数千年前，留下了丰富的地层堆积和文化遗存。
- **发现期**：近现代以来，考古工作者对{name}进行了多次系统发掘，出土了大量珍贵文物。
- **保护期**：21世纪以来，{name}被列为各级重点文物保护单位，保护与展示工作不断深化。

## 核心看点

{{asset://{name}_highlight.jpg|wrapRight|核心遗存|width=40%}}

- **核心遗存区**：保存最完整的遗存主体，展现了当时的建造工艺和生产水平。考古发掘揭示了复杂的建筑结构和精巧的工程设计。
- **出土文物**：包括青铜器、陶器、玉器等，工艺水平令人惊叹，反映了[古蜀文明](/tag/Topic/主题/古蜀文明)的高度发达。
- **遗址公园**：在保护原址的基础上建设了开放式公园，游客可沿步道近距离观察遗址本体，配有详细的解说系统。

## 实用信息

| 项目 | 信息 |
| ---- | ---- |
| 门票 | 免费或低价（具体以景区公告为准） |
| 开放时间 | 8:30-17:30 |
| 最佳季节 | [春](/tag/季节/春)[秋](/tag/季节/秋)两季气候宜人 |
| 交通 | 可从{city}城区乘坐公交或打车前往 |

## 文化价值

{name}是{tag_links}的杰出代表，其出土文物和遗址本体为研究中华文明多元一体格局提供了重要证据。该遗址证明了长江上游地区在远古时期就存在高度发达的文明形态，具有极高的[世界遗产](/tag/Topic/主题/世界遗产)价值。""",

        "打卡地": f"""# {name}

> {desc}

{{asset://{name}_main.jpg|wrapRight|{name}|width=45%}}

## 概况

{name}位于{geo_link}，是成都乃至四川最具人气的城市目的地之一。这里融合了现代商业美学与传统文化元素，是{tag_links}的典型载体。年客流量超千万，在社交媒体上的打卡量长期位居四川前列，是[摄影打卡](/tag/Topic/场景/摄影打卡)和[情侣约会](/tag/Topic/场景/情侣约会)的热门选择。街区内业态丰富，从国际品牌到本地文创应有尽有，适合[上班族](/tag/Audience/用户/上班族)[周末短途](/tag/Topic/场景/周末短途)消磨时光。

## 为什么火

{name}的火爆源于独特的空间设计和文化碰撞。传统建筑形态与现代消费场景的融合产生了强烈的视觉冲击力，每一处转角都是适合[摄影打卡](/tag/Topic/场景/摄影打卡)的天然背景板。社交媒体的传播效应使其成为了城市文化的符号性地标，吸引着不同代际的人群前来体验。

## 打卡攻略

{{asset://{name}_spot.jpg|wrapRight|热门机位|width=40%}}

- **标志性入口**：{name}的主入口是最经典的拍照地点，建筑风格独特，光线在午后尤为适合拍摄，是[摄影打卡](/tag/Topic/场景/摄影打卡)首选。
- **文创聚集区**：汇集了本地独立设计品牌和文创工作室，可以淘到独一无二的纪念品，也是感受成都创意文化的窗口。
- **美食一条街**：从传统[小吃](/tag/Topic/主题/美食文化/小吃)到创意料理应有尽有，人均30-100元即可吃遍一整条街。

## 实用信息

| 项目 | 信息 |
| ---- | ---- |
| 营业时间 | 10:00-22:00 |
| 费用 | 免费进入，消费丰俭由人 |
| 交通 | 地铁直达，站点步行5分钟内 |
| 最佳时段 | 工作日下午人少适合拍照 |

## 文化底蕴

{name}承载的不仅是商业功能，更是城市记忆的活化石。这里的{tag_links}底蕴通过空间设计和文化策展得以传承，让每一位到访者在消费的同时也在阅读城市的历史篇章。""",

        "博物馆": f"""# {name}

> {desc}

{{asset://{name}_facade.jpg|wrapRight|{name}外观|width=45%}}

## 概况

{name}位于{geo_link}，是四川省最重要的文化展示空间之一。馆藏文物丰富，涵盖{tag_links}等多个领域，是了解四川乃至中国西南文明史的必到之地。博物馆建筑本身也是[建筑艺术](/tag/Topic/主题/建筑艺术)的代表作。适合[文化研学](/tag/Topic/场景/文化研学)和[学生](/tag/Audience/用户/学生)研学旅行。年接待观众超百万人次。

## 镇馆之宝

{{asset://{name}_treasure.jpg|wrapRight|核心藏品|width=40%}}

- **核心藏品一**：年代久远，工艺精湛，是该馆最具标志性的展品。材质珍贵，造型独特，被列为国家一级文物，是[古蜀文明](/tag/Topic/主题/古蜀文明)的实物见证。
- **核心藏品二**：出土于重要考古遗址，反映了当时的社会生活和宗教信仰。保存完好，细节清晰可辨。
- **核心藏品三**：兼具艺术价值和历史价值，常年借展国内外重要博物馆，是[石刻艺术](/tag/Topic/主题/石刻艺术)的杰出代表。

## 参观动线

建议从一楼常设展开始，按时间线了解历史脉络。二楼为专题展厅，深入某一领域。三楼或特展厅为临时展览，根据当期展览调整。全程建议2-3小时，租借语音导览效果更佳。

## 实用信息

| 项目 | 信息 |
| ---- | ---- |
| 门票 | 免费（需预约） |
| 开放时间 | 9:00-17:00（16:00停止入馆），周一闭馆 |
| 预约 | 微信公众号提前预约 |
| 交通 | 公共交通可达 |
| 讲解 | 人工讲解200元/次，语音导览30元 |

## 历史与文化

{name}的建立本身就是一部文化传承的故事。从建馆初期的筚路蓝缕到如今的现代化展陈，它见证了社会对{tag_links}保护意识的不断提升。馆内的每一件展品都是历史的碎片，拼凑出中华文明的宏大画卷。""",

        "美食街": f"""# {name}

> {desc}

{{asset://{name}_main.jpg|wrapRight|{name}夜景|width=45%}}

## 概况

{name}位于{geo_link}，是成都最具代表性的美食聚集区之一。街区汇聚了数十乃至上百家[小吃](/tag/Topic/主题/美食文化/小吃)摊位和餐饮店铺，涵盖{tag_links}等多种风味。无论是外地游客还是本地食客，这里都是品尝正宗[川菜](/tag/Topic/主题/美食文化/川菜)的首选地点。[探店](/tag/Format/内容角度/探店)博主的常驻打卡地。

## 必吃清单

{{asset://{name}_food.jpg|wrapRight|招牌小吃|width=40%}}

- **招牌第一味**：这条街的灵魂美食，排队是常态。口味浓郁地道，一口就能感受到成都的麻辣精髓。人均15-25元。
- **经典第二味**：传统工艺制作，现做现卖。外形朴素但味道出众，是[上班族](/tag/Audience/用户/上班族)下班后的首选安慰剂。人均10-20元。
- **网红第三味**：因社交媒体走红的创新小吃，融合传统与现代，颜值与口味兼具。[摄影打卡](/tag/Topic/场景/摄影打卡)和品尝两不误。人均20-30元。
- **隐藏第四味**：只有本地人才知道的巷尾小摊。不起眼的门面下藏着二十年不变的老味道。人均8-15元。
- **甜品第五味**：饭后必来一份的街头甜品。传统配方搭配季节水果，清甜解腻。人均10元。

## 消费指南

| 项目 | 信息 |
| ---- | ---- |
| 人均 | 50-80元可吃遍主要摊位 |
| 营业时间 | 部分摊位10:00起，多数17:00-23:00 |
| 支付 | 微信/支付宝通用 |
| 交通 | 地铁可达，步行5分钟内 |
| 避峰 | [周末短途](/tag/Topic/场景/周末短途)建议工作日前往 |

## 美食文化

{name}承载着成都的[美食文化](/tag/Topic/主题/美食文化)记忆。这里的每一个摊位都有自己的故事，从父辈传下的老配方到年轻一代的创新融合，{tag_links}在这条街上得到了最鲜活的传承。""",

        "古镇": f"""# {name}

> {desc}

{{asset://{name}_panorama.jpg|wrapRight|{name}全景|width=45%}}

## 概况

{name}位于{geo_link}，是四川省保存最为完整的历史城镇之一。古镇{tag_links}底蕴深厚，建筑群保留了明清时期的典型风貌。石板街巷、雕花门窗、天井院落构成了一幅生动的历史画卷，是[文化研学](/tag/Topic/场景/文化研学)和[摄影打卡](/tag/Topic/场景/摄影打卡)的理想目的地。古镇全年接待游客数百万人次，已成为[周末短途](/tag/Topic/场景/周末短途)出行的热门选择。

## 历史沿革

- **始建期**：{name}的历史可追溯到上千年前，因水陆交通便利而逐渐发展为区域商贸重镇。
- **繁盛期**：明清时期达到鼎盛，商铺林立，会馆众多，留下了大量精美的[建筑艺术](/tag/Topic/主题/建筑艺术)遗存。
- **保护期**：21世纪以来启动全面保护修缮，在保持原貌的基础上引入文化旅游业态。

## 核心看点

{{asset://{name}_highlight.jpg|wrapRight|标志性建筑|width=40%}}

- **古街主巷**：保存完整的明清街巷，两侧木构建筑鳞次栉比。漫步其中可感受到数百年前的市井繁华，[登山](/tag/Topic/场景/登山)前后在此休整是绝佳安排。
- **标志性古建**：最能代表{name}建筑特色的核心建筑群，融合了川西民居的实用与雅致。
- **民俗体验区**：可体验传统手工艺和[非遗传承](/tag/Topic/主题/非遗传承)项目，如剪纸、年画、豆腐制作等。

## 实用信息

| 项目 | 信息 |
| ---- | ---- |
| 门票 | 古镇免费，部分景点单独购票 |
| 开放时间 | 全天（部分景点8:00-18:00） |
| 最佳季节 | [春](/tag/季节/春)季花开和[秋](/tag/季节/秋)季银杏时节 |
| 交通 | 成都出发大巴或[自驾游](/tag/Topic/场景/自驾游)均可 |

## 民俗文化

{name}是四川[非遗传承](/tag/Topic/主题/非遗传承)的活态博物馆。这里的{tag_links}传统通过节庆活动、民间手艺和饮食习俗代代相传。古镇的[美食文化](/tag/Topic/主题/美食文化)同样丰富，当地特色小吃值得细细品味。""",

        "餐厅": f"""# {name}

> {desc}

{{asset://{name}_main.jpg|wrapRight|{name}门面|width=45%}}

## 概况

{name}位于{geo_link}，是四川[川菜](/tag/Topic/主题/美食文化/川菜)的标杆性餐厅。创始至今已逾百年，是「中华老字号」认证企业。餐厅以传统烹饪技法著称，{tag_links}在这里得到了最正宗的呈现。是[探店](/tag/Format/内容角度/探店)爱好者和[美食文化](/tag/Topic/主题/美食文化)研究者的必到之地。门店朴素大方，保留了老成都饭馆的烟火气息。

## 招牌菜

{{asset://{name}_dish.jpg|wrapRight|招牌菜品|width=40%}}

- **镇店名菜**：传承百年的经典制法，选料考究，火候精准。一入口便能感受到[川菜](/tag/Topic/主题/美食文化/川菜)「麻辣鲜香」的极致平衡。25元/份。必点。
- **经典二味**：另一道代表性菜品，体现了川菜「一菜一格」的烹饪哲学。搭配米饭堪称完美。35元/份。
- **传统三味**：老成都家常菜的升级版，保持了[小吃](/tag/Topic/主题/美食文化/小吃)原始的朴素风味。30元/份。

## 用餐体验

餐厅环境保留了传统中式装修风格，红木桌椅搭配大方简洁的装饰。服务高效，高峰期翻台快。适合[家庭](/tag/Audience/用户/家庭)聚餐和[情侣](/tag/Audience/用户/情侣)约会，二楼较为安静。整体氛围是热闹的市井烟火气。

## 实用信息

| 项目 | 信息 |
| ---- | ---- |
| 人均 | 50-80元 |
| 营业时间 | 11:00-14:00，17:00-21:00 |
| 预约 | 不接受预约，先到先得 |
| 交通 | 地铁站步行5分钟 |

## 美食故事

{name}的创立充满了成都市井智慧。一道偶然诞生的家常菜，因口味独到而声名远播，最终成为{tag_links}的代表作。这道菜不仅入选了[川菜](/tag/Topic/主题/美食文化/川菜)正谱，更传播到了海外，成为中国饮食文化的一张名片。""",

        "学校": f"""# {name}

> {desc}

{{asset://{name}_gate.jpg|wrapRight|{name}校门|width=45%}}

## 概况

{name}位于{geo_link}，是中国西南地区最具影响力的高等学府之一。学校历史悠久，学科门类齐全，综合实力位居全国前列。校区占地面积广阔，在校师生数万人。{name}以开放包容的学术氛围著称，{tag_links}底蕴深厚，是[文化研学](/tag/Topic/场景/文化研学)的重要目的地。校园建筑中西合璧，也是[摄影打卡](/tag/Topic/场景/摄影打卡)的好去处。

## 校史沿革

- **创建期**：{name}的前身创建于清末，是中国最早的近代高等学校之一，开西南高等教育之先河。
- **发展期**：民国至新中国成立期间，{name}经历了多次合并重组，学科体系不断完善。
- **现代期**：改革开放以来，{name}获评各类重点建设项目，国际化水平显著提升。

## 院系与学科

- **王牌学院一**：全国排名顶尖的优势学科，拥有多个国家级实验室和研究平台。培养了大量行业领军人才。
- **王牌学院二**：历史悠久的传统强势学科，学术传统深厚，师资力量雄厚。
- **特色学院三**：结合地方特色发展的新兴学科，在国内具有独特地位。

## 校园风光

{{asset://{name}_campus.jpg|wrapRight|校园一角|width=40%}}

{name}的校园本身就是一座建筑博物馆。民国时期的老建筑与现代化的教学楼交相辉映，[建筑艺术](/tag/Topic/主题/建筑艺术)爱好者可在此流连半日。校园内绿树成荫，四季花木交替，是[上班族](/tag/Audience/用户/上班族)和[学生](/tag/Audience/用户/学生)休闲散步的好去处。

## 实用信息

| 项目 | 信息 |
| ---- | ---- |
| 参观 | 主校区全天开放 |
| 交通 | 地铁直达，多条公交线路可选 |
| 食堂 | 对外开放，人均15-25元 |

## 文化传承

{name}百余年的办学历程塑造了独特的校园精神。这里走出了众多影响中国的杰出人物，从革命先烈到学术泰斗，{tag_links}和学术自由的传统在校园里代代相传。""",

        "赛事": f"""# {name}

> {desc}

{{asset://{name}_start.jpg|wrapRight|{name}起跑|width=45%}}

## 概况

{name}是四川省最高等级的路跑赛事之一，由{geo_link}政府主办。赛事每年秋季举办，设全程和半程两个项目，参赛规模达数万人。赛道穿越城市核心区域和历史文化地标，是{tag_links}的一次生动展示。吸引来自数十个国家和地区的跑者参与，是[极限运动](/tag/Topic/场景/极限运动)和[登山](/tag/Topic/场景/登山)爱好者拓展城市跑步体验的首选。

## 赛道与赛制

赛道从城市地标起跑，途经多处历史文化景点和现代城市风貌带，终点设在大型场馆。赛道平均海拔约500米，累计爬升较小，利于创造个人最好成绩。全马关门时间6小时15分，半马3小时。

## 参赛指南

| 项目 | 信息 |
| ---- | ---- |
| 报名 | 官网或App，每年7-8月开放抽签 |
| 费用 | 全马200元，半马150元 |
| 资格 | 全马需半年内完赛证明 |
| 时间 | 通常10-11月举办 |
| 交通 | 赛事期间有免费摆渡车 |

## 赛道亮点

{{asset://{name}_route.jpg|wrapRight|赛道风景|width=40%}}

- **起跑段**：从具有[古蜀文明](/tag/Topic/主题/古蜀文明)象征意义的地标出发，在历史与现代的交汇中开启旅程，是[摄影打卡](/tag/Topic/场景/摄影打卡)的第一站。
- **文化段**：穿越历史文化核心区域，沿途可见[三国文化](/tag/Topic/主题/三国文化)遗迹和传统民居，是赛道最具人文厚度的路段。
- **冲刺段**：进入城市核心，两侧观众夹道欢呼，冲线仪式感满满。

## 赛事文化

{name}不仅是一场体育赛事，更是城市文化的集中展示。赛道沿线设有特色补给站，提供[火锅](/tag/Topic/主题/美食文化/火锅)风味能量补给和[茶文化](/tag/Topic/主题/美食文化/茶文化)盖碗茶等本地特色。赛事带动了{tag_links}和城市跑步社群的蓬勃发展，[上班族](/tag/Audience/用户/上班族)周末长跑已成为新生活方式。""",
    }

    result = sections.get(etype, sections["景区"])
    if "/entity/" not in result:
        result = result.rstrip() + f"\n\n周边可联动{rel_link}等目的地，组合行程更加丰富。\n"
    return result


def gen_article(name: str, domain: str, etype: str, angle: str, tags: list[str], geo: str) -> str:
    tag_links = ", ".join(f"[{t.split('/')[-1]}](/tag/{t})" for t in tags[:2])
    city = geo.split("/")[-1]
    return f"""# {name}{angle}指南

> 一篇关于{name}的{angle}深度内容

{{asset://{name}_{angle}_cover.jpg|wrapRight|{name}|width=45%}}

## 前言

{name}是[{city}](/tag/{geo})最值得关注的[{etype}](/tag/Entity/{domain}/{etype})之一。这篇{angle}将带你深入了解[{name}](/entity/{domain}/{etype}/{name})的方方面面，从{tag_links}的视角出发，为你呈现一份实用而有深度的内容。无论你是[家庭](/tag/Audience/用户/家庭)出行还是[独行者](/tag/Audience/用户/独行者)探索，都能从中找到有价值的信息。

## 核心内容

{{asset://{name}_{angle}_detail.jpg|wrapRight|细节展示|width=40%}}

作为{tag_links}的典型代表，{name}拥有独特的魅力。从[摄影打卡](/tag/Topic/场景/摄影打卡)的角度来看，这里的每一处细节都值得被记录。当地的文化传统与现代体验交织，形成了丰富多层次的[{angle}](/tag/Format/内容角度/{angle})素材。

深入体验后你会发现，{name}远不止表面所见。当地人的生活方式、隐藏的小众角落、季节性的特殊体验，都是值得在[{angle}](/tag/Format/内容角度/{angle})中重点推荐的亮点。建议安排至少半天到一天的时间，才能不疾不徐地感受这里的精髓。

## 实用建议

- **最佳时间**：[春](/tag/季节/春)末[秋](/tag/季节/秋)初是最舒适的季节
- **预算参考**：人均200-500元/天（含交通餐饮门票）
- **行前准备**：提前了解开放时间和预约政策
- **周边联动**：可与[{city}](/tag/{geo})周边其他景点组合行程

## 总结

{name}是一处值得反复到访的目的地。每一次来都能发现新的惊喜，这正是{tag_links}的魅力所在。希望这篇[{angle}](/tag/Format/内容角度/{angle})能帮助你更好地规划行程，收获一段难忘的体验。
"""


# ━━━━━━━━━━━━━ 主流程 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    print("=" * 65)
    print(f"E2E Smoke v4: {TASK_ID} / {BATCH_ID}")
    print("=" * 65)

    # 清理旧数据
    tr = task_root(TASK_ID)
    if tr.exists():
        shutil.rmtree(tr)
    ensure_task_layout(TASK_ID)

    td = task_data(TASK_ID)

    # ─── 1. 复制 tags 从 publish/v1 ─────────────────────────────────
    print("\n[1/7] 复制标签体系...")
    src_tags = PUBLISH_ROOT / "v1" / "tags"
    if src_tags.exists():
        shutil.copytree(src_tags, td.tags_dir(), dirs_exist_ok=True)
    tag_count = len(list(td.tags_dir().rglob("_definition.json")))
    print(f"  {tag_count} 标签已复制")

    # ─── 2. 生成 entities ────────────────────────────────────────────
    print("\n[2/7] 生成实体...")
    entity_names = []
    for domain, etype, name, geo, tags, desc, aliases in ENTITIES:
        w(td.entity_json(domain, etype, name), {
            "aliases": aliases,
            "tagRefs": tags,
            "geoTagRef": geo,
            "description": desc,
            "createdAt": NOW_ISO,
            "updatedAt": NOW_ISO,
        })
        page_content = gen_page_content(domain, etype, name, desc, geo, tags)
        w(td.entity_page(domain, etype, name), page_content)
        w(td.entity_manifest(domain, etype, name), {
            "entityRefs": [],
            "tagRefs": tags + [f"Entity/{domain}/{etype}"],
            "assets": [f"{name}_panorama.jpg", f"{name}_highlight.jpg"],
            "createdAt": NOW_ISO,
            "updatedAt": NOW_ISO,
        })
        entity_names.append((domain, etype, name))
    print(f"  {len(ENTITIES)} 实体已生成")

    # ─── 3. 生成 posts ───────────────────────────────────────────────
    print("\n[3/7] 生成 posts...")
    post_count = 0
    for domain, etype, name, geo, tags, desc, aliases in ENTITIES:
        angles = TYPE_ANGLES.get((domain, etype), ["攻略", "体验"])
        for angle in angles:
            title = f"{name}{angle}指南"
            article = gen_article(name, domain, etype, angle, tags, geo)
            w(td.post_article("article", f"Format/内容角度/{angle}", title, 1), article)
            w(td.post_manifest("article", f"Format/内容角度/{angle}", title, 1), {
                "entityRefs": [f"{domain}/{etype}/{name}"],
                "tagRefs": tags + [f"Format/内容角度/{angle}"],
                "sourcePaths": [f"download/sources/{name}/source_01.html"],
                "assets": [f"{name}_{angle}_cover.jpg", f"{name}_{angle}_detail.jpg"],
                "createdAt": NOW_ISO,
                "updatedAt": NOW_ISO,
            })
            post_count += 1
    print(f"  {post_count} 篇 post 已生成")

    # ─── 4. 三段式命令结构 ───────────────────────────────────────────
    print("\n[4/7] 构建三段式命令结构...")
    for cmd in COMMANDS[:-1]:  # exclude publish
        ensure_batch_layout(TASK_ID, BATCH_ID, cmd)
        cmd_root = batch_command_root(TASK_ID, BATCH_ID, cmd)

        steps = {
            "explore": [("geo_discovery", "基于四川省全域范围发现实体")],
            "build": [("entity_extract", "提取并标准化实体信息"),
                      ("tag_expand", "扩展标签体系")],
            "download": [("source_plan", "规划优质来源URL"),
                        ("quality_score", "对下载内容评分筛选")],
            "produce": [("compose", "基于优质来源润色生成文章"),
                       ("review", "审核文章质量")],
            "reconcile": [("consistency_check", "校验实体/标签/post引用一致性")],
        }

        for step, instruction in steps.get(cmd, []):
            w(cmd_root / "assistant_tasks" / f"{step}.json", {
                "step": step,
                "instruction": instruction,
                "createdAt": NOW_ISO,
            })
            inp_dir = cmd_root / "inputs" / step
            inp_dir.mkdir(parents=True, exist_ok=True)
            w(inp_dir / "input.json", {
                "taskId": TASK_ID,
                "batchId": BATCH_ID,
                "step": step,
                "entityCount": len(ENTITIES),
                "createdAt": NOW_ISO,
            })
            res_dir = cmd_root / "results" / step
            res_dir.mkdir(parents=True, exist_ok=True)
            w(res_dir / "result.json", {
                "taskId": TASK_ID,
                "batchId": BATCH_ID,
                "step": step,
                "status": "completed",
                "completedAt": NOW_ISO,
            })
    print(f"  {len(COMMANDS) - 1} 命令三段式完成")

    # ─── 5. changeset ────────────────────────────────────────────────
    print("\n[5/7] 生成 changeset...")
    cs = task_changeset_dir(TASK_ID)
    w(cs / "entities.txt", "\n".join(f"{d}/{t}/{n}" for d, t, n in entity_names) + "\n")
    w(cs / "tags.txt", "\n".join(
        str(p.parent.relative_to(td.tags_dir()))
        for p in td.tags_dir().rglob("_definition.json")
    ) + "\n")
    post_ids = []
    for domain, etype, name, geo, tags, desc, aliases in ENTITIES:
        angles = TYPE_ANGLES.get((domain, etype), ["攻略", "体验"])
        for angle in angles:
            post_ids.append(f"article/内容角度/{angle}/{name}{angle}指南/1")
    w(cs / "posts.txt", "\n".join(post_ids) + "\n")
    print(f"  entities={len(entity_names)}, posts={len(post_ids)}")

    # ─── 6. task_manifest ────────────────────────────────────────────
    print("\n[6/7] 生成 task_manifest...")
    w(task_manifest(TASK_ID), {
        "taskId": TASK_ID,
        "operationType": "add",
        "status": "published",
        "entityCount": len(ENTITIES),
        "postCount": post_count,
        "createdAt": NOW_ISO,
        "publishedAt": NOW_ISO,
    })

    # ─── 7. publish ──────────────────────────────────────────────────
    print("\n[7/7] 发布到 publish/v1...")
    pv = publish_version_root(1)
    pd = publish_data(1)

    # tags（已有，不需再复制）
    # entities
    for domain, etype, name, geo, tags, desc, aliases in ENTITIES:
        for fname in ["_entity.json", "page.md", "manifest.json"]:
            src = td.entity_dir(domain, etype, name) / fname
            dst = pd.entity_dir(domain, etype, name) / fname
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    # posts
    for domain, etype, name, geo, tags, desc, aliases in ENTITIES:
        angles = TYPE_ANGLES.get((domain, etype), ["攻略", "体验"])
        for angle in angles:
            title = f"{name}{angle}指南"
            src_dir = td.post_dir("article", f"Format/内容角度/{angle}", title, 1)
            dst_dir = pd.post_dir("article", f"Format/内容角度/{angle}", title, 1)
            dst_dir.mkdir(parents=True, exist_ok=True)
            for f in src_dir.iterdir():
                shutil.copy2(f, dst_dir / f.name)

    # publish_meta
    w(publish_meta_path(), {"activeVersion": 1, "publishedAt": NOW_ISO})

    # 统计
    p_tags = len(list(pd.tags_dir().rglob("_definition.json")))
    p_entities = len(list(pd.entities_dir().rglob("_entity.json")))
    p_posts = len(list(pd.posts_dir().rglob("manifest.json")))

    print(f"\n{'=' * 65}")
    print(f"E2E Smoke v4 完成！")
    print(f"  runtime: {tag_count} tags, {len(ENTITIES)} entities, {post_count} posts")
    print(f"  publish:  {p_tags} tags, {p_entities} entities, {p_posts} posts")
    print(f"  命令结构: {len(COMMANDS)-1} 命令 x 三段式")
    print(f"  实体类型覆盖: 景区/遗址/打卡地/博物馆/美食街/古镇/餐厅/学校/赛事")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    main()
