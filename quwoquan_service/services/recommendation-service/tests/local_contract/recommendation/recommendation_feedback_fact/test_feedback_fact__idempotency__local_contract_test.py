from datetime import datetime, timezone

import pytest

from internal.recommendation.recommendation_feedback_fact.application.appender import (
    Appender,
    FeedbackFact,
)


class _Store:
    def __init__(self) -> None:
        self.facts = {}

    def append_if_absent(self, fact):
        existing = self.facts.get(fact.source_event_id)
        if existing:
            return existing, False
        self.facts[fact.source_event_id] = fact
        return fact, True


class _Exposures:
    def __init__(self, *exposure_ids) -> None:
        self.exposure_ids = set(exposure_ids)

    def exists(self, exposure_id):
        return exposure_id in self.exposure_ids


class _Closures:
    def __init__(self, *closed) -> None:
        self.closed = set(closed)

    def exists(self, account_id):
        return account_id in self.closed


def _fact() -> FeedbackFact:
    now = datetime.now(timezone.utc)
    return FeedbackFact(
        feedback_id="feedback-001",
        source_event_id="behavior-001",
        exposure_id="exposure-001",
        feed_request_id="request-001",
        subject_id="account-001",
        persona_id="persona-001",
        target_type="post",
        target_id="post-001",
        feedback_type="like",
        value=1.0,
        occurred_at=now,
        recorded_at=now,
    )


def test_feedback_fact_is_idempotent_by_source_behavior_event() -> None:
    appender = Appender(_Store(), _Exposures("exposure-001"), _Closures())
    fact = _fact()
    assert appender.append(fact)[1] is True
    assert appender.append(fact)[1] is False


def test_feedback_fact_requires_persisted_exposure_and_open_subject() -> None:
    with pytest.raises(LookupError):
        Appender(_Store(), _Exposures(), _Closures()).append(_fact())
    with pytest.raises(PermissionError):
        Appender(
            _Store(),
            _Exposures("exposure-001"),
            _Closures("account-001"),
        ).append(_fact())
