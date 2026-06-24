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
        ("择园攻略", "Kindergarten Selection Guide", "幼儿园择园与入园准备"),
        ("幼小衔接", "Preschool-Primary Transition", "从幼儿园到小学的衔接准备"),
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

