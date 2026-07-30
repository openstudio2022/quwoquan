"""Topic/摄影 生成器。

两部分职责不同，不要混：

1. **题材流派**（`风光摄影`/`人像摄影`/…）是社区频道，由创作者选择或运营归类，
   采集通道是 `creator_chip`。对标 500px / 图虫 / Flickr 的频道划分。
2. **器材 / 拍摄参数 / 光线条件**是从 EXIF 直接派生的客观事实，采集通道是 `exif`，
   创作者不需要也不应该手填。这三个维度是差异化的地基：携程/去哪儿有 POI 但没有照片
   元数据，图虫/500px 有 EXIF 但没有实体图谱与社交交集。

每个 EXIF 派生标签的 description 都写清它绑定的 EXIF 字段与阈值，端侧
`CapturePhotographyTagDeriver` 必须与这里的阈值逐条对齐——阈值是产品口径，不是实现
细节，写在两处任何一处漂移都会让「同一张照片在不同版本打出不同标签」。

刻意不建 `Topic/摄影/后期流派`：后期风格的真相源是 `Format/视觉风格/后期风格`，
它已经是同一现实概念在 Format 轴上的完整表达。在 Topic 轴再建一棵只会让同一概念有
两个可写入位置，且 Topic 侧没有任何采集通道能填它。
"""

from __future__ import annotations

_WRITERS: dict = {}

EXIF = "exif"
EXIF_CONSUMERS = ["recall", "scorer", "intersection"]
CHIP = "creator_chip"
CHIP_CONSUMERS = ["recall", "scorer", "intersection", "search_facet"]


def configure_writers(**writers):
    _WRITERS.update(writers)


def _tag(*args, **kwargs):
    return _WRITERS["tag"](*args, **kwargs)


def _tags_list(*args, **kwargs):
    return _WRITERS["tags_list"](*args, **kwargs)


def gen_photography():
    _gen_genres()
    _gen_gear()
    _gen_parameters()
    _gen_light()


def _gen_genres():
    _tag("Topic/摄影", "摄影", "Photography",
         "摄影创作与摄影文化内容：按题材流派形成的社区频道 + 摄影知识与器材内容")
    _tags_list("Topic/摄影", [
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
    ], collection_channel=CHIP, consumed_by=CHIP_CONSUMERS)


def _gen_gear():
    """器材：来自 EXIF 的 cameraMake / cameraModel / lensModel / focalLengthMm。

    机身按「器材类别」而非具体型号建标签：型号是实体（`Entity/商品/类目/数码电子`
    的下游），标签只表达类别，否则标签树会被每年的新机型无限撑大。具体型号走
    `sameGearUsed` 交集，直接比对 `cameraModel` 字符串，不需要标签。
    """
    _tag("Topic/摄影/器材", "器材", "Gear",
         "拍摄所用器材类别，全部由 EXIF 的 cameraMake/cameraModel/lensModel 派生",
         collection_channel=EXIF, consumed_by=EXIF_CONSUMERS)

    _tag("Topic/摄影/器材/机身类型", "机身类型", "Camera Body Type",
         "由 cameraMake + cameraModel 归类的机身类别",
         collection_channel=EXIF, consumed_by=EXIF_CONSUMERS)
    _tags_list("Topic/摄影/器材/机身类型", [
        ("全画幅微单", "Full-frame Mirrorless", "cameraModel 命中全画幅无反机型表"),
        ("半画幅微单", "APS-C Mirrorless", "cameraModel 命中 APS-C 无反机型表"),
        ("中画幅", "Medium Format", "cameraModel 命中中画幅机型表"),
        ("单反相机", "DSLR", "cameraModel 命中单反机型表"),
        ("手机拍摄", "Smartphone", "cameraMake 命中手机厂商表"),
        ("运动相机", "Action Camera", "cameraMake/cameraModel 命中 GoPro/Insta360 等"),
        ("无人机航拍", "Drone", "cameraMake 命中 DJI/Autel 等无人机厂商"),
        ("胶片扫描", "Film Scan", "无 cameraModel 但有扫描仪标识，或机型命中胶片机表"),
    ], collection_channel=EXIF, consumed_by=EXIF_CONSUMERS)

    _tag("Topic/摄影/器材/镜头类型", "镜头类型", "Lens Type",
         "由 lensModel 文本特征判定的镜头类别",
         collection_channel=EXIF, consumed_by=EXIF_CONSUMERS)
    _tags_list("Topic/摄影/器材/镜头类型", [
        ("定焦镜头", "Prime Lens", "lensModel 只含单一焦距值"),
        ("变焦镜头", "Zoom Lens", "lensModel 含焦距区间"),
        ("微距镜头", "Macro Lens", "lensModel 含 Macro/微距 标识"),
        ("鱼眼镜头", "Fisheye Lens", "lensModel 含 Fisheye/鱼眼 标识"),
        ("移轴镜头", "Tilt-shift Lens", "lensModel 含 TS-E/PC-E/移轴 标识"),
    ], collection_channel=EXIF, consumed_by=EXIF_CONSUMERS)


def _gen_parameters():
    """拍摄参数：来自 EXIF 的 shutterSpeedSeconds / apertureFNumber / isoSensitivity。

    阈值取摄影社区的通行口径，且刻意留出中间地带不打标——「不确定就不打」比「所有
    照片都被打上某个参数标签」有用，后者会让这一维度在召回里失去区分度。
    """
    _tag("Topic/摄影/拍摄参数", "拍摄参数", "Exposure Parameters",
         "曝光三要素派生的拍摄手法标签，全部由 EXIF 阈值判定",
         collection_channel=EXIF, consumed_by=EXIF_CONSUMERS)

    # 焦段挂在拍摄参数而不是器材：`focalLengthMm` 属 `parameters` 披露组，而机身/镜头
    # 属 `gear` 组。让路径分组与披露分组一一对应，「关闭某组 → 该子树整体消失」才是一条
    # 可断言的不变量，否则关掉器材开关后 Topic/摄影/器材/** 下还残留焦段标签。
    _tag("Topic/摄影/拍摄参数/焦段", "焦段", "Focal Length Range",
         "由 focalLengthMm 归入的焦段区间（未做等效换算时按 EXIF 原值）",
         collection_channel=EXIF, consumed_by=EXIF_CONSUMERS)
    _tags_list("Topic/摄影/拍摄参数/焦段", [
        ("超广角", "Ultra Wide", "focalLengthMm < 20"),
        ("广角", "Wide", "20 <= focalLengthMm < 35"),
        ("标准", "Standard", "35 <= focalLengthMm < 70"),
        ("中长焦", "Short Telephoto", "70 <= focalLengthMm < 135"),
        ("长焦", "Telephoto", "135 <= focalLengthMm < 300"),
        ("超长焦", "Super Telephoto", "focalLengthMm >= 300"),
    ], collection_channel=EXIF, consumed_by=EXIF_CONSUMERS)

    _tag("Topic/摄影/拍摄参数/快门", "快门", "Shutter",
         "由 shutterSpeedSeconds 判定的快门手法",
         collection_channel=EXIF, consumed_by=EXIF_CONSUMERS)
    _tags_list("Topic/摄影/拍摄参数/快门", [
        ("长曝光", "Long Exposure", "shutterSpeedSeconds >= 1"),
        ("慢门", "Slow Shutter", "1/15 <= shutterSpeedSeconds < 1"),
        ("高速快门", "Fast Shutter", "shutterSpeedSeconds <= 1/1000"),
    ], collection_channel=EXIF, consumed_by=EXIF_CONSUMERS)

    _tag("Topic/摄影/拍摄参数/光圈", "光圈", "Aperture",
         "由 apertureFNumber 判定的景深手法",
         collection_channel=EXIF, consumed_by=EXIF_CONSUMERS)
    _tags_list("Topic/摄影/拍摄参数/光圈", [
        ("大光圈虚化", "Wide Aperture Bokeh", "apertureFNumber <= 2.0"),
        ("小光圈全景深", "Narrow Aperture Deep Focus", "apertureFNumber >= 11"),
    ], collection_channel=EXIF, consumed_by=EXIF_CONSUMERS)

    _tag("Topic/摄影/拍摄参数/感光度", "感光度", "ISO",
         "由 isoSensitivity 判定的感光度区间",
         collection_channel=EXIF, consumed_by=EXIF_CONSUMERS)
    _tags_list("Topic/摄影/拍摄参数/感光度", [
        ("高感夜拍", "High ISO", "isoSensitivity >= 3200"),
        ("低感画质", "Low ISO", "isoSensitivity <= 200"),
    ], collection_channel=EXIF, consumed_by=EXIF_CONSUMERS)


def _gen_light():
    """光线条件：capturedAt + GPS 经纬度推算太阳高度角后判定。

    这一维度是「(实体/机位) × (时间窗口) × (器材/参数)」三元组里的时间窗口面，也是
    `sameSeasonWindow` / `samePhotoSpot` 交集能给出可解释理由的依据：两个人在同一机位
    的同一光线条件下拍过，比「都看过这个页面」强得多。

    GPS 被创作者关闭（place 组关闭）时降级为按本地时间粗判昼夜，不再产出金色/蓝调
    时刻——这两个标签依赖日出日落时刻，没有坐标算不出来，宁可不打。
    """
    _tag("Topic/摄影/光线条件", "光线条件", "Lighting Condition",
         "由 capturedAt 与 GPS 推算太阳高度角判定的光线窗口",
         collection_channel=EXIF, consumed_by=EXIF_CONSUMERS)
    _tags_list("Topic/摄影/光线条件", [
        ("蓝调时刻", "Blue Hour", "日出前或日落后，太阳高度角在 -6° 与 -4° 之间"),
        ("金色时刻", "Golden Hour", "太阳高度角在 -4° 与 6° 之间"),
        ("正午强光", "Harsh Midday Light", "太阳高度角 > 60°"),
        ("夜间无日光", "Night", "太阳高度角 < -6°"),
        ("白天漫射光", "Daylight", "太阳高度角在 6° 与 60° 之间"),
    ], collection_channel=EXIF, consumed_by=EXIF_CONSUMERS)
