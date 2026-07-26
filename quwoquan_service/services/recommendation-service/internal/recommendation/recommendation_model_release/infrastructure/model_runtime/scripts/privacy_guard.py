"""Account-closure tombstone guard for offline recommendation jobs."""

from __future__ import annotations

import hashlib
import hmac
import os
from collections.abc import Iterable


SUBJECT_HMAC_ENV = "CONTENT_ACCOUNT_CLOSURE_SUBJECT_HMAC_SECRET"
TOMBSTONE_COLLECTION = "closed_account_subject_tombstones"


def subject_digest(subject_id: str, secret: str | None = None) -> str:
    normalized = str(subject_id or "").strip()
    if not normalized:
        raise ValueError("account-closure subject id is required")
    resolved_secret = str(secret or os.environ.get(SUBJECT_HMAC_ENV, "")).strip()
    if len(resolved_secret) < 32:
        raise RuntimeError(
            f"{SUBJECT_HMAC_ENV} must contain at least 32 bytes"
        )
    return hmac.new(
        resolved_secret.encode("utf-8"),
        normalized.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def closed_subject_ids(
    db,
    subject_ids: Iterable[str],
    *,
    secret: str | None = None,
) -> set[str]:
    normalized = {
        str(subject_id or "").strip()
        for subject_id in subject_ids
        if str(subject_id or "").strip()
    }
    if not normalized:
        return set()
    digest_to_subject = {
        subject_digest(subject_id, secret): subject_id
        for subject_id in normalized
    }
    rows = db[TOMBSTONE_COLLECTION].find(
        {"_id": {"$in": list(digest_to_subject)}},
        {"_id": 1},
    )
    return {
        digest_to_subject[row["_id"]]
        for row in rows
        if row.get("_id") in digest_to_subject
    }


def reject_closed_documents(
    db,
    documents: Iterable[dict],
    *,
    subject_field: str = "userId",
    secret: str | None = None,
) -> tuple[list[dict], set[str]]:
    rows = list(documents)
    closed = closed_subject_ids(
        db,
        (row.get(subject_field, "") for row in rows),
        secret=secret,
    )
    return (
        [
            row
            for row in rows
            if str(row.get(subject_field, "") or "").strip() not in closed
        ],
        closed,
    )
