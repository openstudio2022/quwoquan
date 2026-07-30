"""Topic/住宿 的八维正交生成器。

住宿是全仓唯一的住宿标签真相源：业态 × 价位 × 主题 × 设施 × 房型 × 区位 × 认证 × 预订特征。
曾经并行存在 Topic/旅行/住宿（话题角度）这第二棵住宿树，同轴重名让召回、交集句和聚合页
只能任选其一，其余副本成为孤儿，故已收敛到此处；Entity/地点/住宿 只保留供 HomepageType
使用的类型骨架，不承载住宿话题。
"""
from __future__ import annotations

_WRITERS = {}


def configure_writers(**writers):
    _WRITERS.update(writers)


def dim(*args, **kwargs):
    return _WRITERS["dim"](*args, **kwargs)


def tag(*args, **kwargs):
    return _WRITERS["tag"](*args, **kwargs)


def tags_list(*args, **kwargs):
    return _WRITERS["tags_list"](*args, **kwargs)


def gen_topic_lodging():
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
        max_depth=2, expected_size=8)
    tags_list("Topic/住宿/预订特征", [
        # 「闪订」只作为别名存在，不再另立同义标签：同一预订特征两个 tagRef 会让
        # 召回与筛选各命中一半内容。
        ("即时确认", "Instant Book", "即时确认预订", ["闪订"]),
        ("免费取消", "Free Cancellation", "可免费取消的预订"),
        ("价保", "Price Match", "最低价保证"),
        ("含早", "Breakfast Included", "房价含早餐的预订"),
        ("含三餐", "All Meals", "含早中晚三餐"),
        ("限时优惠", "Flash Deal", "限时特价优惠"),
        ("会员专享", "Members Only", "会员专享价格与权益"),
        # 从 Topic/旅行/住宿/住宿比价 合并而来：比价是预订环节的特征，不是独立话题。
        ("住宿比价", "Stay Price Comparison", "住宿比价与省钱技巧"),
    ])
