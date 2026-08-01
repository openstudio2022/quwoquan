"""RecommendationSubjectClosureFact guard for offline recommendation jobs."""

from __future__ import annotations

from collections.abc import Iterable


SUBJECT_CLOSURE_COLLECTION = "recommendation_subject_closure_facts"


def closed_subject_ids(
    db,
    subject_ids: Iterable[str],
) -> set[str]:
    normalized = {
        str(subject_id or "").strip()
        for subject_id in subject_ids
        if str(subject_id or "").strip()
    }
    if not normalized:
        return set()
    rows = db[SUBJECT_CLOSURE_COLLECTION].find(
        {"subjectIds": {"$in": sorted(normalized)}},
        {"subjectIds": 1},
    )
    return normalized.intersection(
        str(subject_id)
        for row in rows
        for subject_id in row.get("subjectIds") or []
    )


def reject_closed_documents(
    db,
    documents: Iterable[dict],
    *,
    subject_field: str = "userId",
) -> tuple[list[dict], set[str]]:
    rows = list(documents)
    closed = closed_subject_ids(
        db,
        (row.get(subject_field, "") for row in rows),
    )
    return (
        [
            row
            for row in rows
            if str(row.get(subject_field, "") or "").strip() not in closed
        ],
        closed,
    )
