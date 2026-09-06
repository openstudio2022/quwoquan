# spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#sit-004
from __future__ import annotations

from pathlib import Path

import yaml

from quwoquan_ops.gate import verify_prod_rollout_stackctl_contract as rollout_gate
from quwoquan_ops.gate.verify_root_layout import root_layout_issues


ROOT = Path(__file__).resolve().parents[4]
CONTROLLED_WORKFLOW = ROOT / ".github" / "workflows" / "deploy-prod-auto.yml"


def test_only_unified_controlled_prod_transaction_can_write_prod() -> None:
    retired = ROOT / ".github" / "workflows" / "deploy-prod-gray.yml"
    assert not retired.exists()
    assert rollout_gate.workflow_rollout_issues(CONTROLLED_WORKFLOW) == []
    assert rollout_gate.prod_environment_job_issues(CONTROLLED_WORKFLOW) == []
    text = CONTROLLED_WORKFLOW.read_text(encoding="utf-8")
    assert "  prod_rollout:\n" in text


def test_an_extra_job_cannot_join_the_controlled_prod_transaction(tmp_path: Path) -> None:
    document = yaml.safe_load(CONTROLLED_WORKFLOW.read_text(encoding="utf-8"))
    document["jobs"]["rogue_prod_writer"] = {
        "runs-on": "ubuntu-latest",
        "environment": "production",
        "steps": [{"run": "echo rogue"}],
    }
    forged = tmp_path / "deploy-prod-auto.yml"
    forged.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    issues = rollout_gate.prod_environment_job_issues(forged)

    assert any("rogue_prod_writer" in issue for issue in issues)


def test_hosted_cas_uses_admitted_candidate_digest_and_explicit_readback() -> None:
    text = CONTROLLED_WORKFLOW.read_text(encoding="utf-8")

    for token in (
        "ProdActivationAdmissionFact",
        "prod-admit",
        "ADMISSION_OCI_REF: ${{ needs.prod_activation_admission.outputs.admission_ref }}",
        "ADMISSION_DIGEST: ${{ needs.prod_activation_admission.outputs.admission_digest }}",
        "FROM_CANDIDATE_DIGEST: ${{ steps.activation_input.outputs.from_candidate_digest }}",
        "TO_CANDIDATE_DIGEST: ${{ steps.activation_input.outputs.candidate_digest }}",
        "ADMISSION_LOCAL_REF: ${{ steps.activation_input.outputs.admission_local_ref }}",
        '--admission "$ADMISSION_OCI_REF=$ADMISSION_DIGEST"',
        '--from-candidate-digest "$FROM_CANDIDATE_DIGEST"',
        '--to-candidate-digest "$TO_CANDIDATE_DIGEST"',
        '--prod-activation-admission "$STORE/$ADMISSION_LOCAL_REF"',
        'receipt_id = str(report.get("releaseReceiptId") or "")',
        '"receipt": report.get("hostedReceipt") or {}',
        "--operation release-ledger-receipt",
        '--receipt-id "$FULL_STAGE_RECEIPT_ID"',
        'test -s "$FULL_STAGE_READBACK"',
        '"$FULL_STAGE_READBACK" "$STORE" "$RELEASED_REF" "$FULL_STAGE_RECEIPT_ID"',
        'hosted_exact = released.get("hostedReceiptReadback")',
        'set(hosted_exact) != {"ref", "digest"}',
        '(store / hosted_exact["ref"]).read_text',
        'hosted_receipt.get("receiptId") != expected_receipt_id',
    ):
        assert token in text

    assert text.index("prod-admit") < text.index(
        "stackctl.py deploy --target prod-hosted"
    )


def test_rollout_materializes_published_admission_and_consumes_one_local_envelope() -> None:
    document = yaml.safe_load(CONTROLLED_WORKFLOW.read_text(encoding="utf-8"))
    jobs = document["jobs"]
    outputs = jobs["prod_activation_admission"]["outputs"]
    assert outputs == {
        "admission_ref": "${{ steps.publish.outputs.admission_ref }}",
        "admission_digest": "${{ steps.admit.outputs.admission_digest }}",
    }

    rollout_steps = jobs["prod_rollout"]["steps"]
    activation = next(step for step in rollout_steps if step.get("id") == "activation_input")
    rollout = next(step for step in rollout_steps if step.get("id") == "rollout")
    materialize = str(activation["run"])
    command = str(rollout["run"])

    assert r'[[ "$ADMISSION_OCI_REF" =~ ^ghcr\.io/' in materialize
    assert "materialize-oci" in materialize
    assert '--ref "$ADMISSION_OCI_REF"' in materialize
    assert '= "$ADMISSION_DIGEST"' in materialize
    assert materialize.count("prod-materialize-input") == 1
    assert '--output "$STORE/$ADMISSION_LOCAL_REF"' in materialize
    assert '--github-output "$GITHUB_OUTPUT"' in materialize
    assert 'envelope.get("prodActivationAdmission") != {"ref": admission_ref, "digest": admission_digest}' in materialize
    assert command.count("--prod-activation-admission") == 1
    assert '--prod-activation-admission "$STORE/$ADMISSION_LOCAL_REF"' in command


def test_gate_rejects_legacy_release_identity_config_copy_and_mutable_inputs(
    tmp_path: Path,
) -> None:
    current = CONTROLLED_WORKFLOW.read_text(encoding="utf-8")
    probes = (
        (
            "released_evidence_identity",
            "retired released-evidence identity",
            "RELEASED_RELEASE_EVIDENCE_REF",
        ),
        (
            "qualification_identity",
            "retired qualification identity",
            "qualification_fact_ref:",
        ),
        ("qualified_selector", "mutable qualified selector", "latestQualified"),
        ("source_selector", "mutable source selector", "source_sha:"),
        ("dry_run_branch", "mutable dry-run branch", "dry_run:"),
        (
            "deploy_time_config_copy",
            "deploy-time config/package copy",
            "stackctl.py package",
        ),
    )

    for case_id, label, token in probes:
        forged = tmp_path / f"{case_id}.yml"
        forged.write_text(f"{current}\n# regression probe\n{token}\n", encoding="utf-8")

        issues = rollout_gate.workflow_rollout_issues(forged)

        assert any(token in issue for issue in issues), label


def test_prod_requires_explicit_activation_admission_not_legacy_eaf_input() -> None:
    document = yaml.safe_load(CONTROLLED_WORKFLOW.read_text(encoding="utf-8"))
    triggers = document.get("on") or document.get(True) or {}
    inputs = set((triggers.get("workflow_dispatch") or {}).get("inputs") or {})
    text = CONTROLLED_WORKFLOW.read_text(encoding="utf-8")

    assert inputs == {
        "release_tag_admission_ref",
        "previous_active_released_ledger_ref",
        "rollback_readiness_ref",
    }
    assert "ProdActivationAdmissionFact" in text
    assert "EnvironmentAcceptanceFact" not in text
    assert "environment_acceptance_fact" not in text
    for retired in (
        "QWQ_ENVIRONMENT_ACCEPTANCE_ROOT",
        "PROD_ENVIRONMENT_ACCEPTANCE_REF",
        "PROD_ENVIRONMENT_ACCEPTANCE_DIGEST",
        "PROD_ENVIRONMENT_ACCEPTANCE_ROOT",
        "--environment-acceptance-ref",
        "--environment-acceptance-sha256",
        "--environment-acceptance-root",
    ):
        assert retired not in text


def test_private_prod_state_writer_scripts_are_retired() -> None:
    assert not (ROOT / "quwoquan_ops/cli/prod/config_release_gray_rollout.sh").exists()
    assert not (ROOT / "quwoquan_ops/cli/prod/config_release_rollback.sh").exists()


def test_release_evidence_never_creates_a_top_level_runtime_directory(
    tmp_path: Path,
) -> None:
    canonical = tmp_path / ".release-evidence-manifest"
    canonical.mkdir()

    issues = root_layout_issues(tmp_path)

    assert any(
        ".release-evidence-manifest: retired top-level entry" in issue
        for issue in issues
    )
