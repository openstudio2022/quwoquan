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

def gen_topic_verticals_part2():
    # 5. 时尚穿搭（风格 / 场景 / 单品 / 搭配方法）
    tag("Topic/时尚穿搭", "时尚穿搭", "Fashion & Style", "服饰穿搭与时尚潮流内容")
    tags_list("Topic/时尚穿搭", [
        ("日常穿搭", "Daily Outfit", "日常生活服装搭配"),
        ("职场穿搭", "Office Outfit", "职场正式商务着装"),
        ("通勤穿搭", "Commute Outfit", "通勤上班场景穿搭"),
        ("户外穿搭", "Outdoor Outfit", "户外运动功能性着装"),
        ("旅行穿搭", "Travel Outfit", "旅行出游场景穿搭"),
        ("约会穿搭", "Date Outfit", "约会浪漫风格着装"),
        ("婚礼穿搭", "Wedding Outfit", "婚礼与庆典着装"),
        ("宴会穿搭", "Banquet Outfit", "宴会与正式场合着装"),
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

    # 6. 美妆护肤（护肤 / 彩妆 / 造型修饰 / 工具与产品）
    tag("Topic/美妆护肤", "美妆护肤", "Beauty & Skincare", "美妆护肤化妆品相关内容")
    tags_list("Topic/美妆护肤", [
        ("护肤流程", "Skincare Routine", "日常护肤步骤与流程"),
        ("防晒", "Sunscreen", "防晒与紫外线防护"),
        ("底妆", "Base Makeup", "粉底遮瑕等底妆技巧"),
        ("眼妆", "Eye Makeup", "眼影眼线睫毛膏等眼妆"),
        ("眼霜", "Eye Cream", "眼周护理与眼霜"),
        ("唇妆", "Lip Makeup", "口红唇釉唇线笔"),
        ("彩妆教程", "Makeup Tutorial", "全套彩妆教学"),
        ("仿妆", "Cosplay Makeup", "明星仿妆角色仿妆"),
        ("医美抗衰", "Medical Beauty", "医美项目与抗老护肤"),
        ("面膜", "Mask Care", "面膜与密集护理"),
        ("精华", "Serum", "精华液与功效型护理"),
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

    # 8. 运动（休闲健身 / 户外探险 / 竞技体育 / 极限运动；电竞赛事后续拆出独立主轴）
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

    # 9. 科技（行业趋势 / 公司 / 新技术）
    tag("Topic/科技", "科技", "Tech",
        "行业趋势、公司动态、新技术与科技政策内容")
    tags_list("Topic/科技", [
        ("AI技术", "AI Technology", "人工智能应用与前沿进展"),
        ("机器人", "Robotics", "机器人技术与应用"),
        ("半导体芯片", "Semiconductor", "芯片、半导体与硬件底座"),
        ("新能源", "New Energy", "电动车、储能与能源转型"),
        ("智能家居", "Smart Home", "智能家居与物联网生活"),
        ("编程开发", "Programming", "编程、工程实践与技术学习"),
        ("软件应用", "Software & Apps", "软件产品、工具与应用生态"),
        ("科学探索", "Science Exploration", "基础科学与前沿探索"),
    ])

    # 9b. 数码（消费电子 / 影像 / 器材）
    tag("Topic/数码", "数码", "Digital Devices",
        "消费电子、影像器材、无人机与电子产品内容")
    tags_list("Topic/数码", [
        ("手机测评", "Smartphone Review", "手机性能测评与使用体验"),
        ("电脑测评", "Computer Review", "笔记本台式机测评"),
        ("影像", "Imaging", "相机摄像机与影像器材内容"),
        ("无人机", "Drone", "无人机使用、航拍与器材测评"),
        ("游戏硬件", "Gaming Hardware", "游戏设备、外设与性能测评"),
        ("智能穿戴", "Wearables", "智能手表、手环与可穿戴设备"),
        ("耳机音频", "Audio Gear", "耳机、音箱与音频器材"),
        ("数码配件", "Accessories", "数码配件与周边装备"),
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

    # 31. 摄影（题材社区 / 知识方法 / 活动赛事；对标 500px/图虫/Flickr 等平台频道）
    tag("Topic/摄影", "摄影", "Photography",
        "摄影创作与摄影文化内容：按题材流派形成的社区频道 + 摄影知识与器材内容")
    tags_list("Topic/摄影", [
        ("风光摄影", "Landscape Photography", "以自然风景为主题的摄影创作"),
        ("人像摄影", "Portrait Photography", "以人物肖像为主题的摄影创作"),
        ("儿童摄影", "Children Photography", "以儿童与亲子为主题的摄影创作"),
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



