"""Producer-owned candidate facts for one explicit immutable release cohort."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from content.release.canonical.content_pool_handoff import (
    project_content_pool_handoff,
)
from content.release.canonical.content_pool_record import (
    is_pool_record_admitted,
)
from content.release.canonical.effective_admission import (
    effective_admission_record as _effective_record,
    effective_source_attribution_ready,
    resolve_effective_admission,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
)


@dataclass(frozen=True, slots=True)
class PoolCandidate:
    post_ref: str
    content_id: str
    version: int
    content_type: str
    author_id: str
    variant_purpose: str
    usage_scope: str
    selection_identity_digest: str
    canonical_object_digest: str
    content_library_binding_digest: str


@dataclass(frozen=True, slots=True)
class PoolExclusion:
    post_ref: str
    gate: str
    code: str


@dataclass(frozen=True, slots=True)
class ExplicitCohortSelection:
    candidates: tuple[PoolCandidate, ...]
    pool_digest: str
    eligible_count: int
    counts: dict[str, int]
    milestone: str | None = None
    milestone_targets: Mapping[str, int] | None = None


def _pool_error_code(exc: BaseException) -> str:
    value = str(exc).strip().split(":", 1)[0]
    return value if value.startswith("DATA.") else "DATA.POOL.OBJECT_INVALID"


def _pool_gate_for_code(code: str) -> str:
    if any(token in code for token in ("REFERENCE", "AUTHOR", "MEDIA")):
        return "delivery"
    if any(token in code for token in ("QUALITY", "MANIFEST", "GENERATOR")):
        return "quality"
    return "eligibility"


def _candidate(publish_root: Path, post_ref: str) -> PoolCandidate | None:
    handoff = project_content_pool_handoff(
        publish_root=publish_root,
        object_type="content",
        object_ref=post_ref,
    )
    if handoff is None:
        return None
    if handoff.author_id is None:
        raise ObjectTransactionError(
            f"DATA.POOL.IDENTITY_INVALID: {post_ref} lacks authorId"
        )
    return PoolCandidate(
        post_ref=handoff.object_ref,
        content_id=handoff.object_id,
        version=handoff.content_version,
        content_type=handoff.carrier,
        author_id=handoff.author_id,
        variant_purpose=handoff.variant_purpose,
        usage_scope=handoff.usage_scope,
        selection_identity_digest=handoff.selection_identity_digest,
        canonical_object_digest=handoff.canonical_object_digest,
        content_library_binding_digest=handoff.content_library_binding_digest,
    )


def _delivery_issue(
    publish_root: Path,
    *,
    post_ref: str,
    candidate: PoolCandidate,
) -> str | None:
    root = publish_root / "posts" / post_ref
    manifest = _read_json(root / "manifest.json")
    try:
        admission = resolve_effective_admission(
            root,
            object_type="content",
            document=manifest,
        )
        pool_record = admission.record
    except (OSError, ObjectTransactionError, TypeError, ValueError) as exc:
        return _pool_error_code(exc)
    if not is_pool_record_admitted(pool_record):
        return "DATA.POOL.OBJECT_NOT_ADMITTED"
    if not effective_source_attribution_ready(admission):
        return "DATA.POOL.SOURCE_ATTRIBUTION_INCOMPLETE"
    creator_refs_path = root / "creator.refs.json"
    raw_creator_refs = (
        _read_json(creator_refs_path).get("creatorRefs")
        if creator_refs_path.is_file()
        else [candidate.author_id]
    )
    if not isinstance(raw_creator_refs, list) or not raw_creator_refs:
        return "DATA.POOL.AUTHOR_NOT_ADMITTED"
    for raw_ref in raw_creator_refs:
        creator_ref = str(raw_ref or "").strip()
        creator_root = publish_root / "creators" / creator_ref
        try:
            profile = _read_json(creator_root / "profile.json")
            author_record = _effective_record(
                creator_root,
                profile,
                object_type="author",
            )
        except (OSError, ObjectTransactionError, TypeError, ValueError):
            return "DATA.POOL.AUTHOR_NOT_ADMITTED"
        if not creator_ref or not is_pool_record_admitted(author_record):
            return "DATA.POOL.AUTHOR_NOT_ADMITTED"
    raw_entity_refs = manifest.get("entityRefs")
    if not isinstance(raw_entity_refs, list) or not raw_entity_refs:
        return "DATA.POOL.REFERENCE_MISSING"
    for raw_ref in raw_entity_refs:
        value = str(raw_ref or "").strip()
        if not value.startswith("/entity/"):
            return "DATA.POOL.REFERENCE_MISSING"
        entity_root = publish_root / "entities" / value.removeprefix("/entity/")
        try:
            entity_manifest = _read_json(entity_root / "manifest.json")
            entity_admission = resolve_effective_admission(
                entity_root,
                object_type="homepage",
                document=entity_manifest,
            )
            entity_record = entity_admission.record
        except (OSError, ObjectTransactionError, TypeError, ValueError):
            return "DATA.POOL.REFERENCE_MISSING"
        if not is_pool_record_admitted(
            entity_record
        ) or not effective_source_attribution_ready(entity_admission):
            return "DATA.POOL.REFERENCE_MISSING"
    return None


def discover_explicit_cohort_candidates(
    *,
    publish_root: Path,
    post_refs: Sequence[str],
) -> tuple[list[PoolCandidate], list[PoolExclusion]]:
    """Validate only the caller-declared post set for producer release bytes."""
    candidates: list[PoolCandidate] = []
    excluded: list[PoolExclusion] = []
    for raw_ref in sorted(post_refs):
        post_ref = str(raw_ref)
        try:
            candidate = _candidate(publish_root, post_ref)
            if candidate is None:
                continue
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
            candidates.append(candidate)
        except (OSError, ObjectTransactionError, TypeError, ValueError) as exc:
            code = _pool_error_code(exc)
            excluded.append(
                PoolExclusion(
                    post_ref=post_ref,
                    gate=_pool_gate_for_code(code),
                    code=code,
                )
            )
    return candidates, excluded


def explicit_cohort_digest(candidates: Sequence[PoolCandidate]) -> str:
    rows = [
        {
            "postRef": row.post_ref,
            "contentId": row.content_id,
            "version": row.version,
            "contentType": row.content_type,
            "authorId": row.author_id,
            "variantPurpose": row.variant_purpose,
            "usageScope": row.usage_scope,
            "selectionIdentityDigest": row.selection_identity_digest,
            "canonicalObjectDigest": row.canonical_object_digest,
            "contentLibraryBindingDigest": row.content_library_binding_digest,
        }
        for row in sorted(
            candidates,
            key=lambda item: (item.content_id, item.version, item.post_ref),
        )
    ]
    encoded = json.dumps(
        rows,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


__all__ = [
    "ExplicitCohortSelection",
    "PoolCandidate",
    "PoolExclusion",
    "discover_explicit_cohort_candidates",
    "explicit_cohort_digest",
]
