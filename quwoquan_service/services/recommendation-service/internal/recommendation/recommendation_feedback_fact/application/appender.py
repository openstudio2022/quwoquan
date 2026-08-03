from __future__ import annotations

from typing import Protocol

from internal.recommendation.recommendation_feedback_fact.domain.fact import FeedbackFact


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
        fact.validate()
        if self._subject_closures.exists(fact.subject_id):
            raise PermissionError("closed subjects cannot append recommendation feedback")
        if not self._exposures.exists(fact.exposure_id):
            raise LookupError("recommendation feedback requires a persisted exposure")
        return self._store.append_if_absent(fact)
