from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

DATA_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(DATA_SCRIPTS))

from content.release.environment import activation_predecessor as subject  # noqa: E402
from content.release.environment.activation_envelope import (  # noqa: E402
    EnvironmentActivationEnvelopeError,
    build_environment_activation_envelope,
    document_digest,
)

DIGEST = "sha256:" + "1" * 64
IDENTITY_SET_DIGEST = "sha256:" + "2" * 64


def _checksum(value: dict[str, object]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _previous_receipt(output: Path, environment: str) -> Path:
    activation = {
        "schema": "quwoquan_data.environment_activation_envelope",
        "environment": environment,
        "releaseId": "release-m100",
        "manifestDigest": DIGEST,
        "sourceIdentitySetDigest": IDENTITY_SET_DIGEST,
    }
    receipt: dict[str, object] = {
        "schema": "quwoquan_data.environment_release_readiness",
        "environment": environment,
        "releaseId": "release-m100",
        "manifestDigest": DIGEST,
        "sourceIdentitySetDigest": IDENTITY_SET_DIGEST,
        "releaseClass": "research",
        "productLifecycleState": "research",
        "readinessPhase": "research",
        "verifyRunId": f"verify-{environment}",
        "activationEnvelope": activation,
        "activationEnvelopeDigest": document_digest(activation),
        "appUatEnvelopeDigest": "sha256:" + "3" * 64,
        "passed": True,
    }
    receipt["verificationChecksum"] = _checksum(receipt)
    path = (
        output
        / f"env/{environment}/runs/data-release/release-m100/verify-{environment}"
        / "release-readiness.json"
    )
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
    return path


def test_beta_freezes_exact_alpha_readiness_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    alpha = _previous_receipt(output, "alpha")
    monkeypatch.setattr(subject, "assert_valid", lambda *args, **kwargs: None)

    binding = subject.load_previous_environment_activation(
        environment="beta",
        readiness_path=alpha,
        release_id="release-m100",
        manifest_digest=DIGEST,
        source_identity_set_digest=IDENTITY_SET_DIGEST,
        output_root=output,
    )

    assert binding is not None
    assert binding["environment"] == "alpha"
    assert binding["readinessRef"].endswith("/release-readiness.json")
    assert binding["readinessDigest"].startswith("sha256:")


def test_environment_sequence_and_identity_drift_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "output"
    alpha = _previous_receipt(output, "alpha")
    monkeypatch.setattr(subject, "assert_valid", lambda *args, **kwargs: None)

    with pytest.raises(
        EnvironmentActivationEnvelopeError,
        match="prod milestone activation requires gamma readiness",
    ):
        subject.load_previous_environment_activation(
            environment="prod",
            readiness_path=None,
            release_id="release-m100",
            manifest_digest=DIGEST,
            source_identity_set_digest=IDENTITY_SET_DIGEST,
            output_root=output,
        )
    with pytest.raises(
        EnvironmentActivationEnvelopeError,
        match="path is not canonical",
    ):
        subject.load_previous_environment_activation(
            environment="gamma",
            readiness_path=alpha,
            release_id="release-m100",
            manifest_digest=DIGEST,
            source_identity_set_digest=IDENTITY_SET_DIGEST,
            output_root=output,
        )
    with pytest.raises(
        EnvironmentActivationEnvelopeError,
        match="identity drift",
    ):
        subject.load_previous_environment_activation(
            environment="beta",
            readiness_path=alpha,
            release_id="release-m100",
            manifest_digest="sha256:" + "9" * 64,
            source_identity_set_digest=IDENTITY_SET_DIGEST,
            output_root=output,
        )


def test_milestone_envelope_keeps_prod_research_and_requires_gamma() -> None:
    identity = {
        "sourceRevision": "sha256:" + "4" * 64,
        "sourceDigest": "sha256:" + "5" * 64,
        "entityCatalogDigest": "sha256:" + "6" * 64,
        "executionIds": ["execution-a"],
    }
    predecessor = {
        "environment": "gamma",
        "readinessRef": (
            "env/gamma/runs/data-release/release-m100/verify-gamma/"
            "release-readiness.json"
        ),
        "readinessDigest": "sha256:" + "7" * 64,
        "verifyRunId": "verify-gamma",
        "activationEnvelopeDigest": "sha256:" + "8" * 64,
        "appUatEnvelopeDigest": "sha256:" + "9" * 64,
    }
    envelope = build_environment_activation_envelope(
        environment="prod",
        release_id="release-m100",
        manifest_digest=DIGEST,
        source_revision=None,
        source_digest=None,
        entity_catalog_digest=None,
        release_class="research",
        product_lifecycle_state="research",
        readiness_phase="research",
        import_run_id="import-prod",
        verify_run_id="verify-prod",
        import_report_ref=(
            "env/prod/runs/data-release/release-m100/import-prod/import.json"
        ),
        import_report_digest="sha256:" + "a" * 64,
        app_uat_envelope={"executedSamples": 100},
        research_isolation={
            "policyRef": "quwoquan_ops/environments/prod/runtime.yaml",
            "policySha256": "sha256:" + "b" * 64,
            "subjectHash": "sha256:" + "c" * 64,
        },
        research_isolation_verification_ref=(
            "env/prod/runs/data-release/release-m100/verify-prod/"
            "research-isolation-verification.json"
        ),
        research_isolation_verification_digest="sha256:" + "d" * 64,
        source_identities=[identity],
        source_identity_set_digest=IDENTITY_SET_DIGEST,
        milestone="M100",
        previous_environment_activation=predecessor,
    )

    assert envelope["releaseClass"] == "research"
    assert envelope["productLifecycleState"] == "research"
    assert envelope["previousEnvironmentActivation"] == predecessor
