"""Strongly typed issue contract for offline data workflows.

Data issues are internal workflow outcomes, not HTTP error responses.  Stable
codes and recovery actions drive orchestration; ``message`` is presentation
only and must never be parsed to select a control-flow branch.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class DataIssueCode(StrEnum):
    SOURCE_MISSING = "DATA.SOURCE.MISSING"
    SOURCE_UNREADABLE = "DATA.SOURCE.UNREADABLE"
    SOURCE_PLAN_INVALID = "DATA.SOURCE.PLAN_INVALID"
    SOURCE_RETAINED_SHORTFALL = "DATA.SOURCE.RETAINED_SHORTFALL"
    SOURCE_CATEGORY_SHORTFALL = "DATA.SOURCE.CATEGORY_SHORTFALL"
    SOURCE_PRIMARY_AUTHORITY_MISSING = "DATA.SOURCE.PRIMARY_AUTHORITY_MISSING"
    SOURCE_ENTITY_MISMATCH = "DATA.SOURCE.ENTITY_MISMATCH"
    SOURCE_PAGE_TYPE_INVALID = "DATA.SOURCE.PAGE_TYPE_INVALID"
    SOURCE_CONTENT_INCOMPLETE = "DATA.SOURCE.CONTENT_INCOMPLETE"
    SOURCE_QUALIFICATION_EXHAUSTED = "DATA.SOURCE.QUALIFICATION_EXHAUSTED"
    MEDIA_FETCH_FAILED = "DATA.MEDIA.FETCH_FAILED"
    MEDIA_RIGHTS_UNAVAILABLE = "DATA.MEDIA.RIGHTS_UNAVAILABLE"
    MEDIA_PUBLISHABLE_SHORTFALL = "DATA.MEDIA.PUBLISHABLE_SHORTFALL"
    MEDIA_ENUMERATION_INCOMPLETE = "DATA.MEDIA.ENUMERATION_INCOMPLETE"
    MEDIA_DOWNLOAD_INCOMPLETE = "DATA.MEDIA.DOWNLOAD_INCOMPLETE"
    MEDIA_CAPTION_INVALID = "DATA.MEDIA.CAPTION_INVALID"
    MEDIA_COVER_CONFLICT = "DATA.MEDIA.COVER_CONFLICT"
    AGENT_REVIEW_UNAVAILABLE = "DATA.AGENT.REVIEW_UNAVAILABLE"
    AGENT_REVIEW_INVALID = "DATA.AGENT.REVIEW_INVALID"
    AGENT_EXECUTION_FAILED = "DATA.AGENT.EXECUTION_FAILED"
    AGENT_CREDENTIAL_INVALID = "DATA.AGENT.CREDENTIAL_INVALID"
    AGENT_PROVIDER_REJECTED = "DATA.AGENT.PROVIDER_REJECTED"
    AGENT_SCALE_CALIBRATION_REQUIRED = "DATA.AGENT.SCALE_CALIBRATION_REQUIRED"
    AGENT_TIMEOUT = "DATA.AGENT.TIMEOUT"
    AGENT_RESULT_INVALID = "DATA.AGENT.RESULT_INVALID"
    CONTENT_CLASSIFICATION_REJECTED = "DATA.CONTENT.CLASSIFICATION_REJECTED"
    ENVIRONMENT_NOT_READY = "DATA.ENVIRONMENT.NOT_READY"
    NETWORK_UNREACHABLE = "DATA.INFRA.NETWORK_UNREACHABLE"
    CONTRACT_INVALID = "DATA.CONTRACT.INVALID"
    QUALITY_FAILED = "DATA.QUALITY.FAILED"
    QUEUE_EXECUTION_FAILED = "DATA.QUEUE.EXECUTION_FAILED"
    QUEUE_GOVERNANCE_INVALID = "DATA.QUEUE.GOVERNANCE_INVALID"
    QUEUE_STARTUP_FAILED = "DATA.QUEUE.STARTUP_FAILED"
    QUEUE_RESULT_ENVELOPE_INVALID = "DATA.QUEUE.RESULT_ENVELOPE_INVALID"
    QUEUE_TIMEOUT = "DATA.QUEUE.TIMEOUT"
    INTERNAL_UNEXPECTED = "DATA.INTERNAL.UNEXPECTED"


class DataIssueLane(StrEnum):
    ALL = "all"
    HOMEPAGE = "homepage"
    ARTICLE = "article"
    IMAGE = "image"
    VIDEO = "video"


class DataIssueStage(StrEnum):
    ANNOTATE_ENTITIES = "annotate-entities"
    AGENT_COMPOSE = "agent_compose"
    AUTHOR = "author"
    BASELINE = "baseline"
    BUILD_HOMEPAGE = "build_homepage"
    BUILD_PREPARE = "build_prepare"
    BUILD_VALIDATE = "build_validate"
    COMPOSE_BRIEF = "compose_brief"
    CONTENT_PLAN = "content_plan"
    CONTROLLER_YIELD = "controller_yield"
    DOWNLOAD = "download"
    DOWNLOAD_FETCH = "download_fetch"
    DOWNLOAD_PLAN = "download_plan"
    DRAFT = "4.draft"
    ENTITY_SOURCE_BUNDLE = "entity_source_bundle"
    EXPLORE = "explore"
    IMAGE_FETCH = "image_fetch"
    IMAGE_RIGHTS = "image_rights"
    MEDIA_CHECK = "media_check"
    POST_COMPOSE = "post_compose"
    POST_PLAN = "post_plan"
    POST_AUTHOR = "post_author"
    POST_ANNOTATE = "post_annotate"
    POST_REVIEW = "post_review"
    PUBLISH = "publish"
    QUALITY_ANALYSIS = "quality_analysis"
    REVIEW = "review"
    SOURCE_GATE = "source_gate"
    SOURCE_PLAN = "source_plan"
    SOURCE_SCREEN = "source_screen"
    VERIFY_HOMEPAGE_MEDIA = "verify_homepage_media"


class DataRecoveryAction(StrEnum):
    RETRY_SOURCE_DISCOVERY = "retry_source_discovery"
    REPLACE_SOURCE = "replace_source"
    REPLACE_MEDIA = "replace_media"
    REWIND_DOWNLOAD = "rewind_download"
    REWIND_COMPOSE = "rewind_compose"
    RETRY_AGENT = "retry_agent"
    MANUAL_REVIEW = "manual_review"
    STOP = "stop"


@dataclass(frozen=True, slots=True)
class DataIssue:
    code: DataIssueCode
    stage: DataIssueStage
    message: str
    ref: str = ""
    lane: DataIssueLane = DataIssueLane.ALL
    recovery: DataRecoveryAction = DataRecoveryAction.STOP
    attributes: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.code, DataIssueCode):
            raise TypeError("DataIssue.code must be DataIssueCode")
        if not isinstance(self.stage, DataIssueStage):
            raise TypeError("DataIssue.stage must be DataIssueStage")
        if not isinstance(self.lane, DataIssueLane):
            raise TypeError("DataIssue.lane must be DataIssueLane")
        if not isinstance(self.recovery, DataRecoveryAction):
            raise TypeError("DataIssue.recovery must be DataRecoveryAction")
        if not self.message.strip():
            raise ValueError("DataIssue.message must not be empty")
        normalized: list[tuple[str, str]] = []
        seen: set[str] = set()
        for raw_key, raw_value in self.attributes:
            key = str(raw_key).strip()
            value = str(raw_value).strip()
            if not key or key in seen:
                raise ValueError(f"DataIssue.attributes key invalid or duplicated: {key!r}")
            if len(key) > 64 or len(value) > 512:
                raise ValueError(f"DataIssue.attributes exceeds size limit: {key!r}")
            seen.add(key)
            normalized.append((key, value))
        if len(normalized) > 16:
            raise ValueError("DataIssue.attributes exceeds property limit")
        object.__setattr__(self, "attributes", tuple(normalized))

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code.value,
            "stage": self.stage.value,
            "ref": self.ref,
            "lane": self.lane.value,
            "recovery": self.recovery.value,
            "message": self.message,
            "attrs": {key: value for key, value in self.attributes},
        }
        from core.schema import assert_valid

        assert_valid(payload, "_common", "data_issue", label=f"data_issue:{self.code.value}")
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> DataIssue:
        if not isinstance(payload, Mapping):
            raise TypeError("DataIssue payload must be an object")
        # Validate the original wire payload before reconstructing the value
        # object.  Validating only ``issue.as_dict()`` would silently discard an
        # unknown wire field and turn a contract drift into an apparent success.
        from core.schema import assert_valid

        assert_valid(dict(payload), "_common", "data_issue", label="data_issue")
        attrs = payload.get("attrs")
        if attrs is None:
            attrs = {}
        if not isinstance(attrs, Mapping):
            raise TypeError("DataIssue.attrs must be an object")
        issue = cls(
            code=DataIssueCode(str(payload.get("code") or "")),
            stage=DataIssueStage(str(payload.get("stage") or "")),
            ref=str(payload.get("ref") or ""),
            lane=DataIssueLane(str(payload.get("lane") or DataIssueLane.ALL.value)),
            recovery=DataRecoveryAction(str(payload.get("recovery") or "")),
            message=str(payload.get("message") or ""),
            attributes=tuple((str(key), str(value)) for key, value in attrs.items()),
        )
        return issue

    def __str__(self) -> str:
        prefix = f"{self.ref}: " if self.ref else ""
        return f"{prefix}[{self.code.value}] {self.message}"


class DataIssueError(RuntimeError):
    """Fail a workflow boundary with validated, machine-actionable issues.

    A stage may still render a concise human message, but it must not throw an
    untyped ``ValueError``/``RuntimeError`` across the orchestration boundary
    when the cause is already known as a data-control-plane outcome.
    """

    def __init__(self, issues: Sequence[DataIssue]) -> None:
        normalized = tuple(issues)
        if not normalized:
            raise ValueError("DataIssueError requires at least one DataIssue")
        if not all(isinstance(issue, DataIssue) for issue in normalized):
            raise TypeError("DataIssueError issues must be DataIssue values")
        self.issues = normalized
        super().__init__("; ".join(issue_messages(normalized)))


def data_issue(
    code: DataIssueCode,
    *,
    stage: DataIssueStage,
    message: str,
    ref: str = "",
    lane: DataIssueLane = DataIssueLane.ALL,
    recovery: DataRecoveryAction = DataRecoveryAction.STOP,
    attributes: Mapping[str, object] | None = None,
) -> DataIssue:
    return DataIssue(
        code=code,
        stage=stage,
        message=message,
        ref=ref,
        lane=lane,
        recovery=recovery,
        attributes=tuple(
            (str(key), str(value)) for key, value in (attributes or {}).items()
        ),
    )


def issue_messages(issues: Iterable[DataIssue]) -> list[str]:
    return [str(issue) for issue in issues]


def data_issues(
    code: DataIssueCode,
    *,
    stage: DataIssueStage,
    messages: Iterable[object],
    ref: str = "",
    lane: DataIssueLane = DataIssueLane.ALL,
    recovery: DataRecoveryAction = DataRecoveryAction.STOP,
) -> list[DataIssue]:
    return [
        data_issue(
            code,
            stage=stage,
            message=str(message),
            ref=ref,
            lane=lane,
            recovery=recovery,
        )
        for message in messages
        if str(message).strip()
    ]


def issues_for_ref(issues: Sequence[DataIssue], ref: str) -> list[DataIssue]:
    return [issue for issue in issues if issue.ref == ref]


__all__ = [
    "DataIssue",
    "DataIssueCode",
    "DataIssueError",
    "DataIssueLane",
    "DataIssueStage",
    "DataRecoveryAction",
    "data_issue",
    "data_issues",
    "issue_messages",
    "issues_for_ref",
]
