from __future__ import annotations

from typing import Protocol

from internal.recommendation.recommendation_subject_closure_fact.domain.fact import SubjectClosureFact


class SubjectClosureStore(Protocol):
    def append_if_absent(self, fact: SubjectClosureFact) -> tuple[SubjectClosureFact, bool]: ...

    def exists(self, account_id: str) -> bool: ...


class Appender:
    def __init__(self, store: SubjectClosureStore) -> None:
        self._store = store

    def append(self, fact: SubjectClosureFact) -> tuple[SubjectClosureFact, bool]:
        fact.validate()
        return self._store.append_if_absent(fact)

    def is_blocked(self, account_id: str) -> bool:
        normalized = account_id.strip()
        if not normalized:
            raise ValueError("accountId is required")
        return self._store.exists(normalized)
