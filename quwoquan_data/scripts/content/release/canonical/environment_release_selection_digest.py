"""Pool digest projection for environment release selection."""

from __future__ import annotations

from content.release.canonical.environment_release_selection import (
    Any,
    PoolCandidate,
    Sequence,
    hashlib,
    json,
)


def _pool_digest(candidates: Sequence[PoolCandidate]) -> str:
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
