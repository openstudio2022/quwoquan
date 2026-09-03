"""Data-owned, environment-neutral UAT sample plan for immutable releases."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from content.release.canonical.object_transaction_contract import ObjectTransactionError
from content.release.canonical.release_uat_sampling_authority import (
    ReleaseUatSamplingAuthorityError,
    validate_release_uat_sampling_authority,
)
from core.schema import assert_valid
from core.tree_integrity import tree_integrity_stats
from governance.coverage.distribution import load_content_distribution_policy

CARRIERS = ("homepage", "article", "image", "video")
ENTRIES = ("feed", "search", "recommendation", "direct_or_object_route")
PLAN_REF = "uat/sample_plan.json"
_SCHEMA = "quwoquan_data.release_uat_sample_plan"
_SPEC_REF = "specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#req-006"
_MILESTONE_COHORT_TARGETS = load_content_distribution_policy().milestone_targets()


class ReleaseUatSamplePlanError(ObjectTransactionError):
    """The release-bound UAT sample plan violates its closed contract."""


def exact_document_bytes(value: Mapping[str, Any]) -> bytes:
    """Return the exact bytes used by the immutable JSON writer."""
    return (
        json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def exact_document_sha256(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(exact_document_bytes(value)).hexdigest()


def canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def release_identity_digest(
    *,
    release_id: str,
    canonical_merkle: str,
    selection_evidence: Mapping[str, str],
) -> str:
    """Bind immutable release identity without hashing the plan or payload itself."""
    return canonical_digest(
        {
            "schema": "quwoquan_data.release_uat_sample_plan_identity",
            "releaseId": release_id,
            "canonicalMerkle": canonical_merkle,
            "selectionEvidence": dict(selection_evidence),
        }
    )


def release_object_digest(object_root: Path) -> str:
    """Digest one exact object subtree as released, including paths and bytes."""
    if object_root.is_symlink() or not object_root.is_dir():
        raise ReleaseUatSamplePlanError(
            f"DATA.RELEASE.UAT_SAMPLE_OBJECT_REF_INVALID: {object_root}"
        )
    return str(tree_integrity_stats(object_root)["merkleRoot"])


def _object_binding(
    *,
    release_objects_root: Path,
    carrier: str,
    identity: str,
    release_ref: str,
) -> tuple[str, str, str]:
    object_ref = (
        f"objects/entities/{release_ref}"
        if carrier == "homepage"
        else f"objects/posts/{release_ref}"
    )
    object_path = release_objects_root.parent / object_ref
    try:
        object_path.resolve(strict=True).relative_to(
            release_objects_root.resolve(strict=True)
        )
    except (FileNotFoundError, ValueError) as exc:
        raise ReleaseUatSamplePlanError(
            f"DATA.RELEASE.UAT_SAMPLE_OBJECT_REF_INVALID: {object_ref}"
        ) from exc
    return identity, object_ref, release_object_digest(object_path)


def _release_populations(
    release_contents: Sequence[Mapping[str, object]],
    entity_refs: Sequence[str],
    *,
    release_objects_root: Path,
) -> dict[str, list[tuple[str, str, str]]]:
    populations: dict[str, list[tuple[str, str, str]]] = {
        "homepage": sorted(
            _object_binding(
                release_objects_root=release_objects_root,
                carrier="homepage",
                identity=f"/entity/{str(ref).removeprefix('/entity/')}",
                release_ref=str(ref).removeprefix("/entity/"),
            )
            for ref in entity_refs
        ),
        "article": [],
        "image": [],
        "video": [],
    }
    for row in release_contents:
        post_ref = str(row.get("postRef") or "").strip()
        carrier = post_ref.partition("/")[0]
        identity = str(row.get("contentId") or "").strip()
        if carrier not in {"article", "image", "video"} or not identity or not post_ref:
            raise ReleaseUatSamplePlanError(
                "DATA.RELEASE.UAT_SAMPLE_CONTENT_IDENTITY_INVALID: "
                f"postRef={post_ref!r} contentId={identity!r}"
            )
        populations[carrier].append(
            _object_binding(
                release_objects_root=release_objects_root,
                carrier=carrier,
                identity=identity,
                release_ref=post_ref,
            )
        )
    for carrier in CARRIERS:
        rows = sorted(populations[carrier])
        identities = [identity for identity, _ref, _digest in rows]
        refs = [ref for _identity, ref, _digest in rows]
        if len(identities) != len(set(identities)) or len(refs) != len(set(refs)):
            raise ReleaseUatSamplePlanError(
                f"DATA.RELEASE.UAT_SAMPLE_COHORT_DUPLICATED: carrier={carrier}"
            )
        populations[carrier] = rows
    return populations


def _matrix() -> list[dict[str, str]]:
    return [
        {
            "entry": entry,
            "carrier": carrier,
            "applicability": "required",
            "specRef": _SPEC_REF,
            "runnerClass": f"qwq.content_consumer.{entry}.{carrier}.v1",
        }
        for entry in ENTRIES
        for carrier in CARRIERS
    ]


def _sample_distribution(
    *,
    milestone: str | None,
    populations: Mapping[str, Sequence[tuple[str, str, str]]],
    sampling_authority: Mapping[str, Any] | None,
) -> dict[str, int]:
    if milestone is not None:
        try:
            cohort_targets = _MILESTONE_COHORT_TARGETS[milestone]
        except KeyError as exc:
            raise ReleaseUatSamplePlanError(
                f"DATA.RELEASE.UAT_SAMPLE_MILESTONE_INVALID: {milestone!r}"
            ) from exc
        if milestone == "M100":
            if sampling_authority is not None:
                raise ReleaseUatSamplePlanError(
                    "DATA.RELEASE.UAT_SAMPLE_AUTHORITY_UNEXPECTED: M100 uses its frozen 25/25/40/10 contract"
                )
            return {
                "homepage": cohort_targets["homepage"] // 4,
                "article": cohort_targets["article"] // 4,
                "image": cohort_targets["image"] * 2 // 5,
                "video": cohort_targets["video"],
            }
        if milestone == "M1000":
            if not isinstance(sampling_authority, Mapping):
                raise ReleaseUatSamplePlanError(
                    "DATA.RELEASE.UAT_SAMPLE_AUTHORITY_MISSING: M1000 forbids implementation-selected auto-min distribution"
                )
            strategy = sampling_authority.get("strategy")
            distribution = (
                strategy.get("sampleDistribution")
                if isinstance(strategy, Mapping)
                else None
            )
            if not isinstance(distribution, Mapping) or set(distribution) != set(CARRIERS):
                raise ReleaseUatSamplePlanError(
                    "DATA.RELEASE.UAT_SAMPLE_AUTHORITY_INVALID: M1000 authority distribution is incomplete"
                )
            return {carrier: int(distribution[carrier]) for carrier in CARRIERS}
        if sampling_authority is not None:
            raise ReleaseUatSamplePlanError(
                "DATA.RELEASE.UAT_SAMPLE_AUTHORITY_UNSUPPORTED: external authority currently applies only to M1000"
            )
        sample_size = min(cohort_targets.values())
        return {carrier: sample_size for carrier in CARRIERS}
    if sampling_authority is not None:
        raise ReleaseUatSamplePlanError(
            "DATA.RELEASE.UAT_SAMPLE_AUTHORITY_UNEXPECTED: baseline plan has no milestone authority"
        )
    return {carrier: (1 if populations[carrier] else 0) for carrier in CARRIERS}


def build_release_uat_sample_plan(
    *,
    release_id: str,
    milestone: str | None,
    pool_digest: str,
    source_identity_set_digest: str,
    canonical_merkle: str,
    release_contents: Sequence[Mapping[str, object]],
    entity_refs: Sequence[str],
    release_objects_root: Path,
    eligible_population_counts: Mapping[str, int],
    sampling_authority: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one deterministic plan for every pool release selection scope."""
    populations = _release_populations(
        release_contents,
        entity_refs,
        release_objects_root=release_objects_root,
    )
    selection_evidence = {
        "poolDigest": pool_digest,
        "sourceIdentitySetDigest": source_identity_set_digest,
        "canonicalMerkle": canonical_merkle,
        "releaseContentsDigest": canonical_digest(
            sorted(
                (dict(row) for row in release_contents),
                key=lambda row: (
                    str(row.get("contentId") or ""),
                    int(row.get("version") or 0),
                    str(row.get("postRef") or ""),
                ),
            )
        ),
        "releaseEntityCohortDigest": canonical_digest(
            sorted(str(ref) for ref in entity_refs)
        ),
    }
    distribution = _sample_distribution(
        milestone=milestone,
        populations=populations,
        sampling_authority=sampling_authority,
    )
    prefix = milestone.lower() if milestone is not None else "baseline"
    samples: list[dict[str, str]] = []
    for carrier in CARRIERS:
        sample_size = distribution[carrier]
        if len(populations[carrier]) < sample_size:
            raise ReleaseUatSamplePlanError(
                "DATA.RELEASE.UAT_SAMPLE_SHORTFALL: "
                f"milestone={milestone!r} carrier={carrier} "
                f"required={sample_size} exact={len(populations[carrier])}"
            )
        for ordinal, (identity, object_ref, object_digest) in enumerate(
            populations[carrier][:sample_size], start=1
        ):
            samples.append(
                {
                    "sampleId": f"{prefix}-{carrier}-{ordinal:03d}",
                    "carrier": carrier,
                    "objectId": identity,
                    "objectRef": object_ref,
                    "objectDigest": object_digest,
                }
            )
    document: dict[str, Any] = {
        "schema": _SCHEMA,
        "releaseId": release_id,
        "releaseDigest": release_identity_digest(
            release_id=release_id,
            canonical_merkle=canonical_merkle,
            selection_evidence=selection_evidence,
        ),
        "milestone": milestone,
        "selectionEvidence": selection_evidence,
        "eligiblePopulationCounts": {
            carrier: int(eligible_population_counts.get(carrier, 0))
            for carrier in CARRIERS
        },
        "exactCohortCounts": {
            carrier: len(populations[carrier]) for carrier in CARRIERS
        },
        "entryCarrierCells": _matrix(),
        "sampleStrategy": {
            "authority": (dict(sampling_authority) if sampling_authority is not None else None),
            "name": (
                "stratified_exact" if milestone is not None
                else "baseline_per_required_carrier"
            ),
            "version": 1,
            "seedDigest": canonical_digest(
                {
                    "releaseDigest": release_identity_digest(
                        release_id=release_id,
                        canonical_merkle=canonical_merkle,
                        selection_evidence=selection_evidence,
                    ),
                    "sampleDistribution": distribution,
                }
            ),
            "carrierOrder": list(CARRIERS),
            "sortKey": "identity",
            "direction": "ascending",
            "objectDigestAlgorithm": "sha256-path-blob-merkle",
            "sampleDistribution": distribution,
        },
        "sampleCount": len(samples),
        "samples": samples,
    }
    return validate_release_uat_sample_plan(
        document,
        release_contents=release_contents,
        entity_refs=entity_refs,
        release_objects_root=release_objects_root,
        expected_release_id=release_id,
        expected_milestone=milestone,
        expected_selection_evidence=selection_evidence,
    )


def validate_release_uat_sample_plan(
    value: object,
    *,
    release_contents: Sequence[Mapping[str, object]] | None = None,
    entity_refs: Sequence[str] | None = None,
    release_objects_root: Path | None = None,
    expected_release_id: str | None = None,
    expected_milestone: str | None = None,
    expected_selection_evidence: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Validate schema and release-bound cross-field invariants."""
    try:
        assert_valid(
            value,
            "release",
            "release_uat_sample_plan",
            label="release_uat_sample_plan",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise ReleaseUatSamplePlanError(
            f"DATA.RELEASE.UAT_SAMPLE_SCHEMA_INVALID: {exc}"
        ) from exc
    if not isinstance(value, Mapping):
        raise ReleaseUatSamplePlanError(
            "DATA.RELEASE.UAT_SAMPLE_SCHEMA_INVALID: document must be an object"
        )
    document = dict(value)
    release_id = str(document["releaseId"])
    milestone = document["milestone"]
    if milestone is not None:
        milestone = str(milestone)
    if milestone is not None and milestone not in _MILESTONE_COHORT_TARGETS:
        raise ReleaseUatSamplePlanError(
            f"DATA.RELEASE.UAT_SAMPLE_MILESTONE_INVALID: {milestone!r}"
        )
    if expected_release_id is not None and release_id != expected_release_id:
        raise ReleaseUatSamplePlanError("DATA.RELEASE.UAT_SAMPLE_RELEASE_ID_DRIFT")
    if expected_milestone is not None and milestone != expected_milestone:
        raise ReleaseUatSamplePlanError("DATA.RELEASE.UAT_SAMPLE_MILESTONE_DRIFT")
    evidence = document["selectionEvidence"]
    if not isinstance(evidence, Mapping):
        raise ReleaseUatSamplePlanError(
            "DATA.RELEASE.UAT_SAMPLE_SELECTION_EVIDENCE_INVALID"
        )
    if expected_selection_evidence is not None and dict(evidence) != dict(
        expected_selection_evidence
    ):
        raise ReleaseUatSamplePlanError(
            "DATA.RELEASE.UAT_SAMPLE_SELECTION_EVIDENCE_DRIFT"
        )
    expected_release_digest = release_identity_digest(
        release_id=release_id,
        canonical_merkle=str(evidence["canonicalMerkle"]),
        selection_evidence={key: str(item) for key, item in evidence.items()},
    )
    if document["releaseDigest"] != expected_release_digest:
        raise ReleaseUatSamplePlanError("DATA.RELEASE.UAT_SAMPLE_RELEASE_DIGEST_DRIFT")

    exact_counts = document["exactCohortCounts"]
    eligible_counts = document["eligiblePopulationCounts"]
    if not isinstance(exact_counts, Mapping) or not isinstance(eligible_counts, Mapping):
        raise ReleaseUatSamplePlanError("DATA.RELEASE.UAT_SAMPLE_POPULATION_INVALID")
    if any(
        int(eligible_counts[carrier]) < int(exact_counts[carrier])
        for carrier in CARRIERS
    ):
        raise ReleaseUatSamplePlanError(
            "DATA.RELEASE.UAT_SAMPLE_ELIGIBLE_POPULATION_SHORTFALL"
        )
    if milestone is not None and dict(exact_counts) != _MILESTONE_COHORT_TARGETS[milestone]:
        raise ReleaseUatSamplePlanError(
            "DATA.RELEASE.UAT_SAMPLE_EXACT_COHORT_DRIFT: "
            f"expected={_MILESTONE_COHORT_TARGETS[milestone]} actual={dict(exact_counts)}"
        )

    expected_cells = _matrix()
    if document["entryCarrierCells"] != expected_cells:
        raise ReleaseUatSamplePlanError("DATA.RELEASE.UAT_SAMPLE_ENTRY_CARRIER_DRIFT")
    policy = document["sampleStrategy"]
    if not isinstance(policy, Mapping):
        raise ReleaseUatSamplePlanError("DATA.RELEASE.UAT_SAMPLE_STRATEGY_INVALID")
    expected_name = (
        "stratified_exact" if milestone is not None else "baseline_per_required_carrier"
    )
    if (
        policy.get("name") != expected_name
        or policy.get("objectDigestAlgorithm") != "sha256-path-blob-merkle"
    ):
        raise ReleaseUatSamplePlanError("DATA.RELEASE.UAT_SAMPLE_STRATEGY_DRIFT")

    samples = document["samples"]
    if not isinstance(samples, list) or document["sampleCount"] != len(samples):
        raise ReleaseUatSamplePlanError("DATA.RELEASE.UAT_SAMPLE_COUNT_DRIFT")
    distribution = policy.get("sampleDistribution")
    if not isinstance(distribution, Mapping) or Counter(
        str(sample.get("carrier")) for sample in samples
    ) != Counter(distribution):
        raise ReleaseUatSamplePlanError("DATA.RELEASE.UAT_SAMPLE_DISTRIBUTION_DRIFT")
    authority = policy.get("authority")
    if milestone == "M1000":
        if not isinstance(authority, Mapping):
            raise ReleaseUatSamplePlanError("DATA.RELEASE.UAT_SAMPLE_AUTHORITY_MISSING")
        try:
            authority = validate_release_uat_sampling_authority(
                authority, release_id=release_id,
                release_digest=str(document["releaseDigest"]),
            )
        except ReleaseUatSamplingAuthorityError as exc:
            raise ReleaseUatSamplePlanError(
                f"DATA.RELEASE.UAT_SAMPLE_AUTHORITY_DRIFT: {exc}"
            ) from exc
    elif authority is not None:
        raise ReleaseUatSamplePlanError("DATA.RELEASE.UAT_SAMPLE_AUTHORITY_UNEXPECTED")
    if milestone is not None and dict(distribution) != _sample_distribution(
        milestone=milestone,
        populations={carrier: () for carrier in CARRIERS},
        sampling_authority=authority if isinstance(authority, Mapping) else None,
    ):
        raise ReleaseUatSamplePlanError("DATA.RELEASE.UAT_SAMPLE_DISTRIBUTION_DRIFT")
    if milestone is None and any(
        int(distribution[carrier]) != (1 if int(exact_counts[carrier]) > 0 else 0)
        for carrier in CARRIERS
    ):
        raise ReleaseUatSamplePlanError("DATA.RELEASE.UAT_SAMPLE_CANARY_DRIFT")
    sample_ids = [str(sample.get("sampleId") or "") for sample in samples]
    object_ids = [str(sample.get("objectId") or "") for sample in samples]
    refs = [str(sample.get("objectRef") or "") for sample in samples]
    if (
        len(sample_ids) != len(set(sample_ids))
        or len(object_ids) != len(set(object_ids))
        or len(refs) != len(set(refs))
    ):
        raise ReleaseUatSamplePlanError(
            "DATA.RELEASE.UAT_SAMPLE_IDENTITY_DUPLICATED"
        )

    release_inputs = (release_contents, entity_refs, release_objects_root)
    if any(item is not None for item in release_inputs) and not all(
        item is not None for item in release_inputs
    ):
        raise ReleaseUatSamplePlanError(
            "DATA.RELEASE.UAT_SAMPLE_RELEASE_INPUT_INCOMPLETE"
        )
    if (
        release_contents is not None
        and entity_refs is not None
        and release_objects_root is not None
    ):
        populations = _release_populations(
            release_contents,
            entity_refs,
            release_objects_root=release_objects_root,
        )
        actual_counts = {carrier: len(populations[carrier]) for carrier in CARRIERS}
        if dict(exact_counts) != actual_counts:
            raise ReleaseUatSamplePlanError(
                "DATA.RELEASE.UAT_SAMPLE_EXACT_COHORT_DRIFT"
            )
        expected_distribution = {
            carrier: int(distribution[carrier]) for carrier in CARRIERS
        }
        prefix = milestone.lower() if milestone is not None else "baseline"
        expected_samples = [
            {
                "sampleId": f"{prefix}-{carrier}-{ordinal:03d}",
                "carrier": carrier,
                "objectId": identity,
                "objectRef": object_ref,
                "objectDigest": object_digest,
            }
            for carrier in CARRIERS
            for ordinal, (identity, object_ref, object_digest) in enumerate(
                populations[carrier][: expected_distribution[carrier]], start=1
            )
        ]
        if len(samples) != len(expected_samples):
            raise ReleaseUatSamplePlanError(
                "DATA.RELEASE.UAT_SAMPLE_SELECTION_DRIFT"
            )
        for actual_sample, expected_sample in zip(
            samples, expected_samples, strict=True
        ):
            if actual_sample.get("objectRef") != expected_sample["objectRef"]:
                raise ReleaseUatSamplePlanError(
                    "DATA.RELEASE.UAT_SAMPLE_OBJECT_REF_DRIFT"
                )
            if actual_sample.get("objectDigest") != expected_sample["objectDigest"]:
                raise ReleaseUatSamplePlanError(
                    "DATA.RELEASE.UAT_SAMPLE_OBJECT_DIGEST_DRIFT"
                )
            if actual_sample != expected_sample:
                raise ReleaseUatSamplePlanError(
                    "DATA.RELEASE.UAT_SAMPLE_SELECTION_DRIFT"
                )
    expected_seed = canonical_digest(
        {
            "releaseDigest": document["releaseDigest"],
            "sampleDistribution": dict(distribution),
        }
    )
    if policy.get("seedDigest") != expected_seed:
        raise ReleaseUatSamplePlanError("DATA.RELEASE.UAT_SAMPLE_SEED_DRIFT")
    return document


__all__ = [
    "CARRIERS",
    "ENTRIES",
    "PLAN_REF",
    "ReleaseUatSamplePlanError",
    "build_release_uat_sample_plan",
    "canonical_digest",
    "exact_document_bytes",
    "exact_document_sha256",
    "release_identity_digest",
    "release_object_digest",
    "validate_release_uat_sample_plan",
]
