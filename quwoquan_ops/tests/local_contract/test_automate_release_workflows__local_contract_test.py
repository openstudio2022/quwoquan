from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
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


def test_provider_release_evidence_executes_matrix_and_prod_before_oci_publish() -> None:
    assert SPEC_REF
    payload = _workflow(PROVIDER_WORKFLOW)
    text = PROVIDER_WORKFLOW.read_text(encoding="utf-8")
    job = payload["jobs"]["provider_release_evidence"]

    assert set(payload["on"]) == {"workflow_dispatch"}
    assert job["environment"] == "production"
    assert "stackctl.py matrix" in text
    assert "--targets alpha-local,beta-local,gamma-local" in text
    assert "provider_release_evidence.py execute-prod" in text
    assert "provider_release_evidence.py package" in text
    assert text.index("stackctl.py matrix") < text.index(
        "provider_release_evidence.py execute-prod"
    )
    assert text.index("provider_release_evidence.py execute-prod") < text.index(
        "Publish executed Provider evidence OCI"
    )
    assert "QWQ_PROVIDER_CONFORMANCE_ATTESTATION_KEY" in text
    assert "source-only conformance metadata" in text


def test_provider_oci_is_bound_to_exact_component_and_candidate_image_set() -> None:
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
    assert "load_validate_and_derive" in helper
    assert 'readiness_issues(report, environment="prod")' in helper
    assert "evidence_files(evidence_root)" in helper


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
