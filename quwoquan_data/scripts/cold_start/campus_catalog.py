"""校园冷启动标杆 catalog（10 所 985/211 高校）。"""
from __future__ import annotations

CAMPUS_TASK_ID = "校园冷启动_首批50校"
CAMPUS_BATCH_ID = "pilot"
CAMPUS_RELEASE_ID = "campus_cold_start_r1"

# angle, format_ref (None for 索引), topic_ref, template
CAMPUS_POST_SPECS: list[tuple[str, str | None, str, str]] = [
    ("索引", None, "Topic/教育成长/校园生活", "journal"),
    ("新生攻略", "Format/内容角度/攻略/新生攻略", "Topic/教育成长/校园生活", "gentle"),
    ("校园评测", "Format/内容角度/测评/校园评测", "Topic/教育成长/校园生活", "journal"),
]

CAMPUS_SCHOOLS: list[dict] = [
    {
        "name": "四川大学",
        "label_en": "Sichuan University",
        "geo": "Topic/地理/行政区/中国/四川省/成都市",
        "motto": "海纳百川 有容乃大",
        "tags": [
            "Entity/机构/学校/大学",
            "Entity/机构/学校/985高校",
            "Entity/机构/学校/211高校",
            "Entity/机构/学校/双一流",
            "Entity/机构/学校/综合类",
            "Entity/机构/学校/公办",
        ],
        "highlights": [
            "望江、华西、江安三校区，口腔医学与文史学科全国领先。",
            "新生可先锁定望江校区周边动线与地铁接驳。",
            "校园生活标签：[/tag/Topic/教育成长/校园生活](/tag/Topic/教育成长/校园生活)",
        ],
    },
    {
        "name": "北京大学",
        "label_en": "Peking University",
        "geo": "Topic/地理/行政区/中国/北京市",
        "motto": "爱国进步民主科学",
        "tags": [
            "Entity/机构/学校/大学",
            "Entity/机构/学校/985高校",
            "Entity/机构/学校/211高校",
            "Entity/机构/学校/双一流",
            "Entity/机构/学校/综合类",
            "Entity/机构/学校/公办",
        ],
        "highlights": [
            "燕园未名湖与博雅塔是校园地标，人文社科底蕴深厚。",
            "建议新生熟悉选课系统与通识课节奏。",
            "关注 [/tag/Audience/圈子/校园圈/母校圈](/tag/Audience/圈子/校园圈/母校圈) 社群。",
        ],
    },
    {
        "name": "清华大学",
        "label_en": "Tsinghua University",
        "geo": "Topic/地理/行政区/中国/北京市",
        "motto": "自强不息 厚德载物",
        "tags": [
            "Entity/机构/学校/大学",
            "Entity/机构/学校/985高校",
            "Entity/机构/学校/211高校",
            "Entity/机构/学校/双一流",
            "Entity/机构/学校/理工类",
            "Entity/机构/学校/公办",
        ],
        "highlights": [
            "工科与基础学科优势突出，校园面积广阔。",
            "新生需提前了解院系分流与实验室安全规范。",
            "理工氛围浓厚，建议平衡学业与社团活动。",
        ],
    },
    {
        "name": "复旦大学",
        "label_en": "Fudan University",
        "geo": "Topic/地理/行政区/中国/上海市",
        "motto": "博学而笃志 切问而近思",
        "tags": [
            "Entity/机构/学校/大学",
            "Entity/机构/学校/985高校",
            "Entity/机构/学校/211高校",
            "Entity/机构/学校/双一流",
            "Entity/机构/学校/综合类",
            "Entity/机构/学校/公办",
        ],
        "highlights": [
            "邯郸、枫林、张江、江湾四校区，新闻与医学见长。",
            "上海生活成本较高，新生可提前规划住宿与通勤。",
        ],
    },
    {
        "name": "浙江大学",
        "label_en": "Zhejiang University",
        "geo": "Topic/地理/行政区/中国/浙江省/杭州市",
        "motto": "求是创新",
        "tags": [
            "Entity/机构/学校/大学",
            "Entity/机构/学校/985高校",
            "Entity/机构/学校/211高校",
            "Entity/机构/学校/双一流",
            "Entity/机构/学校/综合类",
            "Entity/机构/学校/公办",
        ],
        "highlights": [
            "紫金港、玉泉、西溪、华家池、之江多校区布局。",
            "工科与农学、计算机学科实力突出。",
        ],
    },
    {
        "name": "武汉大学",
        "label_en": "Wuhan University",
        "geo": "Topic/地理/行政区/中国/湖北省/武汉市",
        "motto": "自强 弘毅 求是 拓新",
        "tags": [
            "Entity/机构/学校/大学",
            "Entity/机构/学校/985高校",
            "Entity/机构/学校/211高校",
            "Entity/机构/学校/双一流",
            "Entity/机构/学校/综合类",
            "Entity/机构/学校/公办",
        ],
        "highlights": [
            "樱花季与东湖风光是校园名片，测绘、法学、图书情报等学科知名。",
            "夏季湿热，新生需关注宿舍空调与防蚊措施。",
        ],
    },
    {
        "name": "南京大学",
        "label_en": "Nanjing University",
        "geo": "Topic/地理/行政区/中国/江苏省/南京市",
        "motto": "诚朴雄伟 励学敦行",
        "tags": [
            "Entity/机构/学校/大学",
            "Entity/机构/学校/985高校",
            "Entity/机构/学校/211高校",
            "Entity/机构/学校/双一流",
            "Entity/机构/学校/综合类",
            "Entity/机构/学校/公办",
        ],
        "highlights": [
            "鼓楼、仙林、苏州校区，文理基础学科传统强校。",
            "学术氛围严谨，适合慢热型新生逐步融入。",
        ],
    },
    {
        "name": "上海交通大学",
        "label_en": "Shanghai Jiao Tong University",
        "geo": "Topic/地理/行政区/中国/上海市",
        "motto": "饮水思源 爱国荣校",
        "tags": [
            "Entity/机构/学校/大学",
            "Entity/机构/学校/985高校",
            "Entity/机构/学校/211高校",
            "Entity/机构/学校/双一流",
            "Entity/机构/学校/理工类",
            "Entity/机构/学校/公办",
        ],
        "highlights": [
            "闵行、徐汇、黄浦等校区，船舶、机械、医学、安泰经管等学科领先。",
            "工科实验课比例高，注意时间管理与安全培训。",
        ],
    },
    {
        "name": "同济大学",
        "label_en": "Tongji University",
        "geo": "Topic/地理/行政区/中国/上海市",
        "motto": "同舟共济",
        "tags": [
            "Entity/机构/学校/大学",
            "Entity/机构/学校/985高校",
            "Entity/机构/学校/211高校",
            "Entity/机构/学校/双一流",
            "Entity/机构/学校/理工类",
            "Entity/机构/学校/公办",
        ],
        "highlights": [
            "建筑、土木、交通、汽车等传统王牌学科。",
            "四平路、嘉定、沪西等校区风格各异。",
        ],
    },
    {
        "name": "中国人民大学",
        "label_en": "Renmin University of China",
        "geo": "Topic/地理/行政区/中国/北京市",
        "motto": "实事求是",
        "tags": [
            "Entity/机构/学校/大学",
            "Entity/机构/学校/985高校",
            "Entity/机构/学校/211高校",
            "Entity/机构/学校/双一流",
            "Entity/机构/学校/综合类",
            "Entity/机构/学校/公办",
        ],
        "highlights": [
            "人文社科、法学、经济学、新闻学见长。",
            "中关村校区生活便利，实习与讲座资源丰富。",
        ],
    },
]


def build_post_tag_refs(school: dict, angle: str, format_ref: str | None) -> list[str]:
    refs = list(school["tags"]) + [school["geo"], "Topic/教育成长"]
    topic = next(t for a, f, t, _ in CAMPUS_POST_SPECS if a == angle)
    refs.append(topic)
    if format_ref:
        refs.append(format_ref)
    if angle == "索引":
        refs.append("Audience/圈子/校园圈/母校圈")
    seen: set[str] = set()
    out: list[str] = []
    for r in refs:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out
