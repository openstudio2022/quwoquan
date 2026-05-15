"""生成完整标签体系到 publish/v1/tags/

四大分组：Topic / Audience / Format / Entity
- Topic: 主题垂类与场景/事件话题/时间/地理（行政区由 bootstrap_admin_regions.py 生成；垂类无 Topic/主题 中间层）
- Audience: 用户/创作者/圈子（商品画像并入 Entity/商品）
- Format: 内容载体/内容角度/表现手法/视觉风格/互动玩法/商业形式
- Entity: 9 领域类型骨架（不实例化具体对象）

原则：
- _definition.json 只含 label/labelEn/aliases/description/sourceRefs/notes/createdAt/updatedAt
- tagId 由目录路径推导，不写入文件
- 不含 appliesTo/leafConstraint/status/lifecycle/weight/deprecatedTo/startDate/endDate

用法:
  python3 bootstrap_tags.py              # 全量生成
  python3 bootstrap_tags.py --dry-run    # 仅统计不写盘
  python3 bootstrap_tags.py --group Topic  # 只生成某个分组
"""
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common.paths import PUBLISH_ROOT, NOW_ISO

TAGS_ROOT = PUBLISH_ROOT / "v1" / "tags"

DRY_RUN = False
_stats: dict[str, int] = {}


def write_json(path: Path, data: dict):
    if DRY_RUN:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _group_file(group: str) -> Path:
    return TAGS_ROOT / group / "_group.json"


def _dim_file(path: str) -> Path:
    return TAGS_ROOT / path / "_dimension.json"


def _def_file(path: str) -> Path:
    return TAGS_ROOT / path / "_definition.json"


def group(group_id: str, label: str, label_en: str, semantics: str, dimensions: list[str]):
    write_json(_group_file(group_id), {
        "id": group_id, "label": label, "labelEn": label_en,
        "semantics": semantics,
        "expectedDimensions": dimensions,
        "createdAt": NOW_ISO, "updatedAt": NOW_ISO,
    })


def dim(path: str, label: str, label_en: str, desc: str,
        max_depth: int = 3, expected_size: int = 0,
        path_policy: str = "any-depth", ref_hint: str = ""):
    data = {
        "label": label, "labelEn": label_en,
        "description": desc,
        "maxDepth": max_depth,
        "pathPolicy": path_policy,
        "createdAt": NOW_ISO, "updatedAt": NOW_ISO,
    }
    if expected_size:
        data["expectedSize"] = expected_size
    if ref_hint:
        data["refHint"] = ref_hint
    write_json(_dim_file(path), data)


def tag(path: str, label: str, label_en: str, desc: str,
        aliases: list[str] | None = None):
    group_key = path.split("/")[0]
    _stats[group_key] = _stats.get(group_key, 0) + 1
    data: dict = {
        "label": label, "labelEn": label_en,
        "description": desc,
        "createdAt": NOW_ISO, "updatedAt": NOW_ISO,
    }
    if aliases:
        data["aliases"] = aliases
    write_json(_def_file(path), data)


def tags_list(prefix: str, items: list[tuple]):
    """批量生成叶子标签。items = [(中文名, 英文名, 描述[, aliases])]"""
    for item in items:
        cn, en, desc = item[0], item[1], item[2]
        aliases = item[3] if len(item) > 3 else None
        tag(f"{prefix}/{cn}", cn, en, desc, aliases)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# T O P I C
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def gen_topic():
    group("Topic", "内容主题", "Topic",
          "描述内容所属的主题领域、地理位置、时间节点、事件话题与场景氛围",
          [
              "Topic/自然风光", "Topic/历史文化", "Topic/美食餐饮", "Topic/住宿", "Topic/旅行",
              "Topic/时尚穿搭", "Topic/美妆护肤", "Topic/健康养生", "Topic/运动",
              "Topic/数码科技", "Topic/汽车文化", "Topic/家居生活", "Topic/教育成长",
              "Topic/职场效率", "Topic/亲子育儿", "Topic/情感关系", "Topic/影视娱乐",
              "Topic/游戏电竞", "Topic/二次元", "Topic/艺术创作", "Topic/三农生活",
              "Topic/宠物动物", "Topic/金融理财", "Topic/非遗民俗", "Topic/宗教信仰",
              "Topic/命理玄学", "Topic/法律政务", "Topic/公益社会", "Topic/军事国防",
              "Topic/国际视野", "Topic/购物消费", "Topic/摄影",
              "Topic/场景", "Topic/事件话题", "Topic/时间", "Topic/地理",
          ])

    _gen_topic_verticals()
    _gen_topic_场景()
    _gen_topic_事件话题()
    _gen_topic_时间()
    # 地理/行政区 由 bootstrap_admin_regions.py 生成，此处只生成地理骨架
    _gen_topic_地理_骨架()


def _gen_topic_verticals():
    # 1. 自然风光（仅自然审美现象；具体地形实例见 Entity/地点/自然景观）
    tag("Topic/自然风光", "自然风光", "Nature & Scenery", "自然审美与天象类景观主题，侧重观感与现象而非行政区划")
    tags_list("Topic/自然风光", [
        ("彩林", "Autumn Forest", "秋季彩色林木景观"),
        ("星空", "Starry Sky", "银河星空自然夜景"),
        ("极光", "Aurora", "极光天象景观"),
        ("花海", "Flower Sea", "大面积鲜花景观"),
        ("森林", "Forest", "森林丛林林海景观"),
        ("云海", "Sea of Clouds", "云海云雾奇观"),
        ("日出日落", "Sunrise & Sunset", "日出与日落天象景观"),
        ("雾凇", "Rime Ice", "雾凇冰挂等冬季凝结景观"),
        ("雪景", "Snowscape", "降雪与雪景氛围"),
        ("候鸟迁徙", "Bird Migration", "候鸟迁飞与观鸟季"),
    ])

    # 2. 历史文化
    tag("Topic/历史文化", "历史文化", "History & Culture", "人类历史遗迹、传统文化与文明相关主题")
    tags_list("Topic/历史文化", [
        ("古镇文化", "Ancient Town Culture", "古镇老街的历史风貌"),
        ("宗教文化", "Religious Culture", "佛教道教伊斯兰基督教等宗教文化", ["佛教", "道教"]),
        ("考古遗址", "Archaeological Site", "考古发掘与历史遗址"),
        ("红色文化", "Red Culture", "革命历史与红色精神"),
        ("帝王文化", "Imperial Culture", "皇家宫廷与帝制历史"),
        ("三国文化", "Three Kingdoms Culture", "三国历史文化专题"),
        ("古蜀文明", "Ancient Shu Civilization", "古蜀国文化遗存"),
        ("丝绸之路", "Silk Road", "丝绸之路历史文化"),
        ("茶文化", "Tea Culture", "茶的历史、产地与文化", ["茶道", "茶艺"]),
        ("酒文化", "Wine & Liquor Culture", "白酒、黄酒、葡萄酒文化", ["白酒", "黄酒"]),
        ("节庆文化", "Festival Culture", "传统节日与民俗庆典"),
        ("建筑艺术", "Architectural Art", "传统与现代建筑艺术"),
        ("文物收藏", "Antique & Collection", "文物古玩与收藏鉴赏"),
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
        ("闪订", "Instant Book", "即时确认预订"),
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
        max_depth=2, expected_size=14)
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
    ])

    # 4.2 玩法（在旅行中执行的具体活动，可单独消费的体验单元；22 项）
    dim("Topic/旅行/玩法", "玩法", "Activities",
        "旅行中在目的地执行的具体活动体验；与旅行主题正交：主题=旅行整体气质，玩法=具体子活动",
        max_depth=2, expected_size=22)
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
        ("摄影旅拍", "Travel Photography", "以摄影创作为核心的旅行体验，与 Topic/数码科技/摄影摄像（器材技巧）和 Topic/艺术创作/摄影艺术（艺术属性）正交"),
        ("观鸟观兽", "Wildlife Watching", "野生动物与鸟类观察体验"),
        ("观星", "Stargazing", "暗夜星空观测体验"),
        ("看演出", "Live Performance", "现场演出与表演观赏体验"),
        ("校园参观", "Campus Tour", "名校打卡与校园参观游览体验"),
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

    # 4.6 住宿（内容讲住宿的哪个话题；15 项；与 Entity/地点/住宿 六轴实体骨架正交）
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

    # 5. 时尚穿搭
    tag("Topic/时尚穿搭", "时尚穿搭", "Fashion & Style", "服饰穿搭与时尚潮流内容")
    tags_list("Topic/时尚穿搭", [
        ("日常穿搭", "Daily Outfit", "日常生活服装搭配"),
        ("职场穿搭", "Office Outfit", "职场正式商务着装"),
        ("户外穿搭", "Outdoor Outfit", "户外运动功能性着装"),
        ("约会穿搭", "Date Outfit", "约会浪漫风格着装"),
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

    # 6. 美妆护肤
    tag("Topic/美妆护肤", "美妆护肤", "Beauty & Skincare", "美妆护肤化妆品相关内容")
    tags_list("Topic/美妆护肤", [
        ("护肤流程", "Skincare Routine", "日常护肤步骤与流程"),
        ("底妆", "Base Makeup", "粉底遮瑕等底妆技巧"),
        ("眼妆", "Eye Makeup", "眼影眼线睫毛膏等眼妆"),
        ("唇妆", "Lip Makeup", "口红唇釉唇线笔"),
        ("彩妆教程", "Makeup Tutorial", "全套彩妆教学"),
        ("仿妆", "Cosplay Makeup", "明星仿妆角色仿妆"),
        ("医美抗衰", "Medical Beauty", "医美项目与抗老护肤"),
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

    # 8. 运动（休闲健身 / 户外探险 / 竞技体育 / 极限运动 / 电竞）
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

    # 9. 数码科技
    tag("Topic/数码科技", "数码科技", "Digital & Tech", "数码产品与科学技术相关内容")
    tags_list("Topic/数码科技", [
        ("手机测评", "Smartphone Review", "手机性能测评与使用体验"),
        ("电脑测评", "Computer Review", "笔记本台式机测评"),
        ("智能家居", "Smart Home", "智能家居设备与生活"),
        ("影像", "Imaging", "相机摄像机相关内容"),
        ("无人机", "Drone", "无人机使用与航拍"),
        ("AI技术", "AI Technology", "人工智能应用与进展"),
        ("游戏硬件", "Gaming Hardware", "游戏设备外设测评"),
        ("软件应用", "Software & Apps", "手机应用与软件工具"),
        ("编程开发", "Programming", "代码开发与技术学习"),
        ("科学探索", "Science Exploration", "科学知识与前沿探索"),
        ("新能源", "New Energy", "电动车与新能源技术"),
    ])

    # 10. 汽车文化
    tag("Topic/汽车文化", "汽车文化", "Car Culture", "汽车文化与用车相关内容")
    tags_list("Topic/汽车文化", [
        ("汽车测评", "Car Review", "整车全面测评"),
        ("新能源汽车", "NEV Review", "电动车混动车测评"),
        ("改装升级", "Car Modification", "汽车改装与升级"),
        ("养车保养", "Car Maintenance", "汽车保养与维修"),
        ("驾驶技巧", "Driving Skills", "驾驶技巧与安全"),
        ("摩托车", "Motorcycle", "摩托车文化与测评"),
    ])

    # 11. 家居生活
    tag("Topic/家居生活", "家居生活", "Home & Living", "家居装修与生活方式内容")
    tags_list("Topic/家居生活", [
        ("装修设计", "Interior Design", "室内设计与装修风格"),
        ("家具软装", "Furniture & Decor", "家具选购与软装搭配"),
        ("厨房烹饪", "Kitchen & Cooking", "厨房烹饪技巧与家电"),
        ("家电测评", "Home Appliance Review", "家用电器测评"),
        ("园艺植物", "Gardening & Plants", "庭院园艺与室内植物"),
        ("整理收纳", "Organization & Storage", "家居整理收纳技巧"),
        ("清洁卫生", "Cleaning", "家居清洁与卫生"),
        ("租房布置", "Rental Decoration", "出租屋改造与布置"),
        ("极简生活", "Minimalist Living", "极简主义生活方式"),
        ("DIY手工", "DIY & Crafts", "手工制作与DIY改造"),
    ])

    # 12. 教育成长（12 子域 + 叶子）
    tag("Topic/教育成长", "教育成长", "Education & Growth",
        "教育学习与个人成长内容，覆盖基础教育到终身学习全链路")

    # 12.1 基础教育
    tag("Topic/教育成长/基础教育", "基础教育", "Basic Education", "学前到高中阶段的教育内容")
    tags_list("Topic/教育成长/基础教育", [
        ("学前教育", "Preschool Education", "幼儿园及学前阶段教育"),
        ("小学教育", "Primary Education", "小学阶段课程与学习"),
        ("初中教育", "Junior High Education", "初中阶段课程与学习"),
        ("高中教育", "Senior High Education", "高中阶段课程与学习"),
        ("幼小衔接", "Preschool-Primary Transition", "从幼儿园到小学的过渡准备"),
    ])

    # 12.2 校园生活
    tag("Topic/教育成长/校园生活", "校园生活", "Campus Life", "在校期间的日常生活与社交体验")
    tags_list("Topic/教育成长/校园生活", [
        ("宿舍生活", "Dorm Life", "宿舍日常与室友相处"),
        ("食堂生活", "Cafeteria Life", "校园食堂与美食"),
        ("社团活动", "Club Activities", "学生社团与课外活动"),
        ("军训", "Military Training", "新生军训体验"),
        ("开学季", "Back to School", "开学季的准备与氛围"),
        ("毕业季", "Graduation Season", "毕业典礼与离校"),
        ("校园兼职", "Campus Part-time Job", "在校期间的兼职经历"),
        ("校园恋爱", "Campus Romance", "校园恋爱与情感"),
        ("校园穿搭", "Campus Fashion", "校园日常穿搭与造型"),
    ])

    # 12.3 学业学术
    tag("Topic/教育成长/学业学术", "学业学术", "Academic", "课程学习、科研与学术活动")
    tags_list("Topic/教育成长/学业学术", [
        ("选课指南", "Course Selection Guide", "大学选课策略与推荐"),
        ("考试备考", "Exam Preparation", "期中期末与各类考试备考"),
        ("毕业论文", "Thesis", "毕业论文选题与写作"),
        ("毕业设计", "Graduation Project", "毕业设计与答辩"),
        ("学术科研", "Academic Research", "学术研究与论文发表"),
        ("学术竞赛", "Academic Competition", "学科竞赛与创新大赛"),
        ("GPA管理", "GPA Management", "绩点管理与成绩优化"),
    ])

    # 12.4 升学深造
    tag("Topic/教育成长/升学深造", "升学深造", "Further Education", "考研保研考博等升学相关内容")
    tags_list("Topic/教育成长/升学深造", [
        ("考研", "Postgraduate Entrance Exam", "硕士研究生考试备考"),
        ("保研推免", "Graduate Recommendation", "保研推免申请与准备"),
        ("考博", "Doctoral Entrance Exam", "博士研究生考试备考"),
        ("MBA与EMBA", "MBA & EMBA", "工商管理硕士申请与备考"),
        ("申请策略", "Application Strategy", "升学申请的整体策略与规划"),
    ])

    # 12.5 考试认证
    tag("Topic/教育成长/考试认证", "考试认证", "Certification Exams",
        "各类职业资格与等级考试的应试策略、报名流程与考场经验")
    tags_list("Topic/教育成长/考试认证", [
        ("四六级", "CET-4/6", "大学英语四六级考试"),
        ("考公务员", "Civil Service Exam", "国家公务员考试备考"),
        ("考编制", "Public Institution Exam", "事业单位编制考试"),
        ("司法考试", "Bar Exam", "国家法律职业资格考试"),
        ("注册会计师", "CPA Exam", "注册会计师资格考试"),
        ("教师资格证", "Teaching Certificate", "教师资格考试"),
        ("计算机等级考试", "Computer Grade Exam", "全国计算机等级考试"),
        ("医师资格证", "Medical License", "执业医师资格考试"),
    ])

    # 12.6 实习求职（校园身份视角：在校生或应届生的实习与校招）
    tag("Topic/教育成长/实习求职", "实习求职", "Campus Internship & Job",
        "在校生或应届生视角的实习与校招，与 Topic/职场效率/求职招聘（社会人视角）正交")
    tags_list("Topic/教育成长/实习求职", [
        ("校园实习", "Campus Internship", "在校期间的实习经历与技巧"),
        ("校园招聘", "Campus Recruitment", "校园招聘会与宣讲会"),
        ("秋招春招", "Fall/Spring Recruitment", "秋招春招的时间线与策略"),
        ("简历优化", "Resume Optimization", "针对应届生的简历优化技巧"),
    ])

    # 12.7 留学海外
    tag("Topic/教育成长/留学海外", "留学海外", "Study Abroad", "海外留学申请、生活与归国经历")
    tags_list("Topic/教育成长/留学海外", [
        ("留学申请", "Study Abroad Application", "海外院校申请与文书"),
        ("海外生活", "Life Abroad", "留学期间的日常生活"),
        ("海归经历", "Returnee Experience", "海归回国后的经历与适应"),
        ("文化适应", "Cultural Adaptation", "跨文化适应与冲击"),
        ("奖学金申请", "Scholarship Application", "各类奖学金申请攻略"),
    ])

    # 12.8 语言学习
    tag("Topic/教育成长/语言学习", "语言学习", "Language Learning",
        "外语能力培养方法与技巧，聚焦语言能力本身而非应试")
    tags_list("Topic/教育成长/语言学习", [
        ("口语练习", "Speaking Practice", "外语口语练习方法"),
        ("阅读技巧", "Reading Skills", "外语阅读理解技巧"),
        ("听力训练", "Listening Training", "外语听力提升方法"),
        ("写作方法", "Writing Methods", "外语写作技巧与模板"),
        ("语言考试", "Language Exams", "雅思托福GRE等语言能力评估考试"),
    ])

    # 12.9 学习方法
    tag("Topic/教育成长/学习方法", "学习方法", "Study Methods", "高效学习方法与技巧分享")
    tags_list("Topic/教育成长/学习方法", [
        ("高效笔记", "Effective Note-taking", "笔记方法与工具"),
        ("复习策略", "Review Strategy", "科学复习与记忆巩固"),
        ("时间管理", "Time Management", "学习时间规划与管理"),
        ("记忆技巧", "Memory Techniques", "记忆方法与脑科学"),
    ])

    # 12.10 成人教育
    tag("Topic/教育成长/成人教育", "成人教育", "Adult Education", "面向成人的继续教育与学历提升")
    tags_list("Topic/教育成长/成人教育", [
        ("自考", "Self-study Exam", "高等教育自学考试"),
        ("成人高考", "Adult College Entrance Exam", "成人高等学校招生考试"),
        ("在职研究生", "Part-time Graduate", "在职攻读硕士学位"),
        ("继续教育", "Continuing Education", "各类继续教育与进修"),
    ])

    # 12.11 职业技能
    tag("Topic/教育成长/职业技能", "职业技能", "Professional Skills", "职场技能与资格证书")
    tags_list("Topic/教育成长/职业技能", [
        ("职场技能", "Workplace Skills", "职场通用技能提升"),
        ("资格证书", "Professional Certificate", "行业资格证书备考"),
    ])

    # 12.12 阅读写作
    tag("Topic/教育成长/阅读写作", "阅读写作", "Reading & Writing", "书籍推荐与写作技巧")
    tags_list("Topic/教育成长/阅读写作", [
        ("书籍推荐", "Book Recommendations", "各类书籍推荐与书单"),
        ("写作技巧", "Writing Skills", "写作方法与技巧分享"),
        ("读书笔记", "Reading Notes", "读书笔记与摘要"),
    ])

    # 13. 职场效率
    tag("Topic/职场效率", "职场效率", "Workplace & Productivity", "职场发展与效率提升内容")
    tags_list("Topic/职场效率", [
        ("求职招聘", "Job Hunting", "简历求职与面试技巧"),
        ("职业规划", "Career Planning", "职业发展路径规划"),
        ("创业经验", "Entrepreneurship", "创业故事与经验分享"),
        ("效率工具", "Productivity Tools", "效率软件与工具使用"),
        ("副业收入", "Side Income", "兼职副业与第二收入"),
        ("远程办公", "Remote Work", "在家远程工作的经验"),
        ("自媒体运营", "Self-Media Operation", "内容创作与自媒体运营"),
        ("领导力", "Leadership", "管理与领导力发展"),
        ("沟通技巧", "Communication Skills", "职场沟通与表达"),
    ])

    # 14. 亲子育儿
    tag("Topic/亲子育儿", "亲子育儿", "Parenting & Kids", "育儿经验与亲子互动内容")
    tags_list("Topic/亲子育儿", [
        ("孕期分享", "Pregnancy", "孕期生活与经验"),
        ("新生儿护理", "Newborn Care", "新生儿喂养与护理"),
        ("幼儿成长", "Toddler Growth", "1-3岁幼儿发展"),
        ("儿童教育", "Child Education", "学龄前后儿童教育"),
        ("亲子活动", "Parent-Child Activities", "亲子互动游戏与活动"),
        ("儿童安全", "Child Safety", "儿童安全防护知识"),
        ("辅食营养", "Baby Food", "婴幼儿辅食与营养"),
        ("母婴用品", "Baby Products", "母婴产品评测与推荐"),
        ("幼儿园选择", "Kindergarten Selection", "幼儿园择园攻略与评价"),
        ("幼小衔接", "Preschool-Primary Transition", "学前到小学的过渡准备与衔接"),
        ("学前启蒙", "Early Education", "幼儿早期教育与能力启蒙"),
    ])

    # 15. 情感关系
    tag("Topic/情感关系", "情感关系", "Relationship & Emotions", "爱情婚姻家庭人际关系内容")
    tags_list("Topic/情感关系", [
        ("恋爱约会", "Dating & Romance", "恋爱相处与约会技巧"),
        ("婚姻家庭", "Marriage & Family", "婚姻生活与家庭关系"),
        ("亲子关系", "Parent-Child Bond", "父母子女的情感连接"),
        ("友情社交", "Friendship & Social", "友谊维系与社交技巧"),
        ("情感疗愈", "Emotional Healing", "失恋分手与情感修复"),
        ("两性话题", "Gender & Sexuality", "两性关系与性别话题"),
        ("个人成长", "Personal Growth", "自我提升与内心成长"),
        ("心理疗愈", "Mental Healing", "焦虑抑郁等心理疗愈"),
    ])

    # 16. 影视娱乐
    tag("Topic/影视娱乐", "影视娱乐", "Entertainment & Media", "影视综艺音乐娱乐内容")
    tags_list("Topic/影视娱乐", [
        ("电影", "Movies", "电影评论与推荐"),
        ("电视剧", "TV Drama", "国产剧海外剧追剧"),
        ("综艺节目", "Variety Show", "综艺娱乐节目"),
        ("音乐", "Music", "音乐分享与推荐"),
        ("明星八卦", "Celebrity News", "娱乐明星动态"),
        ("直播生态", "Livestream Ecosystem", "直播生态、互动与商业化形态"),
        ("短视频文化", "Short Video Culture", "短视频创作与文化"),
        ("影视解说", "Movie Commentary", "电影电视剧解说与分析"),
    ])

    # 17. 游戏电竞
    tag("Topic/游戏电竞", "游戏电竞", "Gaming & Esports", "电子游戏与电竞相关内容")
    tags_list("Topic/游戏电竞", [
        ("手机游戏", "Mobile Gaming", "手游攻略与推荐"),
        ("PC游戏", "PC Gaming", "电脑端游戏"),
        ("主机游戏", "Console Gaming", "PS/Xbox/Switch游戏"),
        ("游戏攻略", "Game Guide", "游戏技巧与通关攻略"),
        ("独立游戏", "Indie Games", "独立小型游戏推荐"),
        ("桌游卡牌", "Board Games", "桌游卡牌游戏"),
        ("VR游戏", "VR Gaming", "虚拟现实游戏体验"),
    ])

    # 18. 二次元
    tag("Topic/二次元", "二次元", "ACG Culture", "动画漫画游戏次文化内容")
    tags_list("Topic/二次元", [
        ("动画", "Anime", "日本动画作品"),
        ("漫画", "Manga & Comics", "漫画作品与推荐"),
        ("cosplay", "Cosplay", "角色扮演与服装制作"),
        ("虚拟偶像", "Virtual Idol", "Vtuber等虚拟主播"),
        ("轻小说", "Light Novel", "日式轻小说"),
        ("国产动漫", "Chinese Anime", "国产动画与漫画"),
        ("同人创作", "Fan Creation", "同人文同人画二创"),
    ])

    # 19. 艺术创作
    tag("Topic/艺术创作", "艺术创作", "Art & Creativity", "艺术创作与设计内容")
    tags_list("Topic/艺术创作", [
        ("绘画插画", "Painting & Illustration", "绘画艺术与数字插画"),
        ("雕塑装置", "Sculpture & Installation", "雕塑与装置艺术"),
        ("音乐创作", "Music Creation", "原创音乐制作"),
        ("书法篆刻", "Calligraphy", "中国书法与篆刻"),
        ("设计创意", "Design & Creative", "平面产品UI设计"),
        ("手工制作", "Handcraft", "手工艺品与DIY创作"),
        ("街头艺术", "Street Art", "涂鸦与街头艺术"),
        ("传统工艺", "Traditional Crafts", "刺绣陶瓷漆器等传统工艺"),
    ])

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

    # 31. 摄影（独立垂类，含题材社区 + 知识类；对标 500px/图虫/Flickr 等平台频道）
    tag("Topic/摄影", "摄影", "Photography",
        "摄影创作与摄影文化内容：按题材流派形成的社区频道 + 摄影知识与器材内容")
    tags_list("Topic/摄影", [
        ("风光摄影", "Landscape Photography", "以自然风景为主题的摄影创作"),
        ("人像摄影", "Portrait Photography", "以人物肖像为主题的摄影创作"),
        ("街头摄影", "Street Photography", "城市街头抓拍与日常记录"),
        ("纪实摄影", "Documentary Photography", "纪实报道与社会记录摄影"),
        ("建筑摄影", "Architecture Photography", "建筑与城市景观摄影"),
        ("野生动物摄影", "Wildlife Photography", "野生动物生态摄影"),
        ("微距摄影", "Macro Photography", "微观世界的近距离摄影"),
        ("美食摄影", "Food Photography", "美食与饮品的摄影创作"),
        ("静物摄影", "Still Life Photography", "静物构成与产品摄影"),
        ("人文摄影", "Cultural Photography", "民族民俗与人文题材摄影"),
        ("时尚摄影", "Fashion Photography", "时尚造型与服饰摄影"),
        ("运动摄影", "Sports Photography", "体育运动与动作抓拍摄影"),
        ("婚礼摄影", "Wedding Photography", "婚纱婚礼纪实摄影"),
        ("商业摄影", "Commercial Photography", "商业广告与产品摄影"),
        ("旅行摄影", "Travel Photography", "旅途见闻与异域风情摄影"),
        ("水下摄影", "Underwater Photography", "水下世界探索摄影"),
        ("航拍摄影", "Aerial Photography", "无人机与航空俯瞰摄影"),
        ("夜景星空", "Night & Astro Photography", "夜景城市与星空银河摄影"),
        ("抽象摄影", "Abstract Photography", "抽象形式与实验性摄影"),
        ("艺术摄影", "Fine Art Photography", "观念艺术与纯艺术摄影"),
        ("新闻摄影", "Photojournalism", "新闻事件与现场报道摄影"),
        ("花卉摄影", "Botanical Photography", "花卉植物专项摄影"),
        ("摄影教程", "Photography Tutorial", "拍摄技巧与方法教学"),
        ("器材评测", "Gear Review", "相机镜头附件评测对比"),
        ("后期技巧", "Post-processing Tips", "Lightroom/PS/手机修图技巧"),
        ("摄影赛事", "Photo Contest", "国内外摄影比赛资讯"),
        ("摄影史", "History of Photography", "摄影历史与经典大师作品"),
        ("手机摄影", "Mobile Photography", "手机拍摄技巧与后期"),
    ])


def _gen_topic_场景():
    dim("Topic/场景", "场景", "Scene",
        "内容所适配的使用场景与氛围，与主题垂类正交", max_depth=3, expected_size=50)

    tag("Topic/场景/生活场景", "生活场景", "Daily Life Scene", "日常生活相关使用场景")
    tags_list("Topic/场景/生活场景", [
        ("早餐场景", "Breakfast Scene", "早餐饮食内容场景"),
        ("午休场景", "Lunch Break Scene", "午休时间使用场景"),
        ("深夜场景", "Late Night Scene", "深夜浏览与夜间活动"),
        ("通勤场景", "Commute Scene", "上下班通勤碎片时间"),
        ("居家场景", "Home Scene", "居家休息与放松"),
        ("健身前后", "Pre-Post Workout Scene", "运动健身前后场景"),
        ("约会场景", "Date Scene", "情侣约会出行场景"),
        ("校园场景", "Campus Daily Scene", "图书馆、教室、宿舍、食堂、操场等校园空间场景"),
    ])

    tag("Topic/场景/情绪场景", "情绪场景", "Emotional Scene", "特定情绪与心境场景")
    tags_list("Topic/场景/情绪场景", [
        ("治愈系", "Healing", "疗愈放松的内容场景", ["治愈"]),
        ("解压场景", "Stress Relief", "舒缓压力的内容"),
        ("励志正能量", "Inspirational", "激励向上的内容场景"),
        ("搞笑娱乐", "Comedy", "轻松搞笑的娱乐内容"),
        ("感人催泪", "Emotional", "感人泪点的内容"),
    ])

    tag("Topic/场景/社交场景", "社交场景", "Social Scene", "社交互动相关场景")
    tags_list("Topic/场景/社交场景", [
        ("朋友聚会", "Friend Gathering", "朋友聚餐聚会场景"),
        ("同事聚餐", "Colleague Dinner", "职场同事聚餐场景"),
        ("家庭聚会", "Family Gathering", "家庭聚会活动场景"),
        ("网友见面", "Online Friend Meetup", "网络认识后线下见面"),
    ])


def _gen_topic_事件话题():
    """事件话题骨架：只建立一级分类节点。
    所有叶子节点由 bootstrap_event_topics.py 统一管理，避免重复定义。
    """
    dim("Topic/事件话题", "事件话题", "Trending Topics",
        "时效性话题与热点事件分类，不写生命周期字段，热度由 tag_runtime/topic_hotness.ndjson 管理",
        max_depth=3, expected_size=100)

    tag("Topic/事件话题/社会热点", "社会热点", "Social Trending", "社会民生热点话题")
    tag("Topic/事件话题/赛事活动", "赛事活动", "Sports & Event Topics", "体育赛事与大型活动话题")
    tag("Topic/事件话题/文娱话题", "文娱话题", "Entertainment Topics", "影视娱乐热点话题")
    tag("Topic/事件话题/地区话题", "地区话题", "Regional Topics", "特定地区热点话题")


def _gen_topic_时间():
    dim("Topic/时间", "时间", "Time Dimension",
        "内容与时间节点的关联，包括节气、节假日、季节与时代标签",
        max_depth=3, expected_size=100, path_policy="prefer-leaf")

    tag("Topic/时间/四季", "四季", "Four Seasons", "四季时令内容分类")
    tags_list("Topic/时间/四季", [
        ("春季", "Spring", "春季内容"),
        ("夏季", "Summer", "夏季内容"),
        ("秋季", "Autumn", "秋季内容", ["秋天"]),
        ("冬季", "Winter", "冬季内容", ["冬天"]),
    ])

    tag("Topic/时间/节气", "节气", "Solar Terms", "中国二十四节气")
    for solarterm, en, desc in [
        ("立春", "Start of Spring", "二十四节气之立春"),
        ("雨水", "Rain Water", "二十四节气之雨水"),
        ("惊蛰", "Awakening of Insects", "二十四节气之惊蛰"),
        ("春分", "Spring Equinox", "二十四节气之春分"),
        ("清明", "Clear and Bright", "二十四节气之清明"),
        ("谷雨", "Grain Rain", "二十四节气之谷雨"),
        ("立夏", "Start of Summer", "二十四节气之立夏"),
        ("小满", "Grain Buds", "二十四节气之小满"),
        ("芒种", "Grain in Ear", "二十四节气之芒种"),
        ("夏至", "Summer Solstice", "二十四节气之夏至"),
        ("小暑", "Minor Heat", "二十四节气之小暑"),
        ("大暑", "Major Heat", "二十四节气之大暑"),
        ("立秋", "Start of Autumn", "二十四节气之立秋"),
        ("处暑", "End of Heat", "二十四节气之处暑"),
        ("白露", "White Dew", "二十四节气之白露"),
        ("秋分", "Autumn Equinox", "二十四节气之秋分"),
        ("寒露", "Cold Dew", "二十四节气之寒露"),
        ("霜降", "Frost's Descent", "二十四节气之霜降"),
        ("立冬", "Start of Winter", "二十四节气之立冬"),
        ("小雪", "Minor Snow", "二十四节气之小雪"),
        ("大雪", "Major Snow", "二十四节气之大雪"),
        ("冬至", "Winter Solstice", "二十四节气之冬至"),
        ("小寒", "Minor Cold", "二十四节气之小寒"),
        ("大寒", "Major Cold", "二十四节气之大寒"),
    ]:
        tag(f"Topic/时间/节气/{solarterm}", solarterm, en, desc)

    tag("Topic/时间/法定节假日", "法定节假日", "National Holidays", "中国法定节假日")
    tags_list("Topic/时间/法定节假日", [
        ("元旦", "New Year's Day", "1月1日元旦假日"),
        ("春节", "Chinese New Year", "农历正月初一春节", ["过年"]),
        ("清明节", "Qingming Festival", "清明扫墓祭祖节日"),
        ("劳动节", "Labour Day", "5月1日劳动节假日"),
        ("端午节", "Dragon Boat Festival", "农历五月初五端午"),
        ("中秋节", "Mid-Autumn Festival", "农历八月十五中秋"),
        ("国庆节", "National Day", "10月1日国庆节"),
    ])

    tag("Topic/时间/传统节日", "传统节日", "Traditional Festivals", "中国传统节日与民俗纪念日")
    tags_list("Topic/时间/传统节日", [
        ("元宵节", "Lantern Festival", "正月十五元宵节"),
        ("七夕节", "Qixi Festival", "农历七月初七七夕", ["情人节"]),
        ("重阳节", "Double Ninth Festival", "农历九月初九重阳"),
        ("腊八节", "Laba Festival", "农历腊月初八腊八节"),
        ("冬至节", "Winter Solstice Day", "冬至习俗活动"),
    ])

    tag("Topic/时间/纪念日", "纪念日", "Memorial Days", "国家及社会纪念日")
    tags_list("Topic/时间/纪念日", [
        ("南京大屠杀纪念日", "Nanjing Massacre Memorial", "12月13日国家公祭日"),
        ("抗日战争胜利纪念日", "Anti-Japanese War Victory Day", "9月3日纪念日"),
        ("建军节", "Army Day", "8月1日建军节"),
        ("建党节", "CPC Founding Day", "7月1日建党节"),
    ])

    tag("Topic/时间/商业节日", "商业节日", "Commercial Holidays", "商家推出的节日与促销节点")
    tags_list("Topic/时间/商业节日", [
        ("双十一", "Double 11", "11月11日购物节", ["双11"]),
        ("618", "618 Festival", "6月18日年中购物节"),
        ("黑色星期五", "Black Friday", "年末打折促销"),
        ("女神节", "Women's Day Shopping", "3月8日女神节促销"),
        ("儿童节购物", "Children's Day Shopping", "6月1日儿童节"),
        ("情人节促销", "Valentine's Shopping", "2月14日情人节"),
        ("母亲节促销", "Mother's Day Shopping", "5月母亲节"),
    ])

    tag("Topic/时间/生肖年", "生肖年", "Chinese Zodiac Year", "农历生肖年份")
    tags_list("Topic/时间/生肖年", [
        ("鼠年", "Year of Rat", "农历鼠年"),
        ("牛年", "Year of Ox", "农历牛年"),
        ("虎年", "Year of Tiger", "农历虎年"),
        ("兔年", "Year of Rabbit", "农历兔年"),
        ("龙年", "Year of Dragon", "农历龙年"),
        ("蛇年", "Year of Snake", "农历蛇年"),
        ("马年", "Year of Horse", "农历马年"),
        ("羊年", "Year of Goat", "农历羊年"),
        ("猴年", "Year of Monkey", "农历猴年"),
        ("鸡年", "Year of Rooster", "农历鸡年"),
        ("狗年", "Year of Dog", "农历狗年"),
        ("猪年", "Year of Pig", "农历猪年"),
    ])


def _gen_topic_地理_骨架():
    dim("Topic/地理", "地理", "Geography",
        "地理维度：行政区（5层）由 bootstrap_admin_regions.py 生成；自然地标实例由 bootstrap_geo_landmarks.py 生成；本脚本生成骨架",
        max_depth=5, expected_size=600)
    # 骨架节点只创建维度说明，实际节点由 helper 脚本生成
    tag("Topic/地理/行政区", "行政区", "Administrative Region",
        "行政区划：国家/省/市/区县/街道，完整内容由 bootstrap_admin_regions.py 生成")
    tag("Topic/地理/地形地貌", "地形地貌", "Landform",
        "地理科学中的地表形态分类；具体自然地物实例可落入 Entity/地点/自然景观，亦可由 bootstrap_geo_landmarks.py 生成")

    # 区域（跨国地理/文化聚合，叶子级不挂国家）
    dim("Topic/地理/区域", "区域", "Region",
        "跨国地理与文化聚合区域分类；子项为叶子级聚合标签，国家由 Topic/地理/行政区/ 表达",
        max_depth=3, expected_size=30, ref_hint="Topic/地理/行政区")

    tag("Topic/地理/区域/亚洲", "亚洲", "Asia", "亚洲大洲区域聚合")
    tags_list("Topic/地理/区域/亚洲", [
        ("东亚", "East Asia", "中日韩蒙等东亚地区"),
        ("东南亚", "Southeast Asia", "泰越柬缅马印尼菲等东南亚地区"),
        ("南亚", "South Asia", "印巴孟斯等南亚次大陆"),
        ("中亚", "Central Asia", "哈乌土吉塔等中亚地区"),
        ("西亚", "West Asia", "伊朗土耳其阿联酋等西亚中东地区"),
    ])

    tag("Topic/地理/区域/欧洲", "欧洲", "Europe", "欧洲大洲区域聚合")
    tags_list("Topic/地理/区域/欧洲", [
        ("西欧", "Western Europe", "英法荷比卢等西欧地区"),
        ("北欧", "Northern Europe", "挪瑞芬丹冰等北欧地区"),
        ("南欧", "Southern Europe", "意西葡希等地中海南欧地区"),
        ("中欧", "Central Europe", "德奥瑞捷波匈等中欧地区"),
        ("东欧", "Eastern Europe", "俄乌白波罗的海等东欧地区"),
    ])

    tag("Topic/地理/区域/美洲", "美洲", "Americas", "美洲大洲区域聚合")
    tags_list("Topic/地理/区域/美洲", [
        ("北美", "North America", "美加墨北美地区"),
        ("中美", "Central America", "危地马拉哥斯达黎加等中美洲"),
        ("南美", "South America", "巴西阿根廷秘鲁等南美地区"),
    ])

    tag("Topic/地理/区域/非洲", "非洲", "Africa", "非洲大洲区域聚合")
    tags_list("Topic/地理/区域/非洲", [
        ("北非", "North Africa", "埃及摩洛哥突尼斯等北非地区"),
        ("东非", "East Africa", "肯尼亚坦桑尼亚埃塞等东非地区"),
        ("南部非洲", "Southern Africa", "南非纳米比亚博茨瓦纳等南部非洲"),
        ("西非", "West Africa", "尼日利亚加纳塞内加尔等西非地区"),
        ("中非", "Central Africa", "刚果喀麦隆等中非地区"),
    ])

    tag("Topic/地理/区域/大洋洲", "大洋洲", "Oceania", "大洋洲区域聚合")
    tags_list("Topic/地理/区域/大洋洲", [
        ("澳新", "Australia & New Zealand", "澳大利亚与新西兰"),
        ("太平洋岛国", "Pacific Islands", "斐济帕劳汤加等太平洋岛国"),
    ])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# A U D I E N C E
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def gen_audience():
    group("Audience", "受众画像", "Audience",
          "描述内容受众特征（用户/创作者/圈子）的多维度标签体系，用于内容匹配与推荐",
          ["Audience/用户", "Audience/创作者", "Audience/圈子"])

    _gen_audience_用户()
    _gen_audience_创作者()
    _gen_audience_圈子()


def _gen_audience_用户():
    dim("Audience/用户", "用户画像", "User Profile",
        "用户的人口统计、生活方式与行为特征，16个子维度",
        max_depth=3, expected_size=300)

    # 1. 性别
    dim("Audience/用户/性别", "性别", "Gender", "用户性别维度",
        max_depth=2, path_policy="leaf-only")
    tags_list("Audience/用户/性别", [
        ("男", "Male", "男性用户"),
        ("女", "Female", "女性用户"),
        ("其他", "Non-binary", "非二元性别用户"),
    ])

    # 2. 代际
    dim("Audience/用户/代际", "代际", "Generation", "用户出生年代标签",
        max_depth=2, path_policy="leaf-only")
    tags_list("Audience/用户/代际", [
        ("10后", "Gen Alpha", "2010年后出生"),
        ("00后", "Gen Z late", "2000-2009年出生"),
        ("95后", "Gen Z early", "1995-1999年出生"),
        ("90后", "Millennials late", "1990-1994年出生"),
        ("85后", "Millennials", "1985-1989年出生"),
        ("80后", "Gen X late", "1980-1984年出生"),
        ("70后", "Gen X", "1970-1979年出生"),
        ("60后", "Baby Boomer", "1960-1969年出生"),
        ("50后", "Silent Generation", "1950-1959年出生"),
    ])

    # 3. 国籍
    dim("Audience/用户/国籍", "国籍", "Nationality",
        "用户国籍；国家/地区节点与 Topic/地理/行政区 对齐，避免重复维护国家列表",
        max_depth=2, path_policy="leaf-only", ref_hint="Topic/地理/行政区")
    for country, en in [
        ("中国", "Chinese"), ("美国", "American"), ("日本", "Japanese"),
        ("韩国", "Korean"), ("英国", "British"), ("法国", "French"),
        ("德国", "German"), ("加拿大", "Canadian"), ("澳大利亚", "Australian"),
        ("新西兰", "New Zealander"), ("新加坡", "Singaporean"), ("马来西亚", "Malaysian"),
        ("泰国", "Thai"), ("越南", "Vietnamese"), ("印度", "Indian"),
        ("俄罗斯", "Russian"), ("意大利", "Italian"), ("西班牙", "Spanish"),
        ("巴西", "Brazilian"), ("其他", "Other Nationality"),
    ]:
        tag(f"Audience/用户/国籍/{country}", country, en, f"{country}籍用户")

    # 4. 族群
    dim("Audience/用户/族群", "族群", "Ethnicity",
        "用户族裔背景，纯客观分类，不做价值判断",
        max_depth=3, path_policy="leaf-only")
    tag("Audience/用户/族群/中国民族", "中国民族", "Chinese Ethnic Groups", "中国56个民族分类")
    for ethnic in ["汉族", "藏族", "羌族", "彝族", "苗族", "壮族",
                   "满族", "蒙古族", "维吾尔族", "回族", "朝鲜族",
                   "土家族", "侗族", "瑶族", "白族", "哈尼族",
                   "黎族", "傣族", "布依族", "其他少数民族"]:
        tag(f"Audience/用户/族群/中国民族/{ethnic}", ethnic, ethnic, f"中国{ethnic}")
    tag("Audience/用户/族群/海外族裔", "海外族裔", "Overseas Ethnicities", "海外族裔背景")
    for ethnic, en in [("华裔", "Chinese Diaspora"), ("亚裔", "Asian"),
                       ("欧裔", "European"), ("非裔", "African"),
                       ("拉丁裔", "Latino"), ("混血", "Mixed Heritage")]:
        tag(f"Audience/用户/族群/海外族裔/{ethnic}", ethnic, en, f"{ethnic}用户群体")

    # 5. 语言
    dim("Audience/用户/语言", "语言", "Language",
        "用户使用的主要语言", max_depth=2, path_policy="leaf-only")
    for lang, en in [
        ("普通话", "Mandarin"), ("粤语", "Cantonese"), ("闽南语", "Hokkien"),
        ("上海话", "Shanghainese"), ("四川话", "Sichuanese"), ("藏语", "Tibetan"),
        ("英语", "English"), ("日语", "Japanese"), ("韩语", "Korean"),
        ("法语", "French"), ("德语", "German"), ("西班牙语", "Spanish"),
        ("阿拉伯语", "Arabic"), ("俄语", "Russian"), ("葡萄牙语", "Portuguese"),
    ]:
        tag(f"Audience/用户/语言/{lang}", lang, en, f"使用{lang}的用户群体")

    # 6. 教育
    dim("Audience/用户/教育", "教育", "Education", "用户教育背景",
        max_depth=3, path_policy="prefer-leaf")
    tag("Audience/用户/教育/学历", "学历", "Education Level",
        "用户最终学历")
    tags_list("Audience/用户/教育/学历", [
        ("初中及以下", "Junior High or Below", "初中及以下学历"),
        ("高中或中专", "Senior High", "高中中专学历"),
        ("大专", "Associate Degree", "大专学历"),
        ("本科", "Bachelor's Degree", "本科学历"),
        ("硕士", "Master's Degree", "硕士研究生学历"),
        ("博士", "Doctoral Degree", "博士学历"),
    ])
    tag("Audience/用户/教育/教育经历", "教育经历", "Education Experience", "特殊教育经历")
    tags_list("Audience/用户/教育/教育经历", [
        ("留学生", "International Student", "海外留学经历"),
        ("海归", "Returnee", "海归回国人员"),
        ("成人教育", "Adult Education", "成人参加的继续教育"),
    ])

    # 7. 职业身份
    dim("Audience/用户/职业", "职业身份", "Occupation",
        "用户职业与从业领域", max_depth=3, path_policy="prefer-leaf")
    tag("Audience/用户/职业/互联网", "互联网", "Internet Industry", "互联网科技行业职业")
    tags_list("Audience/用户/职业/互联网", [
        ("程序员", "Developer", "软件开发工程师"),
        ("产品经理", "Product Manager", "产品设计与管理"),
        ("设计师", "Designer", "UI/UX视觉设计师"),
        ("运营", "Operations", "内容运营与用户增长"),
        ("数据分析师", "Data Analyst", "数据分析工程师"),
    ])
    for job, en, desc in [
        ("学生", "Student", "在校学习的学生群体"),
        ("公务员", "Government Employee", "政府公务员"),
        ("教师", "Teacher", "教育机构教学人员"),
        ("医生护士", "Medical Staff", "医疗卫生从业者"),
        ("金融从业者", "Finance Professional", "银行证券基金等金融职业"),
        ("媒体人", "Media Professional", "记者编辑等媒体从业者"),
        ("法律从业者", "Legal Professional", "律师法官等法律从业者"),
        ("蓝领工人", "Blue-collar Worker", "制造业体力劳动者"),
        ("服务业", "Service Industry", "餐饮零售等服务行业"),
        ("自由职业者", "Freelancer", "独立接单自由职业"),
        ("个体户", "Self-employed", "个体工商户"),
        ("农业从业者", "Agricultural Worker", "农业相关从业人员"),
        ("军人警察", "Military & Police", "现役军人与警察"),
        ("离退休人员", "Retired", "已离退休人员"),
    ]:
        tag(f"Audience/用户/职业/{job}", job, en, desc)

    # 8. 收入
    dim("Audience/用户/收入", "收入水平", "Income Level",
        "用户月收入与资产段划分", max_depth=2, path_policy="prefer-leaf")
    tag("Audience/用户/收入/月薪段", "月薪段", "Monthly Salary Range", "按月薪划分的收入段")
    tags_list("Audience/用户/收入/月薪段", [
        ("5K以下", "Below 5K", "月薪5000元以下"),
        ("5K-10K", "5K-10K CNY", "月薪5000-10000元"),
        ("10K-20K", "10K-20K CNY", "月薪10000-20000元"),
        ("20K-50K", "20K-50K CNY", "月薪20000-50000元"),
        ("50K以上", "Above 50K", "月薪5万元以上"),
    ])
    tag("Audience/用户/收入/资产段", "资产段", "Wealth Level", "按资产划分的财富水平")
    tags_list("Audience/用户/收入/资产段", [
        ("无房无车", "No Property", "暂无房产车辆"),
        ("有车有房", "Has Property", "有房或有车"),
        ("百万资产", "Millionaire", "资产百万以上"),
        ("千万资产", "10M+ Wealth", "资产千万以上"),
    ])

    # 9. 婚姻家庭
    dim("Audience/用户/婚姻家庭", "婚姻家庭", "Marital & Family",
        "用户婚姻状态与家庭结构", max_depth=2, path_policy="prefer-leaf")
    tags_list("Audience/用户/婚姻家庭", [
        ("未婚单身", "Single", "未婚单身状态"),
        ("恋爱中", "In Relationship", "有稳定伴侣"),
        ("已婚无孩", "Married No Kids", "已婚但尚无子女"),
        ("已婚有孩", "Married with Kids", "已婚并有子女"),
        ("亲子家庭", "Family with Kids", "有子女的家庭出行"),
        ("三代同游", "Multi-generation", "三代人同行的家庭旅行"),
        ("离异", "Divorced", "离异状态"),
        ("空巢老人", "Empty Nester", "子女离家的老年人"),
        ("单亲家庭", "Single Parent", "单亲抚养家庭"),
    ])

    # 10. 消费特征
    dim("Audience/用户/消费特征", "消费特征", "Consumer Traits",
        "用户消费能力与偏好", max_depth=2, path_policy="prefer-leaf")
    tags_list("Audience/用户/消费特征", [
        ("价格敏感型", "Price Sensitive", "以价格为主要决策因素"),
        ("穷游型", "Budget Traveler", "低预算穷游式消费偏好"),
        ("性价比型", "Value for Money", "注重性价比的消费决策"),
        ("品质优先型", "Quality First", "以品质为主要决策因素"),
        ("奢华型", "Luxury-oriented", "偏好高端奢华消费"),
        ("冲动消费型", "Impulsive Buyer", "容易受推荐影响冲动购买"),
        ("理性比较型", "Rational Shopper", "倾向多方比较后决策"),
        ("品牌忠诚型", "Brand Loyal", "忠于特定品牌"),
        ("新品尝鲜型", "Early Adopter", "喜欢尝试新产品"),
    ])

    # 11. 生活阶段（孕育相关信息仅放此维度）
    dim("Audience/用户/生活阶段", "生活阶段", "Life Stage",
        "用户当前所处的人生阶段", max_depth=2, path_policy="prefer-leaf")
    tags_list("Audience/用户/生活阶段", [
        ("在校学生", "Student Life Stage", "目前在校就读阶段"),
        ("求职期", "Job Seeking", "正在求职找工作"),
        ("职场新人", "Career Starter", "刚入职场1-3年"),
        ("职场中坚", "Career Mid-stage", "职场5年以上"),
        ("管理层", "Management", "担任管理职务"),
        ("创业期", "Entrepreneurship Stage", "正在创业"),
        ("蜜月期", "Honeymoon Period", "新婚蜜月阶段"),
        ("备孕中", "Trying to Conceive", "备孕阶段"),
        ("孕期", "Pregnancy", "妊娠期"),
        ("产后恢复", "Postpartum", "产后恢复阶段"),
        ("退休后", "Post-retirement", "已退休生活"),
        ("间隔年", "Gap Year", "短暂休息探索期"),
    ])

    # 12. 作息习惯（仅昼夜节律）
    dim("Audience/用户/作息习惯", "作息习惯", "Daily Routine",
        "用户昼夜作息节律", max_depth=2, path_policy="prefer-leaf")
    tags_list("Audience/用户/作息习惯", [
        ("早起型", "Early Bird", "习惯早起的用户"),
        ("夜猫型", "Night Owl", "深夜活跃的用户"),
    ])

    # 13. 性格特质
    dim("Audience/用户/性格特质", "性格特质", "Personality Traits",
        "用户性格特征标签", max_depth=2, path_policy="prefer-leaf")
    tags_list("Audience/用户/性格特质", [
        ("内向", "Introvert", "偏内向性格"),
        ("外向", "Extrovert", "偏外向性格"),
        ("理性", "Rational", "理性逻辑型"),
        ("感性", "Emotional", "感性直觉型"),
        ("冒险", "Adventurous", "喜欢冒险挑战"),
        ("保守", "Conservative", "偏保守稳重"),
        ("社牛", "Social Butterfly", "极度外向善社交"),
        ("社恐", "Socially Anxious", "社交焦虑内敛"),
    ])

    # 14. 健康状况
    dim("Audience/用户/健康状况", "健康状况", "Health Status",
        "用户健康特殊状态（不含孕期；孕期见生活阶段）", max_depth=2, path_policy="prefer-leaf")
    tags_list("Audience/用户/健康状况", [
        ("普通健康", "Generally Healthy", "无特殊健康状况"),
        ("慢性病管理", "Chronic Disease", "管理慢性疾病"),
        ("术后康复", "Post-surgery", "手术后康复期"),
        ("残障用户", "Disability", "有身体或感官障碍"),
    ])

    # 15. 数字使用习惯
    dim("Audience/用户/数字使用习惯", "数字使用习惯", "Digital Usage Habits",
        "用户数字平台、设备与内容消费习惯", max_depth=3, path_policy="prefer-leaf")
    tag("Audience/用户/数字使用习惯/平台偏好", "平台偏好", "Platform Preference", "主要使用的内容平台")
    tags_list("Audience/用户/数字使用习惯/平台偏好", [
        ("抖音用户", "TikTok/Douyin User", "主要使用抖音"),
        ("小红书用户", "Xiaohongshu User", "主要使用小红书"),
        ("B站用户", "Bilibili User", "主要使用B站"),
        ("微博用户", "Weibo User", "主要使用微博"),
        ("知乎用户", "Zhihu User", "主要使用知乎"),
        ("公众号用户", "WeChat User", "主要使用微信公众号"),
        ("YouTube用户", "YouTube User", "主要使用YouTube"),
    ])
    tag("Audience/用户/数字使用习惯/设备偏好", "设备偏好", "Device Preference", "主要使用的设备")
    tags_list("Audience/用户/数字使用习惯/设备偏好", [
        ("苹果用户", "Apple User", "使用iPhone/iPad"),
        ("安卓用户", "Android User", "使用安卓设备"),
        ("PC用户", "PC User", "主要使用电脑"),
    ])
    tag("Audience/用户/数字使用习惯/内容消费", "内容消费", "Content Consumption",
        "内容消费偏好模式")
    tags_list("Audience/用户/数字使用习惯/内容消费", [
        ("碎片化阅读", "Fragmented Reading", "利用碎片时间快速浏览"),
        ("深度长文", "Deep Reading", "偏好深度长文内容"),
        ("视频优先", "Video First", "优先消费视频内容"),
        ("图文优先", "Image-Text First", "优先消费图文内容"),
        ("音频优先", "Audio First", "优先消费音频内容"),
    ])
    tag("Audience/用户/数字使用习惯/媒介与场景偏好", "媒介与场景偏好", "Media & Scene Preference",
        "内容形态与时间场景的倾向（承接原作息中的媒介项）")
    tags_list("Audience/用户/数字使用习惯/媒介与场景偏好", [
        ("短视频优先", "Short Video First", "偏好短视频内容消费"),
        ("音频用户", "Audio-heavy User", "偏好播客与音频内容"),
        ("深度阅读型", "Deep Reading Type", "偏好深度长内容研读"),
        ("通勤碎片化", "Commute Snacking", "通勤路上碎片消费"),
    ])

    # 16. 创作行为
    dim("Audience/用户/创作行为", "创作行为", "Creative Behavior",
        "用户的内容创作倾向", max_depth=2, path_policy="prefer-leaf")
    tags_list("Audience/用户/创作行为", [
        ("活跃创作者", "Active Creator", "频繁发布原创内容"),
        ("偶尔分享", "Occasional Sharer", "偶尔分享生活内容"),
        ("只浏览", "Lurker", "只消费不发布"),
        ("评论活跃", "Active Commenter", "经常留评论互动"),
        ("收藏型", "Collector", "大量收藏内容"),
        ("分享转发", "Sharer & Forwarder", "喜欢分享转发内容"),
    ])


def _gen_audience_创作者():
    dim("Audience/创作者", "创作者画像", "Creator Profile",
        "内容创作者的规模、风格与商业特征", max_depth=3, expected_size=50)

    dim("Audience/创作者/粉丝量级", "粉丝量级", "Follower Scale",
        "创作者账号的粉丝规模", max_depth=2, path_policy="leaf-only")
    tags_list("Audience/创作者/粉丝量级", [
        ("素人", "Nano Influencer", "粉丝1000以内"),
        ("小博主", "Micro Influencer", "粉丝1000-1万"),
        ("腰部博主", "Mid-tier Influencer", "粉丝1万-10万"),
        ("头部博主", "Macro Influencer", "粉丝10万-100万"),
        ("大V", "Mega Influencer", "粉丝100万-500万"),
        ("顶流", "Top KOL", "粉丝500万以上"),
    ])

    dim("Audience/创作者/创作领域宽度", "创作领域宽度", "Creator Domain Breadth",
        "创作者内容覆盖的领域宽度与专注度", max_depth=2)
    tags_list("Audience/创作者/创作领域宽度", [
        ("深度垂类", "Deep Niche", "专注单一垂直领域"),
        ("多元创作", "Multi-niche", "覆盖多个领域"),
        ("泛娱乐型", "General Entertainment", "内容广泛无固定垂类"),
    ])

    dim("Audience/创作者/平台属性", "平台属性", "Platform Attribute",
        "创作者活跃的主要内容平台", max_depth=2)
    for platform, en in [
        ("抖音创作者", "Douyin Creator"), ("小红书博主", "Xiaohongshu Blogger"),
        ("B站UP主", "Bilibili UP"), ("微博博主", "Weibo Blogger"),
        ("公众号作者", "WeChat Account Author"), ("视频号创作者", "WeChat Video Creator"),
        ("YouTube博主", "YouTuber"), ("X博主", "X Creator"),
    ]:
        tag(f"Audience/创作者/平台属性/{platform}", platform, en, f"主要在{platform.replace('创作者', '').replace('博主', '').replace('UP主', '').replace('作者', '')}平台活跃")

    dim("Audience/创作者/创作风格", "创作风格", "Creator Style",
        "创作者的内容生产风格", max_depth=2)
    tags_list("Audience/创作者/创作风格", [
        ("原创内容", "Original Content", "100%原创内容"),
        ("二次创作", "Secondary Creation", "基于他人内容再创作"),
        ("教学型", "Tutorial Style", "以教学指导为主"),
        ("纪实型", "Documentary Style", "真实记录风格"),
        ("虚构叙事型", "Fictional Narrative", "剧情虚构内容"),
    ])


def _gen_audience_圈子():
    dim("Audience/圈子", "圈子画像", "Community Profile",
        "社群与圈子类型的骨架分类", max_depth=3, expected_size=40)

    dim("Audience/圈子/地缘圈", "地缘圈", "Geo-based Circles",
        "以地理与生活半径聚合的圈子", max_depth=2)
    tags_list("Audience/圈子/地缘圈", [
        ("同城老乡", "Same-city Locals", "同城/同乡熟人向社群"),
        ("业主邻里", "Neighborhood HOA", "小区与楼盘业主类社群"),
        ("同城兴趣据点", "Local Meetup Hub", "同城线下活动与据点半径社群"),
    ])

    dim("Audience/圈子/官方圈", "官方圈", "Official Circles",
        "机构、品牌或政务背书的官方社群", max_depth=2)
    tags_list("Audience/圈子/官方圈", [
        ("品牌会员官方", "Brand Official Club", "品牌官方会员与用户群"),
        ("政务民生服务", "Gov-civic Services", "政务号与便民服务社群"),
        ("文旅景区官方", "Tourism Official", "目的地与景区官方社群"),
        ("媒体机构读者", "Media Reader Club", "媒体/出版机构读者群"),
    ])

    dim("Audience/圈子/付费圈", "付费圈", "Paid Circles",
        "以付费门槛或订阅维系的社群", max_depth=2)
    tags_list("Audience/圈子/付费圈", [
        ("知识星球类", "Knowledge Planet-style", "付费专栏类深度社群"),
        ("私教陪跑", "Coaching Circle", "小班私教/陪跑群"),
        ("品牌订阅会员", "Subscription Club", "品牌订阅制会员群"),
        ("付费活动营", "Paid Bootcamp", "打卡营与训练营类社群"),
    ])

    dim("Audience/圈子/兴趣聚合圈", "兴趣聚合圈", "Interest Aggregation Circles",
        "跨地域以主题/同人/技能聚合的圈子", max_depth=2)
    tags_list("Audience/圈子/兴趣聚合圈", [
        ("话题连载社群", "Topic Series Club", "连载话题与栏目讨论群"),
        ("同人二创社区", "Fan Creation Hub", "同人二创与作品共创"),
        ("技能互助小组", "Skill Exchange Pod", "学习/技能互助小组"),
        ("垂类收藏家", "Niche Collector Circle", "模型、黑胶等垂类收藏圈"),
    ])

    dim("Audience/圈子/校园圈", "校园圈", "Campus Circles",
        "以校园关系（校友、院系、年级、备考）聚合的圈子", max_depth=2)
    tags_list("Audience/圈子/校园圈", [
        ("母校圈", "Alma Mater Circle", "同一学校的校友社群"),
        ("院系圈", "Department Circle", "同一院系的师生社群"),
        ("年级圈", "Class Year Circle", "同一届的同学社群"),
        ("校友圈", "Alumni Circle", "毕业后的校友联络社群"),
        ("职场互助圈", "Career Mutual Aid Circle", "校友间的职场帮扶社群"),
        ("备考圈", "Exam Prep Circle", "考研/考公/考编等备考互助社群"),
    ])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# F O R M A T
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def gen_format():
    group("Format", "内容形式", "Format",
          "描述内容的物理载体、创作视角、表现手法等六个互斥子维度。各子维度正交，一篇内容可同时引用多个子维度的标签。",
          ["Format/内容载体", "Format/内容角度", "Format/表现手法",
           "Format/视觉风格", "Format/互动玩法", "Format/商业形式"])

    _gen_format_内容载体()
    _gen_format_内容角度()
    _gen_format_表现手法()
    _gen_format_视觉风格()
    _gen_format_互动玩法()
    _gen_format_商业形式()


def _gen_format_内容载体():
    dim("Format/内容载体", "内容载体", "Content Medium",
        "内容以何种物理形式存在；保留文章/视频/图文/直播/音频/问答/行程单七大媒介",
        max_depth=3, expected_size=55)

    tag("Format/内容载体/文章", "文章", "Article",
        "以文字为主的内容载体形式")
    tags_list("Format/内容载体/文章", [
        ("长文", "Long Article", "3000字以上深度文章"),
        ("短文", "Short Article", "1000字以内轻量文章"),
        ("游记", "Travel Journal", "旅行游记文章"),
        ("测评文", "Review Article", "产品或体验测评文章"),
        ("小说", "Fiction", "虚构叙事小说"),
        ("漫画文", "Manga Article", "图文混排漫画内容"),
        ("专栏文", "Column Article", "专栏连载文章"),
        ("公众号文", "WeChat Article", "微信公众号推文"),
    ])

    tag("Format/内容载体/视频", "视频", "Video",
        "以动态影像为主的内容载体形式")
    tags_list("Format/内容载体/视频", [
        ("短视频", "Short Video", "1分钟以内竖屏短视频"),
        ("中视频", "Mid-length Video", "1-30分钟视频"),
        ("长视频", "Long Video", "30分钟以上长视频"),
        ("360全景视频", "360 VR Video", "沉浸式全景视频"),
        ("延时摄影", "Time-lapse", "延时摄影视频"),
        ("慢动作视频", "Slow Motion", "高帧率慢动作"),
    ])

    tag("Format/内容载体/图文", "图文", "Image & Text",
        "图片与文字混合的内容载体形式")
    tags_list("Format/内容载体/图文", [
        ("九宫格", "Nine-grid", "小红书九宫格图文"),
        ("图集", "Photo Album", "多图组合图集"),
        ("长图", "Long Image", "竖版长图卡片"),
        ("单图", "Single Image", "单张图片配文"),
        ("漫画", "Comic Strip", "漫画故事图文"),
        ("信息图", "Infographic", "数据可视化信息图"),
        ("Carousel", "Carousel Post", "滑动卡片合集"),
    ])

    tag("Format/内容载体/直播", "直播", "Livestream",
        "实时直播内容载体")
    tags_list("Format/内容载体/直播", [
        ("游戏直播", "Game Livestream", "实时游戏直播"),
        ("带货直播", "Shopping Livestream", "电商带货直播"),
        ("才艺直播", "Talent Livestream", "才艺表演直播"),
        ("户外直播", "Outdoor Livestream", "户外探索直播"),
        ("教学直播", "Educational Livestream", "知识技能直播课"),
        ("事件直播", "Event Livestream", "现场活动直播"),
        ("PK直播", "PK Battle Livestream", "互动PK对战直播"),
    ])

    tag("Format/内容载体/音频", "音频", "Audio",
        "以声音为主的内容载体")
    tags_list("Format/内容载体/音频", [
        ("播客", "Podcast", "音频播客节目"),
        ("有声书", "Audiobook", "文字内容的音频版"),
        ("音乐", "Music Audio", "音乐与原声"),
        ("ASMR", "ASMR", "助眠解压声音"),
        ("广播剧", "Radio Drama", "音频戏剧"),
        ("白噪音", "White Noise", "背景白噪音"),
    ])

    tag("Format/内容载体/问答", "问答", "Q&A",
        "以问题与回答为主的内容形式")
    tags_list("Format/内容载体/问答", [
        ("知识问答", "Knowledge Q&A", "知乎风格深度问答"),
        ("经验贴", "Experience Post", "个人经历经验分享"),
        ("百科问答", "Encyclopedia Q&A", "百科知识问答"),
    ])

    tag("Format/内容载体/行程单", "行程单", "Itinerary",
        "旅行行程规划单")
    tags_list("Format/内容载体/行程单", [
        ("携程行程", "Ctrip Itinerary", "携程平台行程单"),
        ("马蜂窝行程", "MFW Itinerary", "马蜂窝行程规划"),
        ("DIY行程", "Custom Itinerary", "自制行程规划单"),
    ])


def _gen_format_内容角度():
    dim("Format/内容角度", "内容角度", "Content Angle",
        "内容的创作切入视角，14个互斥视角，每篇内容至少标注一个",
        max_depth=3, expected_size=120)

    tag("Format/内容角度/攻略", "攻略", "Guide",
        "提供实操指引、路线推荐、方法论的内容视角")
    tags_list("Format/内容角度/攻略", [
        ("行前指南", "Pre-trip Guide", "出发前准备与注意事项"),
        ("路线推荐", "Route Recommendation", "旅行或行动路线推荐"),
        ("实用清单", "Practical Checklist", "行前或购物实用清单"),
        ("玩法精选", "Activity Selection", "精选活动与体验"),
        ("季节限定", "Seasonal Tips", "特定季节的专属攻略"),
        ("亲子专享", "Family Guide", "亲子旅行与活动攻略"),
        ("银发专享", "Senior Guide", "适合老年人的攻略"),
        ("小众秘境", "Hidden Gem Guide", "小众目的地发现指引"),
        ("省钱攻略", "Budget Guide", "低价优惠攻略"),
        ("住宿攻略", "Accommodation Guide", "住宿选择与预订攻略"),
        ("新生攻略", "Freshman Guide", "大学或学校新生入学攻略"),
        ("选课攻略", "Course Selection Guide", "大学选课策略与避坑指南"),
    ])

    tag("Format/内容角度/体验", "体验", "Experience",
        "记录亲身体验与感受的内容视角")
    tags_list("Format/内容角度/体验", [
        ("亲身体验", "Personal Experience", "第一人称真实体验记录"),
        ("旅居体验", "Live-in Experience", "长期住居体验记录"),
        ("沉浸式体验", "Immersive Experience", "深度沉浸式体验"),
        ("慢综体验", "Slow Life Experience", "慢节奏生活体验"),
        ("极限体验", "Extreme Experience", "极限挑战体验"),
    ])

    tag("Format/内容角度/测评", "测评", "Review",
        "对产品、服务、场所进行评测对比的内容视角")
    tags_list("Format/内容角度/测评", [
        ("横向对比", "Horizontal Comparison", "多个同类产品横向对比"),
        ("纵向对比", "Vertical Comparison", "同产品不同版本对比"),
        ("长期测试", "Long-term Test", "长时间使用后测评"),
        ("性能测评", "Performance Test", "性能参数专项测评"),
        ("价位测评", "Price-value Test", "性价比测评"),
        ("专业评测", "Professional Review", "专业维度深度评测"),
        ("住宿测评", "Accommodation Review", "住宿设施综合测评"),
        ("酒店横评", "Hotel Comparison", "多家酒店横向对比测评"),
        ("校园评测", "Campus Review", "学校、院系、食堂、宿舍等校园设施综合评测"),
    ])

    tag("Format/内容角度/探店", "探店", "Store Visit",
        "探访餐厅、门店、景点、住宿的打卡体验内容视角")
    tags_list("Format/内容角度/探店", [
        ("餐厅探店", "Restaurant Visit", "探访餐厅进行评测"),
        ("咖啡探店", "Cafe Visit", "探访咖啡馆"),
        ("酒吧探店", "Bar Visit", "探访酒吧"),
        ("景点探店", "Attraction Visit", "实地到访景点"),
        ("购物探店", "Shopping Visit", "探访商场或品牌店"),
        ("民宿探店", "Homestay Visit", "探访特色民宿"),
        ("夜市探店", "Night Market Visit", "夜市美食探访"),
        ("酒店探店", "Hotel Visit", "探访酒店进行评测"),
        ("度假村探店", "Resort Visit", "实地探访度假村体验分享"),
        ("酒店餐厅探店", "Hotel Dining Visit", "探访酒店内餐厅"),
        ("茶馆探店", "Teahouse Visit", "探访茶馆品茶体验"),
        ("夜宵探店", "Late Night Food Visit", "探访夜宵摊点"),
        ("面包甜品探店", "Bakery Visit", "探访面包甜品店"),
        ("Bistro探店", "Bistro Visit", "探访Bistro餐厅"),
    ])

    tag("Format/内容角度/种草", "种草", "Product Recommendation",
        "向他人推荐好物的内容视角")
    tags_list("Format/内容角度/种草", [
        ("好物种草", "Product Recommendation", "推荐优质好物"),
        ("单品种草", "Single Item Rec", "单件商品重点推荐"),
        ("清单种草", "List Recommendation", "多件好物清单推荐"),
        ("场景种草", "Scene-based Rec", "特定场景下的推荐"),
        ("IP种草", "IP Product Rec", "联名IP商品推荐"),
    ])

    tag("Format/内容角度/拔草", "拔草", "Anti-Recommendation",
        "揭示产品或场所缺陷、不符预期的内容视角")
    tags_list("Format/内容角度/拔草", [
        ("长测拔草", "Long-term Test Fail", "长期使用后失望的评测"),
        ("失望对比", "Disappointing Comparison", "与宣传对比的失望"),
        ("翻车实录", "Fail Record", "使用失败的真实记录"),
    ])

    tag("Format/内容角度/避雷", "避雷", "Warning & Caution",
        "提醒他人避开踩坑的内容视角")
    tags_list("Format/内容角度/避雷", [
        ("踩雷预警", "Pitfall Warning", "提醒踩雷注意事项"),
        ("商家避雷", "Business Warning", "提醒商家或服务问题"),
        ("产品避雷", "Product Warning", "提醒劣质产品"),
        ("目的地避雷", "Destination Warning", "旅行目的地踩坑提醒"),
        ("住宿避雷", "Accommodation Warning", "住宿踩坑避雷提醒"),
    ])

    tag("Format/内容角度/盘点", "盘点", "Roundup",
        "归纳总结多个对象的盘点类内容视角")
    tags_list("Format/内容角度/盘点", [
        ("年度盘点", "Annual Roundup", "年度总结盘点"),
        ("主题盘点", "Themed Roundup", "特定主题的盘点"),
        ("Top榜单", "Top List", "排行榜式盘点"),
        ("月度盘点", "Monthly Roundup", "月度内容盘点"),
    ])

    tag("Format/内容角度/教程", "教程", "Tutorial",
        "教授方法与步骤的教学内容视角")
    tags_list("Format/内容角度/教程", [
        ("入门教程", "Beginner Tutorial", "零基础入门指导"),
        ("进阶教程", "Advanced Tutorial", "有基础后的进阶"),
        ("速成教程", "Quick Tutorial", "快速上手教程"),
        ("实操步骤", "Step-by-step Guide", "详细操作步骤"),
        ("问题答疑", "Q&A Tutorial", "常见问题解答"),
    ])

    tag("Format/内容角度/科普", "科普", "Science Communication",
        "传递知识与普及科学的内容视角")
    tags_list("Format/内容角度/科普", [
        ("知识科普", "Knowledge Popularization", "通俗易懂的知识普及"),
        ("技术科普", "Tech Science Com", "技术原理科普"),
        ("科学辟谣", "Myth Busting", "澄清科学谣言"),
        ("行业揭秘", "Industry Insider", "行业内幕科普"),
    ])

    tag("Format/内容角度/观点评论", "观点评论", "Opinion & Commentary",
        "发表观点与深度评论的内容视角（区别于UGC评论区'评论'概念）")
    tags_list("Format/内容角度/观点评论", [
        ("深度评论", "In-depth Commentary", "深度分析评论"),
        ("热点评论", "Hot Topic Commentary", "热点事件评论"),
        ("辣评", "Spicy Comment", "犀利直白的点评"),
        ("辩论", "Debate", "正反两方观点辩论"),
    ])

    tag("Format/内容角度/资讯", "资讯", "News & Info",
        "新闻报道与信息传播的内容视角")
    tags_list("Format/内容角度/资讯", [
        ("快讯", "Breaking News", "快速传播的最新资讯"),
        ("深度报道", "In-depth Report", "深度调查报道"),
        ("专题报道", "Feature Report", "特定主题专题报道"),
        ("追踪报道", "Follow-up Report", "持续追踪事件进展"),
        ("辟谣", "Debunking", "澄清虚假信息"),
    ])

    tag("Format/内容角度/叙事", "叙事", "Narrative & Storytelling",
        "个人故事、真实事件、人物传记的叙事内容视角（对应图文/视频等载体，不限定某一种 Story 控件）")
    tags_list("Format/内容角度/叙事", [
        ("个人故事", "Personal Story", "个人真实经历叙述"),
        ("旅行叙事", "Travel Story", "旅途故事叙述"),
        ("真实事件", "True Event", "真实发生的事件记录"),
        ("人物传记", "Biography", "人物生平故事叙述"),
        ("纪实记录", "Documentary Record", "真实生活记录"),
    ])

    tag("Format/内容角度/日记", "日记", "Diary & Journal",
        "日常生活记录类的内容视角")
    tags_list("Format/内容角度/日记", [
        ("生活日记", "Life Diary", "日常生活记录日记"),
        ("创业日记", "Startup Diary", "创业历程日记"),
        ("留学日记", "Study Abroad Diary", "海外留学生活日记"),
        ("健身日记", "Fitness Diary", "健身运动打卡日记"),
        ("育儿日记", "Parenting Diary", "育儿日常记录"),
        ("校园日记", "Campus Diary", "校园日常生活记录日记"),
    ])

    tag("Format/内容角度/经验分享", "经验分享", "Experience Sharing",
        "个人经验总结与心得分享的内容视角")
    tags_list("Format/内容角度/经验分享", [
        ("考研经验", "Postgrad Exam Experience", "考研备考心得与经验分享"),
        ("保研经验", "Recommendation Experience", "保研推免经验与心得"),
        ("留学经验", "Study Abroad Experience", "留学申请与海外生活经验"),
        ("求职经验", "Job Hunting Experience", "求职面试与职场经验分享"),
        ("校招经验", "Campus Recruitment Experience", "校园招聘笔试面试经验"),
    ])


def _gen_format_表现手法():
    dim("Format/表现手法", "表现手法", "Production Technique",
        "视频/直播/图文的表演形态与剪辑手法，与内容角度正交",
        max_depth=3, expected_size=60)

    tag("Format/表现手法/表演形态", "表演形态", "Performance Style",
        "创作者的表演与互动风格")
    tags_list("Format/表现手法/表演形态", [
        ("Vlog", "Vlog", "随拍跟拍的真实日常记录"),
        ("口播", "Talking Head", "面对镜头直接讲述"),
        ("短剧", "Short Drama", "剧情化短视频"),
        ("Reaction反应", "Reaction Video", "对内容做出即时反应"),
        ("合拍", "Duet", "与他人内容合拍互动"),
        ("翻拍", "Cover & Remake", "翻拍经典内容"),
        ("变装", "Outfit Change", "变装换装效果"),
        ("舞蹈", "Dance", "舞蹈表演类"),
        ("唱歌", "Singing", "音乐演唱类"),
        ("配音", "Voice-over", "配音翻译类"),
        ("挑战", "Challenge", "参与平台挑战话题"),
    ])

    tag("Format/表现手法/剪辑形态", "剪辑形态", "Edit Style",
        "视频后期剪辑与制作风格")
    tags_list("Format/表现手法/剪辑形态", [
        ("混剪", "Mashup Edit", "多素材混合剪辑"),
        ("快剪", "Fast Cut", "快节奏高密度剪辑"),
        ("慢剪", "Slow Edit", "慢节奏缓和剪辑"),
        ("卡点", "Beat Sync", "音乐节拍卡点"),
        ("反转", "Twist Edit", "结尾反转剪辑手法"),
        ("蒙太奇", "Montage", "蒙太奇叙事手法"),
        ("直播切片", "Livestream Clip", "精选直播片段重新剪辑"),
    ])

    tag("Format/表现手法/运镜", "运镜", "Camera Movement",
        "摄影/摄像运镜手法")
    tags_list("Format/表现手法/运镜", [
        ("固定机位", "Fixed Shot", "固定不动的镜头"),
        ("推拉镜头", "Push & Pull", "前后推拉运动镜头"),
        ("摇移镜头", "Pan & Tilt", "左右或上下摇移"),
        ("跟随镜头", "Following Shot", "跟随主体移动"),
        ("环绕镜头", "Arc Shot", "环绕主体拍摄"),
        ("无人机镜头", "Drone Shot", "无人机航拍"),
    ])

    tag("Format/表现手法/特效", "特效", "Visual Effects",
        "视频特效与后期处理")
    tags_list("Format/表现手法/特效", [
        ("转场特效", "Transition Effect", "画面转场特效"),
        ("绿幕合成", "Green Screen", "绿幕抠图合成"),
        ("AR特效", "AR Filter", "增强现实滤镜特效"),
        ("定格动画", "Stop Motion", "定格动画特效"),
    ])

    tag("Format/表现手法/摄影技法", "摄影技法", "Photography Technique",
        "静态摄影的拍摄技术手段，与视频运镜/剪辑正交")
    tags_list("Format/表现手法/摄影技法", [
        ("长曝光", "Long Exposure", "延长快门时间记录运动轨迹"),
        ("多重曝光", "Multiple Exposure", "多次曝光叠加在同一画面"),
        ("光绘", "Light Painting", "长曝光配合移动光源绘制图案"),
        ("延时", "Timelapse", "间隔拍摄合成时间流逝效果"),
        ("全景接片", "Panorama Stitching", "多张照片拼接成宽幅全景"),
        ("高速抓拍", "High Speed Freeze", "高速快门冻结瞬间动作"),
        ("追焦", "Panning", "跟随主体移动拍摄产生速度感"),
        ("星轨", "Star Trail", "长时间曝光记录星体运动轨迹"),
        ("景深合成", "Focus Stacking", "多张不同焦点合成全景深"),
        ("红外", "Infrared", "红外线波段拍摄产生超现实效果"),
        ("倒影", "Reflection", "利用水面镜面等反射构成画面"),
        ("剪影", "Silhouette", "逆光下主体呈现黑色轮廓"),
        ("散景", "Bokeh", "大光圈制造柔美的焦外光斑"),
        ("堆栈", "Stacking", "多帧堆叠降噪或丝化水面等"),
    ])

    tag("Format/表现手法/构图手法", "构图手法", "Composition Method",
        "画面空间组织与视觉引导的构成方法")
    tags_list("Format/表现手法/构图手法", [
        ("三分法", "Rule of Thirds", "将画面分为九宫格在交叉点放置主体"),
        ("对称构图", "Symmetry", "利用对称轴创造稳定均衡的画面"),
        ("引导线", "Leading Lines", "利用线条引导视线到主体"),
        ("框架构图", "Framing", "利用前景元素形成画中画框架"),
        ("极简留白", "Negative Space", "大面积留白突出主体"),
        ("对角线", "Diagonal", "对角线方向排列制造动感"),
        ("前景纵深", "Foreground Depth", "加入前景增强空间纵深感"),
        ("俯拍", "Bird's Eye View", "从高处垂直向下俯视拍摄"),
        ("仰拍", "Low Angle", "低角度仰视拍摄产生气势感"),
    ])


def _gen_format_视觉风格():
    dim("Format/视觉风格", "视觉风格", "Visual Style",
        "摄影摄像的视觉调性与后期风格，面向图片/视频类内容",
        max_depth=3, expected_size=45)

    tag("Format/视觉风格/视觉调性", "视觉调性", "Visual Tone",
        "内容整体的视觉审美风格")
    for tone, en, desc in [
        ("胶片感", "Film Look", "模拟胶片颗粒感与色调"),
        ("日系小清新", "Japanese Fresh Style", "日本清新自然色调"),
        ("暗调低饱和", "Dark Low Saturation", "暗部压低低饱和度"),
        ("高调明亮", "High Key Bright", "高调明亮风格"),
        ("电影感", "Cinematic Look", "电影级宽画幅色调"),
        ("赛博朋克", "Cyberpunk", "霓虹未来感色彩"),
        ("极简白", "Minimalist White", "极简白色调"),
        ("复古棕", "Vintage Brown", "复古胶片棕色调"),
        ("韩系", "Korean Style", "韩系白皙细腻风格"),
        ("法式", "French Style", "法式优雅色调"),
        ("中古风", "Vintage Style", "中古复古风格"),
        ("Y2K风", "Y2K Style", "2000年代千禧风格"),
        ("黑白", "Black & White", "纯黑白无彩色摄影风格"),
        ("纪实风", "Documentary Style", "真实未修饰的纪实影像风格"),
        ("色彩浓郁", "Vivid & Saturated", "高饱和度鲜艳色彩风格"),
    ]:
        tag(f"Format/视觉风格/视觉调性/{tone}", tone, en, desc)

    tag("Format/视觉风格/后期风格", "后期风格", "Post-processing Style",
        "照片/视频后期处理的风格")
    for style, en in [
        ("原片直出", "SOOC"), ("重度修图", "Heavy Retouching"),
        ("HDR效果", "HDR Effect"), ("滤镜风格", "Filter Style"),
        ("胶片模拟", "Film Simulation"), ("调色风格", "Color Grading"),
    ]:
        tag(f"Format/视觉风格/后期风格/{style}", style, en,
            f"{style}风格的后期处理")


def _gen_format_互动玩法():
    dim("Format/互动玩法", "互动玩法", "Engagement Mechanics",
        "平台内特有的互动机制标签", max_depth=2, expected_size=15)
    tags_list("Format/互动玩法", [
        ("话题讨论", "Topic Discussion", "参与话题讨论互动"),
        ("抽奖活动", "Giveaway", "粉丝抽奖互动"),
        ("征集投稿", "Content Submission", "向粉丝征集内容"),
        ("连麦互动", "Live Link-up", "直播连麦互动"),
        ("接力活动", "Relay Activity", "话题接力传播"),
        ("合辑共建", "Collaborative Collection", "共同建设内容合辑"),
        ("投票互动", "Voting Engagement", "发起投票互动"),
    ])


def _gen_format_商业形式():
    dim("Format/商业形式", "商业形式", "Commercial Format",
        "内容中涉及的商业合作形式标注", max_depth=2, expected_size=12)
    tags_list("Format/商业形式", [
        ("带货推广", "Product Promotion", "商品推广销售内容"),
        ("品牌合作", "Brand Collaboration", "与品牌合作产出内容"),
        ("广告内容", "Paid Advertisement", "付费广告内容"),
        ("赞助内容", "Sponsored Content", "企业赞助的内容"),
        ("团购活动", "Group Buying", "拼团团购推广"),
        ("效果广告", "Performance Ad", "按效果计费广告"),
        ("内容植入", "Product Placement", "内容中自然植入"),
        ("联名合作", "Co-branding", "与其他品牌联名合作"),
    ])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# E N T I T Y
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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

    tag("Entity/商品/服饰", "服饰", "Apparel", "服饰单品")
    tags_list("Entity/商品/服饰", [
        ("上衣", "Top", "上装类型"),
        ("下装", "Bottom", "裤子裙子等下装"),
        ("外套", "Outerwear", "外套夹克类型"),
        ("鞋类", "Shoes", "各类鞋履"),
        ("包袋", "Bag", "包袋配件类型"),
        ("配饰", "Accessories", "首饰配饰类型"),
    ])

    tag("Entity/商品/美妆", "美妆", "Beauty Product", "美妆护肤商品")
    tags_list("Entity/商品/美妆", [
        ("护肤品", "Skincare", "护肤产品类型"),
        ("彩妆品", "Cosmetics", "彩妆产品类型"),
        ("香水", "Perfume", "香水香氛"),
        ("美容工具", "Beauty Tool", "美容仪器工具"),
    ])

    tag("Entity/商品/食品", "食品", "Food Product", "食品饮料商品")
    tags_list("Entity/商品/食品", [
        ("零食", "Snack", "休闲零食类型"),
        ("饮品", "Beverage", "饮料饮品类型"),
        ("生鲜食材", "Fresh Food", "生鲜农产品"),
        ("调味品", "Condiment", "调料酱料类型", ["酱料"]),
        ("保健品", "Health Supplement", "保健营养品"),
    ])

    for ptype, en, desc in [
        ("数码", "Digital Product", "数码电子产品"),
        ("家居", "Home Product", "家居用品"),
        ("母婴用品", "Baby Product", "母婴产品"),
        ("运动用品", "Sports Product", "运动健身器材"),
        ("文具", "Stationery", "文具学习用品"),
        ("玩具", "Toy", "玩具游戏产品"),
        ("汽车用品", "Auto Product", "汽车配件用品"),
    ]:
        tag(f"Entity/商品/{ptype}", ptype, en, desc)

    dim("Entity/商品/类目", "类目", "Product Category",
        "商品所属的消费类目（画像）", max_depth=2, path_policy="prefer-leaf")
    for cat, en in [
        ("服饰", "Apparel"), ("美妆", "Beauty"), ("食品饮料", "Food & Beverage"),
        ("数码电子", "Digital Electronics"), ("家居家电", "Home & Appliances"),
        ("母婴", "Maternity & Baby"), ("运动户外", "Sports & Outdoor"),
        ("图书文具", "Books & Stationery"), ("玩具", "Toys"),
        ("旅游服务", "Travel Services"), ("医疗健康", "Healthcare"),
        ("宠物", "Pet Products"),
    ]:
        tag(f"Entity/商品/类目/{cat}", cat, en, f"{cat}类商品")

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
# 全局 taxonomy 快照
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def write_taxonomy():
    dimensions = []
    for group_id in ["Topic", "Audience", "Format", "Entity"]:
        group_dir = TAGS_ROOT / group_id
        if not group_dir.exists():
            continue
        for dim_path in group_dir.iterdir():
            if not dim_path.is_dir():
                continue
            count = sum(1 for _ in dim_path.rglob("_definition.json"))
            dimensions.append({
                "id": f"{group_id}/{dim_path.name}",
                "group": group_id,
                "label": dim_path.name,
                "count": count,
            })

    total = sum(d["count"] for d in dimensions)
    by_group: dict[str, int] = {}
    for d in dimensions:
        by_group[d["group"]] = by_group.get(d["group"], 0) + d["count"]

    write_json(TAGS_ROOT / "_taxonomy.json", {
        "version": "v4",
        "schemaVersion": "1.0",
        "groups": ["Topic", "Audience", "Format", "Entity"],
        "dimensions": dimensions,
        "totalCount": total,
        "stats": {"byGroup": by_group},
        "generatedAt": NOW_ISO,
    })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# main
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GENERATORS: dict[str, callable] = {
    "Topic": gen_topic,
    "Audience": gen_audience,
    "Format": gen_format,
    "Entity": gen_entity,
}


def main():
    global DRY_RUN

    parser = argparse.ArgumentParser(description="生成四分组标签体系")
    parser.add_argument("--dry-run", action="store_true", help="仅统计不写盘")
    parser.add_argument("--group", choices=["Topic", "Audience", "Format", "Entity"],
                        help="只生成指定分组")
    args = parser.parse_args()
    DRY_RUN = args.dry_run

    if args.group:
        GENERATORS[args.group]()
    else:
        for g, fn in GENERATORS.items():
            print(f"  生成 {g} ...")
            fn()

    if not DRY_RUN:
        write_taxonomy()

    print("\n=== bootstrap_tags 统计 ===")
    total = 0
    for k, v in sorted(_stats.items()):
        print(f"  {k}: {v}")
        total += v
    print(f"  合计: {total}")
    if DRY_RUN:
        print("  [dry-run 模式，未写盘]")


if __name__ == "__main__":
    main()
