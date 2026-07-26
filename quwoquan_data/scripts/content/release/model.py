"""Closed vocabulary shared by canonical release and environment shipping."""
from __future__ import annotations

from enum import StrEnum

from core.control_types import DeploymentEnvironment


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


FULL_SYNC_RELEASE_KINDS = (ReleaseKind.CONTENT, ReleaseKind.EMPTY_BASELINE)
DEPLOYMENT_ENVIRONMENTS = tuple(DeploymentEnvironment)


__all__ = [
    "DEPLOYMENT_ENVIRONMENTS",
    "FULL_SYNC_RELEASE_KINDS",
    "DataSourceOwner",
    "DeletePolicy",
    "DeploymentEnvironment",
    "EvidenceStatus",
    "ImportMode",
    "ReleaseKind",
]
