"""Pure typed-issue routing for download/build stage orchestration."""
from __future__ import annotations

from core.control_types import ExecutionStage
from core.data_issue import DataIssue

from content.execution.support import (
    Any,
    DataIssueCode,
    DataIssueStage,
    DataRecoveryAction,
    Mapping,
    data_issue,
)
from content.execution.workspace import ExecutionSourceDigestDriftError

_MEDIA_RECOVERY_BY_CODE = {
    DataIssueCode.MEDIA_ENUMERATION_INCOMPLETE: DataRecoveryAction.REWIND_DOWNLOAD,
    DataIssueCode.MEDIA_DOWNLOAD_INCOMPLETE: DataRecoveryAction.REWIND_DOWNLOAD,
    DataIssueCode.MEDIA_CAPTION_INVALID: DataRecoveryAction.REWIND_COMPOSE,
    DataIssueCode.MEDIA_COVER_CONFLICT: DataRecoveryAction.REWIND_COMPOSE,
}


def typed_media_validation_issues(
    media_report: Mapping[str, Any],
) -> tuple[DataIssue, ...]:
    return tuple(
        DataIssue(
            code=issue.code,
            stage=DataIssueStage.BUILD_VALIDATE,
            message=issue.message,
            ref=issue.ref,
            lane=issue.lane,
            recovery=_MEDIA_RECOVERY_BY_CODE.get(issue.code, DataRecoveryAction.STOP),
            attributes=issue.attributes,
        )
        for issue in (
            DataIssue.from_dict(row)
            for row in (media_report.get("issues") or [])
            if isinstance(row, Mapping)
        )
    )


def media_validation_fallback(issues: tuple[DataIssue, ...]) -> ExecutionStage:
    codes = {issue.code for issue in issues}
    if DataIssueCode.MEDIA_ENUMERATION_INCOMPLETE in codes:
        return ExecutionStage.DOWNLOAD_PLAN
    if DataIssueCode.MEDIA_DOWNLOAD_INCOMPLETE in codes:
        return ExecutionStage.DOWNLOAD_FETCH
    return ExecutionStage.BUILD_HOMEPAGE


def source_digest_drift_issue(
    error: ExecutionSourceDigestDriftError,
) -> DataIssue:
    """Render immutable input drift without treating it as a source retry."""
    return data_issue(
        DataIssueCode.CONTRACT_INVALID,
        stage=DataIssueStage.DOWNLOAD_FETCH,
        recovery=DataRecoveryAction.STOP,
        message="execution source digest drift; execution must be recreated",
        attributes={"contract": "sourceDigest", "reason": str(error)},
    )
