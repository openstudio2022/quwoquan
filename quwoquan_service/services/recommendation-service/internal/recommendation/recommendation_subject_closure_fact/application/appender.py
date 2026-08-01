from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SubjectClosureFact:
    account_id: str
    subject_ids: tuple[str, ...]
    source_event_id: str
    source_digest: str
    closed_at: datetime
    recorded_at: datetime


class SubjectClosureStore(Protocol):
    def append_if_absent(self, fact: SubjectClosureFact) -> tuple[SubjectClosureFact, bool]: ...

    def exists(self, account_id: str) -> bool: ...


class Appender:
    def __init__(self, store: SubjectClosureStore) -> None:
        self._store = store

    def append(self, fact: SubjectClosureFact) -> tuple[SubjectClosureFact, bool]:
        if not fact.account_id.strip() or not fact.source_event_id.strip() or not fact.source_digest.strip():
            raise ValueError("recommendation closure identity and source digest are required")
        if (
            not fact.subject_ids
            or fact.account_id not in fact.subject_ids
            or any(not subject_id.strip() for subject_id in fact.subject_ids)
            or len(set(fact.subject_ids)) != len(fact.subject_ids)
        ):
            raise ValueError("recommendation closure subjectIds must uniquely include accountId")
        if fact.closed_at > fact.recorded_at:
            raise ValueError("recommendation closure recordedAt cannot precede closedAt")
        return self._store.append_if_absent(fact)

    def is_blocked(self, account_id: str) -> bool:
        normalized = account_id.strip()
        if not normalized:
            raise ValueError("accountId is required")
        return self._store.exists(normalized)
