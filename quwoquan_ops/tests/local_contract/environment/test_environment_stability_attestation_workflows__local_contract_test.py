from __future__ import annotations

import ast
from pathlib import Path

import yaml

from quwoquan_ops.ci import release_qualification
from quwoquan_ops.cli.lib.environment_stability_final_acceptance import (
    GITHUB_ATTESTED_WORKFLOW_BY_KIND,
    RETIRED_GITHUB_ATTESTED_EVIDENCE_KINDS,
)

ROOT = Path(__file__).resolve().parents[4]
WORKFLOWS = ROOT / ".github/workflows"
MODEL_PATH = (
    ROOT / "quwoquan_ops/cli/lib/environment_stability_final_acceptance/model.py"
)
PROD_SIM_WORKFLOW_PATH = WORKFLOWS / "prod-sim-manual-admission.yml"
RELEASE_QUALIFICATION_WORKFLOW_PATH = WORKFLOWS / "release-qualification.yml"
RETIRED_WORKFLOWS = (
    "app-env-device-matrix-self-hosted.yml",
    "beta-device-platform.yml",
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
    module = ast.parse(MODEL_PATH.read_text(encoding="utf-8"))
    assignments = {
        target.id: node.value
        for node in module.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    value = assignments["GITHUB_ATTESTED_WORKFLOW_BY_KIND"]
    assert isinstance(value, ast.Dict)
    return {
        ast.literal_eval(raw_key): ast.literal_eval(raw_value)
        for raw_key, raw_value in zip(value.keys, value.values, strict=True)
    }


def test_retired_device_and_nightly_workflows_and_mutable_pointer_are_absent() -> None:
    for name in RETIRED_WORKFLOWS:
        assert not (WORKFLOWS / name).exists()
    workflow_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in WORKFLOWS.glob("*.yml")
    )
    assert "RELEASED_RELEASE_EVIDENCE_REF" not in workflow_text
    assert "app-env-device-matrix-self-hosted.yml" not in MODEL_PATH.read_text(
        encoding="utf-8"
    )


def test_only_prod_sim_retains_github_attestation_diagnostic_authority() -> None:
    assert RETIRED_GITHUB_ATTESTED_EVIDENCE_KINDS == {
        "recovery.ios",
        "recovery.android",
        "nightly",
    }
    assert GITHUB_ATTESTED_WORKFLOW_BY_KIND == {
        "prod_sim": ".github/workflows/prod-sim-manual-admission.yml",
    }
    assert _attested_workflow_map() == GITHUB_ATTESTED_WORKFLOW_BY_KIND

    workflow = _workflow(PROD_SIM_WORKFLOW_PATH)
    signer = workflow["jobs"]["attest_prod_sim_report"]
    assert signer["permissions"] == MINIMUM_ATTESTATION_PERMISSIONS
    actions = [
        step for step in signer["steps"] if step.get("uses") == ATTEST_ACTION
    ]
    assert len(actions) == 1
    assert actions[0]["with"] == {"subject-path": "${{ env.RECEIPT_PATH }}"}


def test_prod_sim_is_explicitly_non_promotable_before_oidc_attestation() -> None:
    workflow = _workflow(PROD_SIM_WORKFLOW_PATH)
    producer = workflow["jobs"]["prod_sim_admission"]
    assert producer["runs-on"] == ["self-hosted", "macOS", "ARM64"]
    assert producer["environment"] == "prod-sim-admission"
    assert _step_index(
        producer,
        "Prove the rehearsal cannot become release evidence",
    ) < _step_index(
        producer,
        "Bind and verify canonical prod-sim report",
    )

    signer = workflow["jobs"]["attest_prod_sim_report"]
    assert signer["if"] == "${{ needs.prod_sim_admission.result == 'success' }}"
    assert _step_index(
        signer,
        "Verify passed non-promotable prod-sim report bindings",
    ) < _step_index(
        signer,
        "Attest exact prod-sim report bytes",
    )


def test_release_qualification_owns_physical_device_package_acceptance() -> None:
    workflow = _workflow(RELEASE_QUALIFICATION_WORKFLOW_PATH)
    package_input = workflow["on"]["workflow_dispatch"]["inputs"][
        "package_acceptance_fact_ref"
    ]
    assert package_input == {
        "description": (
            "Exact physical Android/iOS package acceptance OCI @sha256 ref"
        ),
        "required": "true",
        "type": "string",
    }

    job = workflow["jobs"]["materialize_candidate"]
    assert job["environment"] == "release-qualification"
    assert job["needs"] == [
        "allocate_build_number",
        "service_factory",
        "app_factory",
    ]
    package_step_name = "Require external final package acceptance"
    finalize_step_name = (
        "Materialize CandidateMaterialManifest and QualificationFact"
    )
    assert _step_index(job, package_step_name) < _step_index(
        job,
        finalize_step_name,
    )

    package_step = next(
        step
        for step in job["steps"]
        if step.get("name") == package_step_name
    )
    assert package_step["env"] == {
        "PACKAGE_ACCEPTANCE_REF": "${{ inputs.package_acceptance_fact_ref }}"
    }
    package_command = package_step["run"]
    assert (
        '[[ "$PACKAGE_ACCEPTANCE_REF" =~ '
        r'^ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}$ ]]'
        in package_command
    )
    assert (
        "Android and iOS physical-device package acceptance" in package_command
    )
    assert "same materialId" in package_command

    finalize_step = next(
        step
        for step in job["steps"]
        if step.get("name") == finalize_step_name
    )
    assert finalize_step["env"]["PACKAGE_ACCEPTANCE_REF"] == (
        "${{ inputs.package_acceptance_fact_ref }}"
    )
    finalize_command = finalize_step["run"]
    materialize_package = (
        'PACKAGE_EXACT="$(materialize_fact package-acceptance '
        '"$PACKAGE_ACCEPTANCE_REF")"'
    )
    assert materialize_package in finalize_command
    assert finalize_command.index(materialize_package) < finalize_command.index(
        "qualification-finalize"
    )
    assert '--package-acceptance "$PACKAGE_EXACT"' in finalize_command

    source = Path(release_qualification.__file__).read_text(encoding="utf-8")
    assert 'name == "packageAcceptance"' in source
    assert 'fact.get("materialId") != material.get("materialId")' in source
    compact_source = "".join(source.split())
    assert (
        'fact.get("physicalDevicePlatforms")!=["android","ios"]'
        in compact_source
    )
    assert "final package acceptance requires both physical platforms" in source


def test_prod_sim_consumes_clean_deployable_release_closure() -> None:
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
        if step.get("name")
        == "Verify deployable manifest, OIDC and artifact closure"
    )["run"]
    assert "consume_released_release_evidence.py" in candidate
    assert "--require-status deployable" in candidate
    assert '--expected-source-sha "${{ inputs.source_sha }}"' in candidate
    assert '--github-output "$GITHUB_OUTPUT"' in candidate

    diagnostics = next(
        step
        for step in producer["steps"]
        if str(step.get("uses") or "").startswith("actions/upload-artifact@")
    )
    assert diagnostics["if"] == "${{ failure() && !cancelled() }}"


def test_remaining_attested_workflow_has_no_local_or_secret_fallback() -> None:
    workflow = PROD_SIM_WORKFLOW_PATH.read_text(encoding="utf-8").lower()
    for forbidden in (
        "hmac-sha256:",
        "local-sha256:",
        "attestation_key",
        "attestation_secret",
    ):
        assert forbidden not in workflow
