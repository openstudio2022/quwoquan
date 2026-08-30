# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-004
"""prove-m1000-four-env is explicit, read-only, and fail-closed."""
from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[4]
DATA_SCRIPTS = ROOT / "quwoquan_data" / "scripts"
OPS_ROOT = ROOT / "quwoquan_ops"
for value in (DATA_SCRIPTS, OPS_ROOT):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

from content.release.canonical import (  # noqa: E402
    m1000_four_environment_proof_validation as validation,
)
from content.release.canonical.m1000_four_environment_proof import (  # noqa: E402
    M1000FourEnvironmentProofError,
    evaluate_m1000_four_environment_proof,
)
from content.release.canonical.release_uat_sample_plan import canonical_digest  # noqa: E402

D = "sha256:" + "a" * 64
FINGERPRINT = "sha256:" + "f" * 64
PACKAGE_DIGEST = "sha256:" + "b" * 64
RELEASE_DIGEST = "sha256:" + "c" * 64
M1000 = {"homepage": 1000, "article": 1000, "image": 1000, "video": 100}
M100 = {"homepage": 100, "article": 100, "image": 100, "video": 10}
DELTA = {"homepage": 900, "article": 900, "image": 900, "video": 90}
ENVIRONMENTS = ("alpha", "beta", "gamma", "prod")
ROLES = (
    "product_owner", "data_content_operations_owner", "quality_user_representative",
    "environment_reliability_owner", "release_owner",
)


def _write(root: Path, ref: str, value: dict[str, Any]) -> dict[str, str]:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.write_bytes(raw)
    return {"ref": ref, "digest": "sha256:" + hashlib.sha256(raw).hexdigest()}


def _carrier_rows(target: dict[str, int], carried: dict[str, int]) -> list[dict[str, Any]]:
    return [
        {
            "carrier": carrier,
            "targetCount": target[carrier],
            "predecessorCarriedCount": carried[carrier],
            "newFinalizedCount": target[carrier] - carried[carrier],
            "totalUniqueFinalizedCount": target[carrier],
            "selectedCount": target[carrier],
            "shortfallCount": 0,
        }
        for carrier in ("homepage", "article", "image", "video")
    ]


def _target_binding(
    *, environment: str, target: str, platform: str, profile: str, device: str,
    candidate: str = FINGERPRINT, package: str = PACKAGE_DIGEST,
) -> dict[str, Any]:
    return {
        "schema": "quwoquan_ops.target_uat_binding.v1",
        "releaseId": "release-m1000",
        "releaseDigest": RELEASE_DIGEST,
        "releaseUatSamplePlanRef": "release/sample-plan.json",
        "releaseUatSamplePlanDigest": D,
        "environment": environment,
        "target": target,
        "candidateDigest": candidate,
        "packageDigest": package,
        "platform": platform,
        "profile": profile,
        "provider": {"identity": "provider-real"},
        "device": {"identity": device, "class": "physical", "registered": True},
    }


def _build(
    tmp_path: Path,
    *,
    m100: dict[str, int] | None = None,
    m1000: dict[str, int] | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    m100_targets = dict(M100 if m100 is None else m100)
    m1000_targets = dict(M1000 if m1000 is None else m1000)
    predecessor = {
        "schema": "quwoquan_data.research_scale_promotion",
        "promotionId": "promotion-m100",
        "releaseId": "release-m100",
        "targetScale": "M100",
        "carrierCounts": _carrier_rows(m100_targets, {carrier: 0 for carrier in m100_targets}),
    }
    predecessor_ref = _write(tmp_path, "scale/m100.json", predecessor)
    sample_distribution = {"homepage": 13, "article": 17, "image": 19, "video": 7}
    samples = [
        {"sampleId": f"{carrier}-{index}", "carrier": carrier}
        for carrier in sample_distribution
        for index in range(sample_distribution[carrier])
    ]
    sample_plan = {
        "schema": "quwoquan_data.release_uat_sample_plan",
        "releaseId": "release-m1000",
        "releaseDigest": RELEASE_DIGEST,
        "milestone": "M1000",
        "exactCohortCounts": m1000_targets,
        "sampleStrategy": {"sampleDistribution": sample_distribution},
        "sampleCount": sum(sample_distribution.values()),
        "samples": samples,
    }
    sample_ref = _write(tmp_path, "release/sample-plan.json", sample_plan)
    release = {
        "schema": "quwoquan_data.release",
        "releaseId": "release-m1000",
        "releaseKind": "content",
        "releaseClass": "research",
        "selectionScope": "milestone",
        "milestone": "M1000",
        "milestoneTargets": m1000_targets,
        "samplePlanRef": sample_ref["ref"],
        "samplePlanDigest": sample_ref["digest"],
    }
    release_ref = _write(tmp_path, "release/header.json", release)
    promotion = {
        "schema": "quwoquan_data.research_scale_promotion",
        "promotionId": "promotion-m1000",
        "releaseId": "release-m1000",
        "targetScale": "M1000",
        "predecessorPromotion": {
            "promotionId": predecessor["promotionId"],
            "releaseId": predecessor["releaseId"],
            "manifestDigest": D,
            "targetScale": "M100",
            "receiptRef": predecessor_ref["ref"],
            "receiptDigest": predecessor_ref["digest"],
        },
        "carrierCounts": _carrier_rows(m1000_targets, m100_targets),
    }
    promotion_ref = _write(tmp_path, "scale/m1000.json", promotion)
    strategy = {
        "selectorId": "joint-selector",
        "selectorVersion": 1,
        "sampleDistribution": sample_distribution,
    }
    approval = {
        "schema": "quwoquan_data.m1000_app_uat_sample_approval",
        "strategyDigest": canonical_digest(strategy),
        "approvals": [
            {"role": "product_owner", "authorityId": "product-a", "decision": "approved"},
            {"role": "quality_owner", "authorityId": "quality-b", "decision": "approved"},
        ],
    }
    approval_ref = _write(tmp_path, "sampling/approval.json", approval)
    freeze = {
        "schema": "quwoquan_data.m1000_app_uat_sample_freeze",
        "milestone": "M1000",
        "releaseId": "release-m1000",
        "releaseDigest": RELEASE_DIGEST,
        "strategy": strategy,
        "strategyDigest": canonical_digest(strategy),
        "approvalRef": approval_ref["ref"],
        "approvalDigest": approval_ref["digest"],
    }
    freeze_ref = _write(tmp_path, "sampling/freeze.json", freeze)

    previous: tuple[str, dict[str, str]] | None = None
    gates: list[dict[str, Any]] = []
    mutable: dict[str, dict[str, Any]] = {
        "promotion": promotion,
        "freeze": freeze,
        "approval": approval,
    }
    for environment in ENVIRONMENTS:
        target = f"{environment}-target"
        profiles = (
            ("android", "production" if environment == "prod" else "promotable", f"{environment}-android"),
            ("ios", "production" if environment == "prod" else "promotable", f"{environment}-ios"),
        )
        binding_refs = []
        for platform, profile, device in profiles:
            binding = _target_binding(
                environment=environment, target=target, platform=platform,
                profile=profile, device=device,
            )
            exact = _write(tmp_path, f"{environment}/binding-{platform}.json", binding)
            binding_refs.append({**exact, "platform": platform, "deviceProfile": profile})
        lifecycle = {
            "schema": "quwoquan_data.environment_release_lifecycle_exit",
            "environment": environment,
            "originalReleaseId": "release-m1000",
            "replayManifestDigest": RELEASE_DIGEST,
            "passed": True,
        }
        lifecycle_ref = _write(tmp_path, f"{environment}/lifecycle.json", lifecycle)
        acceptance = {
            "schema": "quwoquan_ops.environment_acceptance_fact.v1",
            "factId": "sha256:" + ({"alpha": "1", "beta": "2", "gamma": "3", "prod": "4"}[environment]) * 64,
            "environment": environment,
            "target": target,
            "releaseId": "release-m1000",
            "releaseDigest": RELEASE_DIGEST,
            "sourceFingerprint": FINGERPRINT,
            "targetBindingRefs": binding_refs,
            "activeCas": {"releaseDigest": RELEASE_DIGEST},
            "lifecycleExit": lifecycle_ref,
            "predecessorAcceptance": (
                None
                if previous is None
                else {
                    "environment": previous[0],
                    "factId": previous[1]["factId"],
                    "ref": previous[1]["ref"],
                    "digest": previous[1]["digest"],
                }
            ),
        }
        acceptance_ref = _write(tmp_path, f"{environment}/acceptance.json", acceptance)
        previous = (
            environment,
            {"factId": acceptance["factId"], **acceptance_ref},
        )
        capacity = {
            "environment": environment, "target": target,
            "releaseId": "release-m1000", "releaseDigest": RELEASE_DIGEST,
            "sourceFingerprint": FINGERPRINT, "status": "passed",
            "withinCapacityBudget": True, "withinTimelinessBudget": True,
        }
        capacity_ref = _write(tmp_path, f"{environment}/capacity.json", capacity)
        fault = {
            "environment": environment, "target": target,
            "releaseId": "release-m1000", "releaseDigest": RELEASE_DIGEST,
            "sourceFingerprint": FINGERPRINT, "status": "passed",
            "automaticRecoveryStatus": "MEASURED",
            "rollbackVerified": True, "replayVerified": True,
        }
        fault_ref = _write(tmp_path, f"{environment}/fault.json", fault)
        acceptances = []
        for role in ROLES:
            role_fact = {
                "environment": environment, "target": target,
                "releaseId": "release-m1000", "releaseDigest": RELEASE_DIGEST,
                "sourceFingerprint": FINGERPRINT, "status": "accepted",
                "role": role, "decision": "accepted",
            }
            role_ref = _write(tmp_path, f"{environment}/role-{role}.json", role_fact)
            acceptances.append({"role": role, **role_ref})
        gates.append({
            "environment": environment,
            "target": target,
            "environmentAcceptanceFact": acceptance_ref,
            "capacityTimeliness": capacity_ref,
            "faultRecovery": fault_ref,
            "responsibilityAcceptances": acceptances,
        })
        mutable[f"{environment}_acceptance"] = acceptance
    request = {
        "schema": "quwoquan_data.m1000_four_environment_proof_request",
        "candidateVersion": "candidate-v1",
        "sourceFingerprint": FINGERPRINT,
        "m1000ReleaseHeader": release_ref,
        "m1000SamplePlan": sample_ref,
        "m1000Promotion": promotion_ref,
        "m100PredecessorPromotion": predecessor_ref,
        "sampleStrategyFreeze": freeze_ref,
        "sampleStrategyApproval": approval_ref,
        "environmentGates": gates,
    }
    return request, mutable


def _patch_exact(root: Path, binding: dict[str, str], value: dict[str, Any]) -> None:
    updated = _write(root, binding["ref"], value)
    binding["digest"] = updated["digest"]


def _relaxed_environment_acceptance(
    payload: dict[str, Any], **_kwargs: object
) -> dict[str, Any]:
    return payload


def test_pass__uses_exact_delta_joint_strategy_same_package_and_four_env_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, _ = _build(tmp_path)
    monkeypatch.setattr(
        "content.release.canonical.m1000_four_environment_proof_validation.validate_environment_acceptance_fact",
        _relaxed_environment_acceptance,
    )
    result = evaluate_m1000_four_environment_proof(
        artifact_root=tmp_path, request=request
    )

    assert result["exactCohortCounts"] == M1000
    assert result["predecessorCounts"] == M100
    assert result["requiredNewCounts"] == DELTA
    assert result["sampleDistribution"] == {
        "homepage": 13, "article": 17, "image": 19, "video": 7,
    }
    assert [row["environment"] for row in result["environments"]] == list(ENVIRONMENTS)
    assert result["verdict"] == "pass"


def test_m1000_targets_and_delta_follow_distribution_policy_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = validation.load_content_distribution_policy().milestone_targets()
    m100 = {
        carrier: count + index + 1
        for index, (carrier, count) in enumerate(current["M100"].items())
    }
    m1000 = {
        carrier: count + (index + 1) * 10
        for index, (carrier, count) in enumerate(current["M1000"].items())
    }
    delta = {carrier: m1000[carrier] - m100[carrier] for carrier in m1000}

    class DriftedPolicy:
        def milestone_targets(self) -> dict[str, dict[str, int]]:
            return {"M100": m100, "M1000": m1000}

    monkeypatch.setattr(
        validation, "load_content_distribution_policy", lambda: DriftedPolicy()
    )
    monkeypatch.setattr(
        validation,
        "validate_environment_acceptance_fact",
        _relaxed_environment_acceptance,
    )
    request, _ = _build(tmp_path, m100=m100, m1000=m1000)

    result = evaluate_m1000_four_environment_proof(
        artifact_root=tmp_path, request=request
    )

    assert result["exactCohortCounts"] == m1000
    assert result["predecessorCounts"] == m100
    assert result["requiredNewCounts"] == delta


def test_fail_closed__rejects_delta_sampling_role_candidate_and_package_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "content.release.canonical.m1000_four_environment_proof_validation.validate_environment_acceptance_fact",
        _relaxed_environment_acceptance,
    )

    request, mutable = _build(tmp_path / "delta")
    mutable["promotion"]["carrierCounts"][0]["newFinalizedCount"] = 899
    _patch_exact(tmp_path / "delta", request["m1000Promotion"], mutable["promotion"])
    with pytest.raises(M1000FourEnvironmentProofError, match="delta"):
        evaluate_m1000_four_environment_proof(artifact_root=tmp_path / "delta", request=request)

    request, mutable = _build(tmp_path / "sampling")
    mutable["approval"]["approvals"][1]["authorityId"] = "product-a"
    _patch_exact(tmp_path / "sampling", request["sampleStrategyApproval"], mutable["approval"])
    mutable["freeze"]["approvalDigest"] = request["sampleStrategyApproval"]["digest"]
    _patch_exact(tmp_path / "sampling", request["sampleStrategyFreeze"], mutable["freeze"])
    with pytest.raises(M1000FourEnvironmentProofError, match="distinct"):
        evaluate_m1000_four_environment_proof(artifact_root=tmp_path / "sampling", request=request)

    request, _ = _build(tmp_path / "role")
    request["environmentGates"][2]["responsibilityAcceptances"].pop()
    with pytest.raises((M1000FourEnvironmentProofError, ValueError), match="responsibility|数量"):
        evaluate_m1000_four_environment_proof(artifact_root=tmp_path / "role", request=request)

    request, _ = _build(tmp_path / "candidate")
    binding_ref = request["environmentGates"][1]["environmentAcceptanceFact"]
    acceptance = json.loads((tmp_path / "candidate" / binding_ref["ref"]).read_text())
    target_binding = acceptance["targetBindingRefs"][0]
    binding = json.loads((tmp_path / "candidate" / target_binding["ref"]).read_text())
    binding["candidateDigest"] = "sha256:" + "9" * 64
    updated = _write(tmp_path / "candidate", target_binding["ref"], binding)
    target_binding["digest"] = updated["digest"]
    _patch_exact(tmp_path / "candidate", binding_ref, acceptance)
    with pytest.raises(M1000FourEnvironmentProofError, match="current candidate"):
        evaluate_m1000_four_environment_proof(artifact_root=tmp_path / "candidate", request=request)

    request, _ = _build(tmp_path / "package")
    binding_ref = request["environmentGates"][3]["environmentAcceptanceFact"]
    acceptance = json.loads((tmp_path / "package" / binding_ref["ref"]).read_text())
    target_binding = acceptance["targetBindingRefs"][0]
    binding = json.loads((tmp_path / "package" / target_binding["ref"]).read_text())
    binding["packageDigest"] = "sha256:" + "8" * 64
    updated = _write(tmp_path / "package", target_binding["ref"], binding)
    target_binding["digest"] = updated["digest"]
    _patch_exact(tmp_path / "package", binding_ref, acceptance)
    with pytest.raises(M1000FourEnvironmentProofError, match="immutable package|Alpha"):
        evaluate_m1000_four_environment_proof(artifact_root=tmp_path / "package", request=request)


def test_fail_closed__rejects_missing_raw_evidence_before_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "content.release.canonical.m1000_four_environment_proof_validation.validate_environment_acceptance_fact",
        _relaxed_environment_acceptance,
    )
    request, _ = _build(tmp_path)
    request["environmentGates"][0]["faultRecovery"]["ref"] = "alpha/missing.json"
    with pytest.raises(M1000FourEnvironmentProofError, match="unavailable"):
        evaluate_m1000_four_environment_proof(artifact_root=tmp_path, request=request)
