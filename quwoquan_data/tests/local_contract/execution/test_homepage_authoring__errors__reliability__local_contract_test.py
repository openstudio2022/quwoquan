from __future__ import annotations

from content.execution.controller import homepage_author_evidence
from core.data_issue import DataIssueCode, DataIssueLane, DataRecoveryAction


def test_homepage_materialization_exception_is_a_redacted_typed_issue() -> None:
    issue = homepage_author_evidence._homepage_finalization_unexpected_issue(
        "普陀山",
        RuntimeError("cursor crsr_secret_value failed"),
    )

    assert issue.code is DataIssueCode.INTERNAL_UNEXPECTED
    assert issue.stage.value == "build_homepage"
    assert issue.ref == "普陀山"
    assert issue.lane is DataIssueLane.HOMEPAGE
    assert issue.recovery is DataRecoveryAction.STOP
    attrs = issue.as_dict()["attrs"]
    assert attrs["errorType"] == "RuntimeError"
    assert attrs["errorMessage"] == "cursor <redacted-cursor-key> failed"
