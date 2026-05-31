"""Lightweight deterministic dispatch for common user instructions."""
from __future__ import annotations

from template.router import RouteRequest


# 地域/季节关键词 -> catalog key（条件修饰维，不参与选模板）。
REGION_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("高原", "川西", "西藏", "青藏", "藏区", "高海拔"), "高原"),
    (("雪山", "登山", "高山"), "雪山"),
    (("海岛", "海边", "沿海", "海滨", "跳岛"), "沿海海岛"),
    (("沙漠", "戈壁", "雅丹", "胡杨"), "沙漠戈壁"),
    (("雨林", "热带", "秘境"), "雨林秘境"),
    (("山地", "森林", "林海"), "山地森林"),
    (("城市", "都市", "citywalk", "城市漫步", "街区"), "平原都市"),
    (("乡村", "田园", "村落", "梯田"), "乡村田园"),
]

SEASON_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("雨季",), "雨季"),
    (("旱季",), "旱季"),
    (("旺季",), "旺季"),
    (("淡季",), "淡季"),
    (("春季", "春天", "踏青", "花期"), "春"),
    (("夏季", "夏天", "避暑", "暑期"), "夏"),
    (("秋季", "秋天", "红叶", "彩林"), "秋"),
    (("冬季", "冬天", "冰雪", "滑雪", "雪景"), "冬"),
]


def detect_region(instruction: str) -> str | None:
    text = instruction.lower()
    for keywords, region in REGION_KEYWORDS:
        if any(k.lower() in text for k in keywords):
            return region
    return None


def detect_season(instruction: str) -> str | None:
    text = instruction.lower()
    for keywords, season in SEASON_KEYWORDS:
        if any(k.lower() in text for k in keywords):
            return season
    return None


def dispatch_instruction(instruction: str, *, default_vertical: str = "travel") -> RouteRequest:
    text = instruction.lower()
    region = detect_region(instruction)
    season = detect_season(instruction)
    vertical = "campus" if any(k in instruction for k in ["学校", "校园", "新生", "考研", "选课"]) else default_vertical
    if vertical == "campus":
        subject_kind = "entity"
        subject_type = "机构/学校"
        audience = "freshmanStudent" if "新生" in instruction else None
        if "评测" in instruction or "测评" in instruction:
            intent = "校园评测"
        elif "选课" in instruction:
            intent = "选课攻略"
        elif "考研" in instruction:
            intent = "考研经验"
        elif "家长" in instruction or "择校" in instruction:
            intent = "攻略"
            audience = "campusParent"
        else:
            intent = "新生攻略" if audience else "体验"
        # 校园域当前不消费地域/季节，保持透传但不强加
        return RouteRequest(vertical, subject_kind, subject_type, intent, audience)

    subject_kind = "topic" if any(k in instruction for k in ["线路", "环线", "自驾", "榜单", "画报", "地理", "机位", "跟团", "周末", "深度", "徒步", "穿越"]) else "entity"
    subject_type = "旅行/线路" if subject_kind == "topic" else "地点/景区"
    audience = None
    if "自驾" in instruction:
        audience = "selfDriveTraveler"
    elif any(k in instruction for k in ["跟团", "报团", "旅行团"]):
        audience = "groupTourTraveler"
    elif any(k in instruction for k in ["周末", "2天1夜", "两日", "当日往返"]):
        audience = "weekendLocalTraveler"
    elif any(k in instruction for k in ["北京", "上海", "深圳", "外地", "飞成都", "高铁到成都", "入川"]):
        audience = "hubInboundTraveler"
    elif any(k in instruction for k in ["徒步", "穿越", "探险", "秘境", "深度游", "双周"]):
        audience = "selfDriveTraveler"
    if "画报" in instruction or "美图" in instruction or "图集" in instruction:
        subject_type = "旅行/主题" if subject_kind == "topic" else subject_type
        intent = "美图"
    elif "地理" in instruction or "深读" in instruction:
        subject_type = "旅行/主题"
        intent = "深度报道"
    elif "机位" in instruction or "摄影" in instruction:
        subject_type = "旅行/主题"
        intent = "科普"
        audience = "photoTraveler"
    elif "避险" in instruction or "补给" in instruction:
        subject_type = "旅行/线路"
        intent = "行前指南"
    elif any(k in instruction for k in ["跟团", "报团", "旅行团"]):
        subject_type = "旅行/线路"
        intent = "跟团指南"
    elif any(k in instruction for k in ["徒步", "穿越", "探险", "秘境"]) and any(k in instruction for k in ["深度", "双周", "洛克", "格聂"]):
        subject_type = "旅行/线路"
        intent = "深度探险"
    elif any(k in instruction for k in ["周末", "2天1夜", "两日游"]):
        subject_type = "旅行/线路"
        intent = "攻略"
    elif any(k in instruction for k in ["北京", "上海", "深圳", "外地", "飞成都", "高铁到成都"]):
        subject_type = "旅行/线路"
        intent = "攻略"
    elif "榜单" in instruction or "top" in text:
        subject_type = "旅行/榜单"
        intent = "盘点"
    elif "游记" in instruction:
        subject_type = "旅行/主题"
        intent = "叙事"
    elif "自驾" in instruction or "线路" in instruction or "路书" in instruction:
        subject_type = "旅行/线路"
        intent = "路线推荐"
    else:
        intent = "攻略"
    return RouteRequest(vertical, subject_kind, subject_type, intent, audience, region=region, season=season)
