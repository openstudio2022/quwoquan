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


def gen_topic_society_public_affairs():
    # 20. 三农生活
    tag("Topic/三农生活", "三农生活", "Rural Life & Agriculture", "农村农业农民生活内容")
    tags_list("Topic/三农生活", [
        ("农村生活", "Rural Life", "乡村日常生活记录"),
        ("农业种植", "Farming", "种地务农与农技"),
        ("农产品", "Agricultural Products", "农产品介绍与销售"),
        ("乡村旅游", "Rural Tourism", "农家乐与乡村游"),
        ("新农人", "New Farmer", "新型职业农民故事"),
    ])

    # 21. 宠物动物
    tag("Topic/宠物动物", "宠物动物", "Pets & Animals", "宠物饲养与动物内容")
    tags_list("Topic/宠物动物", [
        ("猫", "Cat", "猫咪饲养与日常", ["喵星人", "猫咪"]),
        ("狗", "Dog", "狗狗饲养与训练", ["旺星人", "狗狗"]),
        ("小动物", "Small Pets", "兔子仓鼠鱼等小动物"),
        ("异宠", "Exotic Pets", "蜥蜴蛇等异国宠物"),
        ("野生动物", "Wildlife", "野生动物科普与保护"),
        ("动物救助", "Animal Rescue", "流浪动物救助领养"),
        ("宠物医疗", "Pet Medical", "宠物健康与医疗"),
    ])

    # 22. 金融理财
    tag("Topic/金融理财", "金融理财", "Finance & Investment", "金融投资与个人理财内容")
    tags_list("Topic/金融理财", [
        ("股票基金", "Stocks & Funds", "股票基金投资"),
        ("储蓄存款", "Savings & Deposits", "储蓄理财与存款"),
        ("保险", "Insurance", "保险产品与规划"),
        ("房产投资", "Real Estate Investment", "房产买卖与投资"),
        ("加密货币", "Cryptocurrency", "区块链与数字货币"),
        ("消费理财", "Consumer Finance", "日常消费理财技巧"),
        ("贷款信用", "Loans & Credit", "信用卡贷款知识"),
    ])

    # 23. 非遗民俗（独立垂类，与历史文化正交）
    tag("Topic/非遗民俗", "非遗民俗", "Intangible Heritage", "非物质文化遗产与民间风俗")
    tags_list("Topic/非遗民俗", [
        ("戏曲艺术", "Traditional Opera", "京剧川剧豫剧等戏曲艺术"),
        ("传统音乐", "Traditional Music", "民乐古琴等传统音乐"),
        ("民间工艺", "Folk Crafts", "剪纸糖画皮影等民间工艺"),
        ("传统节庆", "Traditional Festivals", "春节中秋端午等传统节日"),
        ("少数民族文化", "Ethnic Minority Culture", "各少数民族独特文化"),
        ("地方方言", "Local Dialect", "方言文化与保护"),
        ("民俗活动", "Folk Activities", "庙会祭祀等民俗活动"),
    ])

    # 24. 宗教信仰（独立垂类）
    tag("Topic/宗教信仰", "宗教信仰", "Religion & Belief", "宗教文化与信仰相关内容")
    tags_list("Topic/宗教信仰", [
        ("佛教", "Buddhism", "佛教寺庙与修行"),
        ("道教", "Taoism", "道教文化与道观"),
        ("伊斯兰教", "Islam", "伊斯兰文化与清真寺"),
        ("基督教", "Christianity", "基督教文化与教堂"),
        ("民间信仰", "Folk Religion", "妈祖关帝等民间信仰"),
        ("藏传佛教", "Tibetan Buddhism", "藏传佛教文化"),
    ])

    # 25. 命理玄学（独立垂类；MBTI 见 Topic/健康养生/心理健康/MBTI）
    tag("Topic/命理玄学", "命理玄学", "Metaphysics & Fortune", "星座、塔罗、风水生肖等民俗玄学内容")
    tags_list("Topic/命理玄学", [
        ("星座", "Zodiac Signs", "十二星座性格与运势",
         ["十二星座"]),
        ("塔罗牌", "Tarot", "塔罗牌占卜"),
        ("风水玄学", "Feng Shui", "风水与玄学文化"),
        ("生肖运势", "Chinese Zodiac", "十二生肖运势"),
        ("血型性格", "Blood Type Personality", "血型与性格分析"),
    ])
    tags_list("Topic/命理玄学/星座", [
        ("白羊座", "Aries", "白羊座"),
        ("金牛座", "Taurus", "金牛座"),
        ("双子座", "Gemini", "双子座"),
        ("巨蟹座", "Cancer", "巨蟹座"),
        ("狮子座", "Leo", "狮子座"),
        ("处女座", "Virgo", "处女座"),
        ("天秤座", "Libra", "天秤座"),
        ("天蝎座", "Scorpio", "天蝎座"),
        ("射手座", "Sagittarius", "射手座"),
        ("摩羯座", "Capricorn", "摩羯座"),
        ("水瓶座", "Aquarius", "水瓶座"),
        ("双鱼座", "Pisces", "双鱼座"),
    ])

    # 26. 法律政务
    tag("Topic/法律政务", "法律政务", "Law & Government", "法律知识与政务服务内容")
    tags_list("Topic/法律政务", [
        ("法律常识", "Legal Knowledge", "日常法律知识普及"),
        ("维权指南", "Rights Protection", "消费者权益维权"),
        ("政策解读", "Policy Interpretation", "政府政策解读"),
        ("行政办事", "Government Services", "政务办理指南"),
        ("劳动权益", "Labor Rights", "劳动合同与工资权益"),
    ])

    # 27. 公益社会
    tag("Topic/公益社会", "公益社会", "Public Interest & Society", "公益活动与社会议题内容")
    tags_list("Topic/公益社会", [
        ("环保绿色", "Environmental Protection", "环保行动与低碳生活"),
        ("慈善公益", "Charity", "慈善募捐与公益活动"),
        ("社会民生", "Social Issues", "民生问题与社会话题"),
        ("女性平权", "Gender Equality", "女性权益与性别平等"),
        ("残障关怀", "Disability Care", "残障人士关怀与无障碍"),
    ])

    # 28. 军事国防
    tag("Topic/军事国防", "军事国防", "Military & Defense", "军事装备与国防文化内容")
    tags_list("Topic/军事国防", [
        ("军事装备", "Military Equipment", "武器装备科普"),
        ("军事历史", "Military History", "战争历史与军事史"),
        ("国防教育", "National Defense Education", "爱国主义与国防教育"),
        ("军旅生活", "Military Life", "军人日常与军营文化"),
    ])

    # 29. 国际视野
    tag("Topic/国际视野", "国际视野", "Global Perspective", "国际新闻与跨文化内容")
    tags_list("Topic/国际视野", [
        ("国际新闻", "World News", "全球时事新闻"),
        ("跨文化交流", "Cross-Cultural Exchange", "不同文化的交流碰撞"),
        ("海外华人", "Overseas Chinese", "海外华人生活"),
        ("国家文化", "National Culture", "各国文化与风土人情"),
        ("外语学习动态", "Language Learning Trends", "全球语言学习热点"),
    ])

    # 30. 购物消费
    tag("Topic/购物消费", "购物消费", "Shopping & Consumer", "购物攻略与消费趋势内容")
    tags_list("Topic/购物消费", [
        ("电商购物", "E-commerce", "网购平台与购物攻略"),
        ("线下购物", "Offline Shopping", "实体商场与购物中心"),
        ("奢侈品", "Luxury Goods", "奢侈品鉴别与购买"),
        ("二手交易", "Second-hand Trade", "二手物品交易"),
        ("海淘代购", "Cross-border Shopping", "海外购物与代购"),
        ("特卖折扣", "Sales & Discounts", "特卖活动与折扣攻略"),
        ("好物清单", "Shopping List", "精选好物推荐清单"),
    ])
