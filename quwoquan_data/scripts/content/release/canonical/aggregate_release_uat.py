"""Build and seal aggregate-release UAT sampling artifacts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from content.release.canonical.environment_release_selection import (
    EnvironmentReleaseSelection,
)
from content.release.canonical.object_source_identity import source_identity_set
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
    _digest_file,
    _write_json,
)
from content.release.canonical.release_uat_sample_plan import (
    PLAN_REF as UAT_SAMPLE_PLAN_REF,
)
from content.release.canonical.release_uat_sample_plan import (
    build_release_uat_sample_plan,
    canonical_digest,
    release_identity_digest,
)
from content.release.canonical.release_uat_sampling_authority import (
    load_release_uat_sampling_authority,
)


def derive_release_sample_source_identity_set_digest(
    *,
    environment_selection: EnvironmentReleaseSelection | None,
    source_identity_set_digest: str | None,
    execution_ids: Sequence[str],
    source_revision: str | None,
    source_digest: str | None,
    entity_catalog_digest: str | None,
) -> str | None:
    """Derive the sampling identity digest for environment-scoped releases."""
    if environment_selection is None or source_identity_set_digest is not None:
        return source_identity_set_digest
    _source_identities, digest = source_identity_set(
        [
            {
                "executionId": execution_id,
                "sourceRevision": str(source_revision or ""),
                "sourceDigest": str(source_digest or ""),
                "entityCatalogDigest": str(entity_catalog_digest or ""),
            }
            for execution_id in execution_ids
        ]
    )
    return digest


def build_release_uat_sample_plan_artifact(
    *,
    payload: Path,
    release_id: str,
    environment_selection: EnvironmentReleaseSelection | None,
    sample_source_identity_set_digest: str | None,
    selected_merkle: str,
    release_contents: Sequence[Mapping[str, object]] | None,
    entity_refs: Sequence[str],
    sampling_authority_artifact_root: Path | None,
    sampling_authority_binding: Mapping[str, str] | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Build and write the release-bound UAT plan for every content selection."""
    if environment_selection is None:
        return None, None

    sampling_authority: Mapping[str, Any] | None = None
    authority_args = (
        sampling_authority_artifact_root,
        sampling_authority_binding,
    )
    if environment_selection.milestone == "M1000":
        if any(item is None for item in authority_args):
            raise ObjectTransactionError(
                "DATA.RELEASE.UAT_SAMPLE_AUTHORITY_MISSING: M1000 aggregate "
                "build requires projected authority exact ref+digest"
            )
        contents_digest = canonical_digest(
            sorted(
                (dict(row) for row in (release_contents or [])),
                key=lambda row: (
                    str(row.get("contentId") or ""),
                    int(row.get("version") or 0),
                    str(row.get("postRef") or ""),
                ),
            )
        )
        selection_evidence = {
            "poolDigest": environment_selection.pool_digest,
            "sourceIdentitySetDigest": (
                sample_source_identity_set_digest or ""
            ),
            "canonicalMerkle": selected_merkle,
            "releaseContentsDigest": contents_digest,
            "releaseEntityCohortDigest": canonical_digest(
                sorted(str(ref) for ref in entity_refs)
            ),
        }
        expected_release_digest = release_identity_digest(
            release_id=release_id,
            canonical_merkle=selected_merkle,
            selection_evidence=selection_evidence,
        )
        sampling_authority = load_release_uat_sampling_authority(
            artifact_root=sampling_authority_artifact_root,
            authority_binding=sampling_authority_binding,
            release_id=release_id,
            release_digest=expected_release_digest,
        )
    elif any(item is not None for item in authority_args):
        raise ObjectTransactionError(
            "DATA.RELEASE.UAT_SAMPLE_AUTHORITY_UNEXPECTED: projected authority "
            "inputs apply only to M1000"
        )

    plan = build_release_uat_sample_plan(
        release_id=release_id,
        milestone=environment_selection.milestone,
        pool_digest=environment_selection.pool_digest,
        source_identity_set_digest=(sample_source_identity_set_digest or ""),
        canonical_merkle=selected_merkle,
        release_contents=release_contents or [],
        entity_refs=entity_refs,
        release_objects_root=payload / "objects",
        eligible_population_counts={
            **environment_selection.eligible_counts,
            "homepage": max(
                int(environment_selection.eligible_counts.get("homepage", 0)),
                len(entity_refs),
            ),
        },
        sampling_authority=sampling_authority,
    )
    plan_path = payload / UAT_SAMPLE_PLAN_REF
    _write_json(plan_path, plan)
    return plan, _digest_file(plan_path)


__all__ = [
    "UAT_SAMPLE_PLAN_REF",
    "build_release_uat_sample_plan_artifact",
    "derive_release_sample_source_identity_set_digest",
]
