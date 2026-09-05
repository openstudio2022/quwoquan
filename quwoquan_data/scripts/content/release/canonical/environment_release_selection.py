"""Canonical candidate discovery and digest helpers for explicit cohorts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

DATA_POST_CAPS: dict[str, int | None] = {
    "alpha": 2_100,
    "beta": 10_000,
    "gamma": 100_000,
    "prod": None,
}

from content.release.canonical.environment_release_support import (
    pool_error_code,
    pool_gate_for_code,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
)
from content.release.canonical.pool_source_attribution import (
    source_attribution_complete,
)

from content.release.canonical.environment_release_candidate import (
    PoolCandidate,
    PoolExclusion,
    _candidate,
    _delivery_issue,
)


def pool_delivery_issue(
    publish_root: Path,
    *,
    post_ref: str,
    candidate: PoolCandidate,
) -> str | None:
    """Expose the single object-level delivery closure used by inspect/build."""

    return _delivery_issue(
        publish_root,
        post_ref=post_ref,
        candidate=candidate,
    )


def discover_pool_candidates(
    *,
    publish_root: Path,
    post_refs: Sequence[str],
    strict_admission: bool,
    allowed_entity_refs: set[str] | None = None,
) -> tuple[list[PoolCandidate], list[PoolExclusion]]:
    """Discover the shared canonical candidates without selecting a release class."""

    candidates: list[PoolCandidate] = []
    excluded: list[PoolExclusion] = []
    for ref in sorted(post_refs):
        post_ref = str(ref)
        try:
            candidate = _candidate(
                publish_root,
                post_ref,
                strict_admission=strict_admission,
            )
            if candidate is None:
                continue
            if strict_admission:
                issue_code = _delivery_issue(
                    publish_root,
                    post_ref=post_ref,
                    candidate=candidate,
                )
                if issue_code is not None:
                    excluded.append(
                        PoolExclusion(
                            post_ref=post_ref,
                            gate="delivery",
                            code=issue_code,
                        )
                    )
                    continue
            if allowed_entity_refs is not None:
                manifest = _read_json(
                    publish_root / "posts" / post_ref / "manifest.json"
                )
                raw_refs = manifest.get("entityRefs")
                entity_refs = (
                    {str(value).removeprefix("/entity/") for value in raw_refs}
                    if isinstance(raw_refs, list)
                    else set()
                )
                if not entity_refs or not entity_refs.issubset(allowed_entity_refs):
                    excluded.append(
                        PoolExclusion(
                            post_ref=post_ref,
                            gate="delivery",
                            code="DATA.POOL.REFERENCE_MISSING",
                        )
                    )
                    continue
            candidates.append(candidate)
        except (OSError, ObjectTransactionError, TypeError, ValueError) as exc:
            code = pool_error_code(exc)
            excluded.append(
                PoolExclusion(
                    post_ref=post_ref,
                    gate=pool_gate_for_code(code),
                    code=code,
                )
            )
    return candidates, excluded



def pool_candidate_digest(candidates: Sequence[PoolCandidate]) -> str:
    """Digest an already explicit, release-class-neutral candidate set."""
    rows: list[dict[str, Any]] = [
        {
            "postRef": row.post_ref, "contentId": row.content_id,
            "version": row.version, "contentType": row.content_type,
            "authorId": row.author_id, "variantPurpose": row.variant_purpose,
            "usageScope": row.usage_scope,
            "selectionIdentityDigest": row.selection_identity_digest,
            "canonicalObjectDigest": row.canonical_object_digest,
            "contentLibraryBindingDigest": row.content_library_binding_digest,
        }
        for row in sorted(candidates, key=lambda item: (item.content_id, item.version, item.post_ref))
    ]
    encoded = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()



__all__ = [
    "DATA_POST_CAPS",
    "PoolExclusion",
    "discover_pool_candidates",
    "pool_candidate_digest",
    "pool_delivery_issue",
    "source_attribution_complete",
]
