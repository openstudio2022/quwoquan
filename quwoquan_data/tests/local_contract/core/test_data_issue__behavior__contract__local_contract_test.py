from __future__ import annotations

import pytest

from core.data_issue import (
    DataIssue,
    DataIssueCode,
    DataIssueStage,
    DataIssueLane,
    DataRecoveryAction,
    data_issue,
)
from content.execution.stage_reports import build_gate_report


def test_data_issue_round_trip_keeps_control_fields_separate_from_message() -> None:
    issue = data_issue(
        DataIssueCode.SOURCE_RETAINED_SHORTFALL,
        stage=DataIssueStage.DOWNLOAD_FETCH,
        ref="西湖",
        lane=DataIssueLane.HOMEPAGE,
        recovery=DataRecoveryAction.RETRY_SOURCE_DISCOVERY,
        message="retained=0 required=1",
        attributes={"retained": 0, "required": 1},
    )

    restored = DataIssue.from_dict(issue.as_dict())

    assert restored == issue
    assert restored.code is DataIssueCode.SOURCE_RETAINED_SHORTFALL
    assert restored.stage is DataIssueStage.DOWNLOAD_FETCH
    assert restored.attributes == (("retained", "0"), ("required", "1"))
    assert "retryable" not in issue.as_dict()


def test_data_issue_rejects_unknown_code_and_non_string_attribute_container() -> None:
    payload = data_issue(
        DataIssueCode.CONTRACT_INVALID,
        stage=DataIssueStage.DOWNLOAD_PLAN,
        message="invalid plan",
    ).as_dict()
    payload["code"] = "DATA.UNKNOWN"
    with pytest.raises(ValueError):
        DataIssue.from_dict(payload)

    payload["code"] = DataIssueCode.CONTRACT_INVALID.value
    payload["attrs"] = ["not", "an", "object"]
    with pytest.raises(ValueError, match="\\$\\.attrs"):
        DataIssue.from_dict(payload)


def test_data_issue_rejects_unknown_wire_fields_instead_of_dropping_them() -> None:
    payload = data_issue(
        DataIssueCode.AGENT_REVIEW_INVALID,
        stage=DataIssueStage.REVIEW,
        message="review result is missing independent findings",
    ).as_dict()
    payload["legacyRetryable"] = True

    with pytest.raises(ValueError, match="legacyRetryable"):
        DataIssue.from_dict(payload)


def test_data_issue_rejects_excessive_attributes() -> None:
    attributes = {f"key{index}": str(index) for index in range(17)}

    with pytest.raises(ValueError, match="property limit"):
        data_issue(
            DataIssueCode.CONTRACT_INVALID,
            stage=DataIssueStage.DOWNLOAD_PLAN,
            message="too many control fields",
            attributes=attributes,
        )


def test_data_issue_domain_constructor_rejects_wire_strings() -> None:
    with pytest.raises(TypeError, match="stage must be DataIssueStage"):
        DataIssue(
            code=DataIssueCode.CONTRACT_INVALID,
            stage="download_plan",  # type: ignore[arg-type]
            message="wire values must be decoded before domain construction",
        )


def test_stage_gate_serializes_typed_issues_without_fallback_double_truth() -> None:
    issue = data_issue(
        DataIssueCode.SOURCE_MISSING,
        stage=DataIssueStage.REVIEW,
        ref="post-1",
        recovery=DataRecoveryAction.REWIND_DOWNLOAD,
        message="evidence file missing",
    )

    report = build_gate_report(
        execution_id="20260712--travel-article-quality--cn-zhejiang--canary-001",
        command="post",
        step="review",
        ref="post-1",
        passed=False,
        issues=[issue],
    )

    assert report["issues"] == [issue.as_dict()]
    assert "fallbackStage" not in report
