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


def gen_topic_technology_learning():
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
