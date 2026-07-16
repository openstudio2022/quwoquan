"""Closed vocabularies shared by data execution and release control flow."""
from __future__ import annotations

from enum import StrEnum


class ContentType(StrEnum):
    HOMEPAGE = "homepage"
    ARTICLE = "article"
    IMAGE = "image"
    VIDEO = "video"


class RolloutMilestone(StrEnum):
    BASELINE = "baseline"
    CANARY = "canary"
    M1 = "m1"
    M2 = "m2"
    M3 = "m3"


class DeploymentEnvironment(StrEnum):
    ALPHA = "alpha"
    BETA = "beta"
    GAMMA = "gamma"
    PROD = "prod"


class SelectionPolicy(StrEnum):
    FROZEN = "frozen"


class ReplacementPolicy(StrEnum):
    FORBIDDEN = "forbidden"


class RuntimeEnvironment(StrEnum):
    LOCAL = "local"
    CLOUD = "cloud"


class AgentProvider(StrEnum):
    CURSOR_SDK = "cursor_sdk"
    CODEX_CLI = "codex_cli"


class ReadinessMode(StrEnum):
    COMMERCIAL = "commercial"
    CALIBRATION = "calibration"


class ExecutionStage(StrEnum):
    DOWNLOAD_PLAN = "download_plan"
    DOWNLOAD_FETCH = "download_fetch"
    BUILD_PREPARE = "build_prepare"
    BUILD_HOMEPAGE = "build_homepage"
    BUILD_VALIDATE = "build_validate"
    CONTENT_PLAN = "content_plan"
    POST_PLAN = "post_plan"
    POST_COMPOSE = "post_compose"
    POST_AUTHOR = "post_author"
    POST_ANNOTATE = "post_annotate"
    POST_REVIEW = "post_review"
    PUBLISH = "publish"


class StageKind(StrEnum):
    AUTO = "auto"
    CHECKPOINT = "checkpoint"


class StageStatus(StrEnum):
    DONE = "done"
    WAITING = "waiting"
    FAILED = "failed"
    SKIPPED = "skipped"


EXECUTION_MILESTONES = (
    RolloutMilestone.CANARY,
    RolloutMilestone.M1,
    RolloutMilestone.M2,
    RolloutMilestone.M3,
)
MILESTONE_ORDER = EXECUTION_MILESTONES
MILESTONE_PREDECESSOR = {
    RolloutMilestone.CANARY: None,
    RolloutMilestone.M1: RolloutMilestone.CANARY,
    RolloutMilestone.M2: RolloutMilestone.M1,
    RolloutMilestone.M3: RolloutMilestone.M2,
}


__all__ = [
    "EXECUTION_MILESTONES",
    "MILESTONE_ORDER",
    "MILESTONE_PREDECESSOR",
    "AgentProvider",
    "ContentType",
    "DeploymentEnvironment",
    "ExecutionStage",
    "ReadinessMode",
    "ReplacementPolicy",
    "RolloutMilestone",
    "RuntimeEnvironment",
    "SelectionPolicy",
    "StageKind",
    "StageStatus",
]
