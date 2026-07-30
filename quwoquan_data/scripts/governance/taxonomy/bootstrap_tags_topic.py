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

from governance.taxonomy.bootstrap_tags_topic_verticals_part1 import (
    configure_writers as _configure_topic_verticals_part1,
    gen_topic_verticals_part1,
)
from governance.taxonomy.bootstrap_tags_topic_verticals_part2 import (
    configure_writers as _configure_topic_verticals_part2,
    gen_topic_verticals_part2,
)
from governance.taxonomy.bootstrap_tags_topic_photography import (
    configure_writers as _configure_topic_photography,
    gen_photography,
)


def configure_writers(**writers):
    _WRITERS.update(writers)
    _configure_topic_verticals_part1(**writers)
    _configure_topic_verticals_part2(**writers)
    _configure_topic_photography(**writers)

def gen_topic():
    group("Topic", "内容主题", "Topic",
          "描述内容所属的主题领域、地理位置、时间节点、事件/话题与场景氛围",
          [
              "Topic/自然风光", "Topic/历史文化", "Topic/美食餐饮", "Topic/住宿", "Topic/旅行",
              "Topic/时尚穿搭", "Topic/美妆护肤", "Topic/健康养生", "Topic/运动",
              "Topic/科技", "Topic/数码", "Topic/人文社科",
              "Topic/汽车文化", "Topic/家居生活", "Topic/教育成长",
              "Topic/职场效率", "Topic/亲子育儿", "Topic/情感关系", "Topic/影视娱乐",
              "Topic/游戏电竞", "Topic/二次元", "Topic/艺术创作", "Topic/三农生活",
              "Topic/宠物动物", "Topic/金融理财", "Topic/非遗民俗", "Topic/宗教信仰",
              "Topic/命理玄学", "Topic/法律政务", "Topic/公益社会", "Topic/军事国防",
              "Topic/国际视野", "Topic/购物消费", "Topic/摄影",
              "Topic/场景", "Topic/事件", "Topic/话题", "Topic/时间", "Topic/地理",
          ])

    _gen_topic_verticals()
    _gen_topic_事件()
    _gen_topic_话题()
    _gen_topic_场景()
    _gen_topic_时间()
    # 地理/行政区 由 bootstrap_admin_regions.py 生成，此处只生成地理骨架
    _gen_topic_地理_骨架()


def _gen_topic_verticals():
    gen_topic_verticals_part1()
    gen_topic_verticals_part2()
    gen_photography()


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


def _gen_topic_事件():
    tag("Topic/事件", "事件", "Event",
        "具有发生性、进程性和时间节点的现实或线上事件主题")
    tags_list("Topic/事件", [
        ("节庆活动", "Festival Event", "节日庆典、线下活动与主题事件"),
        ("演出赛事", "Performance & Competition", "演唱会、展演、比赛等事件"),
        ("新闻现场", "News Event", "正在发生或已发生的新闻现场事件"),
        ("社会事件", "Social Event", "公共议题、社会关注与公共性事件"),
        ("平台活动", "Platform Campaign", "平台发起的征集、运营与社区活动"),
    ])


def _gen_topic_话题():
    tag("Topic/话题", "话题", "Topic Thread",
        "围绕某个议题持续讨论、参与互动和表达观点的话题主题")
    tags_list("Topic/话题", [
        ("热点讨论", "Trending Discussion", "围绕热点内容展开的讨论"),
        ("经验交流", "Experience Sharing", "围绕经验、攻略与方法的交流话题"),
        ("观点争鸣", "Debate", "观点表达、立场对比与讨论"),
        ("社区接龙", "Community Relay", "接力、挑战、参与式扩散话题"),
        ("问答求助", "Q&A Help", "提问、答疑与求助型话题"),
    ])


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

    # 刻意不再生成 Topic/时间/商业节日 与 Topic/时间/生肖年（共 19 个标签）：
    # 两者都没有采集通道，也没有任何消费方——促销节点由运营活动位表达，生肖年可由
    # capturedAt 直接推算，无需固化成标签。它们只会稀释时间轴的召回权重。


def _gen_topic_地理_骨架():
    dim("Topic/地理", "地理", "Geography",
        "地理维度：行政区与自然地标由 qwq-data taxonomy 生成；本模块生成分类骨架",
        max_depth=5, expected_size=600)
    # 骨架节点只创建维度说明，实际节点由 helper 脚本生成
    tag("Topic/地理/行政区", "行政区", "Administrative Region",
        "行政区划：国家/省/市/区县/街道，完整内容由 qwq-data taxonomy bootstrap-admin-regions 生成")
    tag("Topic/地理/地形地貌", "地形地貌", "Landform",
        "地理科学中的地表形态分类；具体自然地物实例可落入 Entity/地点/自然景观，并由 qwq-data taxonomy bootstrap-geo-landmarks 生成")

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
