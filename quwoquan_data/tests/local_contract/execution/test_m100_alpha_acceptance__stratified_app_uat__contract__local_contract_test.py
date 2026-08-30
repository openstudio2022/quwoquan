"""M100 Alpha acceptance consumes canonical plan, raw results and acceptance fact.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-006.t1
spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-006.t2
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import content.execution.campaign.m100_alpha_acceptance as subject
import pytest
from core.schema import assert_valid

from quwoquan_ops.cli.lib.target_uat_binding import build_target_uat_binding

DISTRIBUTION = {"homepage": 25, "article": 25, "image": 40, "video": 10}
MANIFEST_DIGEST = "sha256:" + "b" * 64
SPEC_REF = (
    "specs/feature-tree/runtime/runtime-config/"
    "environment-topology-and-packaging/spec.md#gwt-006"
)


def _write(root: Path, ref: str, payload: object) -> tuple[str, str]:
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return ref, "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _samples() -> list[dict[str, str]]:
    return [
        {
            "sampleId": f"m100-{carrier}-{ordinal:03d}",
            "carrier": carrier,
            "objectId": f"{carrier}-{ordinal:03d}",
            "objectRef": (
                f"objects/entities/{carrier}-{ordinal:03d}"
                if carrier == "homepage"
                else f"objects/posts/{carrier}/{carrier}-{ordinal:03d}"
            ),
            "objectDigest": "sha256:"
            + hashlib.sha256(f"{carrier}-{ordinal:03d}".encode()).hexdigest(),
        }
        for carrier, count in DISTRIBUTION.items()
        for ordinal in range(1, count + 1)
    ]


def _plan() -> dict[str, object]:
    return {
        "schema": "quwoquan_data.release_uat_sample_plan",
        "releaseId": "release-m100",
        "milestone": "M100",
        "exactCohortCounts": {
            "homepage": 100,
            "article": 100,
            "image": 100,
            "video": 10,
        },
        "sampleCount": 100,
        "sampleStrategy": {
            "sampleDistribution": DISTRIBUTION,
            "objectDigestAlgorithm": "sha256-path-blob-merkle",
        },
        "samples": _samples(),
    }


def _patch_plan_validator(monkeypatch: pytest.MonkeyPatch) -> None:
    real_assert_valid = subject.assert_valid

    def minimal_promotion_schema(value, command, schema_name, **kwargs):
        if schema_name == "research_scale_promotion":
            return None
        return real_assert_valid(value, command, schema_name, **kwargs)

    monkeypatch.setattr(subject, "assert_valid", minimal_promotion_schema)
    monkeypatch.setattr(subject, "validate_release_uat_sample_plan", lambda plan, **_kwargs: dict(plan))


def _fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    include_projection: bool = True,
) -> tuple[Path, dict[str, object]]:
    _patch_plan_validator(monkeypatch)
    root = tmp_path / "output"
    promotion_ref, promotion_digest = _write(
        root,
        "data/promotions/m100.json",
        {
            "schema": "quwoquan_data.research_scale_promotion",
            "promotionId": "promotion-m100",
            "releaseId": "release-m100",
            "manifestDigest": MANIFEST_DIGEST,
            "targetScale": "M100",
        },
    )
    plan_ref, plan_digest = _write(root, "data/releases/release-m100/payload/uat/sample_plan.json", _plan())
    target_binding = build_target_uat_binding(
        runtime_binding={
            "environment": "alpha",
            "target": "alpha-local",
            "releaseId": "release-m100",
            "manifestDigest": MANIFEST_DIGEST,
            "candidateDigest": "sha256:" + "c" * 64,
            "packageDigest": "sha256:" + "d" * 64,
            "runtimeConfigDigest": "sha256:" + "e" * 64,
            "environmentRuntimeDigest": "sha256:" + "f" * 64,
            "startupIdentity": {"configurationDigest": "sha256:" + "1" * 64},
        },
        launch_binding={
            "environment": "alpha",
            "target": "alpha-local",
            "platform": "android",
            "deviceId": "android-emulator-m100",
            "artifactDigest": "sha256:" + "2" * 64,
            "applicationId": "com.leadwise.quwoquan.app",
        },
        sample_plan_binding={
            "releaseId": "release-m100",
            "releaseUatSamplePlanRef": plan_ref,
            "releaseUatSamplePlanDigest": plan_digest,
        },
        active_cas={"ref": "env/alpha/active-cas.json", "digest": "sha256:" + "3" * 64},
        readback={"ref": "env/alpha/readback.json", "digest": "sha256:" + "4" * 64},
        artifact_class="production_behavior",
        build_mode="debug",
        build_profile="nonprod",
        provider={
            "identity": "first-party-https",
            "class": "first_party",
            "type": "https",
            "registered": False,
            "conformanceEvidence": {
                "ref": "env/provider/conformance.json",
                "digest": "sha256:" + "5" * 64,
            },
        },
        device={
            "identity": "android-emulator-m100",
            "class": "emulator",
            "registered": False,
        },
        runner={
            "identity": "m100-alpha-uat",
            "sourcePath": "quwoquan_app/test/user_acceptance/m100_alpha_uat.dart",
            "digest": "sha256:" + "6" * 64,
            "registered": False,
        },
        profile="rehearsal",
        non_promotable=True,
        created_at="2026-08-30T00:00:00Z",
    )
    target_binding_ref, target_binding_digest = _write(
        root, "env/alpha/target-bindings/m100-android.json", target_binding
    )
    readiness_ref, readiness_digest = _write(
        root,
        "env/alpha/runs/data-release/release-m100/release-readiness.json",
        {
            "schema": "quwoquan_data.environment_release_readiness",
            "environment": "alpha",
            "releaseId": "release-m100",
            "manifestDigest": MANIFEST_DIGEST,
            "passed": True,
        },
    )

    raw_pairs: list[tuple[str, str]] = []
    acceptance_rows: list[dict[str, str]] = []
    for sample in _samples():
        ref, digest = _write(
            root,
            f"env/alpha/raw/{sample['sampleId']}.json",
            {
                "schema": "quwoquan.metadata.readiness_case_result",
                "releaseId": "release-m100",
                "sampleId": sample["sampleId"],
                "sampleObjectId": sample["objectId"],
                "carrier": sample["carrier"],
                "entrySurface": "direct_or_object_route",
                "specRef": SPEC_REF,
                "status": "passed",
                "targetUatBindingDigest": target_binding_digest,
                "provider": "first-party-https",
            },
        )
        raw_pairs.append((ref, digest))
        acceptance_rows.append(
            {
                "ref": ref,
                "digest": digest,
                "slotId": "sha256:" + hashlib.sha256(ref.encode()).hexdigest(),
                "status": "passed",
            }
        )
    acceptance_ref, acceptance_digest = _write(
        root,
        "env/alpha/facts/release-m100.json",
        {
            "schema": "quwoquan_ops.environment_acceptance_fact.v1",
            "factId": "sha256:" + "7" * 64,
            "environment": "alpha",
            "target": "alpha-local",
            "releaseId": "release-m100",
            "releaseDigest": MANIFEST_DIGEST,
            "samplePlanRef": plan_ref,
            "samplePlanDigest": plan_digest,
            "targetBindingRefs": [
                {
                    "ref": target_binding_ref,
                    "digest": target_binding_digest,
                    "platform": "android",
                    "deviceProfile": "rehearsal",
                }
            ],
            "requiredRawResults": acceptance_rows,
            "dataReadiness": {"ref": readiness_ref, "digest": readiness_digest},
            "activeCas": {
                "ref": "env/alpha/active-cas.json",
                "digest": "sha256:" + "3" * 64,
                "readbackRef": "env/alpha/readback.json",
                "readbackDigest": "sha256:" + "4" * 64,
                "releaseId": "release-m100",
                "releaseDigest": MANIFEST_DIGEST,
            },
            "lifecycleExit": {"ref": "env/alpha/lifecycle-exit.json", "digest": "sha256:" + "8" * 64},
            "providerReadiness": {"ref": "env/alpha/provider-readiness.json", "digest": "sha256:" + "9" * 64},
            "observabilityReadiness": {"ref": "env/alpha/observability-readiness.json", "digest": "sha256:" + "a" * 64},
            "rollbackReadiness": {"ref": "env/alpha/rollback-readiness.json", "digest": "sha256:" + "b" * 64},
            "predecessorAcceptance": None,
            "resourceFinalization": {
                "leaseRevocationRefs": [{"ref": "env/alpha/lease.json", "digest": "sha256:" + "c" * 64}],
                "lockReleaseRefs": [{"ref": "env/alpha/lock.json", "digest": "sha256:" + "d" * 64}],
                "gcProtectionRefs": [{"ref": "env/alpha/gc.json", "digest": "sha256:" + "e" * 64}],
            },
            "prodReleaseFacts": None,
            "createdAt": "2026-08-30T00:00:00Z",
            "sourceFingerprint": "sha256:" + "f" * 64,
        },
    )
    binding: dict[str, object] = {
        "schema": "quwoquan_data.m100_alpha_acceptance_binding",
        "promotionId": "promotion-m100",
        "promotionReceiptRef": promotion_ref,
        "promotionReceiptDigest": promotion_digest,
        "releaseId": "release-m100",
        "manifestDigest": MANIFEST_DIGEST,
        "releaseUatSamplePlanRef": plan_ref,
        "releaseUatSamplePlanDigest": plan_digest,
        "dataReadinessRef": readiness_ref,
        "dataReadinessExactByteDigest": readiness_digest,
        "alphaEnvironmentAcceptanceRef": acceptance_ref,
        "alphaEnvironmentAcceptanceExactByteDigest": acceptance_digest,
        "requiredRawResultRefs": [ref for ref, _ in raw_pairs],
        "requiredRawResultDigests": [digest for _, digest in raw_pairs],
        "executedSampleCount": 100,
    }
    if include_projection:
        projection_ref, projection_digest = _write(
            root,
            "env/alpha/projections/release-m100.json",
            {
                "schema": "quwoquan_ops.app_uat_result_bundle.v1",
                "releaseId": "release-m100",
                "releaseDigest": MANIFEST_DIGEST,
                "requiredSlots": [
                    {
                        "rawResults": [
                            {"ref": ref, "digest": digest, "rawStatus": "passed"}
                            for ref, digest in raw_pairs
                        ]
                    }
                ],
            },
        )
        binding.update(
            {
                "appUatCompletenessProjectionRef": projection_ref,
                "appUatCompletenessProjectionDigest": projection_digest,
            }
        )
    return root, binding


def _validate(binding: dict[str, object], root: Path) -> dict[str, object]:
    return subject.validate_m100_alpha_acceptance_binding(binding, output_root=root)


def test_m100_alpha_acceptance_binds_exact_plan_raw_and_alpha_acceptance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, binding = _fixture(tmp_path, monkeypatch)

    assert _validate(binding, root) == binding
    assert binding["executedSampleCount"] == 100
    assert len(binding["requiredRawResultRefs"]) == 100
    assert "appUatEnvelopeDigest" not in binding


def test_old_app_uat_envelope_field_is_unknown_and_fails_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, binding = _fixture(tmp_path, monkeypatch)
    invalid = {**binding, "appUatEnvelopeDigest": "sha256:" + "a" * 64}

    with pytest.raises(subject.M100AlphaAcceptanceError, match="未知字段|forbidden"):
        _validate(invalid, root)


def test_raw_failure_and_missing_raw_ref_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, binding = _fixture(tmp_path, monkeypatch, include_projection=False)
    acceptance_path = root / str(binding["alphaEnvironmentAcceptanceRef"])
    acceptance = json.loads(acceptance_path.read_text())
    first_ref = acceptance["requiredRawResults"][0]["ref"]
    raw_path = root / first_ref
    raw = json.loads(raw_path.read_text())
    raw["status"] = "failed"
    raw_path.write_text(json.dumps(raw, sort_keys=True) + "\n", encoding="utf-8")
    new_digest = "sha256:" + hashlib.sha256(raw_path.read_bytes()).hexdigest()
    acceptance["requiredRawResults"][0]["digest"] = new_digest
    acceptance_path.write_text(json.dumps(acceptance, sort_keys=True) + "\n", encoding="utf-8")
    binding["alphaEnvironmentAcceptanceExactByteDigest"] = "sha256:" + hashlib.sha256(acceptance_path.read_bytes()).hexdigest()
    binding["requiredRawResultDigests"][0] = new_digest

    with pytest.raises(subject.M100AlphaAcceptanceError, match="failed"):
        _validate(binding, root)

    root, binding = _fixture(tmp_path / "missing", monkeypatch, include_projection=False)
    acceptance_path = root / str(binding["alphaEnvironmentAcceptanceRef"])
    acceptance = json.loads(acceptance_path.read_text())
    acceptance["requiredRawResults"].pop()
    acceptance_path.write_text(json.dumps(acceptance, sort_keys=True) + "\n", encoding="utf-8")
    binding["alphaEnvironmentAcceptanceExactByteDigest"] = "sha256:" + hashlib.sha256(acceptance_path.read_bytes()).hexdigest()

    with pytest.raises(subject.M100AlphaAcceptanceError, match="MISSING"):
        _validate(binding, root)


def test_acceptance_identity_drift_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, binding = _fixture(tmp_path, monkeypatch, include_projection=False)
    acceptance_path = root / str(binding["alphaEnvironmentAcceptanceRef"])
    acceptance = json.loads(acceptance_path.read_text())
    acceptance["releaseId"] = "release-neighbour"
    acceptance_path.write_text(json.dumps(acceptance, sort_keys=True) + "\n", encoding="utf-8")
    binding["alphaEnvironmentAcceptanceExactByteDigest"] = "sha256:" + hashlib.sha256(acceptance_path.read_bytes()).hexdigest()

    with pytest.raises(subject.M100AlphaAcceptanceError, match="ACCEPTANCE_DRIFT"):
        _validate(binding, root)


def test_projection_cannot_replace_raw_or_environment_acceptance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, binding = _fixture(tmp_path, monkeypatch)
    projection_only = deepcopy(binding)
    projection_only.pop("alphaEnvironmentAcceptanceRef")
    projection_only.pop("alphaEnvironmentAcceptanceExactByteDigest")

    with pytest.raises(subject.M100AlphaAcceptanceError, match="缺 required"):
        _validate(projection_only, root)

    projection_only = deepcopy(binding)
    projection_only.pop("requiredRawResultRefs")
    projection_only.pop("requiredRawResultDigests")
    with pytest.raises(subject.M100AlphaAcceptanceError, match="缺 required"):
        _validate(projection_only, root)


def test_binding_schema_requires_direct_raw_arrays_and_rejects_legacy_fields() -> None:
    with pytest.raises(ValueError, match="未知字段"):
        assert_valid(
            {
                "schema": "quwoquan_data.m100_alpha_acceptance_binding",
                "appUatEnvelopeDigest": "sha256:" + "a" * 64,
            },
            "execution",
            "m100_alpha_acceptance_binding",
        )
