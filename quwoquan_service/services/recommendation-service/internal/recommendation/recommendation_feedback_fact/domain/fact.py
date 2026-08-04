from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math


@dataclass(frozen=True, slots=True)
class RecommendationFeedbackFact:
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

    def validate(self) -> None:
        required = (
            self.feedback_id,
            self.source_event_id,
            self.exposure_id,
            self.feed_request_id,
            self.subject_id,
            self.target_type,
            self.target_id,
            self.feedback_type,
        )
        if not all(value.strip() for value in required):
            raise ValueError("recommendation feedback fact is incomplete")
        if self.occurred_at.tzinfo is None or self.recorded_at.tzinfo is None:
            raise ValueError("recommendation feedback timestamps must be timezone-aware")
        if self.occurred_at > self.recorded_at:
            raise ValueError("recommendation feedback recordedAt cannot precede occurredAt")
        if self.value is not None and not math.isfinite(self.value):
            raise ValueError("recommendation feedback value must be finite")
