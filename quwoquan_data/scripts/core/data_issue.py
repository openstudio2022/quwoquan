"""Strongly typed issue contract for offline data workflows.

Data issues are diagnostic outcomes, not HTTP error responses. Stable codes,
messages and optional refs/origins describe failures; consumers must not derive
recovery control flow from them.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class DataIssueCode(StrEnum):
    MEDIA_ENUMERATION_INCOMPLETE = "DATA.MEDIA.ENUMERATION_INCOMPLETE"
    MEDIA_DOWNLOAD_INCOMPLETE = "DATA.MEDIA.DOWNLOAD_INCOMPLETE"
    MEDIA_CAPTION_INVALID = "DATA.MEDIA.CAPTION_INVALID"
    MEDIA_COVER_CONFLICT = "DATA.MEDIA.COVER_CONFLICT"
    CONTRACT_INVALID = "DATA.CONTRACT.INVALID"




@dataclass(frozen=True, slots=True)
class DataIssue:
    code: DataIssueCode
    message: str
    ref: str = ""
    origin: str = ""
    attributes: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.code, DataIssueCode):
            raise TypeError("DataIssue.code must be DataIssueCode")
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
            "ref": self.ref,
            "origin": self.origin,
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
            ref=str(payload.get("ref") or ""),
            origin=str(payload.get("origin") or ""),
            message=str(payload.get("message") or ""),
            attributes=tuple((str(key), str(value)) for key, value in attrs.items()),
        )
        return issue

    def __str__(self) -> str:
        prefix = f"{self.ref}: " if self.ref else ""
        return f"{prefix}[{self.code.value}] {self.message}"


class DataIssueError(RuntimeError):
    """Fail a workflow boundary with validated, machine-actionable issues.

    A verifier may still render a concise human message, but it must not throw an
    untyped exception when the cause is already known as a diagnostic outcome.
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
    origin: str = "",
    message: str,
    ref: str = "",
    attributes: Mapping[str, object] | None = None,
) -> DataIssue:
    return DataIssue(
        code=code,
        message=message,
        ref=ref,
        origin=origin,
        attributes=tuple(
            (str(key), str(value)) for key, value in (attributes or {}).items()
        ),
    )


def issue_messages(issues: Iterable[DataIssue]) -> list[str]:
    return [str(issue) for issue in issues]


def data_issues(
    code: DataIssueCode,
    *,
    origin: str = "",
    messages: Iterable[object],
    ref: str = "",
) -> list[DataIssue]:
    return [
        data_issue(
            code,
            message=str(message),
            ref=ref,
            origin=origin,
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
    "data_issue",
    "data_issues",
    "issue_messages",
    "issues_for_ref",
]
