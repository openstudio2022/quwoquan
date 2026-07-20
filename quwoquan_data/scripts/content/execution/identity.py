"""Readable, immutable content execution identity."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from core.control_types import ContentType, RolloutMilestone, SelectionPolicy


_EXECUTION_ID_RE = re.compile(
    r"^(?P<date>20\d{6})--"
    r"(?P<vertical>[a-z][a-z0-9-]*)-"
    r"(?P<content_type>homepage|article|image|video)-"
    r"(?P<intent>[a-z][a-z0-9-]*)--"
    r"(?P<scope>[a-z0-9][a-z0-9-]*)--"
    r"(?P<milestone>canary|m1|m2|m3|h10k)-"
    r"(?P<sequence>[0-9]{3,})$"
)


@dataclass(frozen=True)
class ExecutionIdentity:
    execution_id: str
    run_date: str
    vertical: str
    content_type: ContentType
    intent: str
    scope: str
    milestone: RolloutMilestone
    sequence: int


def validate_execution_id(value: str) -> str:
    """Validate the public execution ID without silently normalizing it."""
    execution_id = str(value or "").strip()
    match = _EXECUTION_ID_RE.fullmatch(execution_id)
    if match is None:
        raise ValueError(
            "executionId must be YYYYMMDD--<vertical>-<contentType>-<intent>--"
            "<scope>--<canary|m1|m2|m3|h10k>-<sequence>"
        )
    try:
        date.fromisoformat(
            f"{execution_id[0:4]}-{execution_id[4:6]}-{execution_id[6:8]}"
        )
    except ValueError as exc:
        raise ValueError(f"executionId date is invalid: {execution_id[:8]}") from exc
    return execution_id


def parse_execution_id(value: str) -> ExecutionIdentity:
    execution_id = validate_execution_id(value)
    match = _EXECUTION_ID_RE.fullmatch(execution_id)
    assert match is not None
    fields = match.groupdict()
    return ExecutionIdentity(
        execution_id=execution_id,
        run_date=fields["date"],
        vertical=fields["vertical"],
        content_type=ContentType(fields["content_type"]),
        intent=fields["intent"],
        scope=fields["scope"],
        milestone=RolloutMilestone(fields["milestone"]),
        sequence=int(fields["sequence"]),
    )


def build_execution_id(
    *,
    run_date: str,
    vertical: str,
    content_type: str,
    intent: str,
    scope: str,
    milestone: str,
    sequence: int,
) -> str:
    candidate = (
        f"{run_date}--{vertical}-{content_type}-{intent}--{scope}--"
        f"{milestone}-{int(sequence):03d}"
    )
    return validate_execution_id(candidate)
