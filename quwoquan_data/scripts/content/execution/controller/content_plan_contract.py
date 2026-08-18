"""Immutable content-plan quota contract resolved at the execution boundary."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from content.execution.support import (
    DataIssue,
    DataIssueCode,
    DataIssueStage,
    DataRecoveryAction,
    ExecutionContext,
    data_issue,
    image_count_is_hard_quota,
    minimum_publishable_images_per_target,
)


@dataclass(frozen=True)
class ContentPlanContract:
    articles_per_target: int
    images_per_target: int
    videos_per_target: int
    minimum_articles: int
    minimum_images: int
    minimum_videos: int
    article_lane_enabled: bool
    image_lane_enabled: bool
    video_lane_enabled: bool


def resolve_content_plan_contract(
    ctx: ExecutionContext,
    active_spec: Mapping[str, Any],
) -> tuple[ContentPlanContract | None, tuple[DataIssue, ...]]:
    quotas = (active_spec.get("content") or {}).get("quotas") or {}
    articles = int(quotas.get("entityArticlesPerTarget") or 0)
    images = int(quotas.get("imageWorksPerTarget") or 0)
    videos = int(quotas.get("videoWorksPerTarget") or 0)
    from content.execution.identity import parse_execution_id

    execution_content_type = parse_execution_id(ctx.execution_id).content_type.value
    active_content_types: set[str] = set()
    if articles > 0 or int(quotas.get("routeArticles") or 0) > 0:
        active_content_types.add("article")
    if images > 0:
        active_content_types.add("image")
    if videos > 0:
        active_content_types.add("video")
    if int(quotas.get("entityHomepagesPerTarget") or 0) > 0:
        active_content_types.add("homepage")
    if active_content_types != {execution_content_type}:
        issue = data_issue(
            DataIssueCode.CONTRACT_INVALID,
            stage=DataIssueStage.CONTENT_PLAN,
            ref=ctx.execution_id,
            recovery=DataRecoveryAction.STOP,
            message=(
                "one execution may build exactly its immutable contentType; "
                f"execution={execution_content_type!r} "
                f"quotas={sorted(active_content_types)}; "
                "split carriers through recipe/release fanout"
            ),
        )
        return None, (issue,)
    article_lane_enabled = articles > 0
    image_lane_enabled = images > 0
    video_lane_enabled = videos > 0
    if not article_lane_enabled and not image_lane_enabled and not video_lane_enabled:
        issue = data_issue(
            DataIssueCode.CONTRACT_INVALID,
            stage=DataIssueStage.CONTENT_PLAN,
            ref=ctx.execution_id,
            recovery=DataRecoveryAction.STOP,
            message="content quotas are empty; auto content_plan skipped",
        )
        return None, (issue,)
    return (
        ContentPlanContract(
            articles_per_target=articles,
            images_per_target=images,
            videos_per_target=videos,
            minimum_articles=articles,
            minimum_images=(
                images
                if image_count_is_hard_quota(active_spec)
                else minimum_publishable_images_per_target(active_spec)
            ),
            minimum_videos=videos,
            article_lane_enabled=article_lane_enabled,
            image_lane_enabled=image_lane_enabled,
            video_lane_enabled=video_lane_enabled,
        ),
        (),
    )
