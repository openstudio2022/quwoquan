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

    # 7. 职业身份（我的资料页事实型信息；展示 label 可含“/”，tagRef 路径段不含“/”）
    dim("Audience/用户/职业", "职业身份", "Occupation",
        "用户职业与从业方向；我的资料页 V1 只保存二级分类下的叶子职业",
        max_depth=3, path_policy="leaf-only")
    tag("Audience/用户/职业/产品运营", "产品/运营", "Product & Operations",
        "产品、运营、增长、内容与商业化相关职业")
    tags_list("Audience/用户/职业/产品运营", [
        ("产品经理", "Product Manager", "负责产品规划、体验与迭代"),
        ("产品运营", "Product Operations", "负责产品机制运营与增长闭环"),
        ("内容运营", "Content Operations", "负责内容供给、审核与分发运营"),
        ("用户运营", "User Operations", "负责用户增长、留存与社群运营"),
        ("商业化运营", "Monetization Operations", "负责商业化策略与运营"),
    ])
    tag("Audience/用户/职业/研发技术", "研发/技术", "Engineering & Technology",
        "软件、算法、数据、测试与技术基础设施相关职业")
    tags_list("Audience/用户/职业/研发技术", [
        ("前端开发", "Frontend Engineer", "负责 Web、移动端或跨端前端开发"),
        ("后端开发", "Backend Engineer", "负责服务端、接口与业务系统开发"),
        ("客户端开发", "Client Engineer", "负责 iOS、Android 或 Flutter 客户端开发"),
        ("算法工程师", "Algorithm Engineer", "负责机器学习、推荐、搜索或模型算法"),
        ("数据工程师", "Data Engineer", "负责数据管道、数仓与数据基础设施"),
        ("测试工程师", "QA Engineer", "负责质量保障、自动化测试与发布验证"),
    ])
    tag("Audience/用户/职业/设计创意", "设计/创意", "Design & Creative",
        "视觉、体验、品牌、影像与创意内容相关职业")
    tags_list("Audience/用户/职业/设计创意", [
        ("UI设计师", "UI Designer", "负责界面视觉与组件视觉规范"),
        ("UX设计师", "UX Designer", "负责用户体验、流程与交互设计"),
        ("视觉设计师", "Visual Designer", "负责平面、品牌与视觉表达"),
        ("摄影创作者", "Photography Creator", "以摄影为主要创作方向"),
        ("视频创作者", "Video Creator", "以视频拍摄、剪辑或内容制作为主要方向"),
    ])
    tag("Audience/用户/职业/学生", "学生", "Student",
        "在校学习或处于升学、实习阶段的人群")
    tags_list("Audience/用户/职业/学生", [
        ("大学生", "College Student", "本科或专科阶段在校学生"),
        ("研究生", "Graduate Student", "硕士或博士阶段在校学生"),
        ("高中生", "High School Student", "高中阶段在校学生"),
        ("留学生", "International Student", "海外学习或交换阶段学生"),
        ("实习生", "Intern", "处于实习或校招过渡阶段"),
    ])
    tag("Audience/用户/职业/自由职业", "自由职业", "Freelance",
        "独立接单、个体经营、灵活就业或创业阶段职业")
    tags_list("Audience/用户/职业/自由职业", [
        ("自由职业者", "Freelancer", "独立接单或灵活就业"),
        ("个体经营者", "Self-employed", "个体工商户或小型经营者"),
        ("创业者", "Founder", "正在创业或经营早期项目"),
        ("独立咨询顾问", "Independent Consultant", "以咨询顾问形式提供专业服务"),
        ("独立创作者", "Independent Creator", "以内容或作品创作为主要收入来源"),
    ])

    # 8. 兴趣偏好（我的资料页声明型兴趣；用于推荐、交集、小趣偏好理解）
    dim("Audience/用户/兴趣偏好", "兴趣偏好", "Interest Preferences",
        "用户在资料页主动声明的兴趣标签，独立于内容 Topic，供推荐、交集和助手画像使用",
        max_depth=3, path_policy="leaf-only")
    tag("Audience/用户/兴趣偏好/旅行摄影", "旅行摄影", "Travel & Photography",
        "旅行、摄影、城市探索与户外影像兴趣")
    tags_list("Audience/用户/兴趣偏好/旅行摄影", [
        ("旅行", "Travel", "喜欢旅行与目的地探索"),
        ("摄影", "Photography", "喜欢摄影创作与影像表达"),
        ("城市漫游", "City Walk", "喜欢城市漫步与街区探索"),
        ("风光影像", "Landscape Imagery", "喜欢自然与城市风光拍摄"),
        ("街拍", "Street Photography", "喜欢街头观察与街拍"),
        ("胶片", "Film Photography", "喜欢胶片摄影与复古影像"),
        ("人像", "Portrait", "喜欢人像拍摄与人物表达"),
        ("海岛", "Island", "喜欢海岛旅行与滨海风景"),
        ("雪山", "Snow Mountain", "喜欢雪山、高原与山地景观"),
        ("古镇", "Ancient Town", "喜欢古镇、老街与历史街区"),
        ("自驾", "Self-driving", "喜欢自驾出行"),
        ("徒步", "Hiking", "喜欢徒步、山野与户外路线"),
    ])
    tag("Audience/用户/兴趣偏好/校园", "校园", "Campus",
        "校园生活、校友关系、学习成长与社团兴趣")
    tags_list("Audience/用户/兴趣偏好/校园", [
        ("校园生活", "Campus Life", "关注校园日常与学生生活"),
        ("图书馆", "Library", "喜欢图书馆、自习与学习空间"),
        ("社团", "Student Club", "关注社团活动与兴趣组织"),
        ("校友", "Alumni", "关注校友关系与同校连接"),
        ("校园摄影", "Campus Photography", "喜欢校园影像与校园记录"),
        ("实习", "Internship", "关注实习、校招与职业准备"),
        ("考研", "Postgraduate Exam", "关注考研与升学准备"),
        ("课程", "Courses", "关注课程学习与选课经验"),
        ("毕业季", "Graduation Season", "关注毕业记录与毕业季活动"),
        ("宿舍生活", "Dorm Life", "关注宿舍、同学与校园居住生活"),
    ])
    tag("Audience/用户/兴趣偏好/生活", "生活", "Lifestyle",
        "日常生活、美食、阅读、空间与个人风格兴趣")
    tags_list("Audience/用户/兴趣偏好/生活", [
        ("美食", "Food", "喜欢美食探店与日常餐饮"),
        ("咖啡", "Coffee", "喜欢咖啡馆、咖啡饮品与咖啡文化"),
        ("阅读", "Reading", "喜欢阅读、书单与读书空间"),
        ("书店", "Bookstore", "喜欢书店、独立书店与城市文化空间"),
        ("宠物", "Pets", "喜欢宠物陪伴与宠物生活"),
        ("穿搭", "Outfit", "关注穿搭、风格与日常造型"),
        ("家居", "Home", "关注家居布置、收纳与生活空间"),
    ])
    tag("Audience/用户/兴趣偏好/艺术", "艺术", "Arts",
        "艺术、设计、展览、建筑、电影、音乐与手作兴趣")
    tags_list("Audience/用户/兴趣偏好/艺术", [
        ("设计", "Design", "关注设计、审美与创意表达"),
        ("绘画", "Painting", "喜欢绘画、插画与艺术创作"),
        ("展览", "Exhibition", "喜欢看展与艺术活动"),
        ("博物馆", "Museum", "喜欢博物馆、文博与展陈空间"),
        ("建筑", "Architecture", "关注建筑、空间与城市风貌"),
        ("电影", "Movie", "喜欢电影、影评与观影记录"),
        ("音乐", "Music", "喜欢音乐、歌单、演出与乐器"),
        ("手作", "Handcraft", "喜欢手工、DIY 与创意制作"),
    ])
    tag("Audience/用户/兴趣偏好/科技", "科技", "Technology",
        "科技、AI、数码、编程、产品与创业兴趣")
    tags_list("Audience/用户/兴趣偏好/科技", [
        ("科技", "Technology", "关注科技产业与技术趋势"),
        ("AI", "AI", "关注人工智能、模型与智能工具"),
        ("数码", "Gadgets", "喜欢数码产品、设备与体验"),
        ("编程", "Programming", "喜欢编程、开发与技术实践"),
        ("产品", "Product", "关注产品设计、产品体验与产品方法"),
        ("创业", "Startup", "关注创业、商业模式与早期项目"),
        ("机器人", "Robotics", "关注机器人、自动化与智能硬件"),
        ("智能汽车", "Smart Auto", "关注智能汽车、新能源与车载科技"),
    ])

    # 9. 收入
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
