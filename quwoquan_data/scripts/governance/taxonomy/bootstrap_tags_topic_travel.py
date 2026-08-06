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


def gen_topic_travel():
    # 4. 旅行（9 子维度：旅行主题/玩法/出行方式/行程形态/旅行时长/旅行筹备
    #          + 预算档次/同行人/体能强度）
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
        # 刻意不生成「滑雪滑冰」「瑜伽冥想」：它们的唯一真相源分别是
        # Topic/运动/极限运动/滑雪滑冰 与 Topic/健康养生/瑜伽冥想；
        # 也不生成「潜水浮潜」：同维度已有「潜水」，同轴重名必然产生孤儿（R14）。
        ("潜水", "Diving", "水下潜水与浮潜体验"),
        ("徒步", "Hiking", "徒步穿越与山野路线体验"),
        ("跳伞极限", "Skydiving & Extreme", "跳伞蹦极等极限体验"),
        ("冲浪水上", "Surfing & Water Sports", "冲浪划船等水上运动体验"),
        ("热气球", "Hot Air Balloon", "热气球升空观景体验"),
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

    # 4.6 三个筛选轴：预算档次 / 同行人 / 体能强度
    #
    # 这里刻意不再有「住宿」子维度：住宿的唯一真相源是 Topic/住宿，
    # 旅行侧维护第二棵住宿树会让召回、交集句和聚合页只能任选其一，其余成为孤儿（R14）。
    # 「住宿攻略」「住宿避雷」是叙述角度，归 Format/内容角度；
    # 「川西住宿」「高原住宿」是住宿 × 地理的组合，不做成单独标签。
    #
    # 三个轴都由创作侧打标 chip 采集、进入召回过滤与交集，因此满足标签价值四门测试。
    # 刻意不做「出入境难度」「季节窗口」：那是目的地的客观属性，应挂实体
    # structuredFacts，做成内容标签后创作者不会选、系统也无从采集，必然成为孤儿。
    _TRAVEL_FACET_CHANNEL = "creator_chip"
    _TRAVEL_FACET_CONSUMERS = ["recall", "intersection"]

    dim("Topic/旅行/预算档次", "预算档次", "Budget Tier",
        "单人单日综合花费档次，用于按预算筛选行程与内容",
        max_depth=2, expected_size=5)
    tags_list("Topic/旅行/预算档次", [
        ("穷游", "Shoestring", "极致压缩住宿与交通成本，人均单日花费处于最低档"),
        ("经济", "Budget", "以性价比为先，住经济型住宿、以公共交通为主"),
        ("舒适", "Comfort", "住宿与餐饮达到舒适标准，适度使用打车与门票"),
        ("轻奢", "Premium", "选择精品住宿与特色体验，愿为品质付溢价"),
        ("高端定制", "Luxury Bespoke", "私导、包车、高端住宿与定制行程"),
    ], collection_channel=_TRAVEL_FACET_CHANNEL,
        consumed_by=_TRAVEL_FACET_CONSUMERS)

    # 与旅行主题正交：主题说「去做什么」，同行人说「和谁去」。
    # 两轴用词刻意不同名（主题侧「亲子游」vs 本轴「家庭带娃」），避免同轴重名。
    dim("Topic/旅行/同行人", "同行人", "Travel Party",
        "出行的人群构成；与旅行主题正交：主题=去做什么，同行人=和谁去",
        max_depth=2, expected_size=7)
    tags_list("Topic/旅行/同行人", [
        ("独自出行", "Solo", "一人出行，关注安全、社交与单人友好设施"),
        ("情侣同行", "Couple", "两人情侣出行，关注私密性与纪念性体验"),
        ("家庭带娃", "Family With Kids", "携未成年子女出行，关注亲子设施与节奏"),
        ("携长辈", "With Elders", "携长辈出行，关注无障碍、海拔与体力强度"),
        ("朋友结伴", "With Friends", "同龄朋友结伴出行，关注多人房型与共同玩法"),
        ("携宠出行", "With Pets", "携宠物出行，关注宠物友好住宿与交通规则"),
        ("团队出行", "Group Tour", "十人以上团队或公司团建出行"),
    ], collection_channel=_TRAVEL_FACET_CHANNEL,
        consumed_by=_TRAVEL_FACET_CONSUMERS)

    dim("Topic/旅行/体能强度", "体能强度", "Physical Intensity",
        "行程对体能的要求档次，用于避免把高强度线路推给低体能意愿用户",
        max_depth=2, expected_size=4)
    tags_list("Topic/旅行/体能强度", [
        ("轻松休闲", "Leisurely", "以乘车观光与短距步行为主，日均步行低于 5 公里"),
        ("中等强度", "Moderate", "含较长时间步行或缓坡徒步，日均步行 5-15 公里"),
        ("高强度", "Strenuous", "含长距离徒步、连续爬升或高海拔活动"),
        ("专业级", "Expert", "需要技术装备与专项训练，如技术攀登、洞穴、深潜"),
    ], collection_channel=_TRAVEL_FACET_CHANNEL,
        consumed_by=_TRAVEL_FACET_CONSUMERS)

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
