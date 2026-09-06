"""Prepare pool-wide canonical release inputs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from content.release.canonical.aggregate_release_closure import (
    creator_tag_refs,
    object_root,
)
from content.release.canonical.aggregate_release_pool_closure import (
    candidate_closure,
    entity_candidate_closure,
    pool_execution_ids,
    release_authors,
)
from content.release.canonical.content_pool_handoff import (
    project_content_pool_handoff,
)
from content.release.canonical.content_pool_record import (
    is_pool_record_admitted,
)
from content.release.canonical.effective_admission import (
    effective_admission_record as _effective_record,
)
from content.release.canonical.aggregate_release_selection import (
    ExplicitCohortSelection,
    discover_explicit_cohort_candidates,
    explicit_cohort_digest,
)
from content.release.canonical.object_source_identity import (
    source_identity_set,
    validate_object_source_identity,
)
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _read_json,
)
from core.paths import CONTROL_PLANE_TAXONOMY_ROOT
from core.source_digest import SourceDefinitionSnapshot
from governance.coverage.distribution import load_content_distribution_policy


@dataclass(frozen=True)
class PoolReleasePreparation:
    cohort_selection: ExplicitCohortSelection
    execution_ids: list[str]
    source_digests: tuple[SourceDefinitionSnapshot, ...]
    entity_catalog_digest: str | None
    source_revision: str | None
    source_identities: tuple[dict[str, object], ...]
    source_identity_set_digest: str
    desired: dict[str, list[str]]
    excluded: tuple[dict[str, str], ...]


def pool_post_refs(publish_root: Path) -> list[str]:
    posts_root = publish_root / "posts"
    if not posts_root.is_dir():
        return []
    return [
        path.parent.relative_to(posts_root).as_posix()
        for path in sorted(posts_root.rglob("manifest.json"))
    ]


def pool_entity_refs(publish_root: Path) -> list[str]:
    entities_root = publish_root / "entities"
    if not entities_root.is_dir():
        return []
    return [
        path.parent.relative_to(entities_root).as_posix()
        for path in sorted(entities_root.rglob("manifest.json"))
    ]


def _pool_source_identity_closure(
    publish_root: Path,
    *,
    entity_refs: set[str],
    post_refs: set[str],
) -> tuple[
    tuple[SourceDefinitionSnapshot, ...],
    tuple[dict[str, object], ...],
    str,
]:
    identities: list[dict[str, str]] = []
    source_digests: dict[str, SourceDefinitionSnapshot] = {}
    for kind, refs in (("entities", entity_refs), ("posts", post_refs)):
        for ref in sorted(refs):
            root = object_root(publish_root, kind, ref)
            manifest = _read_json(root / "manifest.json")
            record = _effective_record(
                root,
                manifest,
                object_type=("homepage" if kind == "entities" else "content"),
            )
            identity = (
                record.get("sourceIdentity") if isinstance(record, dict) else None
            )
            if not isinstance(identity, dict):
                raise ObjectTransactionError(
                    f"DATA.POOL.SOURCE_IDENTITY_INVALID: {kind}/{ref}"
                )
            manifest_identity = validate_object_source_identity(manifest)
            if identity != manifest_identity:
                raise ObjectTransactionError(
                    f"DATA.POOL.SOURCE_IDENTITY_DRIFT: {kind}/{ref}"
                )
            source_digest = SourceDefinitionSnapshot(
                digest=manifest_identity["sourceDigest"]
            )
            source_digests[source_digest.digest] = source_digest
            identities.append(identity)
    rows, set_digest = source_identity_set(identities)
    return (
        tuple(source_digests[key] for key in sorted(source_digests)),
        tuple(rows),
        set_digest,
    )


def pool_audit_provenance(
    publish_root: Path,
    *,
    entity_refs: set[str],
    post_refs: set[str],
) -> tuple[
    list[str],
    tuple[SourceDefinitionSnapshot, ...],
    tuple[dict[str, object], ...],
    str,
]:
    """Read producer lineage for release audit, outside eligibility candidates.

    This query runs only after the cohort has been selected through
    ``ContentPoolHandoffQuery``.  Its result may attest the immutable release,
    but cannot add, remove, de-duplicate, or reorder any selected object.
    """

    execution_ids = pool_execution_ids(
        publish_root,
        entity_refs=entity_refs,
        post_refs=post_refs,
    )
    source_digests, source_identities, source_identity_set_digest = (
        _pool_source_identity_closure(
            publish_root,
            entity_refs=entity_refs,
            post_refs=post_refs,
        )
    )
    return (
        execution_ids,
        source_digests,
        source_identities,
        source_identity_set_digest,
    )


def release_contents(
    selection: ExplicitCohortSelection,
) -> list[dict[str, object]]:
    return [
        {
            "contentId": candidate.content_id,
            "version": candidate.version,
            "postRef": candidate.post_ref,
            "selectionIdentityDigest": candidate.selection_identity_digest,
            "canonicalObjectDigest": candidate.canonical_object_digest,
            "contentLibraryBindingDigest": (candidate.content_library_binding_digest),
        }
        for candidate in selection.candidates
    ]


def admitted_pool_author_refs(publish_root: Path) -> list[str]:
    """Return all active admitted Data authors, independent of Post closure."""

    creators_root = publish_root / "creators"
    if not creators_root.is_dir():
        return []
    refs: list[str] = []
    for root in sorted(creators_root.iterdir()):
        if not root.is_dir() or not (root / "profile.json").is_file():
            continue
        profile = _read_json(root / "profile.json")
        record = _effective_record(
            root,
            profile,
            object_type="author",
        )
        if is_pool_record_admitted(record):
            refs.append(root.name)
    return refs



def _pool_snapshot_digest(
    *,
    post_pool_digest: str,
    entity_rows: list[dict[str, object]],
) -> str:
    encoded = json.dumps(
        {
            "postPoolDigest": post_pool_digest,
            "entities": sorted(
                entity_rows,
                key=lambda row: str(row["objectRef"]),
            ),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def prepare_pool_release(
    *,
    publish_root: Path,
    cohort: dict[str, object],
    release_class: str,
) -> PoolReleasePreparation:
    """Validate one exact caller-declared cohort without scanning for candidates."""
    normalized_release_class = str(release_class or "").strip()
    if normalized_release_class not in {"research", "commercial"}:
        raise ObjectTransactionError("DATA.RELEASE.CLASS_INVALID")
    if cohort.get("releaseClass") != normalized_release_class:
        raise ObjectTransactionError("DATA.RELEASE.COHORT_CLASS_DRIFT")
    object_refs = cohort.get("objectRefs")
    expected_counts = cohort.get("expectedCarrierCounts")
    if (
        not isinstance(object_refs, list)
        or not object_refs
        or not isinstance(expected_counts, dict)
    ):
        raise ObjectTransactionError("DATA.RELEASE.COHORT_INVALID")
    entity_refs: set[str] = set()
    post_refs: set[str] = set()
    for raw_ref in object_refs:
        ref = str(raw_ref).strip().strip("/")
        if ref.startswith("entities/"):
            entity_refs.add(ref.removeprefix("entities/"))
        elif ref.startswith("posts/"):
            post_refs.add(ref.removeprefix("posts/"))
        else:
            raise ObjectTransactionError(f"DATA.RELEASE.COHORT_REF_INVALID: {raw_ref}")
    if len(entity_refs) + len(post_refs) != len(object_refs):
        raise ObjectTransactionError("DATA.RELEASE.COHORT_REF_DUPLICATE")
    candidates, exclusions = discover_explicit_cohort_candidates(
        publish_root=publish_root,
        post_refs=sorted(post_refs),
    )
    if exclusions or {row.post_ref for row in candidates} != post_refs:
        raise ObjectTransactionError("DATA.RELEASE.COHORT_POST_NOT_PUBLISHABLE")
    if normalized_release_class == "commercial":
        noncommercial_posts = sorted(
            row.post_ref for row in candidates if row.usage_scope != "commercial"
        )
        if noncommercial_posts:
            raise ObjectTransactionError(
                "DATA.POOL.COMMERCIAL_RIGHTS_REQUIRED: "
                f"posts/{noncommercial_posts[0]}"
            )
    closure_cache: dict[
        str, tuple[set[str], list[str], list[str], list[dict[str, object]]]
    ] = {}
    for post_ref in sorted(post_refs):
        closure_cache[post_ref] = candidate_closure(
            publish_root, post_ref=post_ref, release_class=normalized_release_class
        )
    entity_closure_cache: dict[str, tuple[list[str], list[str]]] = {}
    for entity_ref in sorted(entity_refs):
        root = object_root(publish_root, "entities", entity_ref)
        if not (root / "manifest.json").is_file():
            raise ObjectTransactionError(
                f"DATA.RELEASE.COHORT_ENTITY_MISSING: {entity_ref}"
            )
        handoff = project_content_pool_handoff(
            publish_root=publish_root, object_type="homepage", object_ref=entity_ref
        )
        if handoff is None or (
            normalized_release_class == "commercial"
            and handoff.usage_scope != "commercial"
        ):
            raise ObjectTransactionError(
                f"DATA.RELEASE.COHORT_ENTITY_NOT_PUBLISHABLE: {entity_ref}"
            )
        entity_closure_cache[entity_ref] = entity_candidate_closure(
            publish_root, entity_ref=entity_ref, release_class=normalized_release_class
        )
    required_entities = {
        ref for post_ref in post_refs for ref in closure_cache[post_ref][0]
    }
    if not required_entities.issubset(entity_refs):
        raise ObjectTransactionError("DATA.RELEASE.COHORT_REFERENCE_MISSING")
    counts = {
        "homepage": len(entity_refs),
        "article": sum(row.content_type == "article" for row in candidates),
        "image": sum(row.content_type == "image" for row in candidates),
        "video": sum(row.content_type == "video" for row in candidates),
    }
    if counts != {key: int(expected_counts.get(key, -1)) for key in counts}:
        raise ObjectTransactionError(
            f"DATA.RELEASE.COHORT_COUNT_DRIFT: expected={expected_counts} actual={counts}"
        )
    raw_milestone = cohort.get("milestone")
    milestone = str(raw_milestone).strip() if raw_milestone is not None else None
    milestone_targets = None
    if milestone is not None:
        milestone_targets = load_content_distribution_policy().milestone_targets().get(
            milestone
        )
        if milestone_targets is None:
            raise ObjectTransactionError(
                f"DATA.RELEASE.COHORT_MILESTONE_INVALID: {milestone!r}"
            )
        if counts != milestone_targets:
            raise ObjectTransactionError(
                "DATA.RELEASE.COHORT_MILESTONE_COUNT_DRIFT: "
                f"milestone={milestone} expected={milestone_targets} actual={counts}"
            )
    execution_ids, source_digests, source_identities, source_identity_set_digest = (
        pool_audit_provenance(
            publish_root, entity_refs=entity_refs, post_refs=post_refs
        )
    )
    creator_refs = sorted(
        {ref for post_ref in post_refs for ref in closure_cache[post_ref][1]}
        | {
            ref
            for entity_ref in entity_refs
            for ref in entity_closure_cache[entity_ref][0]
        }
    )
    tag_refs = sorted(
        {ref for post_ref in post_refs for ref in closure_cache[post_ref][2]}
        | {
            ref
            for entity_ref in entity_refs
            for ref in entity_closure_cache[entity_ref][1]
        }
        | set(
            creator_tag_refs(
                publish_root,
                creator_refs=creator_refs,
                control_plane_taxonomy_root=CONTROL_PLANE_TAXONOMY_ROOT,
            )
        )
    )
    selected_candidates = tuple(sorted(candidates, key=lambda row: row.post_ref))
    selection = ExplicitCohortSelection(
        candidates=selected_candidates,
        pool_digest=explicit_cohort_digest(selected_candidates),
        eligible_count=sum(counts.values()),
        counts={**counts, "total": sum(counts.values())},
        milestone=milestone,
        milestone_targets=(
            dict(milestone_targets) if milestone_targets is not None else None
        ),
    )
    return PoolReleasePreparation(
        cohort_selection=selection,
        execution_ids=execution_ids,
        source_digests=source_digests,
        entity_catalog_digest=None,
        source_revision=None,
        source_identities=source_identities,
        source_identity_set_digest=source_identity_set_digest,
        desired={
            "creators": creator_refs,
            "entities": sorted(entity_refs),
            "posts": sorted(post_refs),
            "tags": tag_refs,
        },
        excluded=(),
    )


__all__ = [
    "PoolReleasePreparation",
    "admitted_pool_author_refs",
    "pool_audit_provenance",
    "prepare_pool_release",
    "release_authors",
    "release_contents",
]
