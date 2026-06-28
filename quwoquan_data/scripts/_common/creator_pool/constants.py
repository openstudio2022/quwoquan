"""Creator pool shared constants."""
from __future__ import annotations

TRAVEL_ARCHETYPES: tuple[str, ...] = (
    "travel_blogger",
    "self_drive_expert",
    "landscape_photographer",
    "geo_editor",
    "food_columnist",
    "pro_guide",
    "casual_tourist",
    "local_walker",
)

ACQUIRE_ALLOWLIST_DOMAINS: tuple[str, ...] = (
    "travel.example.org",
    "blog.open-travel.net",
    "rss.wanderlust.io",
    "about.geo-trails.com",
)

POPULARITY_TIERS: tuple[str, ...] = ("head", "waist", "rising", "niche")
OUTPUT_TIERS: tuple[str, ...] = ("prolific", "steady", "seasonal")

# 规范 3 级叶子（唯一真相源 = publish/tags + bootstrap_tags_topic_verticals_part1.py）。
# 禁止退回 2 级短标签：creator-lint 经 tag_exists 校验目录化标签树，2 级短标签不存在即 BLOCK。
TRAVEL_TOPIC_REFS: tuple[str, ...] = (
    "Topic/旅行/出行方式/自驾",
    "Topic/旅行/玩法/摄影旅拍",
    "Topic/旅行/旅行主题/美食之旅",
    "Topic/旅行/出行方式/徒步穿越",
    "Topic/旅行/旅行主题/城市漫步",
    "Topic/旅行/旅行主题/亲子游",
    "Topic/旅行/玩法/露营",
    "Topic/旅行/旅行主题/海岛度假",
    "Topic/旅行/旅行主题/古镇古村",
    "Topic/旅行/旅行主题/高原秘境",
    "Topic/旅行/出行方式/高铁铁路",
    "Topic/旅行/玩法/节庆民俗",
)

COMMERCIAL_CARRIER_BUCKETS: tuple[str, ...] = ("article", "image", "mixed")

TRAVEL_REGION_BUCKETS: tuple[str, ...] = (
    "西南",
    "华东",
    "华北",
    "华南",
    "西北",
    "东北",
    "华中",
)

CARRIER_BUCKETS: tuple[str, ...] = (
    "article_heavy",
    "image_heavy",
    "video_heavy",
    "balanced",
)

PLATFORM_BUCKETS: tuple[str, ...] = (
    "xiaohongshu_style",
    "weibo_style",
    "rss_blog",
    "youtube_style",
)

STAGES: tuple[str, ...] = (
    "1.acquire",
    "2.score",
    "3.enrich",
    "4.materialize",
    "5.validate",
)

DISCLOSURE = {
    "type": "platform_virtual_creator",
    "displayText": "平台虚拟创作者，内容由资料整理与 AI 辅助生成，经平台审核发布。",
    "visible": True,
}

CLAIM_POLICY = {
    "experienceClaimMode": "editorial_synthesis",
    "mayUseFirstPerson": False,
    "mustCiteEvidenceForClaims": True,
    "forbiddenClaims": ["真实亲历", "官方推荐", "商业合作", "专业导游资质"],
}
