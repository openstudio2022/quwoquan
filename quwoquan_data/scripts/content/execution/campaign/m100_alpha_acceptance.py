"""Validate the retired M100 campaign gate against canonical UAT authority facts.

This module is deletion-bound campaign code.  It only validates explicit refs and
must not discover, run, aggregate, or promote App UAT work.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from core.io import read_json
from core.schema import assert_valid
from governance.coverage.distribution import load_content_distribution_policy

from content.release.canonical.release_uat_sample_plan import (
    ReleaseUatSamplePlanError,
    validate_release_uat_sample_plan,
)
from quwoquan_ops.cli.lib.target_uat_binding import (
    TargetUatBindingError,
    validate_target_uat_binding,
)

_EXPECTED_DISTRIBUTION = {
    "homepage": 25,
    "article": 25,
    "image": 40,
    "video": 10,
}

class M100AlphaAcceptanceError(ValueError):
    """The canonical M100 Alpha UAT authority chain is incomplete or drifting."""


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _load_exact_json(
    ref: object,
    expected_digest: object,
    *,
    output_root: Path,
    label: str,
) -> tuple[dict[str, Any], str]:
    reference = str(ref or "").strip()
    digest = str(expected_digest or "").strip()
    if not reference or not digest:
        raise M100AlphaAcceptanceError(f"{label} binding is incomplete")
    root = output_root.expanduser().resolve()
    supplied = root / reference
    if supplied.expanduser().is_symlink():
        raise M100AlphaAcceptanceError(f"{label} must not be a symlink")
    try:
        resolved = supplied.expanduser().resolve(strict=True)
        observed_ref = resolved.relative_to(root).as_posix()
    except (FileNotFoundError, ValueError) as exc:
        raise M100AlphaAcceptanceError(
            f"{label} must be an existing file below QWQ_OUTPUT_ROOT"
        ) from exc
    if observed_ref != reference or _file_digest(resolved) != digest:
        raise M100AlphaAcceptanceError(f"{label} exact-byte digest drift")
    payload = read_json(resolved)
    if not isinstance(payload, Mapping):
        raise M100AlphaAcceptanceError(f"{label} must be an object")
    return dict(payload), observed_ref


def _validate_promotion_receipt(
    promotion: Mapping[str, Any], *, output_root: Path
) -> dict[str, Any]:
    receipt, _ = _load_exact_json(
        promotion.get("receiptRef"),
        promotion.get("receiptDigest"),
        output_root=output_root,
        label="M100 promotion receipt",
    )
    assert_valid(
        receipt,
        "release",
        "research_scale_promotion",
        label="M100 predecessor promotion",
    )
    expected = {
        "promotionId": promotion.get("promotionId"),
        "releaseId": promotion.get("releaseId"),
        "manifestDigest": promotion.get("manifestDigest"),
        "targetScale": "M100",
    }
    if any(receipt.get(field) != value for field, value in expected.items()):
        raise M100AlphaAcceptanceError("M100 promotion receipt identity drift")
    return receipt


def _plan_samples(plan: Mapping[str, Any]) -> list[dict[str, str]]:
    raw_samples = plan.get("samples")
    if not isinstance(raw_samples, list):
        raise M100AlphaAcceptanceError("M100 ReleaseUatSamplePlan samples are missing")
    samples: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    seen_objects: set[str] = set()
    for index, row in enumerate(raw_samples):
        if not isinstance(row, Mapping):
            raise M100AlphaAcceptanceError(
                f"M100 ReleaseUatSamplePlan sample[{index}] is invalid"
            )
        sample_id = str(row.get("sampleId") or "").strip()
        carrier = str(row.get("carrier") or "").strip()
        object_id = str(row.get("objectId") or "").strip()
        object_ref = str(row.get("objectRef") or "").strip()
        object_digest = str(row.get("objectDigest") or "").strip()
        if (
            not sample_id
            or sample_id in seen_ids
            or carrier not in _EXPECTED_DISTRIBUTION
            or not object_id
            or object_id in seen_objects
            or not object_ref
            or not object_digest.startswith("sha256:")
        ):
            raise M100AlphaAcceptanceError(
                "M100 ReleaseUatSamplePlan sample identities are invalid"
            )
        seen_ids.add(sample_id)
        seen_objects.add(object_id)
        samples.append(
            {
                "sampleId": sample_id,
                "carrier": carrier,
                "objectId": object_id,
                "objectRef": object_ref,
                "objectDigest": object_digest,
            }
        )
    return samples


def _validate_sample_plan(
    plan: Mapping[str, Any], *, expected_release_id: str
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    try:
        validated = validate_release_uat_sample_plan(
            plan,
            expected_release_id=expected_release_id,
            expected_milestone="M100",
        )
    except (ReleaseUatSamplePlanError, TypeError, ValueError) as exc:
        raise M100AlphaAcceptanceError(str(exc)) from exc
    samples = _plan_samples(validated)
    exact_counts = validated.get("exactCohortCounts")
    strategy = validated.get("sampleStrategy")
    distribution = (
        strategy.get("sampleDistribution")
        if isinstance(strategy, Mapping)
        else None
    )
    governed_counts = load_content_distribution_policy().milestone_targets()["M100"]
    if (
        validated.get("milestone") != "M100"
        or validated.get("sampleCount") != 100
        or not isinstance(exact_counts, Mapping)
        or dict(exact_counts) != governed_counts
        or distribution != _EXPECTED_DISTRIBUTION
        or Counter(sample["carrier"] for sample in samples)
        != Counter(_EXPECTED_DISTRIBUTION)
        or len(samples) != 100
    ):
        raise M100AlphaAcceptanceError(
            "DATA.SCALE.ALPHA_M100_RELEASE_UAT_SAMPLE_PLAN_INVALID: "
            "M100 requires an exact 100-case 25/25/40/10 plan"
        )
    return validated, samples


def _raw_acceptance_rows(acceptance: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = acceptance.get("requiredRawResults")
    if not isinstance(rows, list) or not rows:
        raise M100AlphaAcceptanceError(
            "Alpha EnvironmentAcceptanceFact must directly list required raw results"
        )
    return [row for row in rows if isinstance(row, Mapping)]


def _validate_raw_results(
    *,
    acceptance: Mapping[str, Any],
    planned_samples: Sequence[Mapping[str, str]],
    output_root: Path,
    release_id: str,
    target_bindings: Mapping[str, str],
) -> list[dict[str, str]]:
    acceptance_rows = _raw_acceptance_rows(acceptance)
    if len(acceptance_rows) != len(acceptance.get("requiredRawResults") or []):
        raise M100AlphaAcceptanceError(
            "Alpha EnvironmentAcceptanceFact required raw refs are invalid"
        )
    acceptance_by_ref: dict[str, Mapping[str, Any]] = {}
    for row in acceptance_rows:
        ref = str(row.get("ref") or "").strip()
        if not ref or ref in acceptance_by_ref:
            raise M100AlphaAcceptanceError(
                "Alpha EnvironmentAcceptanceFact required raw refs are duplicated"
            )
        acceptance_by_ref[ref] = row

    observed: dict[str, dict[str, str]] = {}
    for ref, acceptance_row in acceptance_by_ref.items():
        raw, _ = _load_exact_json(
            ref,
            acceptance_row.get("digest"),
            output_root=output_root,
            label=f"required raw result {ref}",
        )
        sample_id = str(raw.get("sampleId") or raw.get("caseId") or "").strip()
        carrier = str(raw.get("carrier") or "").strip()
        object_id = str(
            raw.get("sampleObjectId")
            or raw.get("sourceObjectId")
            or raw.get("observedObjectId")
            or raw.get("objectId")
            or ""
        ).strip()
        if (
            raw.get("status") != "passed"
            or raw.get("releaseId") != release_id
            or not sample_id
            or sample_id in observed
            or carrier not in _EXPECTED_DISTRIBUTION
            or not object_id
            or raw.get("targetUatBindingDigest") not in target_bindings
            or raw.get("provider")
            != target_bindings.get(str(raw.get("targetUatBindingDigest") or ""))
        ):
            raise M100AlphaAcceptanceError(
                "DATA.SCALE.ALPHA_M100_RAW_RESULT_DRIFT: required raw result failed "
                "or has stale sample identity"
            )
        for field in ("status", "entrySurface", "carrier", "specRef"):
            if field in acceptance_row and acceptance_row.get(field) != raw.get(field):
                raise M100AlphaAcceptanceError(
                    "Alpha EnvironmentAcceptanceFact required raw identity drift"
                )
        observed[sample_id] = {
            "sampleId": sample_id,
            "carrier": carrier,
            "objectId": object_id,
            "ref": ref,
            "digest": str(acceptance_row["digest"]),
        }

    planned = {str(row["sampleId"]): row for row in planned_samples}
    if set(observed) != set(planned):
        raise M100AlphaAcceptanceError(
            "DATA.SCALE.ALPHA_M100_RAW_RESULT_MISSING: raw results do not cover "
            "the exact M100 sample identities"
        )
    for sample_id, expected in planned.items():
        actual = observed[sample_id]
        if (
            actual["carrier"] != expected["carrier"]
            or actual["objectId"] != expected["objectId"]
        ):
            raise M100AlphaAcceptanceError(
                "DATA.SCALE.ALPHA_M100_RAW_RESULT_DRIFT: raw sample identity "
                "does not match ReleaseUatSamplePlan"
            )
    return [observed[str(row["sampleId"])] for row in planned_samples]


def _validate_acceptance(
    acceptance: Mapping[str, Any],
    *,
    release_id: str,
    manifest_digest: str,
    plan_ref: str,
    plan_digest: str,
    output_root: Path,
) -> dict[str, str]:
    if (
        acceptance.get("schema") != "quwoquan_ops.environment_acceptance_fact.v1"
        or acceptance.get("environment") != "alpha"
        or acceptance.get("releaseId") != release_id
        or acceptance.get("releaseDigest") != manifest_digest
        or acceptance.get("predecessorAcceptance") is not None
    ):
        raise M100AlphaAcceptanceError(
            "DATA.SCALE.ALPHA_M100_ACCEPTANCE_DRIFT: EnvironmentAcceptanceFact "
            "does not accept the same Alpha release"
        )
    if acceptance.get("samplePlanRef") != plan_ref:
        raise M100AlphaAcceptanceError("Alpha acceptance sample plan ref drift")
    if acceptance.get("samplePlanDigest") != plan_digest:
        raise M100AlphaAcceptanceError("Alpha acceptance sample plan digest drift")
    target_bindings = acceptance.get("targetBindingRefs")
    if not isinstance(target_bindings, list) or not target_bindings:
        raise M100AlphaAcceptanceError(
            "Alpha EnvironmentAcceptanceFact lacks direct TargetUatBinding refs"
        )
    providers_by_digest: dict[str, str] = {}
    for index, source in enumerate(target_bindings):
        if not isinstance(source, Mapping):
            raise M100AlphaAcceptanceError(
                "Alpha EnvironmentAcceptanceFact TargetUatBinding ref is invalid"
            )
        digest = str(source.get("digest") or "")
        target_binding, _ = _load_exact_json(
            source.get("ref"),
            digest,
            output_root=output_root,
            label=f"Alpha TargetUatBinding[{index}]",
        )
        try:
            target_binding = validate_target_uat_binding(target_binding)
        except TargetUatBindingError as exc:
            raise M100AlphaAcceptanceError(
                f"Alpha TargetUatBinding[{index}] is invalid: {exc}"
            ) from exc
        if (
            target_binding.get("environment") != "alpha"
            or target_binding.get("releaseId") != release_id
            or target_binding.get("releaseDigest") != manifest_digest
            or target_binding.get("releaseUatSamplePlanRef") != plan_ref
            or target_binding.get("releaseUatSamplePlanDigest") != plan_digest
        ):
            raise M100AlphaAcceptanceError(
                "Alpha TargetUatBinding release/sample-plan identity drift"
            )
        provider = target_binding.get("provider")
        provider_identity = (
            str(provider.get("identity") or "")
            if isinstance(provider, Mapping)
            else ""
        )
        if not provider_identity or digest in providers_by_digest:
            raise M100AlphaAcceptanceError(
                "Alpha TargetUatBinding provider identity is missing or duplicated"
            )
        providers_by_digest[digest] = provider_identity
    return providers_by_digest


def _validate_projection(
    *,
    projection_ref: str | None,
    projection_digest: str | None,
    output_root: Path,
    release_id: str,
    raw_rows: Sequence[Mapping[str, str]],
) -> None:
    if projection_ref is None and projection_digest is None:
        return
    projection, _ = _load_exact_json(
        projection_ref,
        projection_digest,
        output_root=output_root,
        label="App UAT completeness projection",
    )
    if (
        projection.get("schema") != "quwoquan_ops.app_uat_result_bundle.v1"
        or projection.get("releaseId") != release_id
    ):
        raise M100AlphaAcceptanceError("App UAT completeness projection identity drift")
    required_slots = projection.get("requiredSlots")
    if not isinstance(required_slots, list):
        raise M100AlphaAcceptanceError("App UAT completeness projection is invalid")
    projected_pairs = {
        (str(row.get("ref") or ""), str(row.get("digest") or ""))
        for slot in required_slots
        if isinstance(slot, Mapping)
        for row in slot.get("rawResults", [])
        if isinstance(row, Mapping)
    }
    raw_pairs = {(row["ref"], row["digest"]) for row in raw_rows}
    if projected_pairs != raw_pairs:
        raise M100AlphaAcceptanceError(
            "App UAT completeness projection does not diagnose the bound raw set"
        )


def bind_m100_alpha_acceptance(
    readiness_receipt: Path | None,
    app_uat_receipt: Path | None,
    *,
    predecessor_promotion: Mapping[str, Any],
    output_root: Path,
) -> dict[str, Any]:
    """Reject retired raw-input mode; canonical callers pass one frozen binding."""

    del readiness_receipt, app_uat_receipt, predecessor_promotion, output_root
    raise M100AlphaAcceptanceError(
        "DATA.SCALE.ALPHA_M100_ACCEPTANCE_RETIRED_INPUT: pass a canonical binding "
        "over ReleaseUatSamplePlan/raw results/EnvironmentAcceptanceFact"
    )


def validate_m100_alpha_acceptance_binding(
    binding: Mapping[str, Any], *, output_root: Path
) -> dict[str, Any]:
    try:
        assert_valid(
            dict(binding),
            "execution",
            "m100_alpha_acceptance_binding",
            label="M100 Alpha acceptance binding",
        )
    except (TypeError, ValueError) as exc:
        raise M100AlphaAcceptanceError(str(exc)) from exc
    promotion = {
        "promotionId": binding["promotionId"],
        "receiptRef": binding["promotionReceiptRef"],
        "receiptDigest": binding["promotionReceiptDigest"],
        "releaseId": binding["releaseId"],
        "manifestDigest": binding["manifestDigest"],
    }
    _validate_promotion_receipt(promotion, output_root=output_root)
    readiness, _ = _load_exact_json(
        binding["dataReadinessRef"],
        binding["dataReadinessExactByteDigest"],
        output_root=output_root,
        label="M100 Data readiness",
    )
    if (
        readiness.get("schema") != "quwoquan_data.environment_release_readiness"
        or readiness.get("environment") != "alpha"
        or readiness.get("releaseId") != binding["releaseId"]
        or readiness.get("manifestDigest") != binding["manifestDigest"]
        or readiness.get("passed") is not True
    ):
        raise M100AlphaAcceptanceError(
            "DATA.SCALE.ALPHA_M100_DATA_READINESS_DRIFT: Data readiness does not "
            "bind the same Alpha release"
        )
    plan, plan_ref = _load_exact_json(
        binding["releaseUatSamplePlanRef"],
        binding["releaseUatSamplePlanDigest"],
        output_root=output_root,
        label="M100 ReleaseUatSamplePlan",
    )
    validated_plan, planned_samples = _validate_sample_plan(
        plan, expected_release_id=str(binding["releaseId"])
    )
    acceptance, acceptance_ref = _load_exact_json(
        binding["alphaEnvironmentAcceptanceRef"],
        binding["alphaEnvironmentAcceptanceExactByteDigest"],
        output_root=output_root,
        label="Alpha EnvironmentAcceptanceFact",
    )
    target_bindings = _validate_acceptance(
        acceptance,
        release_id=str(binding["releaseId"]),
        manifest_digest=str(binding["manifestDigest"]),
        plan_ref=plan_ref,
        plan_digest=str(binding["releaseUatSamplePlanDigest"]),
        output_root=output_root,
    )
    raw_rows = _validate_raw_results(
        acceptance=acceptance,
        planned_samples=planned_samples,
        output_root=output_root,
        release_id=str(binding["releaseId"]),
        target_bindings=target_bindings,
    )
    expected_refs = [row["ref"] for row in raw_rows]
    expected_digests = [row["digest"] for row in raw_rows]
    if (
        list(binding["requiredRawResultRefs"]) != expected_refs
        or list(binding["requiredRawResultDigests"]) != expected_digests
        or binding["executedSampleCount"] != len(raw_rows)
    ):
        raise M100AlphaAcceptanceError(
            "M100 Alpha acceptance binding raw result coverage drift"
        )
    projection_ref = binding.get("appUatCompletenessProjectionRef")
    projection_digest = binding.get("appUatCompletenessProjectionDigest")
    _validate_projection(
        projection_ref=str(projection_ref) if projection_ref is not None else None,
        projection_digest=(
            str(projection_digest) if projection_digest is not None else None
        ),
        output_root=output_root,
        release_id=str(binding["releaseId"]),
        raw_rows=raw_rows,
    )
    # Keep the local variable so plan validation remains visibly authoritative.
    if validated_plan.get("milestone") != "M100":
        raise M100AlphaAcceptanceError("M100 ReleaseUatSamplePlan milestone drift")
    return dict(binding)


__all__ = [
    "M100AlphaAcceptanceError",
    "bind_m100_alpha_acceptance",
    "validate_m100_alpha_acceptance_binding",
]
