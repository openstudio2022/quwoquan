"""Closed vocabulary shared by canonical release and environment shipping."""
from __future__ import annotations

from enum import StrEnum

from core.control_types import DeploymentEnvironment, RolloutMilestone


class ImportMode(StrEnum):
    UPSERT = "upsert"
    SYNC = "sync"


class DeletePolicy(StrEnum):
    NONE = "none"
    TOMBSTONE = "tombstone"


class DataSourceOwner(StrEnum):
    QWQ_DATA = "qwq_data"


class ReleaseKind(StrEnum):
    CONTENT = "content"
    EMPTY_BASELINE = "empty_baseline"


class EvidenceStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"


ROLLOUT_MILESTONES = (
    RolloutMilestone.CANARY,
    RolloutMilestone.M1,
    RolloutMilestone.M2,
    RolloutMilestone.M3,
    RolloutMilestone.H10K,
    RolloutMilestone.LAUNCH,
)
FULL_SYNC_MILESTONES = (RolloutMilestone.BASELINE, *ROLLOUT_MILESTONES)
DEPLOYMENT_ENVIRONMENTS = tuple(DeploymentEnvironment)


__all__ = [
    "DEPLOYMENT_ENVIRONMENTS",
    "FULL_SYNC_MILESTONES",
    "ROLLOUT_MILESTONES",
    "DataSourceOwner",
    "DeletePolicy",
    "DeploymentEnvironment",
    "EvidenceStatus",
    "ImportMode",
    "ReleaseKind",
    "RolloutMilestone",
]
