from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Protocol


@dataclass(frozen=True, slots=True)
class FeedbackFact:
    feedback_id: str
    source_event_id: str
    exposure_id: str
    feed_request_id: str
    subject_id: str
    persona_id: str | None
    target_type: str
    target_id: str
    feedback_type: str
    value: float | None
    occurred_at: datetime
    recorded_at: datetime


class FeedbackFactStore(Protocol):
    def append_if_absent(self, fact: FeedbackFact) -> tuple[FeedbackFact, bool]: ...


class ExposureReader(Protocol):
    def exists(self, exposure_id: str) -> bool: ...


class SubjectClosureReader(Protocol):
    def exists(self, account_id: str) -> bool: ...


class Appender:
    def __init__(
        self,
        store: FeedbackFactStore,
        exposures: ExposureReader,
        subject_closures: SubjectClosureReader,
    ) -> None:
        self._store = store
        self._exposures = exposures
        self._subject_closures = subject_closures

    def append(self, fact: FeedbackFact) -> tuple[FeedbackFact, bool]:
        required = (
            fact.feedback_id,
            fact.source_event_id,
            fact.exposure_id,
            fact.feed_request_id,
            fact.subject_id,
            fact.target_type,
            fact.target_id,
            fact.feedback_type,
        )
        if not all(value.strip() for value in required):
            raise ValueError("recommendation feedback fact is incomplete")
        if fact.occurred_at.tzinfo is None or fact.recorded_at.tzinfo is None:
            raise ValueError("recommendation feedback timestamps must be timezone-aware")
        if fact.occurred_at > fact.recorded_at:
            raise ValueError("recommendation feedback recordedAt cannot precede occurredAt")
        if fact.value is not None and not math.isfinite(fact.value):
            raise ValueError("recommendation feedback value must be finite")
        if self._subject_closures.exists(fact.subject_id):
            raise PermissionError("closed subjects cannot append recommendation feedback")
        if not self._exposures.exists(fact.exposure_id):
            raise LookupError("recommendation feedback requires a persisted exposure")
        return self._store.append_if_absent(fact)
