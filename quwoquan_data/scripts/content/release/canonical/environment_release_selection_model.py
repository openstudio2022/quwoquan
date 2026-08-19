"""Pure identity and ordering model for canonical pool release selection."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from content.release.canonical.object_transaction_contract import ObjectTransactionError

DATA_POST_CAPS: dict[str, int | None] = {
    "alpha": 2_100,
    "beta": 10_000,
    "gamma": 100_000,
    "prod": None,
}
CONTENT_TYPES = ("article", "image", "video")
MILESTONE_TARGETS: dict[str, dict[str, int]] = {
    "M100": {"homepage": 100, "article": 100, "image": 100, "video": 10},
    "M1000": {
        "homepage": 1_000,
        "article": 1_000,
        "image": 1_000,
        "video": 100,
    },
    "M10000": {
        "homepage": 10_000,
        "article": 10_000,
        "image": 10_000,
        "video": 1_000,
    },
}


@dataclass(frozen=True, slots=True)
class PoolCandidate:
    post_ref: str
    content_id: str
    version: int
    content_type: str
    author_id: str
    variant_purpose: str
    usage_scope: str
    execution_id: str = ""
    source_identity_digest: str = ""


@dataclass(frozen=True, slots=True)
class PoolExclusion:
    post_ref: str
    gate: str
    code: str


@dataclass(frozen=True, slots=True)
class EnvironmentReleaseSelection:
    environment: str | None
    release_mode: str
    post_refs: tuple[str, ...]
    candidates: tuple[PoolCandidate, ...]
    pool_digest: str
    eligible_count: int
    counts: dict[str, int]
    excluded: tuple[PoolExclusion, ...]
    selection_scope: str
    milestone: str | None = None
    milestone_targets: Mapping[str, int] | None = None


def latest_versions(
    candidates: Sequence[PoolCandidate], *, release_mode: str
) -> tuple[list[PoolCandidate], list[PoolExclusion]]:
    grouped: dict[str, list[PoolCandidate]] = defaultdict(list)
    identities: set[tuple[str, int]] = set()
    conflicted_content_ids: set[str] = set()
    for candidate in candidates:
        identity = (candidate.content_id, candidate.version)
        if identity in identities:
            conflicted_content_ids.add(candidate.content_id)
        identities.add(identity)
        grouped[candidate.content_id].append(candidate)

    selected: list[PoolCandidate] = []
    excluded: list[PoolExclusion] = []
    for content_id in sorted(grouped):
        versions = grouped[content_id]
        if content_id in conflicted_content_ids:
            excluded.extend(
                PoolExclusion(
                    post_ref=row.post_ref,
                    gate="eligibility",
                    code="DATA.POOL.VERSION_CONFLICT",
                )
                for row in versions
            )
            continue
        if release_mode == "commercial":
            eligible = [row for row in versions if row.usage_scope == "commercial"]
        else:
            originals = [row for row in versions if row.variant_purpose == "original"]
            eligible = originals or versions
        if eligible:
            selected.append(max(eligible, key=lambda row: (row.version, row.post_ref)))
    return selected, excluded


def stable_balanced_order(
    candidates: Sequence[PoolCandidate],
) -> list[PoolCandidate]:
    queues: dict[str, dict[str, deque[PoolCandidate]]] = {
        content_type: {} for content_type in CONTENT_TYPES
    }
    for content_type in CONTENT_TYPES:
        by_author: dict[str, list[PoolCandidate]] = defaultdict(list)
        for candidate in candidates:
            if candidate.content_type == content_type:
                by_author[candidate.author_id].append(candidate)
        queues[content_type] = {
            author_id: deque(
                sorted(
                    rows,
                    key=lambda row: (row.content_id, row.version, row.post_ref),
                )
            )
            for author_id, rows in sorted(by_author.items())
        }

    ordered: list[PoolCandidate] = []
    while any(queues[content_type] for content_type in CONTENT_TYPES):
        for content_type in CONTENT_TYPES:
            author_queues = queues[content_type]
            if not author_queues:
                continue
            author_id = next(iter(author_queues))
            queue = author_queues.pop(author_id)
            ordered.append(queue.popleft())
            if queue:
                author_queues[author_id] = queue
    return ordered


def pool_digest(candidates: Sequence[PoolCandidate]) -> str:
    rows: list[dict[str, Any]] = [
        {
            "postRef": row.post_ref,
            "contentId": row.content_id,
            "version": row.version,
            "contentType": row.content_type,
            "authorId": row.author_id,
            "variantPurpose": row.variant_purpose,
            "usageScope": row.usage_scope,
        }
        for row in sorted(
            candidates,
            key=lambda item: (item.content_id, item.version, item.post_ref),
        )
    ]
    encoded = json.dumps(
        rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


__all__ = [
    "CONTENT_TYPES",
    "DATA_POST_CAPS",
    "MILESTONE_TARGETS",
    "EnvironmentReleaseSelection",
    "PoolCandidate",
    "PoolExclusion",
    "latest_versions",
    "pool_digest",
    "stable_balanced_order",
]
