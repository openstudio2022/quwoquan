from __future__ import annotations

import ast
import json
from pathlib import Path

import yaml

from quwoquan_ops.ci import render_environment_stability_attested_receipt as receipt

ROOT = Path(__file__).resolve().parents[4]
# 常量已随包化拆分迁入 model.py；AST 扫描指向该子模块。
FINAL_ACCEPTANCE_PATH = (
    ROOT / "quwoquan_ops/cli/lib/environment_stability_final_acceptance/model.py"
)
DEVICE_WORKFLOW = ".github/workflows/app-env-device-matrix-self-hosted.yml"
DEVICE_WORKFLOW_PATH = ROOT / DEVICE_WORKFLOW
PLATFORM_WORKFLOW_PATH = ROOT / ".github/workflows/beta-device-platform.yml"
PROD_SIM_WORKFLOW_PATH = ROOT / ".github/workflows/prod-sim-manual-admission.yml"
MATRIX_RUNNER_PATH = ROOT / "quwoquan_ops/ci/run_mobile_platform_matrix.sh"
VALIDATION_SUITES_PATH = (
    ROOT / "quwoquan_ops/environments/gamma/validation_suites.json"
)
ATTEST_ACTION = "actions/attest@f7c2b2a3f1986639bb3d0d22cb88d0e5e1d2c749"
MINIMUM_ATTESTATION_PERMISSIONS = {
    "contents": "read",
    "id-token": "write",
    "attestations": "write",
}


def _workflow(path: Path) -> dict[str, object]:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _step_index(job: dict[str, object], name: str) -> int:
    return next(
        index
        for index, step in enumerate(job["steps"])
        if step.get("name") == name
    )


def _attested_workflow_map() -> dict[str, str]:
    module = ast.parse(FINAL_ACCEPTANCE_PATH.read_text(encoding="utf-8"))
    assignments = {
        target.id: node.value
        for node in module.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    value = assignments["GITHUB_ATTESTED_WORKFLOW_BY_KIND"]
    assert isinstance(value, ast.Dict)
    result: dict[str, str] = {}
    for raw_key, raw_value in zip(value.keys, value.values, strict=True):
        key = ast.literal_eval(raw_key)
        result[key] = (
            DEVICE_WORKFLOW
            if isinstance(raw_value, ast.Name) and raw_value.id == "DEVICE_WORKFLOW"
            else ast.literal_eval(raw_value)
        )
    return result


def test_exact_byte_signers_have_minimum_permissions_and_subject_paths() -> None:
    device = _workflow(DEVICE_WORKFLOW_PATH)
    prod_sim = _workflow(PROD_SIM_WORKFLOW_PATH)
    expected = {
        "attest_android_recovery_receipt": (
            device["jobs"],
            "${{ env.RECEIPT_PATH }}",
        ),
        "attest_ios_recovery_receipt": (
            device["jobs"],
            "${{ env.RECEIPT_PATH }}",
        ),
        "attest_nightly_receipt": (
            device["jobs"],
            "${{ env.RECEIPT_PATH }}",
        ),
        "attest_prod_sim_report": (
            prod_sim["jobs"],
            "${{ env.RECEIPT_PATH }}",
        ),
    }
    for job_name, (jobs, expected_path) in expected.items():
        job = jobs[job_name]
        assert job["permissions"] == MINIMUM_ATTESTATION_PERMISSIONS
        actions = [step for step in job["steps"] if step.get("uses") == ATTEST_ACTION]
        assert len(actions) == 1
        assert actions[0]["with"] == {"subject-path": expected_path}


def test_receipts_are_validated_after_execution_and_before_attestation() -> None:
    device = _workflow(DEVICE_WORKFLOW_PATH)
    platform = _workflow(PLATFORM_WORKFLOW_PATH)
    prod_sim = _workflow(PROD_SIM_WORKFLOW_PATH)

    platform_job = platform["jobs"]["device"]
    assert _step_index(
        platform_job,
        "Verify platform evidence in the producing job",
    ) < _step_index(
        platform_job,
        "Render and verify canonical recovery receipt",
    )
    platform_render = next(
        step
        for step in platform_job["steps"]
        if step.get("name") == "Render and verify canonical recovery receipt"
    )["run"]
    assert platform_render.index("render-recovery") < platform_render.index("verify-case")
    for job_name, names in {
        "attest_android_recovery_receipt": (
            "Materialize exact Android recovery receipt bytes",
            "Verify canonical Android recovery receipt bindings",
            "Attest exact Android recovery receipt bytes",
        ),
        "attest_ios_recovery_receipt": (
            "Materialize exact iOS recovery receipt bytes",
            "Verify canonical iOS recovery receipt bindings",
            "Attest exact iOS recovery receipt bytes",
        ),
        "attest_nightly_receipt": (
            "Render canonical nightly receipt after dual-platform attestations",
            "Verify canonical nightly candidate, commit, release and artifact bindings",
            "Attest exact nightly receipt bytes",
        ),
    }.items():
        job = device["jobs"][job_name]
        assert [_step_index(job, name) for name in names] == sorted(
            _step_index(job, name) for name in names
        )
    producer = prod_sim["jobs"]["prod_sim_admission"]
    assert producer["runs-on"] == ["self-hosted", "macOS", "ARM64", "quwoquan-release-authority"]
    assert producer["environment"] == "prod-sim-admission"
    assert _step_index(
        producer,
        "Prove the rehearsal cannot become release evidence",
    ) < _step_index(
        producer,
        "Bind and verify canonical prod-sim report",
    )
    signer = prod_sim["jobs"]["attest_prod_sim_report"]
    assert signer["if"] == "${{ needs.prod_sim_admission.result == 'success' }}"
    assert "prod_sim_receipt_base64 != ''" not in PROD_SIM_WORKFLOW_PATH.read_text(
        encoding="utf-8"
    )
    materialize = next(
        step
        for step in signer["steps"]
        if step.get("name") == "Materialize exact prod-sim report bytes"
    )["run"]
    assert "passed prod-sim admission did not emit a receipt" in materialize
    assert _step_index(
        signer,
        "Verify passed non-promotable prod-sim report bindings",
    ) < _step_index(
        signer,
        "Attest exact prod-sim report bytes",
    )


def test_workflow_paths_are_kind_specific_and_match_actual_signers() -> None:
    assert _attested_workflow_map() == {
        "recovery.ios": DEVICE_WORKFLOW,
        "recovery.android": DEVICE_WORKFLOW,
        "nightly": DEVICE_WORKFLOW,
        "prod_sim": ".github/workflows/prod-sim-manual-admission.yml",
    }
    assert "attest_nightly_receipt:" in DEVICE_WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "attest_prod_sim_report:" in PROD_SIM_WORKFLOW_PATH.read_text(
        encoding="utf-8"
    )


def test_nightly_runs_recovery_from_one_released_evidence_pointer() -> None:
    suites = json.loads(VALIDATION_SUITES_PATH.read_text(encoding="utf-8"))
    for profile in ("nightly_full", "release_candidate"):
        assert "runtime-recovery" in (
            suites["profiles"][profile]["deviceMatrix"]["matrixKinds"]
        )
    journey = suites["uiJourneys"]["runtime_recovery_journey_patrol"]
    assert journey["runner"] == "patrol"
    assert journey["target"].endswith(
        "runtime_recovery_journey__user_acceptance_test.dart"
    )
    runner = MATRIX_RUNNER_PATH.read_text(encoding="utf-8")
    assert '--persisted-device-session \\' in runner
    assert "runtime-recovery-${MOBILE_PLATFORM}.json" in runner
    workflow = DEVICE_WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "vars.RELEASED_RELEASE_EVIDENCE_REF" in workflow
    assert "consume_released_release_evidence.py" in workflow
    assert "REQUIRED_STATUS=released" in workflow
    assert "--require-status \"${{ steps.inputs.outputs.required_status }}\"" in workflow
    assert "steps.release.outputs.pilot_release_path" in workflow
    assert "steps.release.outputs.pilot_rollback_path" in workflow
    assert "NIGHTLY_" not in workflow
    assert workflow.index(
        "Verify nightly runtime release matches candidate"
    ) < workflow.index("Start stackctl-managed Gamma full runtime")
    assert "verify-release-binding" in workflow


def test_workflows_have_no_local_or_secret_attestation_fallback() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            DEVICE_WORKFLOW_PATH,
            PLATFORM_WORKFLOW_PATH,
            PROD_SIM_WORKFLOW_PATH,
        )
    ).lower()
    for forbidden in (
        "hmac-sha256:",
        "local-sha256:",
        "attestation_key",
        "attestation_secret",
    ):
        assert forbidden not in combined


def test_prod_sim_consumes_clean_main_admitted_release_closure() -> None:
    workflow = _workflow(PROD_SIM_WORKFLOW_PATH)
    producer = workflow["jobs"]["prod_sim_admission"]
    checkout = next(
        step
        for step in producer["steps"]
        if str(step.get("uses") or "").startswith("actions/checkout@")
    )
    assert checkout["with"]["ref"] == "${{ inputs.source_sha }}"
    assert checkout["with"]["persist-credentials"] == "false"

    source_gate = next(
        step
        for step in producer["steps"]
        if step.get("name") == "Require exact reviewed main source"
    )["run"]
    assert "git merge-base --is-ancestor" in source_gate
    assert "git status --porcelain --untracked-files=all" in source_gate

    candidate = next(
        step
        for step in producer["steps"]
        if step.get("name") == "Verify main-admitted manifest, OIDC and artifact closure"
    )["run"]
    assert "consume_released_release_evidence.py" in candidate
    assert "--require-status main-admitted" in candidate
    assert '--expected-source-sha "${{ inputs.source_sha }}"' in candidate
    assert '--github-output "$GITHUB_OUTPUT"' in candidate

    diagnostics = next(
        step
        for step in producer["steps"]
        if str(step.get("uses") or "").startswith("actions/upload-artifact@")
    )
    assert diagnostics["if"] == "${{ failure() && !cancelled() }}"


def test_receipt_validator_rejects_local_authority_and_noncanonical_fields() -> None:
    payload = {
        "schema": "quwoquan.test.case-result",
        "caseId": "environment-stability.recovery.ios",
        "status": "passed",
        "releaseCompositionId": "sha256:" + "1" * 64,
        "commit": "2" * 40,
        "releaseId": "release--pilot-003",
        "releaseDigest": "sha256:" + "3" * 64,
        "artifactDigest": "sha256:" + "4" * 64,
        "executed": 1,
        "skipped": 0,
        "executedAt": "2026-08-04T12:00:00Z",
    }
    assert receipt._validate_case(payload, kind="recovery.ios") == payload

    payload["artifactAttestation"] = "local-sha256:" + "5" * 64
    try:
        receipt._validate_case(payload, kind="recovery.ios")
    except ValueError as exc:
        assert "canonical case result" in str(exc)
    else:
        raise AssertionError("local/noncanonical receipt must be rejected")


def test_receipt_validator_rejects_noncanonical_file_bytes(tmp_path: Path) -> None:
    payload = {
        "schema": "quwoquan.test.case-result",
        "caseId": "environment-stability.nightly-full",
        "status": "passed",
        "releaseCompositionId": "sha256:" + "1" * 64,
        "commit": "2" * 40,
        "releaseId": "release--pilot-003",
        "releaseDigest": "sha256:" + "3" * 64,
        "artifactDigest": "sha256:" + "4" * 64,
        "executed": 2,
        "skipped": 0,
        "executedAt": "2026-08-04T12:00:00Z",
    }
    path = tmp_path / "nightly.json"
    receipt._write_object(path, payload)
    assert receipt._read_canonical_object(path, label="nightly") == payload

    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        receipt._read_canonical_object(path, label="nightly")
    except ValueError as exc:
        assert "bytes are not canonical JSON" in str(exc)
    else:
        raise AssertionError("noncanonical bytes must not reach attestation")
