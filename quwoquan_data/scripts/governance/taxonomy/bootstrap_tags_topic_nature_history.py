"""Generated taxonomy section writer helpers split from bootstrap_tags.py."""
from __future__ import annotations

_WRITERS = {}


def configure_writers(**writers):
    _WRITERS.update(writers)


def group(*args, **kwargs):
    return _WRITERS["group"](*args, **kwargs)


def dim(*args, **kwargs):
    return _WRITERS["dim"](*args, **kwargs)


def tag(*args, **kwargs):
    return _WRITERS["tag"](*args, **kwargs)


def tags_list(*args, **kwargs):
    return _WRITERS["tags_list"](*args, **kwargs)


def gen_topic_nature_history():
    # 1. 自然风光（仅自然审美现象；具体地形实例见 Entity/地点/自然景观）
    tag("Topic/自然风光", "自然风光", "Nature & Scenery", "自然审美与天象类景观主题，侧重观感与现象而非行政区划")
    tags_list("Topic/自然风光", [
        ("彩林", "Autumn Forest", "秋季彩色林木景观"),
        ("星空", "Starry Sky", "银河星空自然夜景"),
        ("极光", "Aurora", "极光天象景观"),
        ("花海", "Flower Sea", "大面积鲜花景观"),
        ("森林", "Forest", "森林丛林林海景观"),
        ("湖泊", "Lakes", "高山湖泊与湖区景观"),
        ("云海", "Sea of Clouds", "云海云雾奇观"),
        ("雪山", "Snow Mountain", "雪山冰川与山岳景观"),
        ("高原风光", "Plateau Scenery", "高原地貌与开阔风光"),
        ("日出日落", "Sunrise & Sunset", "日出与日落天象景观"),
        ("雾凇", "Rime Ice", "雾凇冰挂等冬季凝结景观"),
        ("雪景", "Snowscape", "降雪与雪景氛围"),
        ("候鸟迁徙", "Bird Migration", "候鸟迁飞与观鸟季"),
    ])

    # 2. 历史文化（历史深度层；人文社科另行承载）
    tag("Topic/历史文化", "历史文化", "History & Culture", "人类历史遗迹、传统文化与文明相关主题")
    tags_list("Topic/历史文化", [
        ("古镇文化", "Ancient Town Culture", "古镇老街的历史风貌"),
        ("宗教文化", "Religious Culture", "佛教道教伊斯兰基督教等宗教文化", ["佛教", "道教"]),
        ("考古遗址", "Archaeological Site", "考古发掘与历史遗址"),
        ("红色文化", "Red Culture", "革命历史与红色精神"),
        ("帝王文化", "Imperial Culture", "皇家宫廷与帝制历史"),
        ("世界遗产", "World Heritage", "联合国教科文世界遗产"),
        ("三国文化", "Three Kingdoms Culture", "三国历史文化专题"),
        ("古蜀文明", "Ancient Shu Civilization", "古蜀国文化遗存"),
        ("石刻艺术", "Stone Carving Art", "石刻、石窟与雕刻艺术"),
        ("水利工程", "Water Conservancy Engineering", "古代与现代水利工程遗产"),
        ("丝绸之路", "Silk Road", "丝绸之路历史文化"),
        ("茶文化", "Tea Culture", "茶的历史、产地与文化", ["茶道", "茶艺"]),
        ("酒文化", "Wine & Liquor Culture", "白酒、黄酒、葡萄酒文化", ["白酒", "黄酒"]),
        ("节庆文化", "Festival Culture", "传统节日与民俗庆典"),
        ("建筑艺术", "Architectural Art", "传统与现代建筑艺术"),
        ("文物收藏", "Antique & Collection", "文物古玩与收藏鉴赏"),
    ])

    # 2b. 人文社科（人文观察与社会纪实，和历史深度分离）
    tag("Topic/人文社科", "人文社科", "Humanities & Social Science",
        "人文观察、社会纪实与文化评论内容")
    tags_list("Topic/人文社科", [
        ("城市观察", "Urban Observation", "城市空间、街区与生活方式观察"),
        ("社会纪实", "Social Documentary", "社会现实与纪实观察"),
        ("民俗风物", "Folkways & Customs", "民俗、节庆与地方风物"),
        ("旅行人文", "Travel Humanities", "旅行中的人文观察与记述"),
        ("乡土生活", "Local Life", "乡村、县城与地方日常生活"),
        ("文化评论", "Cultural Commentary", "文化现象与文化议题评论"),
        ("纪录片式观察", "Documentary Observation", "纪实镜头和观察式表达"),
        ("文学散记", "Literary Notes", "文学、散文与随笔式人文表达"),
    ])
