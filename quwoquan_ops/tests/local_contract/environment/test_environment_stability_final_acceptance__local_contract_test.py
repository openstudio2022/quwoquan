# spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/zero-risk-production-readiness/spec.md
from __future__ import annotations

from quwoquan_ops.tests.support.environment_stability_final_acceptance_test_support import (
    Any,
    FinalAcceptanceFixture,
    Path,
    RELEASE_DIGEST,
    RELEASE_ID,
    TEST_DIGEST,
    VerifiedAuthority,
    _canonical_digest,
    _codes,
    _evaluate,
    _reject_attestation,
    _trusted_attestation,
    _write,
    cli,
    json,
    patch,
    pytest,
    sha256_file,
    sys,
    tempfile,
)

from quwoquan_ops.ci.release_evidence_reader import (
    validate_historical_release_snapshot,
)


def test_cli_empty_inputs_exit_one_with_typed_receipt() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        output = Path(temporary) / "final.json"
        with patch.object(
            sys,
            "argv",
            ["verify_environment_stability_final_acceptance.py", "--output", str(output)],
        ):
            assert cli.main() == 1
        payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["verdict"] == "GATE_BLOCK"
    assert "MISSING_INPUT" in _codes(payload)


def test_frozen_final_acceptance_is_diagnostic_only_after_qualification_cutover() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        validate_historical_release_snapshot(
            fixture.manifest,
            artifact_dir=fixture.artifact,
            allowed_statuses={"released"},
        )
        payload = _evaluate(fixture, trusted=True)

    assert payload["verdict"] == "GATE_BLOCK"
    assert payload["artifactClosure"]["candidateId"] == fixture.manifest["candidateId"]
    assert payload["inputs"]["recoveryUat"] == {"ios": None, "android": None}
    assert payload["inputs"]["nightlyArtifact"] is None
    assert payload["inputs"]["prodSim"]["role"] == "diagnostic_only"
    assert payload["inputs"]["prodSim"]["authority"]["kind"] == (
        "github-actions-oidc"
    )
    assert {
        "code": "NON_PROMOTABLE",
        "input": "final_acceptance",
        "message": (
            "frozen diagnostic final acceptance cannot qualify a release; use "
            "QualificationFact and qualified_prod admission"
        ),
    } in payload["blockers"]
    assert not any(
        blocker["input"] in {"recovery.ios", "recovery.android", "nightly"}
        for blocker in payload["blockers"]
    )


def test_immutable_release_attestations_still_do_not_expire_in_diagnostics() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(
            Path(temporary),
            pilot_recorded_at="2025-01-01T00:00:00Z",
        )
        validate_historical_release_snapshot(
            fixture.manifest,
            artifact_dir=fixture.artifact,
            allowed_statuses={"released"},
        )
        payload = _evaluate(fixture, trusted=True)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "NON_PROMOTABLE" in _codes(payload)
    assert "STALE_EVIDENCE" not in _codes(payload)


def test_immutable_release_attestations_cannot_be_future_dated() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(
            Path(temporary),
            pilot_recorded_at="2026-08-05T00:00:00Z",
        )
        payload = _evaluate(fixture, trusted=True)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "STALE_EVIDENCE" in _codes(payload)


def test_completely_local_synthetic_fixture_is_gate_block() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        payload = _evaluate(fixture, trusted=False)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "UNVERIFIABLE_AUTHORITY" in _codes(payload)


def test_three_cell_provider_bundle_is_gate_block() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary), provider_mode="three")
        payload = _evaluate(fixture)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "ARTIFACT_CLOSURE_INVALID" in _codes(payload)


def test_provider_bundle_missing_one_alpha_cell_is_gate_block() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(
            Path(temporary),
            provider_mode="missing_alpha",
        )
        payload = _evaluate(fixture)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "ARTIFACT_CLOSURE_INVALID" in _codes(payload)


def test_provider_bundle_missing_one_prod_cell_is_gate_block() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(
            Path(temporary),
            provider_mode="missing_prod",
        )
        payload = _evaluate(fixture)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "ARTIFACT_CLOSURE_INVALID" in _codes(payload)


def test_provider_bundle_duplicate_cell_is_gate_block() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(
            Path(temporary),
            provider_mode="duplicate",
        )
        payload = _evaluate(fixture)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "ARTIFACT_CLOSURE_INVALID" in _codes(payload)


def test_forged_source_authority_does_not_establish_trust() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        fixture.rewrite(
            "nightly",
            lambda value: value.__setitem__(
                "sourceAuthority",
                "github-actions-oidc",
            ),
        )
        payload = _evaluate(
            fixture,
            trusted=False,
            attestation_verifier=_reject_attestation,
            nightly_artifact=fixture.paths["nightly"],
        )

    assert payload["verdict"] == "GATE_BLOCK"
    assert "UNVERIFIABLE_AUTHORITY" in _codes(payload)


def test_forged_hosted_refs_are_rejected() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        fixture.rewrite(
            "prod_rollback_readback",
            lambda value: value.__setitem__(
                "receiptRef",
                "receipt:hosted:" + "0" * 64,
            ),
        )
        payload = _evaluate(fixture)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "HOSTED_READBACK_INVALID" in _codes(payload)


def test_manifest_unsealed_receipt_bytes_are_rejected() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        rollout_path = Path(fixture.manifest["rolloutReceipt"]["path"])
        _write(
            fixture.artifact / rollout_path,
            {"schema": "release-rollout-receipt", "status": "passed"},
        )
        payload = _evaluate(fixture)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "ARTIFACT_CLOSURE_INVALID" in _codes(payload)


@pytest.mark.parametrize("environment", ("alpha", "beta", "gamma"))
def test_local_copy_of_lifecycle_receipt_is_not_authoritative(
    environment: str,
) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        forged = _write(
            Path(temporary) / f"forged-{environment}-lifecycle.json",
            fixture.payloads[f"content_{environment}"],
        )
        payload = _evaluate(
            fixture,
            **{f"content_lifecycle_{environment}": forged},
        )

    assert payload["verdict"] == "GATE_BLOCK"
    assert "UNVERIFIABLE_AUTHORITY" in _codes(payload)


def test_local_copy_of_green_matrix_is_not_authoritative() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        forged = _write(
            Path(temporary) / "forged-green-matrix.json",
            fixture.payloads["green_matrix"],
        )
        payload = _evaluate(fixture, local_env_green_matrix=forged)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "UNVERIFIABLE_AUTHORITY" in _codes(payload)


def test_emulator_only_green_matrix_cannot_close_final_acceptance() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        emulator_only = {
            **fixture.payloads["green_matrix"],
            "claim": "ALPHA_BETA_GAMMA_EMULATOR_ONLY_FUNCTIONAL_GREEN",
            "deviceProfile": "emulator_only",
            "nonPromotable": True,
            "deviceCoverage": ["ios-simulator", "android-emulator"],
        }
        _write(fixture.paths["green_matrix"], emulator_only)
        payload = _evaluate(fixture)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "NON_PROMOTABLE" in _codes(payload)
    assert "STATUS_NOT_PASSED" in _codes(payload)


def test_identical_candidate_and_rollback_identity_is_gate_block() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))

        def duplicate_candidate_identity(value: dict[str, Any]) -> None:
            value["releaseId"] = RELEASE_ID
            value["payloadSha256"] = RELEASE_DIGEST

        fixture.rewrite("pilot_rollback", duplicate_candidate_identity)
        payload = _evaluate(fixture)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "IDENTITY_MISMATCH" in _codes(payload)
    assert "DIGEST_MISMATCH" in _codes(payload)


@pytest.mark.parametrize(
    ("label", "argument"),
    (
        ("pilot_release", "pilot_release_attestation"),
        ("pilot_rollback", "pilot_rollback_attestation"),
    ),
)
def test_local_copy_of_pilot_attestation_is_not_authoritative(
    label: str,
    argument: str,
) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        forged = _write(
            Path(temporary) / "forged-pilot.json",
            fixture.payloads[label],
        )
        payload = _evaluate(fixture, **{argument: forged})

    assert payload["verdict"] == "GATE_BLOCK"
    assert "UNVERIFIABLE_AUTHORITY" in _codes(payload)


def test_forged_prod_sim_without_oidc_attestation_is_gate_block() -> None:
    def verifier(
        path: Path,
        kind: str,
        manifest: dict[str, Any],
    ) -> VerifiedAuthority:
        if kind == "prod_sim":
            raise RuntimeError("prod-sim signature missing")
        return _trusted_attestation(path, kind, manifest)

    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        payload = _evaluate(
            fixture,
            attestation_verifier=verifier,
        )

    assert payload["verdict"] == "GATE_BLOCK"
    assert any(
        blocker["code"] == "UNVERIFIABLE_AUTHORITY"
        and blocker["input"] == "prod_sim"
        for blocker in payload["blockers"]
    )


def test_attestation_missing_workflow_repo_issuer_claims_is_gate_block() -> None:
    def incomplete(
        path: Path,
        kind: str,
        manifest: dict[str, Any],
    ) -> VerifiedAuthority:
        del manifest
        return VerifiedAuthority(
            authority="github-actions-oidc",
            subject_digest=sha256_file(path),
            verification_digest=TEST_DIGEST,
            claims=frozenset({"receipt_bytes", kind}),
        )

    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        payload = _evaluate(
            fixture,
            attestation_verifier=incomplete,
        )

    assert payload["verdict"] == "GATE_BLOCK"
    assert "UNVERIFIABLE_AUTHORITY" in _codes(payload)


def test_attestation_verifier_failure_is_gate_block() -> None:
    def reject(
        path: Path,
        kind: str,
        manifest: dict[str, Any],
    ) -> VerifiedAuthority:
        del path, kind, manifest
        raise RuntimeError("signature verification failed")

    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        payload = _evaluate(
            fixture,
            trusted=True,
            attestation_verifier=reject,
        )

    assert payload["verdict"] == "GATE_BLOCK"
    assert "UNVERIFIABLE_AUTHORITY" in _codes(payload)


def test_missing_canonical_soak_cannot_restore_snapshot_promotability() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        payload = _evaluate(
            fixture,
            trusted=False,
            attestation_verifier=_trusted_attestation,
        )

    assert payload["verdict"] == "GATE_BLOCK"
    assert any(
        blocker["code"] == "NON_PROMOTABLE"
        and blocker["input"] == "final_acceptance"
        for blocker in payload["blockers"]
    )


def test_missing_alpha_is_typed_gate_block() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        payload = _evaluate(fixture, content_lifecycle_alpha=None)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "MISSING_INPUT" in _codes(payload)


def test_retired_recovery_input_is_unsupported_and_non_promotable() -> None:
    calls: list[str] = []

    def verifier(
        path: Path,
        kind: str,
        manifest: dict[str, Any],
    ) -> VerifiedAuthority:
        calls.append(kind)
        return _trusted_attestation(path, kind, manifest)

    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        payload = _evaluate(
            fixture,
            attestation_verifier=verifier,
            ios_recovery_uat=fixture.paths["recovery_ios"],
        )

    assert payload["verdict"] == "GATE_BLOCK"
    assert calls == ["prod_sim"]
    recovery = payload["inputs"]["recoveryUat"]["ios"]
    assert recovery["role"] == "diagnostic_only"
    assert recovery["authority"] is None
    assert {
        blocker["code"]
        for blocker in payload["blockers"]
        if blocker["input"] == "recovery.ios"
    } == {"UNSUPPORTED_INPUT", "NON_PROMOTABLE"}


def test_retired_android_recovery_cannot_rejoin_through_digest_binding() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        fixture.rewrite(
            "recovery_android",
            lambda value: value.__setitem__(
                "artifactDigest",
                "sha256:" + "f" * 64,
            ),
        )
        payload = _evaluate(
            fixture,
            android_recovery_uat=fixture.paths["recovery_android"],
        )

    assert payload["verdict"] == "GATE_BLOCK"
    assert {
        blocker["code"]
        for blocker in payload["blockers"]
        if blocker["input"] == "recovery.android"
    } == {"UNSUPPORTED_INPUT", "NON_PROMOTABLE"}
    assert not any(
        blocker["code"] == "DIGEST_MISMATCH"
        and blocker["input"] == "recovery.android"
        for blocker in payload["blockers"]
    )


def test_prod_sim_release_binding_must_match_pilot() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        fixture.rewrite(
            "prod_sim",
            lambda value: value.__setitem__(
                "releaseDigest",
                "sha256:" + "f" * 64,
            ),
        )
        payload = _evaluate(fixture)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "DIGEST_MISMATCH" in _codes(payload)


def test_prod_sim_must_remain_explicitly_non_promotable() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))

        def make_promotable(value: dict[str, Any]) -> None:
            value["releaseEligibility"]["status"] = "PASSED"
            value["releaseEligibility"]["promotable"] = True

        fixture.rewrite("prod_sim", make_promotable)
        payload = _evaluate(fixture)

    assert payload["verdict"] == "GATE_BLOCK"
    assert any(
        blocker["code"] == "STATUS_NOT_PASSED"
        and blocker["input"] == "prod_sim"
        for blocker in payload["blockers"]
    )


def test_mixed_release_digest_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))

        def mix(value: dict[str, Any]) -> None:
            value["originalManifestDigest"] = "sha256:" + "f" * 64
            value.pop("verificationChecksum")
            value["verificationChecksum"] = _canonical_digest(value)

        fixture.rewrite("content_gamma", mix)
        payload = _evaluate(fixture)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "DIGEST_MISMATCH" in _codes(payload)


def test_local_hmac_evidence_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        fixture.rewrite(
            "nightly",
            lambda value: value.__setitem__(
                "artifactAttestation",
                "hmac-sha256:" + "0" * 64,
            ),
        )
        payload = _evaluate(
            fixture,
            nightly_artifact=fixture.paths["nightly"],
        )

    assert payload["verdict"] == "GATE_BLOCK"
    assert "LOCAL_ATTESTATION" in _codes(payload)
    assert {
        blocker["code"]
        for blocker in payload["blockers"]
        if blocker["input"] == "nightly"
    } == {"LOCAL_ATTESTATION", "UNSUPPORTED_INPUT", "NON_PROMOTABLE"}


def test_workflow_text_cannot_supply_typed_evidence() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        workflow = Path(temporary) / "WORKFLOW.md"
        workflow.write_text("# PROMOTABLE\n", encoding="utf-8")
        payload = _evaluate(fixture, nightly_artifact=workflow)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "UNSUPPORTED_INPUT" in _codes(payload)


def test_missing_prod_readback_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        fixture = FinalAcceptanceFixture(Path(temporary))
        payload = _evaluate(fixture, prod_rollout_readback=None)

    assert payload["verdict"] == "GATE_BLOCK"
    assert "MISSING_INPUT" in _codes(payload)
