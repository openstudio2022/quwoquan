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


from governance.taxonomy.bootstrap_tags_topic_lodging import (
    configure_writers as _configure_topic_lodging,
    gen_topic_lodging,
)


def configure_writers(**writers):  # noqa: F811 - 覆盖上方定义，串联住宿子模块
    _WRITERS.update(writers)
    _configure_topic_lodging(**writers)


def gen_topic_food():
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
        max_depth=2, expected_size=8)
    tags_list("Topic/美食餐饮/用餐场合", [
        ("约会用餐", "Date Dining", "情侣约会用餐场景"),
        ("家庭聚餐", "Family Gathering", "家庭多人聚餐"),
        ("商务宴请", "Business Dining", "商务接待与宴请"),
        # 刻意不生成「朋友聚会」：唯一真相源是 Topic/场景/社交场景/朋友聚会；
        # 餐饮侧要表达朋友聚餐用「家庭聚餐」以外的场合标签 + 场景标签组合。
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

    # 3b. 住宿（八维正交，实现见 bootstrap_tags_topic_lodging）
    gen_topic_lodging()
