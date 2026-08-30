"""Read-only fail-closed proof for the M1000 four-environment exit."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.schema import assert_valid
from content.release.canonical.m1000_four_environment_proof_validation import (
    ENVIRONMENTS, REQUEST_SCHEMA, SCHEMA,
    M1000FourEnvironmentProofError, _digest, _load_exact, _safe_root, _text,
    _validate_environment, _validate_sampling, _validate_scale, exact_byte_digest,
)


def evaluate_m1000_four_environment_proof(
    *, artifact_root: Path, request: Mapping[str, Any]
) -> dict[str, Any]:
    """Evaluate selected evidence without producing content or touching environments."""
    assert_valid(
        request, "release", "m1000_four_environment_proof_request",
        label="prove-m1000-four-env request",
    )
    if request.get("schema") != REQUEST_SCHEMA:
        raise M1000FourEnvironmentProofError("request schema drifted")
    root = _safe_root(artifact_root)
    candidate_version = _text(request.get("candidateVersion"), label="candidateVersion")
    fingerprint = _digest(request.get("sourceFingerprint"), label="sourceFingerprint")
    release, _release_binding = _load_exact(root, request.get("m1000ReleaseHeader"), label="m1000ReleaseHeader")
    sample_plan, sample_binding = _load_exact(root, request.get("m1000SamplePlan"), label="m1000SamplePlan")
    promotion, _promotion_binding = _load_exact(root, request.get("m1000Promotion"), label="m1000Promotion")
    predecessor, predecessor_binding = _load_exact(root, request.get("m100PredecessorPromotion"), label="m100PredecessorPromotion")
    (
        release_id,
        release_digest,
        m1000_counts,
        m100_counts,
        m1000_delta,
    ) = _validate_scale(
        release=release, sample_plan=sample_plan, promotion=promotion,
        predecessor=predecessor, sample_binding=sample_binding,
        predecessor_binding=predecessor_binding,
    )
    strategy_digest, sample_distribution = _validate_sampling(
        root=root, release_id=release_id, release_digest=release_digest,
        sample_plan=sample_plan, freeze_ref=request.get("sampleStrategyFreeze"),
        approval_ref=request.get("sampleStrategyApproval"),
    )
    gates = request.get("environmentGates")
    if not isinstance(gates, list) or len(gates) != 4:
        raise M1000FourEnvironmentProofError("exactly four environment gates are required")
    projected: list[dict[str, Any]] = []
    previous: tuple[str, str, str] | None = None
    expected_package_digest: str | None = None
    for expected, gate in zip(ENVIRONMENTS, gates, strict=True):
        if not isinstance(gate, Mapping):
            raise M1000FourEnvironmentProofError("environment gate must be an object")
        row, previous = _validate_environment(
            root=root, gate=gate, expected_environment=expected,
            release_id=release_id, release_digest=release_digest,
            fingerprint=fingerprint, previous=previous,
            expected_package_digest=expected_package_digest,
        )
        if expected_package_digest is None:
            expected_package_digest = previous[2]
        projected.append(row)
    result = {
        "schema": SCHEMA,
        "candidateVersion": candidate_version,
        "sourceFingerprint": fingerprint,
        "releaseId": release_id,
        "releaseDigest": release_digest,
        "milestone": "M1000",
        "exactCohortCounts": dict(m1000_counts),
        "predecessorCounts": dict(m100_counts),
        "requiredNewCounts": dict(m1000_delta),
        "sampleStrategyDigest": strategy_digest,
        "sampleDistribution": sample_distribution,
        "environments": projected,
        "verdict": "pass",
    }
    assert_valid(
        result, "release", "m1000_four_environment_proof_result",
        label="prove-m1000-four-env result",
    )
    return result


__all__ = [
    "M1000FourEnvironmentProofError", "evaluate_m1000_four_environment_proof",
    "exact_byte_digest",
]
