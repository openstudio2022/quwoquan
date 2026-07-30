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

def gen_entity():
    group("Entity", "实体类型", "Entity",
          "描述具体对象的类型骨架（地点/机构/活动/人物/品牌/作品/商品/生物/交通工具）。注意：此处只有类型标签，具体实例（海底捞/峨眉山/李白等）进入 entities/ 目录，通过 tagRefs 关联到本树的类型节点。",
          ["Entity/地点", "Entity/机构", "Entity/活动", "Entity/人物",
           "Entity/品牌", "Entity/作品", "Entity/商品", "Entity/生物", "Entity/交通工具"])

    _gen_entity_地点()
    _gen_entity_机构()
    _gen_entity_活动()
    _gen_entity_人物()
    _gen_entity_品牌()
    _gen_entity_作品()
    _gen_entity_商品()
    _gen_entity_生物()
    _gen_entity_交通工具()


def _gen_entity_地点():
    dim("Entity/地点", "地点类型", "Place Type",
        "有明确地理位置的实体类型，具体地点实例进入 entities/地点/ 目录；国家节点与 Topic/地理/行政区 对齐",
        max_depth=4, expected_size=120)

    tag("Entity/地点/景区", "景区", "Scenic Area", "旅游景区的等级与类型")
    tags_list("Entity/地点/景区", [
        ("5A景区", "5A Scenic Spot", "国家5A级旅游景区"),
        ("4A景区", "4A Scenic Spot", "国家4A级旅游景区"),
        ("3A景区", "3A Scenic Spot", "国家3A级旅游景区"),
        ("世界遗产", "World Heritage", "联合国教科文世界遗产"),
        ("国家公园", "National Park", "国家公园体系"),
        ("自然保护区", "Nature Reserve", "自然生态保护区"),
        ("地质公园", "Geopark", "地质地貌公园"),
        ("湿地公园", "Wetland Park", "国家湿地公园"),
    ])

    tag("Entity/地点/遗址", "遗址", "Heritage Site", "历史文化遗址类型")
    tags_list("Entity/地点/遗址", [
        ("考古遗址", "Archaeological Site", "考古发掘的古代遗址"),
        ("历史建筑", "Historic Building", "有历史价值的建筑"),
        ("文化遗产", "Cultural Heritage", "被列入保护的文化遗产"),
    ])

    tag("Entity/地点/古镇", "古镇", "Historic Town", "古镇古村类型")
    tags_list("Entity/地点/古镇", [
        ("历史古镇", "Historic Town", "保存传统风貌的古镇"),
        ("特色古村", "Characteristic Village", "具有地方特色的古村落"),
        ("民族风情村", "Ethnic Village", "少数民族特色村寨"),
    ])

    tag("Entity/地点/餐厅", "餐厅", "Restaurant", "餐饮经营业态分类（与 Topic/美食餐饮/菜系 正交：此处按经营形式分，非饮食流派）")
    tags_list("Entity/地点/餐厅", [
        ("中式正餐", "Chinese Restaurant", "中式正规堂食餐厅"),
        ("西式正餐", "Western Restaurant", "西式正规堂食餐厅"),
        ("日料餐厅", "Japanese Restaurant", "日本料理餐厅"),
        ("韩式餐厅", "Korean Restaurant", "韩式料理餐厅"),
        ("东南亚餐厅", "SEA Restaurant", "东南亚料理餐厅"),
        ("中东餐厅", "Middle Eastern Restaurant", "中东料理餐厅"),
        ("印度餐厅", "Indian Restaurant", "印度料理餐厅"),
        ("火锅店", "Hotpot Restaurant", "火锅经营业态"),
        ("烧烤店", "BBQ Restaurant", "烧烤经营业态"),
        ("串串店", "Skewer Shop", "串串香钵钵鸡业态"),
        ("小吃店", "Snack Shop", "地方小吃经营业态"),
        ("面馆", "Noodle Shop", "面食为主的餐厅"),
        ("米粉店", "Rice Noodle Shop", "米粉米线为主的餐厅"),
        ("茶馆", "Teahouse", "以品茶为主的休闲场所"),
        ("咖啡馆", "Cafe", "以咖啡为主的休闲场所"),
        ("酒吧", "Bar", "以酒水为主的社交场所"),
        ("奶茶店", "Milk Tea Shop", "新式茶饮经营业态"),
        ("烘焙甜品店", "Bakery & Dessert", "烘焙与甜品经营业态"),
        ("Bistro", "Bistro", "轻正式融合餐厅"),
        ("Omakase私厨", "Omakase", "主厨定制料理私厨"),
        ("快餐店", "Fast Food Restaurant", "标准化快餐经营业态"),
        ("自助餐厅", "Buffet Restaurant", "自助取餐经营业态"),
    ])

    tag("Entity/地点/住宿", "住宿", "Accommodation", "住宿经营业态类型骨架")
    dim("Entity/地点/住宿/设施服务", "设施服务", "Accommodation Amenities",
        "住宿实体的设施与服务配置骨架",
        max_depth=2, expected_size=8)
    tags_list("Entity/地点/住宿/设施服务", [
        ("厨房厨具", "Kitchen & Cookware", "提供厨房与厨具，可自炊"),
        ("接送服务", "Transfer Service", "提供接送或摆渡服务"),
        ("早餐服务", "Breakfast Service", "提供早餐或餐食服务"),
        ("洗衣服务", "Laundry Service", "提供洗衣与烘干服务"),
        ("停车位", "Parking", "提供停车位"),
        ("无障碍", "Accessible", "提供无障碍设施与服务"),
    ])
    dim("Entity/地点/住宿/房源形态", "房源形态", "Accommodation Form",
        "住宿实体的空间与房源形态骨架",
        max_depth=2, expected_size=8)
    tags_list("Entity/地点/住宿/房源形态", [
        ("树屋", "Treehouse", "树屋住宿形态"),
        ("合住房间", "Shared Room", "多人合住房间"),
        ("独立房间", "Private Room", "独立房间"),
        ("整租房源", "Entire Place", "整租房源"),
        ("套房", "Suite", "套房形态"),
    ])
    tags_list("Entity/地点/住宿", [
        ("酒店", "Hotel", "标准酒店业态"),
        ("民宿", "Homestay", "非标个人住宿业态"),
        ("客栈", "Inn", "传统风格小型住宿"),
        ("青旅", "Hostel", "青年旅舍业态"),
        ("度假村", "Resort", "度假村业态"),
        ("农家乐", "Farmhouse Stay", "农家住宿业态"),
        ("营地", "Campsite", "帐篷露营地"),
        ("酒店式公寓", "Serviced Apartment", "含酒店服务长租"),
        ("胶囊酒店", "Capsule Hotel", "胶囊迷你住宿"),
        ("特色住宿", "Unique Stay", "树屋船屋等非传统住宿"),
    ])

    tag("Entity/地点/打卡地", "打卡地", "Check-in Spot", "网红打卡地标与城市地标")
    tag("Entity/地点/美食街", "美食街", "Food Street", "集中美食摊贩的街道或区域")

    for etype, en, desc in [
        ("博物馆", "Museum", "博物馆与展馆"),
        ("公园", "Park", "城市公园与郊野"),
        ("宗教场所", "Religious Site", "寺庙道观教堂等"),
        ("温泉", "Hot Spring", "温泉度假场所"),
        ("书店", "Bookstore", "实体书店"),
        ("健身房", "Gym", "健身场馆"),
        ("运动场馆", "Sports Venue", "运动场馆"),
        ("购物中心", "Shopping Mall", "商业综合体"),
    ]:
        tag(f"Entity/地点/{etype}", etype, en, desc)

    tag("Entity/地点/自然景观", "自然景观", "Natural Feature",
        "山岳、水体、生态带等自然地物骨架，承接由 Topic/自然风光 与 Topic/地理/地形地貌 下沉的具体实例")
    tags_list("Entity/地点/自然景观", [
        ("山岳", "Mountain", "山地丘陵等地貌实体"),
        ("水体", "Water Body", "江河湖海等水体实体"),
        ("森林草原", "Forest & Grassland", "森林与草原生态系统"),
        ("湿地荒漠", "Wetland & Desert", "湿地与荒漠地貌"),
        ("冰雪带", "Snow & Ice Belt", "冰川与高寒冰雪带"),
        ("海岸海岛", "Coast & Island", "海岸线与岛屿"),
    ])

    # 主题乐园
    tag("Entity/地点/主题乐园", "主题乐园", "Theme Park",
        "以娱乐游乐为核心的综合性场所类型骨架")
    tags_list("Entity/地点/主题乐园", [
        ("综合主题乐园", "Comprehensive Theme Park", "迪士尼环球影城等综合主题乐园"),
        ("影视主题乐园", "Movie Theme Park", "以影视IP为主题的乐园"),
        ("动物主题乐园", "Animal Theme Park", "动物园与野生动物园"),
        ("水上乐园", "Water Park", "水上游乐设施为主的乐园"),
        ("儿童乐园", "Children's Park", "专为儿童设计的游乐场"),
        ("科幻乐园", "Sci-fi Theme Park", "科技与科幻主题的乐园"),
    ])

    # 交通枢纽
    tag("Entity/地点/交通枢纽", "交通枢纽", "Transport Hub",
        "交通运输核心节点类型骨架")
    tags_list("Entity/地点/交通枢纽", [
        ("机场", "Airport", "民用航空机场"),
        ("高铁站", "HSR Station", "高速铁路车站"),
        ("火车站", "Railway Station", "普通铁路车站"),
        ("客运站", "Bus Terminal", "长途客运站"),
        ("邮轮码头", "Cruise Terminal", "邮轮与客轮码头"),
        ("渡轮码头", "Ferry Terminal", "短途渡轮码头"),
        ("边境口岸", "Border Crossing", "陆路边境出入境口岸"),
    ])

    # 演艺场馆
    tag("Entity/地点/演艺场馆", "演艺场馆", "Performance Venue",
        "演出与表演场所类型骨架")
    tags_list("Entity/地点/演艺场馆", [
        ("剧院", "Theater", "话剧戏剧表演场馆"),
        ("歌剧院", "Opera House", "歌剧与音乐剧场馆"),
        ("音乐厅", "Concert Hall", "交响乐与室内乐演奏场馆"),
        ("演艺中心", "Performance Center", "综合文化演艺中心"),
        ("Live House", "Live House", "小型现场音乐演出场馆"),
        ("露天剧场", "Open-air Theater", "户外露天演出场地"),
    ])

    # 城市（扁平叶子标签，不分子类型）
    tag("Entity/地点/城市", "城市", "City",
        "城市级地点实体类型；具体城市实例在 entities/地点/城市/ 下建实体，"
        "通过 geoTagRef 关联行政区标签。城市属性（省会/旅游/历史等）通过 tagRefs 多标签描述")


def _gen_entity_机构():
    dim("Entity/机构", "机构类型", "Organization Type",
        "有组织架构的法人或团体类型", max_depth=4, expected_size=60)
    for etype, en, desc in [
        ("公司", "Company", "商业企业法人"),
        ("研究所", "Research Institute", "科研院所"),
        ("医院", "Hospital", "医疗卫生机构"),
        ("社团", "Association", "社会组织或协会"),
        ("政府机构", "Government Agency", "政府行政机构"),
        ("基金会", "Foundation", "公益基金会"),
        ("NGO", "NGO", "非政府组织"),
        ("媒体机构", "Media Organization", "媒体与传媒机构"),
    ]:
        tag(f"Entity/机构/{etype}", etype, en, desc)

    # 学校类型骨架（所有叶子直接挂在 Entity/机构/学校/ 下，深度=4，符合 R6 约束）
    tag("Entity/机构/学校", "学校", "School", "各级各类教育机构类型骨架，严禁出现具体学校实例名")

    # 学段类型
    for stype, en, desc in [
        ("幼儿园", "Kindergarten", "学前教育机构"),
        ("小学", "Primary School", "小学阶段教育机构"),
        ("初中", "Junior High School", "初级中学"),
        ("高中", "Senior High School", "高级中学"),
        ("完全中学", "Complete Secondary School", "包含初中和高中的完整中学"),
        ("九年一贯制学校", "9-year School", "小学到初中九年一贯制学校"),
        ("十二年一贯制学校", "12-year School", "小学到高中十二年一贯制学校"),
        ("中等职业学校", "Secondary Vocational School", "中专、技校、职高等中等职业教育机构"),
        ("大学", "University", "普通高等学校本科院校"),
        ("高职院校", "Vocational College", "高等职业技术学院"),
        ("国际学校", "International School", "国际课程体系学校"),
        ("特殊教育学校", "Special Education School", "特殊教育需求学校"),
        ("培训机构", "Training Institution", "课外培训与教育机构"),
    ]:
        tag(f"Entity/机构/学校/{stype}", stype, en, desc)

    # 高校层次属性
    for level, en, desc in [
        ("985高校", "Project 985", "985 工程重点建设高校"),
        ("211高校", "Project 211", "211 工程重点建设高校"),
        ("双一流", "Double First-Class", "世界一流大学和一流学科建设高校"),
        ("普通本科", "Regular Undergraduate", "非重点普通本科院校"),
        ("独立学院", "Independent College", "依托母体高校的独立学院"),
        ("民办本科", "Private Undergraduate", "民办普通本科高校"),
        ("中外合作办学", "Sino-foreign Joint", "中外合作办学机构"),
        ("军事院校", "Military Academy", "军队系统高等院校"),
    ]:
        tag(f"Entity/机构/学校/{level}", level, en, desc)

    # 高校学科类型属性
    for utype, en, desc in [
        ("综合类", "Comprehensive", "学科门类齐全的综合性大学"),
        ("理工类", "Science & Engineering", "以理工学科为主的院校"),
        ("师范类", "Normal/Teacher Training", "以教师培养为主的师范院校"),
        ("农林类", "Agriculture & Forestry", "以农林学科为主的院校"),
        ("医药类", "Medical & Pharmaceutical", "以医药学科为主的院校"),
        ("财经类", "Finance & Economics", "以财经学科为主的院校"),
        ("政法类", "Politics & Law", "以政法学科为主的院校"),
        ("体育类", "Sports", "以体育学科为主的院校"),
        ("艺术类", "Arts", "以艺术学科为主的院校"),
        ("军事类", "Military", "以军事学科为主的院校"),
        ("民族类", "Ethnic/Nationality", "以民族学科为主的院校"),
        ("语言类", "Language", "以外语及语言学科为主的院校"),
    ]:
        tag(f"Entity/机构/学校/{utype}", utype, en, desc)

    # 办学性质属性
    for own, en, desc in [
        ("公办", "Public", "政府主办的公立学校"),
        ("民办", "Private", "社会力量主办的民办学校"),
    ]:
        tag(f"Entity/机构/学校/{own}", own, en, desc)


def _gen_entity_活动():
    dim("Entity/活动", "活动类型", "Event Type",
        "有时间维度的聚集性活动类型", max_depth=3, expected_size=20)
    for etype, en, desc in [
        ("赛事", "Competition", "体育或文化竞技活动"),
        ("节庆", "Festival", "传统或现代节日庆典"),
        ("展会", "Exhibition", "行业展览或博览会"),
        ("演出", "Performance", "音乐戏剧现场表演"),
        ("大会论坛", "Conference", "学术商业论坛"),
        ("粉丝活动", "Fan Event", "粉丝见面会应援"),
    ]:
        tag(f"Entity/活动/{etype}", etype, en, desc)


def _gen_entity_人物():
    dim("Entity/人物", "人物类型", "Person Type",
        "可被关注或研究的人物类型骨架，具体人物实例进入 entities/人物/ 目录",
        max_depth=3, expected_size=30, path_policy="prefer-leaf")

    tag("Entity/人物/公众人物", "公众人物", "Public Figure",
        "有公众影响力的当代人物类型")
    tags_list("Entity/人物/公众人物", [
        ("演员", "Actor/Actress", "影视演员类型"),
        ("歌手", "Singer", "歌手/音乐人类型"),
        ("运动员", "Athlete", "专业运动员类型"),
        ("主持人", "Host", "节目主持人类型"),
        ("网红KOL", "KOL/Influencer", "网络意见领袖类型"),
        ("创业者", "Entrepreneur", "知名创业者类型"),
        ("科学家", "Scientist", "科学研究者类型"),
        ("政治家", "Politician", "政界人物类型"),
    ])

    tag("Entity/人物/历史人物", "历史人物", "Historical Figure",
        "在历史上有重要影响的人物类型")
    tags_list("Entity/人物/历史人物", [
        ("帝王", "Emperor/Ruler", "历史上的帝王君主"),
        ("文人", "Scholar/Poet", "古代文学家诗人"),
        ("科学家", "Historical Scientist", "历史科学家"),
        ("革命家", "Revolutionary", "近现代革命领袖"),
        ("民族英雄", "National Hero", "保家卫国的民族英雄"),
        ("思想家", "Philosopher", "历史哲学思想家"),
        ("军事家", "Military Strategist", "历史军事将领"),
    ])

    tag("Entity/人物/艺术家", "艺术家", "Artist",
        "从事艺术创作的专业人士类型")
    tags_list("Entity/人物/艺术家", [
        ("画家", "Painter", "绘画艺术家"),
        ("音乐家", "Musician", "音乐创作演奏家"),
        ("作家", "Author", "文学作家"),
        ("导演", "Director", "影视导演"),
        ("摄影师", "Photographer", "专业摄影师"),
        ("设计师", "Designer", "工业与视觉设计师"),
    ])

    tag("Entity/人物/达人", "达人", "Influencer",
        "某领域知名创作者达人类型")
    tags_list("Entity/人物/达人", [
        ("美食达人", "Food Influencer", "美食领域知名达人"),
        ("旅行达人", "Travel Influencer", "旅行领域知名达人"),
        ("科技达人", "Tech Influencer", "科技数码达人"),
        ("时尚达人", "Fashion Influencer", "时尚穿搭达人"),
        ("母婴达人", "Parenting Influencer", "母婴育儿达人"),
        ("运动达人", "Sports Influencer", "运动健身达人"),
    ])


def _gen_entity_品牌():
    dim("Entity/品牌", "品牌类型", "Brand Type",
        "商业品牌的类型骨架，具体品牌实例进入 entities/品牌/ 目录",
        max_depth=3, expected_size=50, path_policy="prefer-leaf")

    tag("Entity/品牌/餐饮品牌", "餐饮品牌", "Food Brand", "餐饮行业品牌类型")
    tags_list("Entity/品牌/餐饮品牌", [
        ("中式正餐品牌", "Chinese Restaurant Brand", "中式正规餐厅连锁品牌"),
        ("火锅品牌", "Hotpot Brand", "火锅连锁品牌类型"),
        ("茶饮品牌", "Tea Drink Brand", "新式茶饮连锁品牌"),
        ("咖啡品牌", "Coffee Brand", "咖啡连锁品牌"),
        ("快餐品牌", "Fast Food Brand", "快餐连锁品牌"),
        ("烘焙品牌", "Bakery Brand", "烘焙甜品连锁品牌"),
        ("小吃品牌", "Snack Brand", "地方小吃连锁品牌"),
    ])

    tag("Entity/品牌/住宿品牌", "住宿品牌", "Hospitality Brand", "酒店与住宿品牌类型")
    tags_list("Entity/品牌/住宿品牌", [
        ("国际奢华酒店品牌", "Intl Luxury Hotel Brand", "国际奢华酒店集团品牌"),
        ("国际商务酒店品牌", "Intl Business Hotel Brand", "国际商务酒店品牌"),
        ("国内连锁酒店品牌", "Domestic Hotel Chain", "中国本土连锁酒店品牌"),
        ("精品民宿品牌", "Boutique Homestay Brand", "精品民宿连锁品牌"),
    ])

    tag("Entity/品牌/汽车品牌", "汽车品牌", "Auto Brand", "汽车制造品牌类型")
    tags_list("Entity/品牌/汽车品牌", [
        ("豪华汽车品牌", "Luxury Auto Brand", "豪华级汽车品牌"),
        ("合资汽车品牌", "Joint Venture Auto", "中外合资汽车品牌"),
        ("国产汽车品牌", "Domestic Auto Brand", "中国自主汽车品牌"),
        ("新能源汽车品牌", "NEV Brand", "新能源汽车品牌"),
    ])

    for btype, en, desc in [
        ("运动品牌", "Sports Brand", "运动装备与服饰品牌类型"),
        ("科技品牌", "Tech Brand", "科技数码品牌类型"),
        ("时尚品牌", "Fashion Brand", "时装与奢侈品品牌类型"),
        ("家居品牌", "Home Brand", "家具家居品牌类型"),
        ("美妆品牌", "Beauty Brand", "美妆护肤品牌类型"),
        ("母婴品牌", "Baby Brand", "母婴产品品牌类型"),
        ("饮料品牌", "Beverage Brand", "饮品饮料品牌类型"),
        ("服饰品牌", "Apparel Brand", "服装服饰品牌类型"),
    ]:
        tag(f"Entity/品牌/{btype}", btype, en, desc)

    tag("Entity/品牌/摄影器材品牌", "摄影器材品牌", "Camera & Lens Brand",
        "相机、镜头与摄影附件制造品牌类型")
    tags_list("Entity/品牌/摄影器材品牌", [
        ("佳能", "Canon", "佳能相机与镜头品牌"),
        ("尼康", "Nikon", "尼康相机与镜头品牌"),
        ("索尼", "Sony Imaging", "索尼影像设备品牌"),
        ("富士", "Fujifilm", "富士胶片与数码相机品牌"),
        ("松下", "Panasonic Lumix", "松下Lumix影像品牌"),
        ("奥之心", "OM System", "原奥林巴斯影像品牌"),
        ("哈苏", "Hasselblad", "哈苏中画幅相机品牌"),
        ("徕卡", "Leica", "徕卡光学与相机品牌"),
        ("适马", "Sigma", "适马镜头与相机品牌"),
        ("腾龙", "Tamron", "腾龙镜头品牌"),
        ("大疆", "DJI", "大疆无人机与稳定器品牌"),
        ("智云", "Zhiyun", "智云稳定器品牌"),
    ])


def _gen_entity_作品():
    dim("Entity/作品", "作品类型", "Creative Work Type",
        "人类创造的文化与科技产物类型", max_depth=3, expected_size=20)
    for wtype, en, desc in [
        ("书籍", "Book", "出版物：小说/散文/科普/教材等"),
        ("电影", "Film", "电影：剧情/动画/纪录/科幻等"),
        ("音乐作品", "Music Work", "音乐：流行/古典/民族/电子等"),
        ("游戏", "Game", "游戏：RPG/FPS/策略/休闲等"),
        ("数码产品", "Digital Product", "电子数码硬件"),
        ("软件", "Software", "应用程序与系统"),
        ("艺术品", "Artwork", "绘画雕塑等艺术创作"),
        ("设计作品", "Design Work", "工业与视觉设计作品"),
        ("摄影集", "Photo Book", "摄影画册与影像出版物"),
        ("摄影展", "Photo Exhibition", "摄影展览与影像艺术展"),
    ]:
        tag(f"Entity/作品/{wtype}", wtype, en, desc)


def _gen_entity_商品():
    dim("Entity/商品", "商品", "Product",
        "可购买消费的商品骨架：物理品类 + 画像维度（原 Audience/商品 画像并入）",
        max_depth=4, expected_size=120, path_policy="prefer-leaf")

    # 类目是商品品类的唯一真相源。曾经存在扁平的 Entity/商品/{服饰,美妆,食品,数码,...}
    # 与 Entity/商品/类目/{服饰,美妆,食品饮料,...} 两套并行品类，同轴重名必然让其中一套
    # 成为孤儿（R14），故已合并到 类目 之下，子品类作为 类目 的第二层。
    dim("Entity/商品/类目", "类目", "Product Category",
        "商品所属的消费类目（画像）", max_depth=3, path_policy="prefer-leaf")
    for cat, en in [
        ("数码电子", "Digital Electronics"), ("家居家电", "Home & Appliances"),
        ("母婴", "Maternity & Baby"), ("运动户外", "Sports & Outdoor"),
        ("图书文具", "Books & Stationery"), ("玩具", "Toys"),
        ("旅游服务", "Travel Services"), ("医疗健康", "Healthcare"),
        ("汽车用品", "Auto Product"),
        # 宠物用品而非「宠物」：Entity/生物 已有宠物物种，同名会与物种骨架混淆。
        ("宠物用品", "Pet Products"),
    ]:
        tag(f"Entity/商品/类目/{cat}", cat, en, f"{cat}类商品")

    tag("Entity/商品/类目/服饰", "服饰", "Apparel", "服饰单品")
    tags_list("Entity/商品/类目/服饰", [
        ("上衣", "Top", "上装类型"),
        ("下装", "Bottom", "裤子裙子等下装"),
        ("外套", "Outerwear", "外套夹克类型"),
        ("鞋类", "Shoes", "各类鞋履"),
        ("包袋", "Bag", "包袋配件类型"),
        ("配饰", "Accessories", "首饰配饰类型"),
    ])

    tag("Entity/商品/类目/美妆", "美妆", "Beauty", "美妆护肤商品")
    tags_list("Entity/商品/类目/美妆", [
        ("护肤品", "Skincare", "护肤产品类型"),
        ("彩妆品", "Cosmetics", "彩妆产品类型"),
        ("香水", "Perfume", "香水香氛"),
        ("美容工具", "Beauty Tool", "美容仪器工具"),
    ])

    tag("Entity/商品/类目/食品饮料", "食品饮料", "Food & Beverage", "食品饮料商品")
    tags_list("Entity/商品/类目/食品饮料", [
        ("零食", "Snack", "休闲零食类型"),
        ("饮品", "Beverage", "饮料饮品类型"),
        ("生鲜食材", "Fresh Food", "生鲜农产品"),
        ("调味品", "Condiment", "调料酱料类型", ["酱料"]),
        ("保健品", "Health Supplement", "保健营养品"),
    ])

    dim("Entity/商品/价位段", "价位段", "Price Range",
        "商品价格区间（画像）", max_depth=2, path_policy="leaf-only")
    tags_list("Entity/商品/价位段", [
        ("平价", "Budget", "售价100元以内"),
        ("中端", "Mid-range", "售价100-500元"),
        ("高端", "Premium", "售价2000元以上"),
        ("奢侈", "Luxury", "售价1万元以上"),
    ])

    dim("Entity/商品/适用受众", "适用受众", "Target Audience",
        "商品主要适用的用户群体（画像）", max_depth=2)
    tags_list("Entity/商品/适用受众", [
        ("男性专属", "For Men", "男性用户专属商品"),
        ("女性专属", "For Women", "女性用户专属商品"),
        ("儿童", "For Kids", "儿童适用商品"),
        ("老年人", "For Seniors", "老年人适用商品"),
        ("情侣", "For Couples", "情侣共用商品"),
        ("全家", "Family Use", "全家适用商品"),
    ])

    dim("Entity/商品/适用场景", "适用场景", "Use Scene",
        "商品的主要使用场景（画像）", max_depth=2)
    tags_list("Entity/商品/适用场景", [
        ("日常使用", "Daily Use", "日常生活使用"),
        ("礼物赠送", "Gift", "适合作为礼物"),
        ("办公学习", "Office & Study", "办公室或学习使用"),
        ("旅行出行", "Travel Use", "旅行途中使用"),
        ("运动健身", "Sports Use", "运动健身使用"),
        ("居家", "Home Use", "家庭日常使用"),
    ])

    dim("Entity/商品/销售形式", "销售形式", "Sales Format",
        "主要销售渠道与形式（画像）", max_depth=2)
    tags_list("Entity/商品/销售形式", [
        ("自营电商", "Self-operated E-commerce", "品牌自营电商"),
        ("直播带货", "Livestream Commerce", "直播间销售"),
        ("品牌官方", "Brand Official", "品牌官方渠道"),
        ("海外代购", "Overseas Purchase", "海外商品代购"),
        ("定制品", "Custom Product", "个性化定制商品"),
    ])


def _gen_entity_生物():
    dim("Entity/生物", "生物类型", "Living Being Type",
        "可观赏、养护或科普的自然生命体类型", max_depth=3, expected_size=15)
    tag("Entity/生物/宠物", "宠物", "Pet", "家养宠物")
    tags_list("Entity/生物/宠物", [
        ("猫类", "Cat Species", "猫咪品种与类型"),
        ("犬类", "Dog Species", "狗狗品种与类型"),
        ("小动物类", "Small Pet", "兔仓鼠鱼等小动物"),
        ("异宠类", "Exotic Pet", "蜥蜴蛇等异国宠物"),
    ])
    tag("Entity/生物/植物", "植物", "Plant", "可观赏或栽培的植物")
    tags_list("Entity/生物/植物", [
        ("花卉", "Flower", "观赏花卉类型"),
        ("绿植", "Indoor Plant", "室内绿植类型"),
        ("多肉植物", "Succulent", "多肉植物类型"),
    ])
    tag("Entity/生物/野生动物", "野生动物", "Wildlife",
        "野生动物科普")
    tags_list("Entity/生物/野生动物", [
        ("哺乳动物", "Mammal", "野生哺乳动物"),
        ("鸟类", "Bird", "野生鸟类"),
        ("爬行动物", "Reptile", "爬行纲动物"),
        ("海洋生物", "Marine Life", "海洋水生生物"),
        ("国家级保护动物", "Protected Wildlife", "国家重点保护野生动物"),
    ])


def _gen_entity_交通工具():
    dim("Entity/交通工具", "交通工具类型", "Vehicle Type",
        "可体验或评测的移动载体类型", max_depth=3, expected_size=20)
    for vtype, en, desc in [
        ("汽车", "Car", "汽车车型：轿车/SUV/MPV等"),
        ("摩托车", "Motorcycle", "摩托车类型"),
        ("自行车", "Bicycle", "自行车与电动车类型"),
        ("房车", "RV", "房车旅行车类型"),
        ("船艇", "Boat", "船只与游艇类型"),
        ("飞机", "Aircraft", "民航客机与私人飞机类型"),
    ]:
        tag(f"Entity/交通工具/{vtype}", vtype, en, desc)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
