"""Closed vocabularies shared by data execution and release control flow."""
from __future__ import annotations

from enum import StrEnum


class ContentType(StrEnum):
    HOMEPAGE = "homepage"
    ARTICLE = "article"
    IMAGE = "image"
    VIDEO = "video"


class ExecutionSpecStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"


class ModalityContract(StrEnum):
    SEPARATED_RESEARCH = "separated_research"


class ImageAssetStrategy(StrEnum):
    OPEN_LICENSE_PUBLISH = "open_license_publish"
    LICENSED_PROVIDER_PUBLISH = "licensed_provider_publish"
    AI_GENERATED_ORIGINAL = "ai_generated_original"
    REFERENCE_ONLY_NO_IMAGE_RELEASE = "reference_only_no_image_release"


class ImageCountPolicy(StrEnum):
    SCORE_BONUS = "score_bonus"
    HARD_QUOTA = "hard_quota"


class RolloutMilestone(StrEnum):
    BASELINE = "baseline"
    CANARY = "canary"
    M1 = "m1"
    M2 = "m2"
    M3 = "m3"
    LAUNCH = "launch"


class DeploymentEnvironment(StrEnum):
    ALPHA = "alpha"
    BETA = "beta"
    GAMMA = "gamma"
    PROD = "prod"


class SelectionPolicy(StrEnum):
    FROZEN = "frozen"


class ReplacementPolicy(StrEnum):
    FORBIDDEN = "forbidden"


class SourcePolicyRevision(StrEnum):
    ENCYCLOPEDIA_PRIMARY = "encyclopedia-primary"
    RIGHTS_CLEARED_CONTENT = "rights-cleared-content"
    GOVERNANCE_PROJECTION = "governance-projection"


class RuntimeEnvironment(StrEnum):
    LOCAL = "local"
    CLOUD = "cloud"


class AgentProvider(StrEnum):
    CURSOR_SDK = "cursor_sdk"


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


class ExecutionStateStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    STOPPED_AT_UNTIL = "stopped_at_until"
    WAITING_AGENT = "waiting_agent"
    REPAIRING = "repairing"
    MANUAL_REQUIRED = "manual_required"
    SUCCEEDED = "succeeded"


class PostStage(StrEnum):
    COMPOSE_BRIEF = "compose-brief"
    ANNOTATE_ENTITIES = "annotate-entities"
    REVIEW = "review"


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
    "ExecutionStateStatus",
    "PostStage",
    "ReadinessMode",
    "ReplacementPolicy",
    "RolloutMilestone",
    "RuntimeEnvironment",
    "SelectionPolicy",
    "SourcePolicyRevision",
    "StageKind",
    "StageStatus",
]
