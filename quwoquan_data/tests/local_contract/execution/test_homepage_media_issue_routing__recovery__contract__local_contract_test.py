from __future__ import annotations

from content.execution.controller.stage_download_build import (
    _media_validation_fallback,
    _typed_media_validation_issues,
)
from core.control_types import ExecutionStage
from core.data_issue import (
    DataIssueCode,
    DataIssueStage,
    DataRecoveryAction,
    data_issue,
)


def _wire_issue(code: DataIssueCode) -> dict[str, object]:
    return data_issue(
        code,
        stage=DataIssueStage.VERIFY_HOMEPAGE_MEDIA,
        message="media contract failed",
        ref="test-entity-a",
    ).as_dict()


def test_cover_conflict_preserves_code_and_rewinds_homepage_build() -> None:
    issues = _typed_media_validation_issues(
        {"issues": [_wire_issue(DataIssueCode.MEDIA_COVER_CONFLICT)]}
    )

    assert issues[0].code is DataIssueCode.MEDIA_COVER_CONFLICT
    assert issues[0].stage is DataIssueStage.BUILD_VALIDATE
    assert issues[0].recovery is DataRecoveryAction.REWIND_COMPOSE
    assert _media_validation_fallback(issues) is ExecutionStage.BUILD_HOMEPAGE


def test_download_issue_takes_precedence_over_cover_rebuild() -> None:
    issues = _typed_media_validation_issues(
        {
            "issues": [
                _wire_issue(DataIssueCode.MEDIA_COVER_CONFLICT),
                _wire_issue(DataIssueCode.MEDIA_DOWNLOAD_INCOMPLETE),
            ]
        }
    )

    assert {issue.code for issue in issues} == {
        DataIssueCode.MEDIA_COVER_CONFLICT,
        DataIssueCode.MEDIA_DOWNLOAD_INCOMPLETE,
    }
    assert _media_validation_fallback(issues) is ExecutionStage.DOWNLOAD_FETCH
