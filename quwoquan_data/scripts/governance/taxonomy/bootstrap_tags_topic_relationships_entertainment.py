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


def gen_topic_relationships_entertainment():
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
        # 「幼小衔接」的唯一真相源是 Topic/教育成长/基础教育（学段而非育儿话题，R14）。
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
