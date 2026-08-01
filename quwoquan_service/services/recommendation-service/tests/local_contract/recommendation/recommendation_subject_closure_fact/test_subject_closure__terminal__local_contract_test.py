from datetime import datetime, timedelta, timezone

import pytest

from internal.recommendation.recommendation_subject_closure_fact.application.appender import (
    Appender,
    SubjectClosureFact,
)


class _Store:
    def __init__(self) -> None:
        self.facts = {}

    def append_if_absent(self, fact):
        existing = self.facts.get(fact.account_id)
        if existing:
            return existing, False
        self.facts[fact.account_id] = fact
        return fact, True

    def exists(self, account_id: str) -> bool:
        return any(account_id in fact.subject_ids for fact in self.facts.values())


def test_subject_closure_is_irreversible_and_blocks_revival() -> None:
    now = datetime.now(timezone.utc)
    store = _Store()
    appender = Appender(store)
    fact = SubjectClosureFact("account-001", ("account-001", "persona-001"), "event-001", "digest-001", now, now)
    assert appender.append(fact)[1] is True
    assert appender.append(fact)[1] is False
    assert appender.is_blocked("account-001") is True
    assert appender.is_blocked("persona-001") is True


def test_subject_closure_rejects_recording_before_close() -> None:
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError):
        Appender(_Store()).append(
            SubjectClosureFact("account-001", ("account-001",), "event-001", "digest-001", now, now - timedelta(seconds=1))
        )
