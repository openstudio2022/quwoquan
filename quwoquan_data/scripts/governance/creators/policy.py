"""Repository-owned creator profile policy."""
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

PHOTOGRAPHY_ARCHETYPES: tuple[str, ...] = (
    "portrait_photographer",
    "photo_landscape_photographer",
    "documentary_photographer",
    "street_photographer",
    "architecture_still_photographer",
    "mobile_photographer",
    "gear_reviewer",
    "post_production_educator",
)

TRAVEL_PHOTOGRAPHY_CROSS_ARCHETYPES: tuple[str, ...] = (
    "travel_landscape_photographer",
    "city_walk_photographer",
    "outdoor_hiking_photographer",
    "food_travel_visualist",
    "heritage_documentary_photographer",
    "mobile_travel_creator",
    "gear_lightweight_traveler",
    "local_photo_walk_guide",
)

CREATOR_VERTICAL_SEGMENTS: tuple[str, ...] = (
    "travel_primary",
    "photography_primary",
    "travel_photography_cross",
)

SEGMENT_QUOTA_RATIOS: dict[str, float] = {
    "travel_primary": 0.30,
    "photography_primary": 0.30,
    "travel_photography_cross": 0.40,
}

SEGMENT_QUOTAS_PER_100: dict[str, int] = {
    "travel_primary": 30,
    "photography_primary": 30,
    "travel_photography_cross": 40,
}

ACQUIRE_ALLOWLIST_DOMAINS: tuple[str, ...] = (
    "www.tpoty.com",
    "www.nationalgeographic.com",
    "www.thewanderinglens.com",
    "shotkit.com",
    "www.outdoorphotographymagazine.co.uk",
    "tuchong.com",
    "www.xitek.com",
)

POPULARITY_TIERS: tuple[str, ...] = ("head", "waist", "rising", "niche_expert")
OUTPUT_TIERS: tuple[str, ...] = ("prolific", "steady", "seasonal")

# 规范 3 级叶子（唯一真相源 = control-plane taxonomy + bootstrap_tags_topic_travel.py）。
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

PHOTOGRAPHY_TOPIC_REFS: tuple[str, ...] = (
    "Topic/摄影/风光摄影",
    "Topic/摄影/旅行摄影",
    "Topic/摄影/纪实摄影",
    "Topic/摄影/街头摄影",
    "Topic/摄影/建筑摄影",
    "Topic/摄影/静物摄影",
    "Topic/摄影/手机摄影",
    "Topic/摄影/器材评测",
    "Topic/摄影/摄影教程",
    "Topic/摄影/美食摄影",
    "Topic/摄影/人文摄影",
    "Topic/摄影/夜景星空",
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
    "bilibili_style",
    "gallery_portfolio",
    "magazine_column",
    "community_forum",
)

SOURCE_REGION_CLASS_RATIOS: dict[str, float] = {
    "non_china": 0.45,
    "china": 0.35,
    "cross_region": 0.20,
}

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
