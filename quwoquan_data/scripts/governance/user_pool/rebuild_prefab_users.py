"""Rebuild prefab users and travel-photo creator profiles with compact IDs."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import yaml

from _common.creator_pool.batch_policy import (
    CANONICAL_BATCH_ID,
    default_target_for_batch,
    expected_view_contract,
    uses_dual_view_policy,
    view_counts_from_segments,
)
from _common.creator_pool.constants import PHOTOGRAPHY_TOPIC_REFS, TRAVEL_TOPIC_REFS
from _common.creator_pool.io import artifacts_readiness_path
from _common.io import read_json, write_json, write_ndjson
from _common.paths import PUBLISH_ROOT, REPO_ROOT, SERVICE_CONTRACTS_METADATA_ROOT, now_iso
from governance.user_pool.media_presets import (
    PRESET_ROOT,
    SERVICE_MEDIA_ROOT,
    build_preset_manifest,
    run_media_presets_build,
)

TRAVEL_PHOTO_BATCH = CANONICAL_BATCH_ID
PUBLISHED_INTEREST_TAGS = frozenset((*TRAVEL_TOPIC_REFS, *PHOTOGRAPHY_TOPIC_REFS))
FORBIDDEN_PROFILE_TOKENS = (
    "华南",
    "华北",
    "华东",
    "华中",
    "西南",
    "西北",
    "东北",
    "中国",
    "区域",
    "大区",
    "公开平台信号",
    "衍生",
    "persona",
    "archetype",
    "travel_photo",
    "batch",
)
SYS_USER_ID_RE = re.compile(r"^sys_(travel|photo|travelphoto)_[0-9]{4}$")
SYS_SUB_ID_RE = re.compile(r"^sys_(travel|photo|travelphoto)_[0-9]{4}_sub_[0-9]{2}$")

SERVICE_FIXTURES = SERVICE_CONTRACTS_METADATA_ROOT / "_shared" / "test_fixtures"
CREATOR_FIXTURES = SERVICE_FIXTURES / "creator_pool"
PROFILE_ROOT = REPO_ROOT / "quwoquan_data" / "templates" / "creator_profiles" / "travel"

NAME_A = (
    "海盐",
    "南风",
    "暮色",
    "行李",
    "半坡",
    "青柠",
    "白露",
    "山野",
    "晴窗",
    "松间",
    "野餐",
    "月台",
    "橙光",
    "云片",
    "石阶",
    "风铃",
    "蓝调",
    "旧巷",
    "微光",
    "远帆",
    "浅草",
    "银盐",
    "木棉",
    "灯塔",
    "薄荷",
    "晚晴",
    "星轨",
    "纸飞机",
    "小径",
    "雨停",
    "镜湖",
    "日落",
    "露台",
    "北窗",
    "暖树",
    "慢门",
    "雾灯",
    "竹影",
    "光盒",
    "片场",
)
NAME_B = (
    "相机",
    "胶片",
    "取景",
    "镜头",
    "游记",
    "路书",
    "画册",
    "光线",
    "快门",
    "背包",
    "手账",
    "暗房",
    "片刻",
    "小站",
    "长卷",
    "观景",
    "焦点",
    "构图",
    "足迹",
    "旅笺",
    "光谱",
    "影集",
    "底片",
    "坐标",
    "短诗",
    "清单",
    "风景",
    "路标",
    "明信片",
    "日记",
    "旅灯",
    "远山",
    "慢拍",
    "小路",
    "光影",
    "行路",
    "看见",
)
HANDLE_A = (
    "salt",
    "southwind",
    "dusk",
    "luggage",
    "slope",
    "lime",
    "dew",
    "trail",
    "sunny",
    "pine",
    "picnic",
    "platform",
    "orange",
    "cloud",
    "stone",
    "bell",
    "blue",
    "alley",
    "glow",
    "sail",
    "grass",
    "silver",
    "cotton",
    "beacon",
    "mint",
    "clear",
    "star",
    "paper",
    "path",
    "afterrain",
    "lake",
    "sunset",
    "terrace",
    "window",
    "warmtree",
    "slowshutter",
    "foglamp",
    "bamboo",
    "lightbox",
    "set",
)
HANDLE_B = (
    "camera",
    "film",
    "frame",
    "lens",
    "notes",
    "route",
    "album",
    "light",
    "shutter",
    "pack",
    "journal",
    "darkroom",
    "moment",
    "station",
    "scroll",
    "view",
    "focus",
    "compose",
    "steps",
    "letter",
    "spectrum",
    "gallery",
    "negative",
    "marker",
    "poem",
    "list",
    "scene",
    "sign",
    "postcard",
    "diary",
    "travelight",
    "farhill",
    "slowshot",
    "smallroad",
    "lightshape",
    "walkpath",
    "seen",
)

TOPIC_DEFAULTS = {
    "travel": ["Topic/旅行/玩法/摄影旅拍"],
    "photography": ["Topic/摄影/旅行摄影"],
}

PROFILE_WORDS = {
    "travel_primary": {
        "scene": ("雨后街角", "夜车窗边", "旧城台阶", "山路转弯", "海边长椅", "渡口清晨", "林间小站", "集市入口", "湖边露台", "风口栈道", "寺前石阶", "码头黄昏"),
        "object": ("路书", "手账", "车票", "地图", "清单", "行李牌", "船票", "雨衣", "水壶", "窗景", "站牌", "便签"),
        "care": ("体力", "回程", "预算", "天气", "休息", "绕路", "停留", "转乘", "小店", "脚步", "余地", "好奇心"),
        "mood": ("从容", "不慌", "松弛", "清醒", "耐心", "轻快", "笃定", "自在", "温柔", "有余地"),
        "detail": ("一顿早饭", "一段坡路", "一班慢车", "一处背街", "一场小雨", "一页地图", "一个路口", "一盏晚灯", "一阵海风", "一次停留"),
    },
    "photography_primary": {
        "scene": ("窗边逆光", "蓝调时刻", "街角阴影", "展厅白墙", "雨夜反光", "暗房红灯", "晨雾边缘", "屋檐高光", "旧楼楼梯", "海面微光", "厨房静物", "天台风声"),
        "object": ("快门", "构图", "焦点", "边框", "留白", "胶片", "镜头", "画面", "颗粒", "色温", "暗部", "高光"),
        "care": ("层次", "秩序", "情绪", "质感", "呼吸", "主题", "比例", "节奏", "光比", "色彩", "距离", "现场感"),
        "mood": ("克制", "安静", "诚实", "耐看", "柔软", "锐利", "轻盈", "沉稳", "干净", "有余温"),
        "detail": ("一束侧光", "一格底片", "一面白墙", "一段阴影", "一张试拍", "一条边线", "一处反光", "一次等待", "一只旧镜头", "一张样片"),
    },
    "travel_photography_cross": {
        "scene": ("雪线山口", "海岸公路", "旧城天台", "雨街霓虹", "寺前石阶", "渡口清晨", "湖边蓝调", "峡谷风口", "火车窗边", "梯田日落", "灯塔海风", "夜市转角"),
        "object": ("机位", "路线", "坐标", "脚步", "路标", "天气", "返程", "地图", "镜头", "快门", "背包", "取景框"),
        "care": ("光线", "抵达", "现场", "时间", "方向", "停留", "判断", "节奏", "构图", "风声", "色彩", "距离"),
        "mood": ("带着光", "不赶路", "有画面", "留住风", "能回看", "够真实", "慢慢亮", "像在场", "有方向", "不空泛"),
        "detail": ("一个机位", "一段小路", "一束斜光", "一张路牌", "一场云影", "一次等光", "一页路书", "一处前景", "一班慢车", "一阵山风"),
    },
}

SLOGAN_PATTERNS = {
    "travel_primary": (
        "少赶路，多看{scene}",
        "{scene}值得慢一点",
        "先想回程，再谈远方",
        "好路线也要会休息",
        "给{care}留一点空白",
        "不把出发写成任务",
        "绕路有时比捷径好",
        "{object}里放一份{mood}",
        "真正好玩不靠赶场",
        "{detail}也算目的地",
        "走得慢，才记得住",
        "把难走的路说清楚",
        "我喜欢慢慢抵达",
        "出门也要照顾自己",
        "{scene}不是打卡点",
        "路线之外，还有心情",
        "把麻烦提前写明白",
        "留半天给临时起意",
        "不赶场，也能看很远",
        "{care}比清单更重要",
        "让旅程有回头路",
        "好攻略该让人安心",
        "先把脚步放轻一点",
        "在{scene}学会停下",
        "{object}里也藏着{care}",
        "偶尔绕远，反而更近",
        "比起景点，更记得{detail}",
        "旅途不必每分钟有用",
        "每站都该有喘息",
        "小路也有自己的答案",
        "我替你试试好不好走",
        "把远方拆成今天能走",
        "路书要诚实，也要温柔",
        "不完美的路更像旅行",
        "给下一站留一点力气",
        "有些风景适合晚点到",
        "把{care}写进出发前",
        "一趟路要有可退可进",
        "别急着抵达全部地方",
        "好玩之前，先好走",
    ),
    "photography_primary": (
        "先等光，再按快门",
        "{scene}会替照片说话",
        "照片先诚实，再好看",
        "别替照片安排答案",
        "别让滤镜盖住情绪",
        "别只盯参数，也看呼吸",
        "好照片不急着解释",
        "小细节能撑起一组图",
        "拍清楚，比拍热闹难",
        "别用{object}交代全部{care}",
        "少一点满，多一点想象",
        "我相信安静的画面",
        "让暗部也有故事",
        "构图不是把世界摆正",
        "{scene}适合慢慢看",
        "快门之前先问为什么",
        "照片要有留下来的理由",
        "{object}要服务于情绪",
        "不追热闹，追耐看",
        "画面干净，心就会近",
        "每张图都留一口气",
        "我喜欢有余温的光",
        "{detail}会慢慢带出{care}",
        "一组图要有停顿",
        "宁愿少拍，也要看准",
        "{detail}比参数更动人",
        "好色彩不是越满越好",
        "留白不是空，是等待",
        "在边框里保留现场",
        "照片别太会表演",
        "把光放在该在的位置",
        "按下去之前先看一眼",
        "质感来自克制的选择",
        "我给日常留一束光",
        "让瞬间有自己的重量",
        "画面要稳，情绪要活",
        "别怕阴影，它也在说话",
        "好照片会慢慢回响",
        "看见细节，也放过细节",
        "镜头近一点，心慢一点",
    ),
    "travel_photography_cross": (
        "先找光，再决定往哪走",
        "{scene}要拍，也要走懂",
        "机位之外，也写抵达",
        "一张照片也要知道来路",
        "{detail}值得等一等",
        "路线有风，照片有声",
        "走到现场，再谈构图",
        "我用{object}给旅途留证据",
        "不只出片，也要在场",
        "让照片带着脚步回来",
        "好机位不该只剩坐标",
        "{care}对了，路就亮了",
        "把远方拍得可以回看",
        "路书里也要有光",
        "先看天气，再等情绪",
        "{scene}不是背景，是主角",
        "拍之前先走一段路",
        "每个坐标都要有故事",
        "风景要美，也要能到",
        "把现场感留在图文里",
        "我把路线拍成记忆",
        "镜头负责看，脚步负责信",
        "照片替我记住风向",
        "不是打卡，是带回现场",
        "{detail}替{object}多说一句",
        "走得够近，画面才真",
        "等光的时候也在旅行",
        "好照片要有路的重量",
        "把目的地拍成可走的路",
        "一半给路线，一半给光",
        "机位清楚，故事才落地",
        "我喜欢边走边判断",
        "{detail}会告诉我怎么拍",
        "照片里要有抵达的声音",
        "用图文把风景讲慢一点",
        "先到达，再取景",
        "让{care}成为画面的路标",
        "每次出发都带着取景框",
        "不赶景点，只追一束光",
        "把旅途拍得有人味",
    ),
}

BIO_PATTERNS = {
    "travel_primary": (
        "偏爱{scene}和{care}，常把路线、花费和体力安排写成可执行的出门笔记。",
        "习惯从{detail}开始记录，喜欢讲清楚怎么到、值不值、要不要多停。",
        "不追赶场式旅行，更在意{care}、补给和留白，内容写给准备出发的人。",
        "常整理{object}、路线取舍和现场体验，希望复杂行程看完就能走。",
        "喜欢慢慢走，也会诚实写下绕路和失误；比起种草，更想让人少踩坑。",
        "记录旅行里的小判断：何时出发、在哪里停、哪些地方值得留白。",
        "关注路线节奏和真实体感，写作风格偏清楚、温和，也保留一点个人偏爱。",
        "会把{scene}里的吃住行拆开讲，内容不求热闹，求对下一趟出门有用。",
        "会把{detail}背后的选择写出来，尤其在意{care}、等待和当天状态。",
        "内容常从{object}开始：怎么走、哪里停、哪里其实可以放弃。",
        "喜欢把{scene}写得具体一点，少说漂亮话，多留实用判断。",
        "出发前会先想失败方案，回来后把{care}和小麻烦整理给别人。",
        "不是专业攻略号，更像一个认真记路的人；好走、好停、好回头最重要。",
        "常把一天拆成几段：吃什么、怎么换车、何时该停下来。",
        "会记录{detail}带来的小惊喜，也会说清哪里不值得硬去。",
        "旅行里最在意人的余量，内容偏慢、偏细，也允许临时改变计划。",
    ),
    "photography_primary": (
        "常在{scene}里找画面，记录{object}、{care}和成片取舍，偏爱{mood}的组图。",
        "喜欢把拍摄前后的判断写下来：为什么等光、为什么留白、为什么放弃一张图。",
        "关注光线、色彩和画面顺序，内容以图片、短评和可复用的拍摄练习为主。",
        "不迷信参数，更在意{care}和观看感受；会用组图说明一张照片为什么成立。",
        "常整理{detail}带来的灵感，写给想把日常拍得更耐看的人。",
        "偏爱克制的画面，也会分享失败样片和调整过程，让方法比结果更清楚。",
        "记录街头、静物和旅行题材里的细节，喜欢把复杂后期说得简单一点。",
        "会从{object}讲到观看感受，内容不追爆款，更在意照片能不能留下来。",
        "常把{detail}和最终成片放在一起看，喜欢解释取舍而不是炫技。",
        "会从{scene}里练习观察，拍摄记录偏短、偏诚实，也允许照片不完美。",
        "喜欢研究{object}怎样影响情绪，内容多是图片、复盘和小练习。",
        "不追求每张都惊艳，更想知道一组图为什么看起来舒服。",
        "常拍{scene}里的安静部分，也写等待、失败和重拍的理由。",
        "会把{care}讲得像日常经验，让刚开始拍的人也能跟着试。",
        "偏爱有空气感的照片，喜欢在{detail}里找到整组图的入口。",
        "比起器材堆料，更关注怎么把光线和观看顺序处理稳。",
    ),
    "travel_photography_cross": (
        "一路找{care}也记录{object}，把目的地、机位、天气和现场感放进同一篇图文。",
        "边走边拍，习惯写清楚怎么抵达、什么时候拍、为什么这个角度值得停。",
        "喜欢用照片说明路线里的选择，也用路线解释照片里的光和风。",
        "关注{scene}、取景点和成片节奏，希望看完能知道怎么走，也知道怎么拍。",
        "不只列机位，也会写体力、交通和等待；照片要好看，经验也要真实。",
        "常把{detail}当作一篇图文的开头，让旅行记录既有路线，也有画面记忆。",
        "偏爱有现场感的旅拍内容，会把拍摄判断、失败天气和临时改线一起写进去。",
        "用图文记录目的地的光线、声音和路感，给想边走边拍的人一点参考。",
        "会把{detail}写进路线，也把{care}写进照片，内容偏实拍和复盘。",
        "喜欢在{scene}里边走边找画面，机位、体力和天气都会一起交代。",
        "不把旅拍写成坐标清单，更在意为什么停下、怎么拍、值不值得等。",
        "常从一张照片倒回整段路，把抵达方式和现场判断讲清楚。",
        "图文里会同时出现{object}、天气和失败角度，给想实地拍的人参考。",
        "喜欢把目的地拍得可抵达，也会提醒哪些机位不适合硬赶。",
        "会记录出片之外的部分：等光、改线、吃饭、收相机。",
        "常把{scene}当成练习场，路线写给脚步，照片写给回忆。",
    ),
}

BIO_TAILS = {
    "travel_primary": (
        "也写失误",
        "不催人赶路",
        "会标出退路",
        "偏爱慢半拍",
        "少用空话种草",
        "常补交通细节",
        "把取舍摊开讲",
        "给临时起意留空",
        "会提醒体力余量",
        "喜欢真实体感",
        "也记录不好走的部分",
        "让第一次出发少慌",
    ),
    "photography_primary": (
        "也写废片原因",
        "不靠滤镜撑场",
        "常拆一组图",
        "愿意承认失手",
        "把暗部留住",
        "慢慢看光",
        "少讲参数神话",
        "会说清取舍",
        "喜欢留一点安静",
        "让观看慢下来",
        "也记录修图前后",
        "给画面留呼吸",
    ),
    "travel_photography_cross": (
        "会附机位取舍",
        "把等光也写进去",
        "不只给坐标",
        "也提醒体力",
        "坏天气也会写",
        "路线和照片一起复盘",
        "常把失败角度留下",
        "让图文都有来路",
        "会讲清怎么抵达",
        "把风声留在照片旁边",
        "不把风景拍成清单",
        "也写等待值不值",
    ),
}

HEADLINE_BANKS = {
    "travel_primary": ("慢行路线记录", "出门体验手账", "真实路线笔记", "旅行取舍清单", "不赶场旅行", "城市与小路观察", "行程节奏整理", "给出发前的人"),
    "photography_primary": ("光线与构图笔记", "日常影像练习", "街头与静物观察", "成片取舍复盘", "摄影题材记录", "耐看画面研究", "胶片感与光", "照片为什么成立"),
    "travel_photography_cross": ("机位与路线笔记", "边走边拍图文", "旅途光线记录", "目的地取景观察", "可抵达的好机位", "旅行摄影手账", "风景与现场感", "路线里的画面"),
}

FIXED_SLOGAN_VARIANTS = (
    "{detail}之后，{base}",
    "在{scene}，{base}",
    "{base}，先顾好{care}",
    "{base}，先看{care}",
    "{base}，别丢{care}",
    "{base}，记住{object}",
    "{base}，带上{object}",
    "{base}，等{detail}",
    "{base}，别漏掉{detail}",
    "{base}，慢点看{care}",
    "{base}，再看{detail}",
    "{scene}让我信：{base}",
    "{object}提醒我：{base}",
)


def run_rebuild_prefab_users(
    *,
    batch_id: str = TRAVEL_PHOTO_BATCH,
    target_creators: int = default_target_for_batch(TRAVEL_PHOTO_BATCH),
    system_prefix: str = "sys",
    batch_code: str = "tpdual1k",
    media_preset_set: str = "profile_presets_travel_photo_v1",
    dry_run: bool = False,
) -> dict[str, Any]:
    if system_prefix != "sys":
        raise ValueError("system_prefix must be sys for system creators")
    run_media_presets_build(preset_set=media_preset_set, dry_run=dry_run)
    if dry_run:
        return {"batchId": batch_id, "targetCreators": target_creators, "dryRun": True}

    preset_manifest = read_json(PRESET_ROOT / "manifest.json")
    changed: dict[str, str] = {}
    scale_1k = _rebuild_creator_batch(
        batch_id=batch_id,
        batch_code=batch_code,
        preset_manifest=preset_manifest,
        expected_count=target_creators,
    )
    changed["creatorScale1k"] = str(scale_1k["seedPath"])
    _rewrite_ordinary_prefab_users(preset_manifest)
    _write_creator_pool_slice(scale_1k["users"], batch_id=batch_id, vertical="travel", include_current=True, preset_manifest=preset_manifest)
    _rewrite_migration_map(scale_1k["users"])
    _write_content_bind(scale_1k["users"], batch_id=batch_id)
    _write_prod_rollout(batch_id=batch_id)
    _write_compact_publish(scale_1k["users"], batch_id=batch_id, preset_manifest=preset_manifest)
    issues = rebuild_contract_issues(batch_id=batch_id, target_creators=target_creators)
    if issues:
        raise ValueError("rebuild-prefab-users gate failed: " + "; ".join(issues[:20]))
    return {
        "batchId": batch_id,
        "targetCreators": target_creators,
        "creatorUsers": len(scale_1k["users"]),
        "publishDir": str(PUBLISH_ROOT / "creators"),
        "mediaPresetSet": media_preset_set,
        "changed": changed,
        "dryRun": False,
    }


def rebuild_contract_issues(
    *,
    batch_id: str = TRAVEL_PHOTO_BATCH,
    target_creators: int = default_target_for_batch(TRAVEL_PHOTO_BATCH),
) -> list[str]:
    issues: list[str] = []
    publish_root = PUBLISH_ROOT / "creators"
    expected_publish = {"manifest.json", "creators.jsonl"}
    if not publish_root.is_dir():
        issues.append(f"missing publish creators dir: {publish_root}")
    else:
        files = {path.relative_to(publish_root).as_posix() for path in publish_root.rglob("*") if path.is_file()}
        if files != expected_publish:
            issues.append(f"publish/creators files {sorted(files)} != {sorted(expected_publish)}")
    manifest_path = PRESET_ROOT / "manifest.json"
    if not manifest_path.is_file():
        issues.append("missing profile preset manifest")
        return issues
    preset_manifest = read_json(manifest_path)
    avatar_ids = {row["presetId"] for row in preset_manifest.get("avatars") or []}
    cover_ids = {row["presetId"] for row in preset_manifest.get("covers") or []}
    creators_path = publish_root / "creators.jsonl"
    rows = _read_jsonl(creators_path) if creators_path.is_file() else []
    if len(rows) != target_creators:
        issues.append(f"creator jsonl rows {len(rows)} != {target_creators}")
    segment_counter = Counter(str(row.get("segment") or "") for row in rows)
    if uses_dual_view_policy(batch_id):
        expected_view = expected_view_contract(batch_id, target_creators)
        actual_view = view_counts_from_segments(segment_counter)
        if int(actual_view["travelViewCount"]) != int(expected_view["travelViewCount"]):
            issues.append(
                "travelViewCount "
                f"{int(actual_view['travelViewCount'])} != {int(expected_view['travelViewCount'])}"
            )
        if int(actual_view["photographyViewCount"]) != int(expected_view["photographyViewCount"]):
            issues.append(
                "photographyViewCount "
                f"{int(actual_view['photographyViewCount'])} != {int(expected_view['photographyViewCount'])}"
            )
        if int(actual_view["viewOverlapCount"]) != int(expected_view["viewOverlapCount"]):
            issues.append(
                "viewOverlapCount "
                f"{int(actual_view['viewOverlapCount'])} != {int(expected_view['viewOverlapCount'])}"
            )
        if abs(float(actual_view["viewOverlapRate"]) - float(expected_view["viewOverlapRate"])) > 0.001:
            issues.append(
                "viewOverlapRate "
                f"{float(actual_view['viewOverlapRate']):.4f} != {float(expected_view['viewOverlapRate']):.4f}"
            )
    seen_users: set[str] = set()
    slogan_counts: Counter[str] = Counter()
    bio_counts: Counter[str] = Counter()
    for row in rows:
        user_id = str(row.get("userId") or "")
        sub_id = str(row.get("subAccountId") or "")
        if user_id in seen_users:
            issues.append(f"duplicate userId {user_id}")
        seen_users.add(user_id)
        _append_sys_user_id_issue(issues, user_id)
        _append_sys_sub_id_issue(issues, sub_id, user_id)
        for field in ("displayName", "slogan", "bio"):
            _append_profile_text_issues(issues, str(row.get(field) or ""), field, user_id)
        slogan_counts[str(row.get("slogan") or "")] += 1
        bio_counts[str(row.get("bio") or "")] += 1
        avatar = str(row.get("avatarPresetId") or "")
        cover = str(row.get("coverPresetId") or "")
        if avatar not in avatar_ids:
            issues.append(f"{user_id}: avatarPresetId not in preset manifest")
        if cover not in cover_ids:
            issues.append(f"{user_id}: coverPresetId not in preset manifest")
        if row.get("segment") == "travel_photography_cross":
            verticals = set(row.get("verticals") or [])
            tags = [str(tag) for tag in row.get("tags") or []]
            if not {"travel", "photography"}.issubset(verticals):
                issues.append(f"{user_id}: cross missing dual verticals")
            if not any(tag.startswith("Topic/旅行/") for tag in tags):
                issues.append(f"{user_id}: cross missing travel topic")
            if not any(tag.startswith("Topic/摄影/") for tag in tags):
                issues.append(f"{user_id}: cross missing photography topic")
        for tag in row.get("tags") or []:
            if str(tag).startswith("Topic/") and str(tag) not in PUBLISHED_INTEREST_TAGS:
                issues.append(f"{user_id}: tag not in published leaf allowlist: {tag}")
        for forbidden in (
            "authorId",
            "legacyAliases",
            "avatarObjectKey",
            "coverObjectKey",
            "ipLocation",
            "schemaVersion",
            "personaVersion",
            "importVersion",
            "operations",
            "provenance",
        ):
            if forbidden in row:
                issues.append(f"{user_id}: forbidden field {forbidden}")
    duplicate_slogans = [text for text, count in slogan_counts.items() if text and count > 1]
    if duplicate_slogans:
        issues.append(f"duplicate slogans are not allowed: {duplicate_slogans[:5]}")
    if len(slogan_counts) < int(max(len(rows), 1) * 0.95):
        issues.append(f"slogan unique ratio too low: {len(slogan_counts)}/{len(rows)}")
    similarity = _slogan_similarity_stats([str(row.get("slogan") or "") for row in rows], threshold=0.70)
    if similarity["ratio"] >= 0.01:
        issues.append(
            "slogan high-similarity ratio too high: "
            f"{similarity['count']}/{similarity['totalPairs']}={similarity['ratio']:.4f} >= 0.0100"
        )
    high_088 = _slogan_similarity_stats([str(row.get("slogan") or "") for row in rows], threshold=0.88)
    if high_088["count"] > 0:
        issues.append(f"slogan >=0.88 similarity pairs must be 0, got {high_088['count']}")
    unique_bios = len([text for text in bio_counts if text])
    if unique_bios < 600:
        issues.append(f"bio unique count too low: {unique_bios} < 600")
    _append_ordinary_user_issues(issues)
    return issues


def _rebuild_creator_batch(
    *,
    batch_id: str,
    batch_code: str,
    preset_manifest: dict[str, Any],
    expected_count: int | None = None,
) -> dict[str, Any]:
    seed_path = CREATOR_FIXTURES / _seed_name(batch_id)
    if not seed_path.is_file():
        raise FileNotFoundError(f"missing creator seed: {seed_path}")
    seed = read_json(seed_path)
    source_users = [row for row in seed.get("users") or [] if isinstance(row, dict)]
    if expected_count is not None and len(source_users) != expected_count:
        raise ValueError(f"{batch_id} user count {len(source_users)} != {expected_count}")
    topic_counts: Counter[str] = Counter()
    seen_slogans: set[str] = set()
    rebuilt: list[dict[str, Any]] = []
    for idx, source in enumerate(source_users, start=1):
        segment = str(source.get("verticalSegment") or _segment_from_verticals(source.get("verticalRefs") or []))
        topic_code = _topic_code_for_segment(segment)
        topic_counts[topic_code] += 1
        topic_seq = topic_counts[topic_code]
        rebuilt.append(
            _rebuilt_creator_user(
                source,
                seq=idx,
                batch_id=batch_id,
                batch_code=batch_code,
                preset_manifest=preset_manifest,
                segment=segment,
                topic_code=topic_code,
                topic_seq=topic_seq,
                seen_slogans=seen_slogans,
            )
        )
    write_json(seed_path, {"schemaVersion": "creator_pool.seed/2", "batchId": batch_id, "vertical": "travel", "environment": "alpha", "users": rebuilt})
    _write_creator_templates(rebuilt, batch_id=batch_id)
    _write_relations_seed(rebuilt, batch_id=batch_id)
    return {"seedPath": seed_path, "users": rebuilt}


def _rebuilt_creator_user(
    source: dict[str, Any],
    *,
    seq: int,
    batch_id: str,
    batch_code: str,
    preset_manifest: dict[str, Any],
    segment: str,
    topic_code: str,
    topic_seq: int,
    seen_slogans: set[str],
) -> dict[str, Any]:
    verticals = _verticals_for_segment(segment, source.get("verticalRefs") or [])
    tags = _clean_tags(source.get("interestTagRefs") or source.get("publicProfileTagRefs") or [], verticals=verticals)
    display_name, handle = _name_and_handle(seq)
    avatar, cover = _media_for(seq, segment=segment, preset_manifest=preset_manifest)
    user_id = f"sys_{topic_code}_{topic_seq:04d}"
    sub_id = f"{user_id}_sub_01"
    profile_seq = _profile_text_seq(topic_seq=topic_seq, fallback=seq)
    carrier = _preferred_content_types(source)
    relations = _topic_relations(batch_id=batch_id, verticals=verticals, tags=tags)
    slogan = _unique_slogan(segment=segment, seq=profile_seq, used=seen_slogans)
    profile = {
        "creatorProfileId": user_id,
        "userId": user_id,
        "subAccountId": sub_id,
        "displayName": display_name,
        "userHandle": handle,
        "handle": handle,
        "avatarPresetId": avatar["presetId"],
        "coverPresetId": cover["presetId"],
        "bio": _bio(segment, profile_seq),
        "headline": _headline(segment, profile_seq),
        "slogan": slogan,
        "creatorArchetype": source.get("creatorArchetype"),
        "verticalSegment": segment,
        "verticalRefs": verticals,
        "interestTagRefs": tags,
        "publicProfileTagRefs": _public_tags(verticals, tags),
        "creatorClassTagRefs": [],
        "preferredContentTypes": carrier,
        "carrierAffinity": _carrier_affinity(carrier),
        "preferredBlueprintIds": _preferred_blueprints(segment),
        "coverageScope": {"kind": "thematic", "topicRefs": tags},
        "relations": relations,
        "vertical": "travel",
        "cohortId": batch_id,
        "batchId": batch_id,
        "status": "active",
        "tags": _dedupe(["author", "creator_pool", *verticals, *tags]),
    }
    return profile


def _write_creator_templates(users: list[dict[str, Any]], *, batch_id: str) -> None:
    root = PROFILE_ROOT / batch_id
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    for user in users:
        path = root / f"{user['creatorProfileId']}.creator.yaml"
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(user, f, allow_unicode=True, sort_keys=False)


def _write_relations_seed(users: list[dict[str, Any]], *, batch_id: str) -> None:
    edges: list[dict[str, Any]] = []
    for idx, user in enumerate(users):
        sub = user["subAccountId"]
        if idx > 0:
            edges.append({"kind": "FollowEdge", "fromSubAccountId": sub, "toSubAccountId": users[idx - 1]["subAccountId"]})
        relations = user.get("relations") if isinstance(user.get("relations"), dict) else {}
        for circle_id in relations.get("joinedCircleIds") or []:
            edges.append({"kind": "CircleMember", "subAccountId": sub, "circleId": circle_id})
        for entity_ref in relations.get("entityAffinityRefs") or []:
            edges.append({"kind": "EntityAffinity", "subAccountId": sub, "entityRef": entity_ref})
        for circle_ref in relations.get("circleAffinityRefs") or []:
            edges.append({"kind": "CircleAffinity", "subAccountId": sub, "circleRef": circle_ref})
    name = f"creator_relations.{batch_id}.seed.json"
    write_json(CREATOR_FIXTURES / name, {"schemaVersion": "creator_pool.relations/2", "batchId": batch_id, "relationSeedPolicy": "topic_only_v2", "edges": edges})


def _write_creator_pool_slice(
    users: list[dict[str, Any]],
    *,
    batch_id: str,
    vertical: str,
    include_current: bool,
    preset_manifest: dict[str, Any],
) -> None:
    creator_users = [_user_pool_entry(user, vertical=vertical, batch_id=batch_id, preset_manifest=preset_manifest) for user in users]
    if include_current:
        creator_users.insert(0, _current_user_variant(preset_manifest))
    path = SERVICE_FIXTURES / f"user_pool.creator_pool.{batch_id}.json"
    overlay_path = CREATOR_FIXTURES / f"creator_travel_{batch_id}_user_overlay.json"
    manifest_path = SERVICE_FIXTURES / f"user_pool.manifest.{batch_id}.json"
    legacy_count = len((read_json(SERVICE_FIXTURES / "user_pool.json").get("users") or []))
    overlay_users = [_user_pool_entry(user, vertical=vertical, batch_id=batch_id, preset_manifest=preset_manifest) for user in users]
    write_json(path, {"schemaVersion": "shared.avatar-user-pool.creator_slice/2", "batchId": batch_id, "vertical": vertical, "prefabTrack": "creator_pool", "userCount": len(creator_users), "users": creator_users, "generatedAt": now_iso()})
    write_json(overlay_path, {"schemaVersion": "shared.avatar-user-pool.creator_overlay/2", "batchId": batch_id, "vertical": vertical, "userCount": len(overlay_users), "users": overlay_users, "generatedAt": now_iso()})
    write_json(
        manifest_path,
        {
            "schemaVersion": "shared.avatar-user-pool.manifest/2",
            "defaultTrack": "creator_pool",
            "mergeRules": {
                "archivePath": "_shared/test_fixtures/user_pool.json",
                "creatorPoolPath": f"_shared/test_fixtures/{path.name}",
                "resolutionOrder": ["creator_pool", "archive"],
                "conflictPolicy": "creator_pool_wins",
            },
            "currentUserVariant": {
                "userId": "fixture_user_current",
                "subAccountId": "fixture_sub_current",
            },
            "statistics": {
                "archiveUserCount": legacy_count,
                "creatorPoolUserCount": len(creator_users),
                "mergedUserCount": legacy_count + len(creator_users),
            },
            "batchId": batch_id,
            "generatedAt": now_iso(),
        },
    )


def _user_pool_entry(
    user: dict[str, Any],
    *,
    vertical: str,
    batch_id: str,
    preset_manifest: dict[str, Any],
) -> dict[str, Any]:
    avatar_key = _preset_object_key(preset_manifest, str(user.get("avatarPresetId") or ""), "avatars")
    cover_key = _preset_object_key(preset_manifest, str(user.get("coverPresetId") or ""), "covers")
    vertical_refs = [str(ref) for ref in (user.get("verticalRefs") or [vertical]) if str(ref).strip()]
    primary_theme = str(user.get("primaryTheme") or (vertical_refs[0] if vertical_refs else vertical))
    theme_tags = list(dict.fromkeys([primary_theme, *vertical_refs]))
    return {
        "userId": user.get("creatorProfileId") or user.get("userId"),
        "displayName": user.get("displayName"),
        "avatarObjectKey": avatar_key,
        "backgroundObjectKey": cover_key,
        "avatarPresetId": user.get("avatarPresetId"),
        "coverPresetId": user.get("coverPresetId"),
        "avatarMedia": _media_meta(avatar_key),
        "backgroundMedia": _media_meta(cover_key, width=1600, height=900),
        "bio": user.get("bio"),
        "headline": user.get("headline"),
        "slogan": user.get("slogan"),
        "subAccountRefs": [user.get("subAccountId")],
        "subAccountId": user.get("subAccountId"),
        "userHandle": user.get("userHandle") or user.get("handle"),
        "tags": user.get("tags") or ["author", "creator_pool", vertical],
        "primaryTheme": primary_theme,
        "secondaryThemes": vertical_refs,
        "themeTags": theme_tags,
        "postThemeRefs": list(theme_tags),
        "circleThemeRefs": list(theme_tags),
        "groupPersonaMix": user.get("groupPersonaMix") or [],
        "primaryRole": "secondaryAuthor",
        "creatorArchetype": user.get("creatorArchetype"),
        "verticalSegment": user.get("verticalSegment"),
        "verticalRefs": vertical_refs,
        "interestTagRefs": user.get("interestTagRefs") or [],
        "publicProfileTagRefs": user.get("publicProfileTagRefs") or [],
        "creatorClassTagRefs": user.get("creatorClassTagRefs") or [],
        "coverageScope": user.get("coverageScope") or {},
        "carrierAffinity": user.get("carrierAffinity") or {},
        "preferredBlueprintIds": user.get("preferredBlueprintIds") or [],
        "preferredContentTypes": user.get("preferredContentTypes") or [],
        "relations": user.get("relations") or {},
        "cohortId": batch_id,
        "prefabTrack": "creator_pool",
    }


def _current_user_variant(preset_manifest: dict[str, Any]) -> dict[str, Any]:
    display, handle = "小趣体验号", "qwq-demo"
    avatar = preset_manifest["avatars"][0]
    cover = preset_manifest["covers"][0]
    return {
        "userId": "fixture_user_current",
        "displayName": display,
        "avatarObjectKey": avatar["objectKey"],
        "backgroundObjectKey": cover["objectKey"],
        "avatarPresetId": avatar["presetId"],
        "coverPresetId": cover["presetId"],
        "avatarMedia": _media_meta(avatar["objectKey"]),
        "backgroundMedia": _media_meta(cover["objectKey"], width=1600, height=900),
        "bio": "用于本地验收的当前用户，关注旅行、摄影和日常记录。",
        "headline": "当前体验用户",
        "slogan": "先把体验走顺",
        "subAccountRefs": ["fixture_sub_current"],
        "subAccountId": "fixture_sub_current",
        "userHandle": handle,
        "tags": ["author", "creator_pool", "travel", "photography"],
        "primaryTheme": "travel",
        "secondaryThemes": ["travel", "photography"],
        "themeTags": ["travel", "photography"],
        "postThemeRefs": ["travel", "photography"],
        "circleThemeRefs": ["travel", "photography"],
        "groupPersonaMix": [],
        "primaryRole": "currentUserVariant",
        "verticalRefs": ["travel", "photography"],
        "interestTagRefs": ["Topic/旅行/玩法/摄影旅拍", "Topic/摄影/旅行摄影"],
        "publicProfileTagRefs": ["Topic/旅行", "Topic/摄影"],
        "relations": {},
        "cohortId": TRAVEL_PHOTO_BATCH,
        "slotRole": "currentUserVariant",
        "prefabTrack": "creator_pool",
    }


def _rewrite_ordinary_prefab_users(preset_manifest: dict[str, Any]) -> None:
    path = SERVICE_FIXTURES / "user_pool.json"
    data = read_json(path)
    users = [row for row in data.get("users") or [] if isinstance(row, dict)]
    for idx, user in enumerate(users, start=1):
        user_id = str(user.get("userId") or f"fixture_user_{idx:03d}")
        display, handle = _name_and_handle(idx + 1100)
        avatar, cover = _media_for(idx + 1200, segment="ordinary", preset_manifest=preset_manifest)
        user["displayName"] = _ordinary_display_name(user_id, display)
        user["slogan"] = _ordinary_slogan(user_id)
        user["bio"] = _ordinary_bio(user_id)
        user["avatarPresetId"] = avatar["presetId"]
        user["coverPresetId"] = cover["presetId"]
        user["avatarMedia"] = _media_meta(avatar["objectKey"])
        user["backgroundMedia"] = _media_meta(cover["objectKey"], width=1600, height=900)
        user["userHandle"] = user.get("userHandle") or handle
        if not user.get("subAccountRefs"):
            slug = user_id.removeprefix("fixture_user_") or str(idx)
            user["subAccountRefs"] = [f"fixture_sub_{slug}"]
        user.pop("ipLocation", None)
        user.pop("avatarObjectKey", None)
        user.pop("backgroundObjectKey", None)
        user.pop("coverObjectKey", None)
        user.pop("authorId", None)
        user.pop("archiveAliases", None)
    write_json(path, data)


def _rewrite_migration_map(users: list[dict[str, Any]]) -> None:
    path = SERVICE_FIXTURES / "prefab_user_migration_map.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {}
    mappings = ((data or {}).get("content_pilot_20") or {}).get("mappings") or []
    for idx, item in enumerate(mappings[:20]):
        user = users[idx]
        item["creatorProfileId"] = user["creatorProfileId"]
        item["subAccountId"] = user["subAccountId"]
        item.pop("authorId", None)
    data["currentUserVariant"] = {
        "userId": "fixture_user_current",
        "subAccountId": "fixture_sub_current",
    }
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def _write_content_bind(users: list[dict[str, Any]], *, batch_id: str) -> None:
    from governance.creator_pool.content_bind import write_creator_content_seed

    write_creator_content_seed(batch_id=batch_id)


def _write_prod_rollout(*, batch_id: str) -> None:
    write_json(
        artifacts_readiness_path(f"creator_content_prod_rollout_dryrun.{batch_id}.json"),
        {
            "batchId": batch_id,
            "decision": "go",
            "fixtureApplyAllowed": False,
            "prodPurity": {"prodCarriesTestFixtures": False},
            "generatedAt": now_iso(),
        },
    )


def _write_compact_publish(users: list[dict[str, Any]], *, batch_id: str, preset_manifest: dict[str, Any]) -> None:
    root = PUBLISH_ROOT / "creators"
    if root.exists():
        for child in root.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    root.mkdir(parents=True, exist_ok=True)
    rows = [_publish_row(user) for user in users]
    write_json(
        root / "manifest.json",
        {
            "batchId": batch_id,
            "totalCreators": len(rows),
            "segmentCounts": dict(Counter(row["segment"] for row in rows)),
            "uniqueCreatorCount": len(rows),
            "viewCounts": {
                "travel": int(expected_view_contract(batch_id, len(rows))["travelViewCount"]),
                "photography": int(expected_view_contract(batch_id, len(rows))["photographyViewCount"]),
                "overlap": int(expected_view_contract(batch_id, len(rows))["viewOverlapCount"]),
                "overlapRate": float(expected_view_contract(batch_id, len(rows))["viewOverlapRate"]),
            },
            "identityPolicy": {
                "systemCreatorPrefix": "sys_",
                "userIdPattern": "sys_{topic}_{seq4}",
                "subAccountIdPattern": "{userId}_sub_{seq2}",
                "ordinaryUserSysPrefixAllowed": False,
                "thirdIdentityAllowed": False,
            },
            "mediaPolicy": "system_profile_preset_id_only",
            "mediaPresetSetId": preset_manifest["presetSetId"],
            "publishFiles": ["manifest.json", "creators.jsonl"],
            "qualityGates": {
                "displayNameNoDigits": 1.0,
                "presetIdCoverage": 1.0,
                "crossDualTagCoverage": 1.0,
                "bioUniqueMinCount": 600,
                "leafTagCoverage": 1.0,
                "publishFileCount": 2,
                "sloganSimilarityGte070RatioMax": 0.01,
                "sloganSimilarityGte088PairMax": 0,
            },
            "generatedAt": now_iso(),
        },
    )
    write_ndjson(root / "creators.jsonl", rows)


def _publish_row(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "userId": user["creatorProfileId"],
        "subAccountId": user["subAccountId"],
        "handle": user["handle"],
        "displayName": user["displayName"],
        "slogan": user["slogan"],
        "bio": user["bio"],
        "avatarPresetId": user["avatarPresetId"],
        "coverPresetId": user["coverPresetId"],
        "roles": ["creator"],
        "verticals": user["verticalRefs"],
        "segment": user["verticalSegment"],
        "tags": user["interestTagRefs"],
        "preferredContentTypes": user["preferredContentTypes"],
        "contentRefs": [],
        "entityRefs": list((user.get("relations") or {}).get("entityAffinityRefs") or []),
        "circleRefs": list((user.get("relations") or {}).get("circleAffinityRefs") or []),
    }


def _seed_name(batch_id: str) -> str:
    return f"creator_{batch_id}.seed.json"


def _name_and_handle(seq: int) -> tuple[str, str]:
    a = (seq - 1) % len(NAME_A)
    b = ((seq - 1) * 7 + (seq - 1) // len(NAME_A)) % len(NAME_B)
    return f"{NAME_A[a]}{NAME_B[b]}", f"{HANDLE_A[a]}-{HANDLE_B[b]}"


def _profile_text_seq(*, topic_seq: int, fallback: int) -> int:
    if topic_seq >= 9000:
        return max(1, topic_seq - 9000)
    return topic_seq or fallback


def _slogan(segment: str, seq: int) -> str:
    patterns = SLOGAN_PATTERNS.get(segment, SLOGAN_PATTERNS["travel_primary"])
    style_idx = (seq - 1) % len(patterns)
    variant_idx = (seq - 1) // len(patterns)
    words = _profile_words(segment, style_idx=style_idx, variant_idx=variant_idx)
    pattern = patterns[style_idx]
    slogan = pattern.format(**words)
    if "{" not in pattern:
        slogan = _fixed_slogan_variant(slogan, words=words, style_idx=style_idx, variant_idx=variant_idx)
    return slogan


def _slogan_candidates(segment: str, seq: int) -> list[str]:
    patterns = SLOGAN_PATTERNS.get(segment, SLOGAN_PATTERNS["travel_primary"])
    style_idx = (seq - 1) % len(patterns)
    variant_idx = (seq - 1) // len(patterns)
    words = _profile_words(segment, style_idx=style_idx, variant_idx=variant_idx)
    pattern = patterns[style_idx]
    base = pattern.format(**words)
    candidates = [
        base,
        _fixed_slogan_variant(base, words=words, style_idx=style_idx, variant_idx=variant_idx),
        f"{base}，带上{words['object']}",
        f"{base}，记着{words['care']}",
        f"{base}，为了{words['detail']}",
        f"{base}，留一点{words['mood']}",
        f"{base}，慢一点{words['care']}",
        f"{base}，也带着{words['mood']}",
        f"{words['scene']}里，{base}",
        f"{words['detail']}之后，{base}",
        f"{words['detail']}之后，也看{words['care']}",
        f"{words['object']}提醒我：{base}",
    ]
    unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not (8 <= len(candidate) <= 22):
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        unique.append(candidate)
    return unique


def _unique_slogan(*, segment: str, seq: int, used: set[str]) -> str:
    for candidate in _slogan_candidates(segment, seq):
        if candidate not in used:
            if any(SequenceMatcher(None, candidate, previous).ratio() >= 0.86 for previous in used):
                continue
            used.add(candidate)
            return candidate
    fallback = f"{_slogan(segment, seq)}·{seq % 97:02d}"
    if 8 <= len(fallback) <= 22 and fallback not in used:
        used.add(fallback)
        return fallback
    raise ValueError(f"cannot derive unique slogan for {segment}:{seq}")


def _bio(segment: str, seq: int) -> str:
    patterns = BIO_PATTERNS.get(segment, BIO_PATTERNS["travel_primary"])
    style_idx = (seq - 1) % len(patterns)
    variant_idx = (seq - 1) // len(patterns)
    words = _profile_words(segment, style_idx=style_idx + 11, variant_idx=variant_idx)
    text = patterns[style_idx].format(**words)
    tails = BIO_TAILS.get(segment, BIO_TAILS["travel_primary"])
    for offset in range(len(tails)):
        tail = tails[(style_idx * 3 + variant_idx * 5 + offset) % len(tails)]
        if _bio_tail_repeats(text, tail):
            continue
        candidate = f"{text.rstrip('。')}；{tail}。"
        if len(candidate) <= 60:
            return candidate
    return text


def _headline(segment: str, seq: int) -> str:
    bank = HEADLINE_BANKS.get(segment, HEADLINE_BANKS["travel_primary"])
    return bank[(seq - 1) % len(bank)]


def _profile_words(segment: str, *, style_idx: int, variant_idx: int) -> dict[str, str]:
    banks = PROFILE_WORDS.get(segment, PROFILE_WORDS["travel_primary"])
    style_strides = (3, 5, 7, 11, 13, 17, 19)
    variant_strides = (5, 7, 11, 13, 17, 19, 23)
    words: dict[str, str] = {}
    for offset, (key, values) in enumerate(banks.items(), start=1):
        words[key] = values[
            (
                style_idx * style_strides[(offset - 1) % len(style_strides)]
                + variant_idx * variant_strides[(offset - 1) % len(variant_strides)]
            )
            % len(values)
        ]
    return words


def _bio_tail_repeats(text: str, tail: str) -> bool:
    repeated_tokens = ("失误", "体力", "坐标", "等光", "路线", "照片", "取舍", "滤镜", "暗部", "参数")
    return any(token in text and token in tail for token in repeated_tokens)


def _slogan_similarity_stats(slogans: list[str], *, threshold: float) -> dict[str, Any]:
    total_pairs = len(slogans) * (len(slogans) - 1) // 2
    if total_pairs <= 0:
        return {"threshold": threshold, "count": 0, "totalPairs": total_pairs, "ratio": 0.0}
    count = 0
    for idx, left in enumerate(slogans):
        for right in slogans[idx + 1 :]:
            if SequenceMatcher(None, left, right).ratio() >= threshold:
                count += 1
    return {
        "threshold": threshold,
        "count": count,
        "totalPairs": total_pairs,
        "ratio": count / total_pairs,
    }


def _fixed_slogan_variant(base: str, *, words: dict[str, str], style_idx: int, variant_idx: int) -> str:
    for offset in range(len(FIXED_SLOGAN_VARIANTS)):
        template = FIXED_SLOGAN_VARIANTS[(style_idx + variant_idx + offset) % len(FIXED_SLOGAN_VARIANTS)]
        candidate = template.format(base=base, **words)
        if 8 <= len(candidate) <= 22:
            return candidate
    mood = words.get("mood", "")
    if mood and mood not in base and len(base) + len(mood) + 1 <= 22:
        return f"{base}，{mood}"
    return base


def _ordinary_display_name(user_id: str, fallback: str) -> str:
    mapping = {
        "fixture_user_current": "小趣体验号",
        "fixture_user_photo": "蓝调相机",
        "fixture_user_travel": "行李路书",
        "fixture_user_friend": "晴窗好友",
        "fixture_user_owner": "灯塔主人",
    }
    return mapping.get(user_id, fallback)


def _ordinary_slogan(user_id: str) -> str:
    if "photo" in user_id or "photography" in user_id:
        return "用照片整理日常灵感"
    if "travel" in user_id:
        return "把出门经验写清楚"
    return "认真记录真实生活"


def _ordinary_bio(user_id: str) -> str:
    if "photo" in user_id or "photography" in user_id:
        return "喜欢拍照、看展和整理灵感，也会收藏实用的拍摄经验。"
    if "travel" in user_id:
        return "喜欢计划路线、记录体验，也关注旅途里的好照片。"
    return "用于本地验收的预制用户，资料保持自然可读。"


def _media_for(seq: int, *, segment: str, preset_manifest: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    avatars = _preset_candidates(preset_manifest, "avatars", segment)
    covers = _preset_candidates(preset_manifest, "covers", segment)
    return avatars[(seq - 1) % len(avatars)], covers[((seq - 1) * 7) % len(covers)]


def _preset_candidates(preset_manifest: dict[str, Any], key: str, segment: str) -> list[dict[str, Any]]:
    target = _preset_usage_for_segment(segment)
    rows = [row for row in (preset_manifest.get(key) or []) if target in (row.get("usage") or [])]
    return rows or list(preset_manifest.get(key) or [])


def _preset_usage_for_segment(segment: str) -> str:
    if segment == "travel_primary":
        return "travel"
    if segment == "photography_primary":
        return "photography"
    if segment == "travel_photography_cross":
        return "cross"
    return "travel"


def _preset_object_key(preset_manifest: dict[str, Any], preset_id: str, key: str) -> str:
    for row in preset_manifest.get(key) or []:
        if str(row.get("presetId") or "") == preset_id:
            return str(row.get("objectKey") or "")
    return ""


def _media_meta(object_key: str, *, width: int = 512, height: int = 512) -> dict[str, Any]:
    source = _preset_source_hash(object_key)
    return {
        "objectKey": object_key,
        "version": 1,
        "mimeType": "image/png" if object_key.endswith(".png") else "image/jpeg",
        "width": width,
        "height": height,
        "sizeBytes": (SERVICE_MEDIA_ROOT / object_key).stat().st_size if (SERVICE_MEDIA_ROOT / object_key).is_file() else 0,
        "sourceHash": source,
    }


def _preset_source_hash(object_key: str) -> str:
    path = SERVICE_MEDIA_ROOT / object_key
    if path.is_file():
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    return "sha256:" + hashlib.sha256(object_key.encode()).hexdigest()


def _topic_code_for_segment(segment: str) -> str:
    if segment == "photography_primary":
        return "photo"
    if segment == "travel_photography_cross":
        return "travelphoto"
    return "travel"


def _verticals_for_segment(segment: str, existing: Any) -> list[str]:
    refs = [str(ref) for ref in (existing or []) if str(ref).strip()]
    if segment == "travel_photography_cross":
        return ["travel", "photography"]
    if segment == "photography_primary":
        return ["photography"]
    if segment == "travel_primary":
        return ["travel"]
    return refs or ["travel"]


def _segment_from_verticals(verticals: list[str]) -> str:
    refs = set(verticals)
    if {"travel", "photography"}.issubset(refs):
        return "travel_photography_cross"
    if "photography" in refs:
        return "photography_primary"
    return "travel_primary"


def _clean_tags(raw: Any, *, verticals: list[str]) -> list[str]:
    tags = [
        str(tag)
        for tag in (raw or [])
        if str(tag).strip()
        and "地理" not in str(tag)
        and "Region/" not in str(tag)
        and str(tag) in PUBLISHED_INTEREST_TAGS
    ]
    for vertical in verticals:
        tags.extend(TOPIC_DEFAULTS[vertical])
    if "travel" in verticals and not any(tag.startswith("Topic/旅行/") for tag in tags):
        tags.append("Topic/旅行/玩法/摄影旅拍")
    if "photography" in verticals and not any(tag.startswith("Topic/摄影/") for tag in tags):
        tags.append("Topic/摄影/旅行摄影")
    return _dedupe(tags)


def _public_tags(verticals: list[str], tags: list[str]) -> list[str]:
    roots = ["Topic/旅行"] if "travel" in verticals else []
    if "photography" in verticals:
        roots.append("Topic/摄影")
    return _dedupe([*roots, *tags[:2]])


def _preferred_content_types(source: dict[str, Any]) -> list[str]:
    affinity = source.get("carrierAffinity") if isinstance(source.get("carrierAffinity"), dict) else {}
    if affinity:
        ordered = sorted(affinity.items(), key=lambda item: (-float(item[1] or 0), str(item[0])))
        return [str(name) for name, _ in ordered[:2]]
    segment = str(source.get("verticalSegment") or "")
    if segment == "photography_primary":
        return ["image", "article"]
    if segment == "travel_photography_cross":
        return ["image", "article"]
    return ["article", "image"]


def _carrier_affinity(types: list[str]) -> dict[str, float]:
    base = {"article": 0.1, "image": 0.1, "video": 0.05}
    for idx, item in enumerate(types):
        base[item] = 0.7 if idx == 0 else 0.25
    return base


def _preferred_blueprints(segment: str) -> list[str]:
    if segment == "photography_primary":
        return ["图片_专题", "摄影_教程"]
    if segment == "travel_photography_cross":
        return ["图片_风光", "旅行_个人游记"]
    return ["景区_体验", "旅行_个人游记"]


def _topic_relations(*, batch_id: str, verticals: list[str], tags: list[str]) -> dict[str, Any]:
    joined = [f"fixture_circle_creator_{batch_id}_{vertical}" for vertical in verticals]
    entity_refs = [f"homepage/topic/{vertical}" for vertical in verticals]
    circle_refs = [f"circle/topic/{vertical}" for vertical in verticals]
    for tag in tags[:3]:
        entity_refs.append(f"homepage/tag/{tag.replace('/', '_')}")
    return {
        "joinedCircleIds": _dedupe(joined),
        "followedHomepageCanonicalIds": _dedupe(entity_refs[:3]),
        "entityAffinityRefs": _dedupe(entity_refs),
        "circleAffinityRefs": _dedupe(circle_refs),
        "relationSeedPolicy": "topic_only_v2",
    }


def _append_sys_user_id_issue(issues: list[str], value: str) -> None:
    if not SYS_USER_ID_RE.match(value) or len(value) > 32:
        issues.append(f"invalid system userId {value}")


def _append_sys_sub_id_issue(issues: list[str], value: str, user_id: str) -> None:
    if not SYS_SUB_ID_RE.match(value) or len(value) > 32:
        issues.append(f"invalid system subAccountId {value}")
    if value != f"{user_id}_sub_01":
        issues.append(f"subAccountId {value} must derive from userId {user_id}")


def _append_profile_text_issues(issues: list[str], text: str, field: str, user_id: str) -> None:
    if not text.strip():
        issues.append(f"{user_id}: missing {field}")
    if field == "displayName" and re.search(r"\d", text):
        issues.append(f"{user_id}: displayName has digits")
    for token in FORBIDDEN_PROFILE_TOKENS:
        if token in text:
            issues.append(f"{user_id}: {field} contains forbidden token {token}")


def _append_ordinary_user_issues(issues: list[str]) -> None:
    path = SERVICE_FIXTURES / "user_pool.json"
    data = read_json(path)
    for user in data.get("users") or []:
        user_id = str(user.get("userId") or "")
        if user_id.startswith("sys_"):
            issues.append(f"ordinary user must not use sys prefix: {user_id}")
        if "ipLocation" in user:
            issues.append(f"ordinary user {user_id} must not carry ipLocation")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out
