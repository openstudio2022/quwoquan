"""Typed object-level failures for source fetch batch isolation."""

from __future__ import annotations

from core.data_issue import (
    DataIssue,
    DataIssueCode,
    DataIssueLane,
    DataIssueStage,
    DataRecoveryAction,
    data_issue,
)


def _issue_lane(selected_lanes: set[str] | None) -> DataIssueLane:
    if selected_lanes == {"homepage"}:
        return DataIssueLane.HOMEPAGE
    if selected_lanes == {"article"}:
        return DataIssueLane.ARTICLE
    if selected_lanes == {"image"}:
        return DataIssueLane.IMAGE
    if selected_lanes == {"video"}:
        return DataIssueLane.VIDEO
    return DataIssueLane.ALL


def entity_fetch_issue(
    entity_id: str,
    exc: Exception,
    *,
    selected_lanes: set[str] | None,
) -> DataIssue:
    """Convert one entity exception into a retryable typed exclusion."""

    if isinstance(exc, (ValueError, TypeError)):
        code = DataIssueCode.CONTRACT_INVALID
    elif isinstance(exc, (OSError, TimeoutError)):
        code = DataIssueCode.SOURCE_UNREADABLE
    else:
        code = DataIssueCode.INTERNAL_UNEXPECTED
    return data_issue(
        code,
        stage=DataIssueStage.DOWNLOAD_FETCH,
        ref=entity_id,
        lane=_issue_lane(selected_lanes),
        recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
        message=(
            f"entity source fetch excluded after {type(exc).__name__}: "
            f"{str(exc)[:300]}"
        ),
        attributes={
            "errorType": type(exc).__name__,
            "disposition": "excluded",
        },
    )


__all__ = ["entity_fetch_issue"]
