from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class SubjectClosureFact:
    account_id: str
    subject_ids: tuple[str, ...]
    source_event_id: str
    source_digest: str
    closed_at: datetime
    recorded_at: datetime

    def validate(self) -> None:
        if not self.account_id.strip() or not self.source_event_id.strip() or not self.source_digest.strip():
            raise ValueError("recommendation closure identity and source digest are required")
        if (
            not self.subject_ids
            or self.account_id not in self.subject_ids
            or any(not subject_id.strip() for subject_id in self.subject_ids)
            or len(set(self.subject_ids)) != len(self.subject_ids)
        ):
            raise ValueError("recommendation closure subjectIds must uniquely include accountId")
        if self.closed_at.tzinfo is None or self.recorded_at.tzinfo is None:
            raise ValueError("recommendation closure timestamps must be timezone-aware")
        if self.closed_at > self.recorded_at:
            raise ValueError("recommendation closure recordedAt cannot precede closedAt")
