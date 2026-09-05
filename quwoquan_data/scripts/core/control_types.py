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


class ExecutionPhase(StrEnum):
    """Generic runtime scale marker; product runs are never static types."""

    PILOT = "pilot"
    SCALE = "scale"
    FULL = "full"


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


class SourcePolicyRevision(StrEnum):
    ENCYCLOPEDIA_PRIMARY = "encyclopedia-primary"
    RIGHTS_CLEARED_CONTENT = "rights-cleared-content"
    GOVERNANCE_PROJECTION = "governance-projection"


class ReceiptStage(StrEnum):
    """producer 九阶段 receipt 协议的阶段闭集（DEC-005）。

    对象目录下的过程阶段是本闭集的一个连续子段，不是另一份枚举。receipt CLI、
    工作包目录契约与 layout 门禁都从这里取值——同一个阶段名在三处各写一遍时，
    改名只改了其中一处不会被任何判据发现。
    """

    PLAN = "0.plan"
    SOURCES = "sources"
    DOWNLOAD = "1.download"
    QUALITY = "2.quality"
    COMPOSE = "3.compose"
    DRAFT = "4.draft"
    REVIEW = "5.review"
    PUBLISH = "publish"
    RELEASE = "release"


RECEIPT_STAGE_SEQUENCE: tuple[ReceiptStage, ...] = (
    ReceiptStage.PLAN,
    ReceiptStage.SOURCES,
    ReceiptStage.DOWNLOAD,
    ReceiptStage.QUALITY,
    ReceiptStage.COMPOSE,
    ReceiptStage.DRAFT,
    ReceiptStage.REVIEW,
    ReceiptStage.PUBLISH,
    ReceiptStage.RELEASE,
)

# 逐对象推进、在对象目录下留痕的阶段。显式列出而不是对上面的序列切片：切片会让
# 「哪几个阶段落在对象目录下」变成一个要靠索引数出来的事实。
OBJECT_STAGE_SEQUENCE: tuple[ReceiptStage, ...] = (
    ReceiptStage.DOWNLOAD,
    ReceiptStage.QUALITY,
    ReceiptStage.COMPOSE,
    ReceiptStage.DRAFT,
    ReceiptStage.REVIEW,
)


class MediaHoldingState(StrEnum):
    """一条媒体引用在 content library 上的兑现终态闭集。

    三种不可兑现互不塌陷。库整体不可达是一个库级事实，不得展开成逐条引用缺席：
    展开后读到的是「全部引用缺席」，指向逐对象排查，而真实故障是一次卷掉线或一次
    目录迁移。缺席与漂移也不合并——缺席说明字节从未入库或已被回收，漂移说明库里
    那份字节不是记录里那份，两者的恢复动作不同。
    """

    HONOURED = "honoured"
    ABSENT = "absent"
    DRIFTED = "drifted"
    LIBRARY_UNREACHABLE = "library_unreachable"


class MediaClosureVerdict(StrEnum):
    """一个 release 的媒体闭包判定终态闭集。

    `LIBRARY_UNREACHABLE` 与 `REFERENCES_UNHONOURED` 是两个可区分的终态，前者不得
    展开成后者：库不可达时判定连一条引用都查不了，因此它给出的不是「每条都缺席」
    这个逐对象结论，而是「无法逐条判」这个库级结论，恢复动作也落在库上。
    """

    HONOURED = "honoured"
    REFERENCES_UNHONOURED = "references_unhonoured"
    LIBRARY_UNREACHABLE = "library_unreachable"


class MediaDurabilityState(StrEnum):
    """release 媒体字节的耐久性状态闭集。

    `NOT_ESTABLISHED` 是默认取值，也是闭包判定唯一能得出的取值：库当前可读、
    配置里写着备份目标，都只说明控制面在场，不说明字节有第二个持有方。置位到
    `VERIFIED` 需要一次在隔离恢复目标上的真实恢复证据，那条路径不由本判定给出
    ——本判定只保证耐久性不被默认宣称。
    """

    NOT_ESTABLISHED = "not_established"
    VERIFIED = "verified"


class MediaHoldingRecoveryAction(StrEnum):
    """媒体引用不可兑现时的恢复动作闭集。

    闭集里没有「重新采集原始素材」。交付副本经过重编码、取封面帧与格式转换，没有
    上游能逐字节复现，而原始采集素材在对象产出后已被回收；把重采写进恢复路径等于
    给出一条走不通的出路，读者会据此以为字节还有退路。
    """

    RESTORE_FROM_INDEPENDENT_HOLDER = "restore_from_independent_holder"
    ADMIT_CARRIED_BYTES = "admit_carried_bytes"
    REATTACH_LIBRARY = "reattach_library"
    NONE = "none"




__all__ = [
    "AppUatDataSource", "AppUatStatus", "ContentGenerator", "ContentImportStatus",
    "ContentType", "DeploymentEnvironment", "ExecutionPhase", "ImageSafetyReviewStatus", "MediaClosureVerdict",
    "MediaDurabilityState", "MediaHoldingRecoveryAction", "MediaHoldingState",
    "OBJECT_STAGE_SEQUENCE",
    "RECEIPT_STAGE_SEQUENCE", "ReceiptStage", "ReleaseDeletePolicy",
    "ReleaseRunKind", "ReleaseRunStatus", "ReleaseSourceOwner", "ReleaseSyncMode",
    "ReviewItemKind", "ReviewJudgment", "ReviewOverride",
    "ReviewPublishState", "SourcePolicyRevision",
    "expected_content_generator",
]
