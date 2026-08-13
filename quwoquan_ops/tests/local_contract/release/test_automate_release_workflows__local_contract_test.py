from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
PROVIDER_WORKFLOW = ROOT / ".github/workflows/provider-release-evidence.yml"
PROD_SIM_WORKFLOW = ROOT / ".github/workflows/prod-sim-manual-admission.yml"
DELIVERY_WORKFLOW = ROOT / ".github/workflows/delivery-gate.yml"
PROD_WORKFLOW = ROOT / ".github/workflows/deploy-prod-auto.yml"
DEVICE_WORKFLOW = ROOT / ".github/workflows/app-env-device-matrix-self-hosted.yml"
PROVIDER_HELPER = ROOT / "quwoquan_ops/ci/provider_release_evidence.py"
SPEC_REF = (
    "specs/feature-tree/runtime/deliver-deploy-prod-pipeline/spec.md#req-001"
)


def _workflow(path: Path) -> dict[str, object]:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_provider_release_evidence_derives_one_release_and_executes_all_cells() -> None:
    assert SPEC_REF
    payload = _workflow(PROVIDER_WORKFLOW)
    text = PROVIDER_WORKFLOW.read_text(encoding="utf-8")
    job = payload["jobs"]["provider_release_evidence"]

    assert set(payload["on"]) == {"workflow_dispatch"}
    assert set(payload["on"]["workflow_dispatch"]["inputs"]) == {
        "release_evidence_ref"
    }
    assert job["environment"] == "production"
    assert "vars.RELEASED_RELEASE_EVIDENCE_REF" in text
    assert "consume_released_release_evidence.py" in text
    assert "--require-status released" in text
    assert "stackctl.py matrix" not in text
    assert "provider_release_evidence.py execute-nonprod" in text
    assert "provider_release_evidence.py execute-prod" in text
    assert "provider_release_evidence.py package" in text
    assert text.index("provider_release_evidence.py execute-nonprod") < text.index(
        "provider_release_evidence.py execute-prod"
    )
    assert text.index("provider_release_evidence.py execute-prod") < text.index(
        "Publish executed Provider evidence OCI"
    )
    assert "QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY" in text
    assert "source-only conformance metadata" in text
    assert "evidence_count: ${{ steps.package.outputs.evidence_count }}" in text
    assert "NIGHTLY_" not in text
    assert "PROVIDER_ALPHA_" not in text


def test_provider_oci_is_bound_to_released_candidate_and_manifest_closure() -> None:
    assert SPEC_REF
    delivery = DELIVERY_WORKFLOW.read_text(encoding="utf-8")
    prod = PROD_WORKFLOW.read_text(encoding="utf-8")
    helper = PROVIDER_HELPER.read_text(encoding="utf-8")

    assert "--require-file provider-candidate.json" in delivery
    assert "provider-release-evidence-binding" in delivery
    assert "QWQ_PROVIDER_CONFORMANCE_EXPECTED_IMAGE_DIGEST" in delivery
    assert "provider_component_evidence_ref" in delivery
    assert "needs.service_pipeline.outputs.component_evidence_ref" in prod
    assert "PROD_PROVIDER_CANDIDATE_IMAGE_DIGEST" in prod
    assert "inputs.provider_evidence_ref || vars.PROD_PROVIDER_EVIDENCE_REF" in prod
    assert "provider-conformance-prod-candidate-image-set" in helper
    assert "allowed_statuses={\"released\"}" in helper
    assert '"releaseEvidenceRef": args.release_evidence_ref' in helper
    assert '"candidateId": manifest["candidateId"]' in helper
    assert '"artifactDigest": manifest["artifactDigest"]' in helper
    assert "RELEASE_CLOSURE_PATHS" in helper
    assert "sha256_file(source_path)" in helper
    assert "load_validate_and_derive" in helper
    assert "provider_conformance.readiness_issues(" in helper
    assert "provider_conformance.EVIDENCE_ENVIRONMENTS" in helper
    assert "load_evidence(evidence_root)" in helper
    assert '"evidenceCount": len(evidence_paths)' in helper
    assert "render_provider_conformance_source.py" in delivery
    assert "--archive-dir" in delivery
    assert "render_provider_release_evidence.py" in prod
    assert "--local-env-green-matrix" in delivery
    assert "--require-file evidence/release/alpha-beta-gamma-green-matrix.json" in delivery
    assert "--release-root" in PROVIDER_WORKFLOW.read_text(encoding="utf-8")
    assert "content-lifecycle=$QWQ_PROD_RELEASE_ARTIFACT_ROOT" in prod
    assert "content-lifecycle=$QWQ_PROD_RELEASE_ARTIFACT_ROOT" in (
        DEVICE_WORKFLOW.read_text(encoding="utf-8")
    )


def test_schedule_and_provider_share_one_candidate_pointer() -> None:
    device = _workflow(DEVICE_WORKFLOW)
    provider = _workflow(PROVIDER_WORKFLOW)
    device_text = DEVICE_WORKFLOW.read_text(encoding="utf-8")
    provider_text = PROVIDER_WORKFLOW.read_text(encoding="utf-8")
    redundant_identity_inputs = {
        "candidate_digest",
        "artifact_digest",
        "producer_workflow_run_id",
        "source_git_sha",
        "release_attestation",
        "rollback_release_attestation",
        "component_evidence_ref",
    }
    dispatch_inputs = set(device["on"]["workflow_dispatch"]["inputs"])
    called_inputs = set(device["on"]["workflow_call"]["inputs"])
    provider_inputs = set(provider["on"]["workflow_dispatch"]["inputs"])
    assert dispatch_inputs.isdisjoint(redundant_identity_inputs)
    assert called_inputs.isdisjoint(redundant_identity_inputs)
    assert provider_inputs == {"release_evidence_ref"}
    assert device_text.count("vars.RELEASED_RELEASE_EVIDENCE_REF") == 1
    assert provider_text.count("vars.RELEASED_RELEASE_EVIDENCE_REF") == 1
    assert "REQUIRED_STATUS=released" in device_text
    assert "--require-status released" in provider_text


def test_prod_sim_is_manual_approved_and_explicitly_non_promotable() -> None:
    assert SPEC_REF
    payload = _workflow(PROD_SIM_WORKFLOW)
    text = PROD_SIM_WORKFLOW.read_text(encoding="utf-8")
    job = payload["jobs"]["prod_sim_admission"]

    assert set(payload["on"]) == {"workflow_dispatch"}
    assert job["environment"] == "prod-sim-admission"
    assert "--target prod-hosted" in text
    assert "--mode prevalidate" in text
    assert "--data-mode isolated" in text
    assert "--prevalidate-scope first-party" in text
    assert "PROD_SSH_HOST" not in text
    assert "--ssh-host" not in text
    assert '(report.get("releaseEligibility") or {}).get("status") != "GATE_BLOCK"' in text
    assert "environment-evidence" not in text
    assert "delivery-gate.yml" not in text
    assert "retention-days: 1" in text


def test_nightly_soak_has_start_and_end_diagnostics_before_owned_teardown() -> None:
    assert SPEC_REF
    text = DEVICE_WORKFLOW.read_text(encoding="utf-8")

    assert "Inspect and doctor the managed Gamma runtime before soak" in text
    assert "Inspect and doctor the managed Gamma runtime after soak" in text
    assert text.count("stackctl.py inspect") >= 2
    assert text.count("stackctl.py doctor") >= 2
    assert "if: ${{ always() && needs.beta_stack.outputs.managed_runtime_started == 'true' }}" in text
    assert 'exit "$STATUS"' in text
