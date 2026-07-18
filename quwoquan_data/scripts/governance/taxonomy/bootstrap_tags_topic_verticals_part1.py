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

def gen_topic_verticals_part1():
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

    # 3. 美食餐饮（9 维正交：菜系/品类/饮品/就餐时段/用餐场合/饮食特征/风味口味/认证评级/特色食材）
    tag("Topic/美食餐饮", "美食餐饮", "Food & Dining",
        "饮食文化与餐饮全维度标签体系：菜系×品类×饮品×时段×场合×特征×口味×评级×食材，九维正交")

    # 3.1 菜系（饮食流派，回答"什么菜"）
    dim("Topic/美食餐饮/菜系", "菜系", "Cuisine",
        "按饮食文化流派分类；与品类（食物形态）和 Entity/地点/餐厅（经营业态）正交",
        max_depth=3, expected_size=40)
    tag("Topic/美食餐饮/菜系/中国菜系", "中国菜系", "Chinese Cuisine", "中国八大菜系及地方菜")
    tags_list("Topic/美食餐饮/菜系/中国菜系", [
        ("川菜", "Sichuan Cuisine", "以麻辣著称的四川菜系", ["四川菜", "蜀菜"]),
        ("粤菜", "Cantonese Cuisine", "广东为代表的粤式菜系"),
        ("苏菜", "Jiangsu Cuisine", "江苏淮扬菜系", ["淮扬菜"]),
        ("闽菜", "Fujian Cuisine", "福建海鲜为主的菜系"),
        ("浙菜", "Zhejiang Cuisine", "浙江杭帮菜系", ["杭帮菜"]),
        ("徽菜", "Anhui Cuisine", "安徽徽州菜系"),
        ("鲁菜", "Shandong Cuisine", "山东鲁菜系"),
        ("湘菜", "Hunan Cuisine", "湖南香辣菜系", ["湖南菜"]),
        ("京菜", "Beijing Cuisine", "北京宫廷与民间菜"),
        ("东北菜", "Northeast Cuisine", "东北地方特色菜"),
        ("云贵菜", "Yunnan-Guizhou Cuisine", "云南贵州少数民族特色菜"),
        ("新疆菜", "Xinjiang Cuisine", "新疆维吾尔族特色菜"),
        ("潮汕菜", "Chaoshan Cuisine", "广东潮汕地区菜系"),
        ("客家菜", "Hakka Cuisine", "客家围屋饮食文化"),
        ("台湾菜", "Taiwanese Cuisine", "台湾本土饮食文化"),
        ("港式菜", "Hong Kong Style", "港式茶餐厅与融合菜"),
        ("沪本帮", "Shanghainese", "上海本帮菜系", ["上海菜"]),
        ("陕菜", "Shaanxi Cuisine", "陕西面食与小吃"),
        ("桂菜", "Guangxi Cuisine", "广西米粉酸辣风味"),
    ])
    tag("Topic/美食餐饮/菜系/国际菜系", "国际菜系", "International Cuisine", "各国特色饮食文化")
    tags_list("Topic/美食餐饮/菜系/国际菜系", [
        ("日料", "Japanese Cuisine", "日本料理与寿司刺身"),
        ("韩餐", "Korean Cuisine", "韩国泡菜烤肉料理"),
        ("泰国菜", "Thai Cuisine", "泰式酸辣菜系"),
        ("越南菜", "Vietnamese Cuisine", "越南米粉春卷菜系"),
        ("印尼菜", "Indonesian Cuisine", "印度尼西亚沙爹菜系"),
        ("马来菜", "Malaysian Cuisine", "马来西亚娘惹菜系"),
        ("意大利菜", "Italian Cuisine", "意式披萨面食菜系"),
        ("法国菜", "French Cuisine", "法式精致餐饮"),
        ("西班牙菜", "Spanish Cuisine", "西班牙 Tapas 海鲜饭"),
        ("德国菜", "German Cuisine", "德式香肠啤酒菜系"),
        ("墨西哥菜", "Mexican Cuisine", "墨式卷饼辣酱菜系"),
        ("印度菜", "Indian Cuisine", "印度咖喱飞饼菜系"),
        ("中东菜", "Middle Eastern Cuisine", "阿拉伯土耳其烤肉菜系"),
        ("俄罗斯菜", "Russian Cuisine", "俄式罗宋汤菜系"),
        ("土耳其菜", "Turkish Cuisine", "土耳其烤肉甜品菜系"),
    ])

    # 3.2 品类（食物形态，回答"是什么食物"；与菜系正交，如"川菜火锅"="川菜菜系+火锅品类"）
    dim("Topic/美食餐饮/品类", "品类", "Food Category",
        "按食物形态分类；与菜系（文化流派）正交——同一菜系可出现多种品类",
        max_depth=2, expected_size=18)
    tags_list("Topic/美食餐饮/品类", [
        ("火锅", "Hotpot", "各地火锅文化", ["涮锅"]),
        ("烧烤", "BBQ & Grill", "烧烤炭火料理"),
        ("串串", "Skewers", "串串香与钵钵鸡"),
        ("麻辣烫", "Spicy Pot", "麻辣烫与冒菜"),
        ("面食", "Noodles", "面条饺子馄饨等面食类"),
        ("米粉", "Rice Noodles", "米粉米线等米制主食"),
        ("粥品", "Congee", "粥类与粥铺"),
        ("海鲜河鲜", "Seafood", "海鲜与河鲜料理"),
        ("小吃", "Snacks", "街边小吃与地方特色小食"),
        ("烘焙", "Bakery", "面包蛋糕饼干等烘焙"),
        ("甜品", "Desserts", "甜品糕点与冰品"),
        ("冰品", "Frozen Treats", "冰淇淋雪糕刨冰"),
        ("快餐", "Fast Food", "标准化快速餐饮"),
        ("Brunch", "Brunch", "早午餐 brunch 文化"),
        ("自助", "Buffet", "自助取餐形式"),
        ("夜宵", "Late Night Snack", "深夜食堂与夜宵文化"),
        ("外卖", "Takeaway", "外卖配送餐饮"),
        ("私房菜", "Private Kitchen", "非标准化家宴私厨"),
    ])

    # 3.3 饮品（独立维度，回答"喝什么"）
    dim("Topic/美食餐饮/饮品", "饮品", "Beverages",
        "饮品类别分类，与品类（食物）正交",
        max_depth=2, expected_size=12)
    tags_list("Topic/美食餐饮/饮品", [
        ("咖啡", "Coffee", "咖啡品鉴与文化"),
        ("茶饮", "Tea", "传统茶道与新式茶饮"),
        ("奶茶", "Milk Tea", "奶茶与珍珠奶茶文化"),
        ("果汁", "Juice", "鲜榨果汁与果昔"),
        ("葡萄酒", "Wine", "红酒白酒香槟品鉴"),
        ("白酒", "Baijiu", "中国白酒文化与品鉴"),
        ("啤酒", "Beer", "精酿啤酒与啤酒文化"),
        ("清酒", "Sake", "日本清酒与烧酒"),
        ("鸡尾酒", "Cocktail", "调酒与鸡尾酒文化"),
        ("特调饮品", "Signature Drink", "店家原创特调"),
        ("Bartender文化", "Bartender Culture", "调酒师文化与吧台体验"),
    ])

    # 3.4 就餐时段（时间维度）
    dim("Topic/美食餐饮/就餐时段", "就餐时段", "Meal Time",
        "就餐的时间维度",
        max_depth=2, expected_size=8)
    tags_list("Topic/美食餐饮/就餐时段", [
        ("早餐", "Breakfast", "早餐类餐饮"),
        ("早茶", "Morning Tea", "广式/港式早茶"),
        ("午餐", "Lunch", "午间正餐"),
        ("下午茶", "Afternoon Tea", "下午茶与甜品时间"),
        ("晚餐", "Dinner", "晚间正餐"),
        ("夜宵时段", "Late Night", "深夜食堂时段"),
        ("深夜食堂", "Midnight Diner", "午夜后深夜营业"),
        ("24小时餐饮", "24h Dining", "全天候营业"),
    ])

    # 3.5 用餐场合（在何种场合订这家店/这道菜；与 Topic/场景/社交场景 形成 IS-A 关系）
    dim("Topic/美食餐饮/用餐场合", "用餐场合", "Dining Occasion",
        "用餐的社交与事务场合；限定为餐饮维度的场景细化",
        max_depth=2, expected_size=9)
    tags_list("Topic/美食餐饮/用餐场合", [
        ("约会用餐", "Date Dining", "情侣约会用餐场景"),
        ("家庭聚餐", "Family Gathering", "家庭多人聚餐"),
        ("商务宴请", "Business Dining", "商务接待与宴请"),
        ("朋友聚会", "Friend Gathering", "朋友休闲聚餐"),
        ("独自用餐", "Solo Dining", "一人食与独食体验"),
        ("亲子用餐", "Family with Kids", "带小朋友用餐"),
        ("宴席婚庆", "Banquet & Wedding", "婚宴寿宴升学宴"),
        ("节日聚餐", "Holiday Feast", "春节中秋等节日聚餐"),
        ("独酌小聚", "Solo Drink", "一人独酌的小酌场景"),
    ])

    # 3.6 饮食特征（描述菜品本身属性，非用户偏好；用户的"我是素食者"归 Audience/用户/消费特征）
    dim("Topic/美食餐饮/饮食特征", "饮食特征", "Dietary Attribute",
        "菜品的饮食特殊属性标签",
        max_depth=2, expected_size=13)
    tags_list("Topic/美食餐饮/饮食特征", [
        ("纯素", "Vegan", "完全不含动物成分"),
        ("蛋奶素", "Lacto-ovo Vegetarian", "含蛋奶的素食"),
        ("佛家素", "Buddhist Vegetarian", "寺院斋食"),
        ("清真", "Halal", "符合伊斯兰教饮食规范"),
        ("犹太洁食", "Kosher", "符合犹太教饮食规范"),
        ("低GI", "Low GI", "低升糖指数饮食"),
        ("生酮", "Keto", "生酮高脂低碳饮食"),
        ("地中海", "Mediterranean", "地中海健康饮食模式"),
        ("孕妇餐", "Prenatal Diet", "适合孕期的特殊餐食"),
        ("儿童餐", "Kids Meal", "适合儿童的餐食"),
        ("无麸质", "Gluten-free", "不含麸质的低敏饮食"),
        ("无乳糖", "Lactose-free", "不含乳糖的低敏饮食"),
        ("无坚果", "Nut-free", "不含坚果的低敏饮食"),
    ])

    # 3.7 风味口味（味觉维度）
    dim("Topic/美食餐饮/风味口味", "风味口味", "Flavor Profile",
        "菜品的核心味觉特征",
        max_depth=2, expected_size=10)
    tags_list("Topic/美食餐饮/风味口味", [
        ("麻辣", "Numbing Spicy", "花椒辣椒麻辣风味"),
        ("酸辣", "Sour Spicy", "酸辣开胃风味"),
        ("香辣", "Aromatic Spicy", "香料型辣味"),
        ("清淡", "Light", "清淡少油少盐"),
        ("咸鲜", "Savory", "咸味鲜味为主"),
        ("酸甜", "Sweet & Sour", "酸甜口味"),
        ("甜", "Sweet", "甜味为主的风味"),
        ("原味", "Original", "保留食材本味"),
        ("烟熏", "Smoky", "烟熏风味"),
        ("果香", "Fruity", "水果风味"),
    ])

    # 3.8 认证评级（权威认证与榜单）
    dim("Topic/美食餐饮/认证评级", "认证评级", "Certification & Rating",
        "权威美食评级与认证体系",
        max_depth=3, expected_size=16)
    tag("Topic/美食餐饮/认证评级/米其林", "米其林", "Michelin Guide", "米其林餐厅指南评级体系")
    tags_list("Topic/美食餐饮/认证评级/米其林", [
        ("米其林一星", "Michelin 1 Star", "米其林一星餐厅"),
        ("米其林二星", "Michelin 2 Stars", "米其林二星餐厅"),
        ("米其林三星", "Michelin 3 Stars", "米其林三星餐厅"),
        ("必比登推介", "Bib Gourmand", "米其林必比登推介高性价比餐厅"),
        ("米其林入选", "The Plate", "米其林餐盘入选餐厅"),
    ])
    tag("Topic/美食餐饮/认证评级/黑珍珠", "黑珍珠", "Black Pearl", "黑珍珠餐厅指南评级体系")
    tags_list("Topic/美食餐饮/认证评级/黑珍珠", [
        ("黑珍珠一钻", "Black Pearl 1 Diamond", "黑珍珠一钻餐厅"),
        ("黑珍珠二钻", "Black Pearl 2 Diamonds", "黑珍珠二钻餐厅"),
        ("黑珍珠三钻", "Black Pearl 3 Diamonds", "黑珍珠三钻餐厅"),
    ])
    tags_list("Topic/美食餐饮/认证评级", [
        ("必吃榜", "Must-eat List", "大众点评必吃榜上榜餐厅"),
        ("中华老字号", "China Time-honored Brand", "商务部认定中华老字号"),
        ("省级老字号", "Provincial Heritage Brand", "省级认定老字号"),
        ("非遗美食", "Intangible Heritage Food", "国家级非物质文化遗产美食技艺"),
        ("地理标志", "GI Protected", "国家地理标志保护产品"),
    ])

    # 3.9 特色食材（食材维度）
    dim("Topic/美食餐饮/特色食材", "特色食材", "Featured Ingredient",
        "按核心食材分类的主题标签",
        max_depth=2, expected_size=11)
    tags_list("Topic/美食餐饮/特色食材", [
        ("海鲜", "Seafood", "海洋水产食材"),
        ("河鲜", "Freshwater Fish", "淡水鱼虾蟹食材"),
        ("牛肉", "Beef", "牛肉类特色食材"),
        ("羊肉", "Lamb", "羊肉类特色食材"),
        ("猪肉", "Pork", "猪肉类特色食材"),
        ("禽类", "Poultry", "鸡鸭鹅等禽类食材"),
        ("菌菇", "Mushroom", "野生菌与食用菌"),
        ("野菜", "Wild Vegetable", "山野菜与时令野菜"),
        ("川味食材", "Sichuan Ingredients", "花椒/豆瓣/泡椒等川味特色食材"),
        ("应季食材", "Seasonal Ingredients", "当季时令食材"),
        ("有机食材", "Organic Ingredients", "有机认证食材"),
    ])

    # 3b. 住宿（8 维正交：业态/价位/主题/设施/房型/区位/认证/预订特征；独立于 Topic/旅行/住宿 话题角度）
    tag("Topic/住宿", "住宿", "Accommodation",
        "住宿全维度标签体系：业态×价位×主题×设施×房型×区位×认证×预订，八维正交")

    # 3b.1 业态
    dim("Topic/住宿/业态", "业态", "Accommodation Type",
        "住宿经营业态分类",
        max_depth=3, expected_size=25)
    tag("Topic/住宿/业态/星级酒店", "星级酒店", "Star-rated Hotel", "按星级评定的标准酒店")
    tags_list("Topic/住宿/业态/星级酒店", [
        ("一星酒店", "1-Star Hotel", "一星级酒店"),
        ("二星酒店", "2-Star Hotel", "二星级酒店"),
        ("三星酒店", "3-Star Hotel", "三星级酒店"),
        ("四星酒店", "4-Star Hotel", "四星级酒店"),
        ("五星酒店", "5-Star Hotel", "五星级酒店"),
    ])
    tags_list("Topic/住宿/业态", [
        ("经济连锁", "Budget Chain", "经济型连锁酒店"),
        ("商务酒店", "Business Hotel", "面向商旅的酒店"),
        ("度假酒店", "Resort Hotel", "度假型酒店"),
        ("精品酒店", "Boutique Hotel", "设计感精品酒店"),
        ("设计酒店", "Design Hotel", "建筑师设计酒店"),
        ("酒店式公寓", "Serviced Apartment", "含酒店服务的长租型公寓"),
        ("青旅", "Hostel", "青年旅舍"),
        ("客栈", "Inn", "传统客栈"),
        ("民宿", "Homestay", "非标住宿"),
        ("农家乐", "Farmhouse", "农家住宿体验"),
        ("营地", "Campsite", "帐篷露营场地"),
        ("胶囊酒店", "Capsule Hotel", "胶囊型迷你住宿"),
    ])
    tag("Topic/住宿/业态/度假短租", "度假短租", "Vacation Rental", "按日/周整租的短租住宿（Vrbo型）")
    tags_list("Topic/住宿/业态/度假短租", [
        ("整租公寓", "Rental Apartment", "整套公寓短期出租"),
        ("整租别墅", "Rental Villa", "整栋别墅短期出租"),
        ("整租民居", "Rental House", "整套民居短期出租"),
    ])
    tag("Topic/住宿/业态/特色住宿", "特色住宿", "Unique Stay", "非传统特色住宿类型")
    tags_list("Topic/住宿/业态/特色住宿", [
        ("树屋酒店", "Treehouse Hotel", "树上住宿体验"),
        ("船屋酒店", "Houseboat Hotel", "水上船屋住宿"),
        ("集装箱酒店", "Container Hotel", "集装箱改造住宿"),
        ("帐篷酒店", "Glamping", "豪华帐篷露营"),
        ("冰屋酒店", "Ice Hotel", "冰雪建筑住宿"),
        ("洞穴酒店", "Cave Hotel", "洞穴或窑洞住宿"),
    ])

    # 3b.2 价位档次
    dim("Topic/住宿/价位档次", "价位档次", "Price Tier",
        "住宿价格区间分级",
        max_depth=2, expected_size=5)
    tags_list("Topic/住宿/价位档次", [
        ("经济型", "Budget", "经济型住宿 ¥"),
        ("中端型", "Mid-range", "中端住宿 ¥¥"),
        ("高端型", "Upscale", "高端住宿 ¥¥¥"),
        ("奢华型", "Luxury", "奢华住宿 ¥¥¥¥"),
        ("超奢华型", "Ultra Luxury", "超奢华住宿 ¥¥¥¥¥"),
    ])

    # 3b.3 主题
    dim("Topic/住宿/主题", "主题", "Stay Theme",
        "住宿的主题与特色定位",
        max_depth=2, expected_size=13)
    tags_list("Topic/住宿/主题", [
        ("亲子主题", "Family-friendly", "适合亲子家庭的住宿"),
        ("情侣浪漫", "Romantic", "适合情侣蜜月的住宿"),
        ("宠物友好", "Pet-friendly", "允许携带宠物的住宿"),
        ("温泉主题", "Hot Spring", "含温泉设施的住宿"),
        ("滑雪主题", "Ski-in/Ski-out", "靠近滑雪场的住宿"),
        ("亲水主题", "Waterfront", "临海/临湖/临江住宿"),
        ("康养主题", "Wellness", "以健康养生为主题的住宿"),
        ("商务主题", "Business", "面向商旅的住宿"),
        ("文化体验", "Cultural", "传统文化沉浸式住宿"),
        ("生态田园", "Eco & Rural", "乡村生态体验住宿"),
        ("自驾友好", "Driver-friendly", "便于自驾停车的住宿"),
        ("女性安心", "Women-safe", "女性安全友好的住宿"),
        ("单人友好", "Solo-friendly", "适合独自旅行者的住宿"),
    ])

    # 3b.4 设施服务
    dim("Topic/住宿/设施服务", "设施服务", "Amenities",
        "住宿的设施与服务配置",
        max_depth=2, expected_size=15)
    tags_list("Topic/住宿/设施服务", [
        ("泳池", "Swimming Pool", "含泳池设施"),
        ("健身房", "Gym", "含健身房设施"),
        ("SPA", "SPA", "含 SPA 水疗设施"),
        ("酒店餐厅", "Hotel Restaurant", "含餐厅设施"),
        ("酒店酒吧", "Hotel Bar", "含酒吧设施"),
        ("停车场", "Parking", "含停车设施"),
        ("洗衣服务", "Laundry", "含洗衣服务"),
        ("机场接送", "Airport Transfer", "含机场接送服务"),
        ("儿童设施", "Kids Facilities", "含儿童游乐设施"),
        ("无障碍", "Accessible", "含无障碍设施"),
        ("含早餐", "Breakfast Included", "房价含早餐"),
        ("行政酒廊", "Executive Lounge", "含行政楼层酒廊"),
        ("24h前台", "24h Front Desk", "全天候前台服务"),
        ("会议室", "Meeting Room", "含会议设施"),
        ("免费WiFi", "Free WiFi", "含免费无线网络"),
    ])

    # 3b.5 房型
    dim("Topic/住宿/房型", "房型", "Room Type",
        "客房的物理类型",
        max_depth=2, expected_size=12)
    tags_list("Topic/住宿/房型", [
        ("单人间", "Single Room", "单人入住标准间"),
        ("双床房", "Twin Room", "两张单人床客房"),
        ("大床房", "King/Queen Room", "一张大床客房"),
        ("家庭房", "Family Room", "可容纳家庭的客房"),
        ("亲子房", "Kids-themed Room", "儿童主题客房"),
        ("套房", "Suite", "客厅卧室分离套房"),
        ("复式套房", "Duplex Suite", "上下两层的复式套房"),
        ("Loft", "Loft", "挑高阁楼式客房"),
        ("海景房", "Ocean View", "可见海景的客房"),
        ("山景房", "Mountain View", "可见山景的客房"),
        ("园景房", "Garden View", "可见花园的客房"),
        ("城景房", "City View", "可见城市景观的客房"),
    ])

    # 3b.6 区位
    dim("Topic/住宿/区位", "区位", "Location Type",
        "住宿的地理区位类型",
        max_depth=2, expected_size=13)
    tags_list("Topic/住宿/区位", [
        ("市中心", "City Center", "城市中心区域"),
        ("机场近", "Near Airport", "邻近机场"),
        ("高铁近", "Near HSR Station", "邻近高铁站"),
        ("地铁旁", "Near Metro", "邻近地铁站"),
        ("景区内", "In Scenic Area", "位于景区内部"),
        ("景区附近", "Near Scenic Area", "邻近景区"),
        ("商圈", "Shopping District", "位于商业区"),
        ("CBD", "CBD", "位于中央商务区"),
        ("滨海", "Seaside", "海滨位置"),
        ("山中", "Mountain", "山区位置"),
        ("村镇", "Village & Town", "乡镇位置"),
        ("温泉度假区", "Hot Spring Resort Area", "温泉度假区域"),
        ("滑雪场", "Ski Resort Area", "滑雪场区域"),
    ])

    # 3b.7 认证评级
    dim("Topic/住宿/认证评级", "认证评级", "Stay Certification",
        "住宿权威评级与认证体系",
        max_depth=3, expected_size=12)
    tag("Topic/住宿/认证评级/米其林之钥", "米其林之钥", "MICHELIN Key", "米其林奢华酒店评级体系（2024）")
    tags_list("Topic/住宿/认证评级/米其林之钥", [
        ("一钥", "1 Key", "米其林之钥一钥酒店"),
        ("二钥", "2 Keys", "米其林之钥二钥酒店"),
        ("三钥", "3 Keys", "米其林之钥三钥酒店"),
    ])
    tags_list("Topic/住宿/认证评级", [
        ("携程必住榜", "Ctrip Must-stay List", "携程必住榜上榜酒店"),
        ("金枕头奖", "Golden Pillow Award", "去哪儿金枕头奖"),
        ("Travelers Choice", "Travelers Choice", "猫途鹰旅行者之选"),
        ("最佳新酒店", "Best New Hotel", "年度最佳新开业酒店"),
        ("金钻五星", "National 5-Star", "国家文旅部五星标准"),
        ("甲级民宿", "Grade-A Homestay", "国家甲级民宿认证"),
    ])

    # 3b.8 预订特征
    dim("Topic/住宿/预订特征", "预订特征", "Booking Feature",
        "住宿预订相关的特征标签",
        max_depth=2, expected_size=7)
    tags_list("Topic/住宿/预订特征", [
        ("即时确认", "Instant Book", "即时确认预订", ["闪订"]),
        ("免费取消", "Free Cancellation", "可免费取消的预订"),
        ("价保", "Price Match", "最低价保证"),
        ("含早", "Breakfast Included", "房价含早餐的预订"),
        ("含三餐", "All Meals", "含早中晚三餐"),
        ("限时优惠", "Flash Deal", "限时特价优惠"),
        ("会员专享", "Members Only", "会员专享价格与权益"),
    ])

    # 4. 旅行（7 子维度：旅行主题/玩法/出行方式/行程形态/旅行时长/住宿/旅行筹备）
    tag("Topic/旅行", "旅行", "Travel", "旅行出行完整体验：去哪儿/怎么去/玩什么/住哪儿/吃什么/出片，七子维度正交覆盖")

    # 4.1 旅行主题（本次旅行的整体定位/气质，宏观体验；14 项）
    dim("Topic/旅行/旅行主题", "旅行主题", "Travel Theme",
        "本次旅行的整体定位与气质，宏观体验视角；与玩法正交：主题=旅行定位（1-2个），玩法=具体子活动（可多个）",
        max_depth=2, expected_size=18)
    tags_list("Topic/旅行/旅行主题", [
        ("海岛度假", "Island Vacation", "以海岛为目的地的休闲度假旅行"),
        ("海滨度假", "Beach Vacation", "以海滨为目的地的休闲度假旅行"),
        ("雪山探险", "Snow Mountain Adventure", "以雪山冰川为目的地的探险旅行"),
        ("沙漠探险", "Desert Adventure", "以沙漠戈壁为目的地的探险旅行"),
        ("雨林秘境", "Rainforest Expedition", "热带雨林深度探索旅行"),
        ("极地探险", "Polar Expedition", "南极北极等极地区域探险旅行"),
        ("避暑游", "Summer Retreat", "以避暑纳凉为目的的旅行"),
        ("避寒游", "Winter Escape", "以避寒过冬为目的的旅行"),
        ("城市漫步", "City Walk", "以城市街区漫游为主的旅行体验"),
        ("乡村田园", "Rural Getaway", "以乡村田园风光为主的旅行体验"),
        ("文化深度游", "Cultural Deep Tour", "以历史文化体验为核心的深度旅行"),
        ("网红打卡", "Influencer Hotspot", "以社交媒体热门地点为目标的旅行"),
        ("旅居Long Stay", "Long Stay", "在目的地长期居住的深度旅行方式", ["旅居", "数字游民"]),
        ("朝圣礼佛", "Pilgrimage", "以宗教朝圣为目的的旅行"),
        ("美食之旅", "Food Tour", "以品尝当地美食与饮食文化体验为核心定位的旅行", ["美食", "美食游", "觅食"]),
        ("亲子游", "Family Travel", "以亲子家庭共同出游为核心定位的旅行", ["亲子", "亲子旅行", "遛娃"]),
        ("古镇古村", "Ancient Town & Village", "以古镇古村落人文风貌为核心定位的旅行", ["古镇", "古村", "古城"]),
        ("高原秘境", "Plateau Expedition", "以高原高海拔地区风光与人文为核心定位的旅行", ["高原", "高反", "雪域"]),
    ])

    # 4.2 玩法（在旅行中执行的具体活动，可单独消费的体验单元；25 项）
    dim("Topic/旅行/玩法", "玩法", "Activities",
        "旅行中在目的地执行的具体活动体验；与旅行主题正交：主题=旅行整体气质，玩法=具体子活动",
        max_depth=2, expected_size=25)
    tags_list("Topic/旅行/玩法", [
        ("观光游览", "Sightseeing", "景点观光与城市游览"),
        ("博物馆展览", "Museum & Exhibition", "参观博物馆与展览"),
        ("古迹寻访", "Heritage Exploration", "寻访历史古迹与文化遗产"),
        ("夜游", "Night Tour", "夜间游览与夜景体验"),
        ("市集探店", "Market & Shop", "逛市集与探访特色店铺"),
        ("文创探店", "Creative Shop", "探访文创园区与设计师店铺"),
        ("温泉泡汤", "Hot Spring", "温泉浸泡与汤池体验"),
        ("SPA美容", "SPA & Wellness", "水疗按摩与美容放松体验"),
        ("滑雪滑冰", "Skiing & Skating", "冰雪运动体验"),
        ("潜水浮潜", "Diving & Snorkeling", "水下潜水与浮潜体验"),
        ("跳伞极限", "Skydiving & Extreme", "跳伞蹦极等极限体验"),
        ("冲浪水上", "Surfing & Water Sports", "冲浪划船等水上运动体验"),
        ("热气球", "Hot Air Balloon", "热气球升空观景体验"),
        ("瑜伽冥想", "Yoga & Meditation", "旅行中的身心灵修习体验"),
        ("烹饪课", "Cooking Class", "当地美食烹饪学习体验"),
        ("手作工坊", "Workshop", "手工艺制作体验活动"),
        ("农场体验", "Farm Experience", "田园采摘与农牧体验"),
        ("研学游学", "Study Tour", "研究性学习与游学旅行"),
        ("摄影旅拍", "Travel Photography", "以摄影创作为核心的旅行体验，与 Topic/数码/影像（器材技巧）和 Format/表现手法/摄影技法（拍摄方法）正交"),
        ("观鸟观兽", "Wildlife Watching", "野生动物与鸟类观察体验"),
        ("观星", "Stargazing", "暗夜星空观测体验"),
        ("看演出", "Live Performance", "现场演出与表演观赏体验"),
        ("校园参观", "Campus Tour", "名校打卡与校园参观游览体验"),
        ("露营", "Camping", "野外露营与户外扎营过夜体验", ["营地", "野营", "扎营"]),
        ("节庆民俗", "Festival & Folklore", "参与当地节庆活动与民俗风情体验", ["节庆", "民俗", "庙会"]),
    ])

    # 4.3 出行方式（如何到达/移动，载具维度；13 项）
    dim("Topic/旅行/出行方式", "出行方式", "Transportation",
        "旅行中的交通载具与移动方式",
        max_depth=2, expected_size=13)
    tags_list("Topic/旅行/出行方式", [
        ("自驾", "Self-drive", "自驾车旅行", ["自驾游"]),
        ("租车", "Car Rental", "在目的地租车自驾"),
        ("跟团巴士", "Tour Bus", "跟团大巴出行"),
        ("高铁铁路", "High-speed Rail", "高铁与火车出行"),
        ("飞机航班", "Flight", "民航飞机出行"),
        ("邮轮", "Cruise Ship", "邮轮航线出行"),
        ("游艇", "Yacht", "私人或租赁游艇出行"),
        ("骑行", "Cycling", "自行车骑行旅行"),
        ("摩托旅行", "Motorcycle Trip", "摩托车长途旅行"),
        ("房车", "RV / Campervan", "房车自驾旅行"),
        ("包车", "Private Car", "包车含司机出行"),
        ("公共交通", "Public Transit", "地铁公交等公共交通出行"),
        ("徒步穿越", "Trekking", "长距离徒步穿越旅行"),
    ])

    # 4.4 行程形态（组织形态；6 项）
    dim("Topic/旅行/行程形态", "行程形态", "Trip Format",
        "旅行的组织与产品形态",
        max_depth=2, expected_size=6)
    tags_list("Topic/旅行/行程形态", [
        ("跟团游", "Group Tour", "旅行社组织的团队旅行"),
        ("自由行", "Independent Travel", "自主安排的自由旅行"),
        ("半自由行", "Semi-independent", "部分跟团部分自由的混合形态"),
        ("机酒套餐", "Flight+Hotel Package", "机票加酒店的打包产品"),
        ("私人定制", "Customized Tour", "量身定制的私人旅行方案"),
        ("邮轮包行", "Cruise Package", "邮轮航线全包式旅行"),
    ])

    # 4.5 旅行时长（时间跨度；6 项）
    dim("Topic/旅行/旅行时长", "旅行时长", "Trip Duration",
        "旅行的时间跨度",
        max_depth=2, expected_size=6)
    tags_list("Topic/旅行/旅行时长", [
        ("当日往返", "Day Trip", "一天内往返的短途旅行"),
        ("周末短途", "Weekend Trip", "2天1夜的周末旅行"),
        ("3-5日中线", "3-5 Day Trip", "3至5天的中等时长旅行"),
        ("6-9日长线", "6-9 Day Trip", "6至9天的长线旅行"),
        ("10日以上深度", "10+ Day Trip", "10天以上的深度旅行"),
        ("跨境多国", "Multi-country", "跨越多个国家的长途旅行"),
    ])

    # 4.6 住宿（内容讲住宿的哪个话题；15 项；与 Entity/地点/住宿 10 类扁平实体骨架正交）
    dim("Topic/旅行/住宿", "住宿", "Accommodation Topic",
        "内容围绕住宿的话题角度（讲什么）；与 Entity/地点/住宿（实体是什么）、Format/内容角度（怎么讲）正交",
        max_depth=2, expected_size=15)
    tags_list("Topic/旅行/住宿", [
        ("住宿攻略", "Accommodation Guide", "住宿选择与预订的攻略类内容"),
        ("酒店体验", "Hotel Experience", "酒店入住体验分享"),
        ("民宿体验", "Homestay Experience", "民宿入住体验分享"),
        ("商旅住宿", "Business Travel Stay", "商业差旅住宿相关内容"),
        ("出差住宿", "Business Trip Stay", "具体出差场景下的住宿内容"),
        ("川西住宿", "West Sichuan Stay", "川西地区住宿专题"),
        ("高原住宿", "Plateau Stay", "高原地区住宿注意事项与选择"),
        ("度假住宿", "Vacation Stay", "度假场景下的住宿选择"),
        ("温泉住宿", "Hot Spring Stay", "温泉住宿体验与推荐"),
        ("亲子住宿", "Family Stay", "亲子家庭住宿选择"),
        ("情侣住宿", "Couple Stay", "情侣蜜月住宿推荐"),
        ("青旅住宿", "Hostel Stay", "青年旅舍住宿体验"),
        ("特色住宿", "Unique Stay", "树屋船屋帐篷等非传统住宿体验"),
        ("住宿避雷", "Stay Pitfall", "住宿踩坑与避雷经验"),
        ("住宿比价", "Stay Price Comparison", "住宿比价与省钱技巧"),
    ])

    # 4.7 旅行筹备（行前/行中/行后准备主题；9 项；与 Format/内容角度/攻略 正交）
    dim("Topic/旅行/旅行筹备", "旅行筹备", "Trip Preparation",
        "旅行筹备相关的话题主题（内容讲什么）；与 Format/内容角度/攻略（内容呈现角度/怎么讲）正交",
        max_depth=2, expected_size=9)
    tags_list("Topic/旅行/旅行筹备", [
        ("行前规划", "Pre-trip Planning", "出发前的整体规划与准备"),
        ("签证办理", "Visa Application", "签证申请与入境手续"),
        ("机票预订", "Flight Booking", "机票搜索预订与比价"),
        ("跨境保险", "Travel Insurance", "旅行保险与境外医疗保障"),
        ("外汇兑换", "Currency Exchange", "外币兑换与支付方式"),
        ("电信漫游", "Roaming & SIM", "境外通讯与网络方案"),
        ("行李清单", "Packing List", "行李打包清单与收纳"),
        ("应急避险", "Emergency & Safety", "旅行安全与应急处理"),
        ("行后回顾", "Post-trip Review", "旅行归来的总结与回顾"),
    ])

