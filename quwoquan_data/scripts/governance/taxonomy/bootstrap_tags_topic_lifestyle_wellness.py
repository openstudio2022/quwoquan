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


def gen_topic_lifestyle_wellness():
    # 5. 时尚穿搭（风格 / 场景 / 单品 / 搭配方法）
    tag("Topic/时尚穿搭", "时尚穿搭", "Fashion & Style", "服饰穿搭与时尚潮流内容")
    tags_list("Topic/时尚穿搭", [
        ("日常穿搭", "Daily Outfit", "日常生活服装搭配"),
        ("职场穿搭", "Office Outfit", "职场正式商务着装"),
        ("通勤穿搭", "Commute Outfit", "通勤上班场景穿搭"),
        ("户外穿搭", "Outdoor Outfit", "户外运动功能性着装"),
        ("旅行穿搭", "Travel Outfit", "旅行出游场景穿搭"),
        ("约会穿搭", "Date Outfit", "约会浪漫风格着装"),
        ("婚礼穿搭", "Wedding Outfit", "婚礼与庆典着装"),
        ("宴会穿搭", "Banquet Outfit", "宴会与正式场合着装"),
        ("运动穿搭", "Sports Outfit", "运动健身着装"),
        ("复古风", "Vintage Style", "复古vintage风格穿搭"),
        ("汉服", "Hanfu", "中国传统汉服文化"),
        ("国潮", "Chinese Trendy", "中国潮流国货时尚", ["国风潮流"]),
        ("极简风", "Minimalist Style", "极简主义穿搭"),
        ("街头风", "Streetwear", "街头嘻哈潮流穿搭"),
        ("洛丽塔", "Lolita Fashion", "洛丽塔甜美风格", ["Lolita", "Lo裙"]),
        ("JK制服", "JK Uniform", "日系学院制服风格"),
        ("鞋包配饰", "Shoes Bags Accessories", "鞋类包包饰品搭配"),
        ("单品推荐", "Item Recommendation", "单件服饰产品推荐"),
    ])

    # 6. 美妆护肤（护肤 / 彩妆 / 造型修饰 / 工具与产品）
    tag("Topic/美妆护肤", "美妆护肤", "Beauty & Skincare", "美妆护肤化妆品相关内容")
    tags_list("Topic/美妆护肤", [
        ("护肤流程", "Skincare Routine", "日常护肤步骤与流程"),
        ("防晒", "Sunscreen", "防晒与紫外线防护"),
        ("底妆", "Base Makeup", "粉底遮瑕等底妆技巧"),
        ("眼妆", "Eye Makeup", "眼影眼线睫毛膏等眼妆"),
        ("眼霜", "Eye Cream", "眼周护理与眼霜"),
        ("唇妆", "Lip Makeup", "口红唇釉唇线笔"),
        ("彩妆教程", "Makeup Tutorial", "全套彩妆教学"),
        ("仿妆", "Cosplay Makeup", "明星仿妆角色仿妆"),
        ("医美抗衰", "Medical Beauty", "医美项目与抗老护肤"),
        ("面膜", "Mask Care", "面膜与密集护理"),
        ("精华", "Serum", "精华液与功效型护理"),
        ("素人改造", "Makeover", "普通人化妆前后对比"),
        ("香水调香", "Perfume & Fragrance", "香水品鉴与调香"),
        ("美甲美睫", "Nail & Lash Art", "美甲美睫美容内容"),
        ("发型发色", "Hairstyle", "染发烫发造型"),
        ("男士护肤", "Men Skincare", "男性护肤与男妆"),
        ("平价好物", "Budget Beauty", "性价比高的美妆护肤品"),
        ("成分党", "Ingredient Focus", "护肤品成分研究"),
    ])

    # 7. 健康养生
    tag("Topic/健康养生", "健康养生", "Health & Wellness", "健康生活方式与养生保健内容")
    tags_list("Topic/健康养生", [
        ("中医养生", "Traditional Chinese Medicine", "中医调理与养生方法"),
        ("营养健康", "Nutrition", "饮食营养与健康饮食"),
        ("减肥塑形", "Weight Loss & Body Shaping", "减肥健身塑形方法"),
        ("睡眠调理", "Sleep Health", "睡眠质量与作息调理"),
        ("女性健康", "Women's Health", "女性生理健康与保健"),
        ("慢病管理", "Chronic Disease Management", "高血压糖尿病等慢性病管理"),
        ("药品常识", "Medicine Knowledge", "常用药品与用药知识"),
        ("急救知识", "First Aid", "应急急救方法"),
        ("康复理疗", "Rehabilitation", "伤后康复与理疗"),
        ("瑜伽冥想", "Yoga & Meditation", "瑜伽练习与冥想放松"),
    ])
    tag("Topic/健康养生/心理健康", "心理健康", "Mental Health", "情绪管理与心理健康")
    tag("Topic/健康养生/心理健康/MBTI", "MBTI", "MBTI", "MBTI 与 16 型人格测评", ["16型人格"])
    tags_list("Topic/健康养生/心理健康/MBTI", [
        ("INTJ", "INTJ", "建筑师"),
        ("INTP", "INTP", "逻辑学家"),
        ("ENTJ", "ENTJ", "指挥官"),
        ("ENTP", "ENTP", "辩论家"),
        ("INFJ", "INFJ", "提倡者"),
        ("INFP", "INFP", "调停者"),
        ("ENFJ", "ENFJ", "主人公"),
        ("ENFP", "ENFP", "竞选者"),
        ("ISTJ", "ISTJ", "物流师"),
        ("ISFJ", "ISFJ", "守卫者"),
        ("ESTJ", "ESTJ", "总经理"),
        ("ESFJ", "ESFJ", "执政官"),
        ("ISTP", "ISTP", "鉴赏家"),
        ("ISFP", "ISFP", "探险家"),
        ("ESTP", "ESTP", "企业家"),
        ("ESFP", "ESFP", "表演者"),
    ])

    # 8. 运动（休闲健身 / 户外探险 / 竞技体育 / 极限运动；电竞赛事后续拆出独立主轴）
    tag("Topic/运动", "运动", "Sports", "运动健身、户外探险、竞技体育、极限运动与电竞内容")
    tag("Topic/运动/休闲健身", "休闲健身", "Leisure Fitness", "以健康与体态为目标的日常运动")
    tags_list("Topic/运动/休闲健身", [
        ("瑜伽", "Yoga", "瑜伽练习与教学"),
        ("跑步", "Running", "跑步健身与马拉松"),
        ("健身房训练", "Gym Workout", "室内健身器械训练"),
        ("舞蹈健身", "Dance Fitness", "舞蹈健身类运动"),
        ("女性健身", "Women's Fitness", "针对女性的健身内容"),
    ])
    tag("Topic/运动/户外探险", "户外探险", "Outdoor Adventure", "户外环境与探险类运动")
    tags_list("Topic/运动/户外探险", [
        ("登山", "Mountaineering", "山地攀登与徒步登顶"),
        ("攀岩", "Rock Climbing", "户外与室内攀岩"),
        ("溯溪", "Canyoneering", "溯溪探险运动"),
        ("定向越野", "Orienteering", "定向越野运动"),
        ("飞行运动", "Air Sports", "滑翔伞、跳伞等空中运动"),
        ("水上运动", "Water Sports", "冲浪、帆船、皮划艇等水上运动"),
        ("露营野营", "Camping", "野外露营与营地生活"),
        ("自驾越野", "Off-road Driving", "越野自驾与穿越"),
    ])
    tag("Topic/运动/竞技体育", "竞技体育", "Competitive Sports", "规则化赛事与竞技观赏")
    tags_list("Topic/运动/竞技体育", [
        ("足球", "Football/Soccer", "足球赛事与球队"),
        ("篮球", "Basketball", "篮球赛事"),
        ("网球", "Tennis", "网球赛事"),
        ("羽毛球", "Badminton", "羽毛球运动与赛事"),
        ("乒乓球", "Table Tennis", "乒乓球运动"),
        ("田径", "Athletics", "田赛径赛等田径项目"),
        ("游泳", "Swimming", "竞技游泳与公开水域游泳"),
        ("格斗搏击", "Combat Sports", "拳击、格斗等搏击赛事"),
        ("冬奥冬运", "Winter Sports Competition", "冰雪项目竞技与冬奥相关"),
    ])
    tag("Topic/运动/极限运动", "极限运动", "Extreme Sports", "高风险与技巧型极限项目")
    tags_list("Topic/运动/极限运动", [
        ("跳伞", "Skydiving", "高空跳伞与翼装等"),
        ("冲浪", "Surfing", "海浪冲浪运动"),
        ("滑板", "Skateboarding", "滑板街头与碗池"),
        ("滑雪滑冰", "Skiing & Skating", "滑雪与滑冰类项目"),
        ("蹦极", "Bungee Jumping", "蹦极等高空弹跳"),
    ])
    tag("Topic/运动/电竞", "电竞", "Esports", "电子竞技与游戏竞技内容")
    tags_list("Topic/运动/电竞", [
        ("电竞赛事", "Esports Events", "职业与大众电竞赛事、战队与杯赛"),
        ("游戏竞技直播", "Game & Esports Live", "游戏与电竞向直播内容"),
    ])
