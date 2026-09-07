"""统一多载体框架：共同层契约与 lane adapter 边界的单一真相源。

统一口径：
- 共同层（所有载体同构）：target selection → source unit → asset index →
  review ledger → publish → ship → coverage/env import。
- lane adapter 边界（载体差异只允许出现在此清单声明的产物与阶段差异）：
  - homepage：出 page.md + _entity.json + manifest.json（task 根成品，跨批次唯一）；
  - article：出 writing_pack + draft.article.md → article.md + manifest.json；
  - image：单源图片作品（gallery.md 可选），无 agent 长文写作段；
  - video：Agent 产出脚本与字幕，CLI 只做确定性 H.264 渲染和证据封装。

任何新增载体/新增产物必须先改本契约，再改业务代码；散落的 lane 常量
（download plan 文件名、发布路径、gate 白名单）必须引用本模块，禁止再建第二套。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.control_types import ContentType


CARRIER_CONTRACT_SCHEMA = "quwoquan_data.carrier_contract"

# 共同层阶段（四载体同构，顺序即数据流），与 geo-content-trinity/execution §1 对齐。
COMMON_LAYER_STAGES: tuple[str, ...] = (
    "target_selection",
    "source_unit",
    "asset_index",
    "review_ledger",
    "publish",
    "ship",
    "coverage_env_import",
)


@dataclass(frozen=True)
class CarrierLane:
    """单载体 lane adapter 契约。"""

    lane: ContentType
    # download 段来源计划文件名（无独立下载计划的载体为 None）。
    source_plan_file: str | None
    # 成品必备产物（相对成品目录）。
    final_artifacts: tuple[str, ...]
    # 过程草稿产物（agent 写回；无 agent 写作段的载体为空）。
    draft_artifacts: tuple[str, ...] = ()
    # 是否进入 post_author（bridge 受限段）。
    agent_authored: bool = False
    notes: str = ""
    extra: dict = field(default_factory=dict)


# 排产层（任务规格 content mix）命名 → 载体 lane（批次/目录层）命名。
# 单一真相源：所有内容输入与下载阶段标注必须引用本表，
# 禁止再写内联映射 dict / 注释式映射。
CONTENT_MIX_TO_LANE: dict[str, str] = {
    "homepage": "homepage",
    "article": "article",
    "imagePost": "image",
    "videoPost": "video",
    # 知识卡是 article 载体的排产变体（正文仍走 article.md，预算独立）。
    "knowledgeCard": "article",
}

# lane → canonical 排产命名（反向标注用）。knowledgeCard 是排产变体不占独立 lane，
# 反向映射只取各 lane 的 canonical 主类型。
LANE_TO_CANONICAL_CONTENT_MIX: dict[str, str] = {
    "homepage": "homepage",
    "article": "article",
    "image": "imagePost",
    "video": "videoPost",
}


CARRIER_LANES: dict[str, CarrierLane] = {
    "homepage": CarrierLane(
        lane=ContentType.HOMEPAGE,
        source_plan_file="homepage_source_plan.json",
        final_artifacts=("page.md", "_entity.json", "manifest.json"),
        draft_artifacts=("page.md",),
        agent_authored=True,
        notes="实体主页：成品 task-scoped 落 task 根 entities/，跨批次唯一",
    ),
    "article": CarrierLane(
        lane=ContentType.ARTICLE,
        source_plan_file="article_source_plan.json",
        final_artifacts=("article.md", "manifest.json", "provenance.json"),
        draft_artifacts=("writing_pack", "draft.article.md"),
        agent_authored=True,
        notes="文章：writing_pack 交 agent，draft.article.md 写回后 compose 成品",
    ),
    "image": CarrierLane(
        lane=ContentType.IMAGE,
        source_plan_file="image_source_plan.json",
        final_artifacts=("manifest.json", "provenance.json"),
        draft_artifacts=(),
        agent_authored=False,
        notes="图片作品：单源图片，图必须归属来源单元 assets/ 并有 relevance 标注",
    ),
    "video": CarrierLane(
        lane=ContentType.VIDEO,
        source_plan_file="video_source_plan.json",
        final_artifacts=(
            "manifest.json",
            "provenance.json",
            "assets/video.mp4",
            "assets/poster.webp",
            "subtitles.vtt",
        ),
        draft_artifacts=("video_script.json",),
        agent_authored=True,
        notes="视频：Agent 负责脚本与字幕，CLI 渲染 9:16 H.264 并冻结权利与校验证据",
    ),
}


def research_plan_files() -> dict[str, str]:
    """download 段来源计划文件映射（lane → 文件名）。"""
    return {
        lane.lane.value: lane.source_plan_file
        for lane in CARRIER_LANES.values()
        if lane.source_plan_file
    }


def scaled_lanes() -> tuple[str, ...]:
    """允许按冻结 execution contract 放量的载体集合。"""
    return tuple(l.lane.value for l in CARRIER_LANES.values())
