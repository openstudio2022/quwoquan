"""Closed vocabularies shared by data execution and release control flow."""
from __future__ import annotations

from enum import StrEnum


class ContentType(StrEnum):
    HOMEPAGE = "homepage"
    ARTICLE = "article"
    IMAGE = "image"
    VIDEO = "video"


class ContentGenerator(StrEnum):
    """Canonical provenance state at the content generation boundary."""

    AGENT = "agent"
    IMAGE_EVIDENCE_PACK = "image_evidence_pack"
    PENDING = "pending"


def expected_content_generator(content_type: ContentType) -> ContentGenerator:
    """Return the only valid publication generator for one carrier."""

    if content_type is ContentType.IMAGE:
        return ContentGenerator.IMAGE_EVIDENCE_PACK
    return ContentGenerator.AGENT


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
    ATTRIBUTION_AUDITED_PUBLISH = "attribution_audited_publish"


class ImageCountPolicy(StrEnum):
    SCORE_BONUS = "score_bonus"
    HARD_QUOTA = "hard_quota"


class ExecutionPhase(StrEnum):
    """Generic runtime scale marker; product campaigns are never static types."""

    PILOT = "pilot"
    SCALE = "scale"
    FULL = "full"


class RolloutMilestone(StrEnum):
    BASELINE = "baseline"
    CANARY = "canary"
    M1 = "m1"
    M2 = "m2"
    M3 = "m3"
    H10K = "h10k"
    LAUNCH = "launch"


class DeploymentEnvironment(StrEnum):
    ALPHA = "alpha"
    BETA = "beta"
    GAMMA = "gamma"
    PROD = "prod"


class ReleaseRunKind(StrEnum):
    APPLY = "apply"
    VERIFY = "verify"
    ROLLBACK = "rollback"


class ReleaseRunStatus(StrEnum):
    PREPARED = "prepared"
    COMPLETED = "completed"
    DRY_RUN = "dry_run"
    FAILED = "failed"


class ContentImportStatus(StrEnum):
    ACTIVE = "active"
    DRY_RUN = "dry-run"


class ReleaseSyncMode(StrEnum):
    UPSERT = "upsert"
    SYNC = "sync"


class ReleaseDeletePolicy(StrEnum):
    TOMBSTONE = "tombstone"


class ReleaseSourceOwner(StrEnum):
    QWQ_DATA = "qwq_data"


class AppUatStatus(StrEnum):
    PASSED = "passed"


class AppUatDataSource(StrEnum):
    REMOTE = "remote"


class QueueBackend(StrEnum):
    LOCAL_FILE = "local_file"
    RELIABLE_TASK = "reliabletask"


class QueueJobState(StrEnum):
    QUEUED = "queued"
    LEASED = "leased"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    DEAD = "dead"
    SPILLED = "spilled"


class QueueJobStage(StrEnum):
    """Closed work kinds accepted by the object execution queue."""

    DOWNLOAD = "download"
    AUTHOR = "author"
    PUBLISH = "publish"


class QueueFailureKind(StrEnum):
    """Machine-readable reason class for a queue transition to failure."""

    EXECUTION = "execution"
    GOVERNANCE = "governance"
    STARTUP = "startup"
    RESULT_ENVELOPE = "result_envelope"
    BUDGET = "budget"
    TIMEOUT = "timeout"


class QueueTimelineEvent(StrEnum):
    """Auditable queue lifecycle events; free-form text belongs in attrs only."""

    BLOCKED = "blocked"
    LEASED = "leased"
    SUCCEEDED = "succeeded"
    ENVELOPE_ACCEPTED = "envelope_accepted"
    RECONCILED = "reconciled"
    FAILED = "failed"
    REQUEUED = "requeued"
    REVIVED = "revived"
    RECLAIMED = "reclaimed"


class ReviewItemKind(StrEnum):
    ARTICLE = "article"
    FACT = "fact"
    IMAGE = "image"


class ReviewJudgment(StrEnum):
    CREDIBLE = "credible"
    DOUBTFUL = "doubtful"
    UNJUDGED = "unjudged"


class ReviewOverride(StrEnum):
    PUBLISHABLE = "publishable"
    DISCARD = "discard"


class ReviewPublishState(StrEnum):
    FIX = "fix"
    DISCARD = "discard"
    PUBLISHABLE = "publishable"


class ImageSafetyReviewStatus(StrEnum):
    SAFE = "safe"
    TEXT_HEAVY = "text_heavy"
    NEEDS_REVIEW = "needs_review"
    UNSAFE = "unsafe"


class SelectionPolicy(StrEnum):
    FROZEN = "frozen"


class TargetSelector(StrEnum):
    """Explicit ordering policy for one frozen execution target set."""

    ALL = "all"
    PRIORITY = "priority"
    SOURCE_READY_PRIORITY = "source-ready-priority"


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
    CODEX_SDK = "codex_sdk"


class AgentRunStatus(StrEnum):
    """Terminal status returned by the only managed-agent boundary."""

    FINISHED = "finished"
    ERROR = "error"


class ManagedAgentCheckpointStatus(StrEnum):
    """Lifecycle state of the persisted checkpoint record."""

    COMPLETED = "completed"
    INTERRUPTED = "interrupted"


class AgentFailureKind(StrEnum):
    """Closed failure classes for Cursor SDK and its isolated subprocess."""

    SDK_UNAVAILABLE = "sdk_unavailable"
    CREDENTIAL_INVALID = "credential_invalid"
    BUDGET_EXCEEDED = "budget_exceeded"
    BRIDGE_UNAVAILABLE = "bridge_unavailable"
    SDK_EXECUTION_FAILED = "sdk_execution_failed"
    NO_RESULT = "no_result"
    SUBPROCESS_TIMEOUT = "subprocess_timeout"
    SUBPROCESS_OUTPUT_INVALID = "subprocess_output_invalid"
    SUBPROCESS_EXITED = "subprocess_exited"
    FUTURE_TIMEOUT = "future_timeout"
    CHECKPOINT_GATE = "checkpoint_gate"


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
    RolloutMilestone.H10K,
)
MILESTONE_ORDER = EXECUTION_MILESTONES
MILESTONE_PREDECESSOR = {
    RolloutMilestone.CANARY: None,
    RolloutMilestone.M1: RolloutMilestone.CANARY,
    RolloutMilestone.M2: RolloutMilestone.M1,
    RolloutMilestone.M3: RolloutMilestone.M2,
    RolloutMilestone.H10K: RolloutMilestone.M3,
}


__all__ = [
    "EXECUTION_MILESTONES",
    "MILESTONE_ORDER",
    "MILESTONE_PREDECESSOR",
    "AgentFailureKind",
    "AgentProvider",
    "AgentRunStatus",
    "ManagedAgentCheckpointStatus",
    "AppUatDataSource",
    "AppUatStatus",
    "ContentImportStatus",
    "ContentType",
    "DeploymentEnvironment",
    "ExecutionStage",
    "ExecutionStateStatus",
    "ImageSafetyReviewStatus",
    "PostStage",
    "ReadinessMode",
    "QueueBackend",
    "QueueFailureKind",
    "QueueJobStage",
    "QueueJobState",
    "QueueTimelineEvent",
    "ReleaseDeletePolicy",
    "ReleaseRunKind",
    "ReleaseRunStatus",
    "ReleaseSourceOwner",
    "ReleaseSyncMode",
    "ReviewItemKind",
    "ReviewJudgment",
    "ReviewOverride",
    "ReviewPublishState",
    "ReplacementPolicy",
    "RolloutMilestone",
    "RuntimeEnvironment",
    "SelectionPolicy",
    "SourcePolicyRevision",
    "StageKind",
    "StageStatus",
]
