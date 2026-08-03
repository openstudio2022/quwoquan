from __future__ import annotations

from typing import Protocol

from internal.recommendation.recommendation_exposure_fact.domain.fact import (
    ExposureFact,
    canonical_snapshot_digest,
)


class ExposureFactStore(Protocol):
    def append_if_absent(self, fact: ExposureFact) -> tuple[ExposureFact, bool]: ...

    def find_by_attribution(self, feed_request_id: str, target_id: str) -> ExposureFact | None: ...


class SubjectClosureReader(Protocol):
    def exists(self, account_id: str) -> bool: ...


class Appender:
    def __init__(self, store: ExposureFactStore, subject_closures: SubjectClosureReader) -> None:
        self._store = store
        self._subject_closures = subject_closures

    def append(self, fact: ExposureFact) -> tuple[ExposureFact, bool]:
        fact.validate()
        if self._subject_closures.exists(fact.subject_id):
            raise PermissionError("closed subjects cannot append recommendation exposure")
        return self._store.append_if_absent(fact)

    def find_by_attribution(self, feed_request_id: str, target_id: str) -> ExposureFact | None:
        if not feed_request_id.strip() or not target_id.strip():
            raise ValueError("recommendation exposure attribution is incomplete")
        return self._store.find_by_attribution(feed_request_id.strip(), target_id.strip())
