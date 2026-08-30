"""Select one deterministic environment ReleaseManifest directly from the content pool."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from collections.abc import Sequence
from pathlib import Path
from typing import Any

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
from governance.coverage.distribution import load_content_distribution_policy

DATA_POST_CAPS: dict[str, int | None] = {
    "alpha": 2_100,
    "beta": 10_000,
    "gamma": 100_000,
    "prod": None,
}
# The milestone numbers live only in the content distribution policy, so
# promoting ten to hundred to thousand scale is a control-plane edit and the
# campaign workload, the pool report and this selector cannot drift apart.
MILESTONE_TARGETS: dict[str, dict[str, int]] = (
    load_content_distribution_policy().milestone_targets()
)

from content.release.canonical.environment_release_candidate import (
    _CONTENT_TYPES,
    EnvironmentReleaseSelection,
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


def _latest_versions(
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
            if not eligible:
                excluded.extend(
                    PoolExclusion(
                        post_ref=row.post_ref,
                        gate="eligibility",
                        code="DATA.POOL.COMMERCIAL_RIGHTS_REQUIRED",
                    )
                    for row in versions
                )
                continue
        else:
            originals = [row for row in versions if row.variant_purpose == "original"]
            eligible = originals or versions
        if not eligible:
            continue
        selected.append(max(eligible, key=lambda row: (row.version, row.post_ref)))
    return selected, excluded


def _stable_balanced_order(candidates: Sequence[PoolCandidate]) -> list[PoolCandidate]:
    queues: dict[str, dict[str, deque[PoolCandidate]]] = {
        content_type: {} for content_type in _CONTENT_TYPES
    }
    for content_type in _CONTENT_TYPES:
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
    while any(queues[content_type] for content_type in _CONTENT_TYPES):
        for content_type in _CONTENT_TYPES:
            author_queues = queues[content_type]
            if not author_queues:
                continue
            author_id = next(iter(author_queues))
            queue = author_queues.pop(author_id)
            ordered.append(queue.popleft())
            if queue:
                author_queues[author_id] = queue
    return ordered


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
        rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def pool_candidate_digest(candidates: Sequence[PoolCandidate]) -> str:
    """Digest one release-class-neutral canonical candidate snapshot."""

    return _pool_digest(candidates)


def select_environment_release_posts(
    *,
    publish_root: Path,
    post_refs: Sequence[str],
    environment: str,
    release_class: str,
    strict_admission: bool = False,
) -> EnvironmentReleaseSelection:
    """Select one stable prefix from the shared pool for an explicit release class."""

    env = str(environment).strip()
    if env not in DATA_POST_CAPS:
        raise ObjectTransactionError(
            f"DATA.RELEASE.ENVIRONMENT_POLICY_INVALID: {env!r}"
        )
    release_mode = str(release_class or "").strip()
    if release_mode not in {"research", "commercial"}:
        raise ObjectTransactionError(f"DATA.RELEASE.CLASS_INVALID: {release_mode!r}")
    candidates, excluded = discover_pool_candidates(
        publish_root=publish_root,
        post_refs=post_refs,
        strict_admission=strict_admission,
    )
    latest, version_exclusions = _latest_versions(
        candidates,
        release_mode=release_mode,
    )
    excluded.extend(version_exclusions)
    ordered = _stable_balanced_order(latest)
    eligible_counts = {
        content_type: sum(row.content_type == content_type for row in latest)
        for content_type in _CONTENT_TYPES
    }
    cap = DATA_POST_CAPS[env]
    selected = ordered if cap is None else ordered[:cap]
    counts = {
        content_type: sum(row.content_type == content_type for row in selected)
        for content_type in _CONTENT_TYPES
    }
    counts["total"] = len(selected)
    return EnvironmentReleaseSelection(
        environment=env,
        release_mode=release_mode,
        post_refs=tuple(row.post_ref for row in selected),
        candidates=tuple(selected),
        # The digest identifies the shared, release-class-neutral candidate
        # snapshot. Research and Commercial filters over unchanged pool bytes
        # therefore bind the same poolDigest even though their selected sets
        # differ.
        pool_digest=_pool_digest(candidates),
        eligible_count=len(latest),
        eligible_counts=eligible_counts,
        counts=counts,
        excluded=tuple(
            sorted(excluded, key=lambda row: (row.gate, row.code, row.post_ref))
        ),
        selection_scope="target_environment",
    )


def select_all_publishable_release_posts(
    *,
    publish_root: Path,
    post_refs: Sequence[str],
    release_class: str,
    strict_admission: bool = True,
) -> EnvironmentReleaseSelection:
    """Select every publishable object without environment or milestone identity."""

    release_mode = str(release_class or "").strip()
    if release_mode not in {"research", "commercial"}:
        raise ObjectTransactionError(f"DATA.RELEASE.CLASS_INVALID: {release_mode!r}")
    candidates, excluded = discover_pool_candidates(
        publish_root=publish_root,
        post_refs=post_refs,
        strict_admission=strict_admission,
    )
    latest, version_exclusions = _latest_versions(
        candidates,
        release_mode=release_mode,
    )
    excluded.extend(version_exclusions)
    selected = _stable_balanced_order(latest)
    eligible_counts = {
        content_type: sum(row.content_type == content_type for row in latest)
        for content_type in _CONTENT_TYPES
    }
    counts = {
        content_type: sum(row.content_type == content_type for row in selected)
        for content_type in _CONTENT_TYPES
    }
    counts["total"] = len(selected)
    return EnvironmentReleaseSelection(
        environment=None,
        release_mode=release_mode,
        post_refs=tuple(row.post_ref for row in selected),
        candidates=tuple(selected),
        pool_digest=_pool_digest(candidates),
        eligible_count=len(latest),
        eligible_counts=eligible_counts,
        counts=counts,
        excluded=tuple(
            sorted(excluded, key=lambda row: (row.gate, row.code, row.post_ref))
        ),
        selection_scope="all_publishable",
    )


def select_milestone_release_posts(
    *,
    publish_root: Path,
    post_refs: Sequence[str],
    milestone: str,
    strict_admission: bool = True,
    allowed_entity_refs: set[str] | None = None,
) -> EnvironmentReleaseSelection:
    """Select an exact, deterministic Research cohort for one cumulative milestone."""

    milestone_name = str(milestone).strip()
    targets = MILESTONE_TARGETS.get(milestone_name)
    if targets is None:
        raise ObjectTransactionError(f"DATA.POOL.MILESTONE_INVALID: {milestone_name!r}")
    candidates, excluded = discover_pool_candidates(
        publish_root=publish_root,
        post_refs=post_refs,
        strict_admission=strict_admission,
        allowed_entity_refs=allowed_entity_refs,
    )
    latest, version_exclusions = _latest_versions(
        candidates,
        release_mode="research",
    )
    excluded.extend(version_exclusions)
    ordered = _stable_balanced_order(latest)
    eligible_counts = {
        content_type: sum(row.content_type == content_type for row in latest)
        for content_type in _CONTENT_TYPES
    }
    remaining = {carrier: targets[carrier] for carrier in _CONTENT_TYPES}
    selected: list[PoolCandidate] = []
    selected_entity_refs: set[str] = set()
    for candidate in ordered:
        if remaining[candidate.content_type] <= 0:
            continue
        manifest = _read_json(
            publish_root / "posts" / candidate.post_ref / "manifest.json"
        )
        raw_entity_refs = manifest.get("entityRefs")
        candidate_entity_refs = (
            {str(value).removeprefix("/entity/") for value in raw_entity_refs}
            if isinstance(raw_entity_refs, list)
            else set()
        )
        if (
            not candidate_entity_refs
            or len(selected_entity_refs | candidate_entity_refs) > targets["homepage"]
        ):
            excluded.append(
                PoolExclusion(
                    post_ref=candidate.post_ref,
                    gate="delivery",
                    code="DATA.POOL.MILESTONE_HOMEPAGE_BUDGET_EXCEEDED",
                )
            )
            continue
        selected.append(candidate)
        selected_entity_refs.update(candidate_entity_refs)
        remaining[candidate.content_type] -= 1
    if any(remaining.values()):
        counts = {
            carrier: targets[carrier] - remaining[carrier] for carrier in _CONTENT_TYPES
        }
        raise ObjectTransactionError(
            "DATA.POOL.MILESTONE_SHORTFALL: "
            f"milestone={milestone_name} targets="
            f"{ {carrier: targets[carrier] for carrier in _CONTENT_TYPES} } "
            f"publishable={counts}"
        )
    counts = {
        content_type: sum(row.content_type == content_type for row in selected)
        for content_type in _CONTENT_TYPES
    }
    counts["total"] = len(selected)
    return EnvironmentReleaseSelection(
        environment=None,
        release_mode="research",
        post_refs=tuple(row.post_ref for row in selected),
        candidates=tuple(selected),
        pool_digest=_pool_digest(candidates),
        eligible_count=len(latest),
        eligible_counts=eligible_counts,
        counts=counts,
        excluded=tuple(
            sorted(excluded, key=lambda row: (row.gate, row.code, row.post_ref))
        ),
        selection_scope="milestone",
        milestone=milestone_name,
        milestone_targets=dict(targets),
    )


__all__ = [
    "DATA_POST_CAPS",
    "MILESTONE_TARGETS",
    "EnvironmentReleaseSelection",
    "PoolExclusion",
    "discover_pool_candidates",
    "pool_candidate_digest",
    "pool_delivery_issue",
    "select_all_publishable_release_posts",
    "select_environment_release_posts",
    "select_milestone_release_posts",
    "source_attribution_complete",
]
