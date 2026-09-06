"""Shared typed-issue construction for the homepage media verifiers."""
from __future__ import annotations

from typing import Any, Mapping

from core.data_issue import (
    DataIssue,
    DataIssueCode,
    data_issue,
)


def issue(
    code: DataIssueCode,
    message: str,
    *,
    ref: str,
    attrs: Mapping[str, object] | None = None,
) -> DataIssue:
    return data_issue(
        code,
        origin="verify_homepage_media",
        ref=ref,
        message=message,
        attributes=attrs,
    )


def mapping_rows(value: object) -> list[dict[str, Any]]:
    return [dict(row) for row in (value or []) if isinstance(row, Mapping)]
