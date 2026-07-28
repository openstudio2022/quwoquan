"""Bounded diagnostics for unexpected execution failures."""
from __future__ import annotations

import traceback

from core.data_issue import (
    DataIssue,
    DataIssueCode,
    DataIssueStage,
    DataRecoveryAction,
    data_issue,
)


def unexpected_stage_issue(
    stage: DataIssueStage | str,
    exc: Exception,
    *,
    recovery: DataRecoveryAction = DataRecoveryAction.STOP,
    message: str = "execution stage raised an unexpected exception",
) -> DataIssue:
    """Convert an exception to actionable evidence without a traceback dump."""

    stage_value = stage if isinstance(stage, DataIssueStage) else DataIssueStage(str(stage))
    error_message = " ".join(str(exc).split())[:400] or type(exc).__name__
    frames = traceback.extract_tb(exc.__traceback__)
    location = ""
    if frames:
        frame = frames[-1]
        location = f"{frame.filename.rsplit('/', 1)[-1]}:{frame.lineno}:{frame.name}"
    return data_issue(
        DataIssueCode.INTERNAL_UNEXPECTED,
        stage=stage_value,
        recovery=recovery,
        message=message,
        attributes={
            "errorType": type(exc).__name__,
            "errorMessage": error_message,
            "errorLocation": location,
        },
    )


__all__ = ["unexpected_stage_issue"]
