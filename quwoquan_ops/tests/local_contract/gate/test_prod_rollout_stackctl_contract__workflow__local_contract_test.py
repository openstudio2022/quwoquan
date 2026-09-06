from pathlib import Path

import yaml

from quwoquan_ops.gate import verify_prod_rollout_stackctl_contract as gate

ROOT = Path(__file__).resolve().parents[4]


def test_prod_rollout_stackctl_contract_accepts_current_workflow() -> None:
    workflow = ROOT / ".github/workflows/deploy-prod-auto.yml"
    text = workflow.read_text(encoding="utf-8")
    assert gate.prod_environment_job_issues(workflow) == []
    assert gate.formal_surface_issues() == []
    assert "release_tag_admission_ref:" in text
    assert "latestQualified" not in text
    assert "github.sha" not in text
    assert "--service prod-stack" in text
    assert "--from-candidate-digest" in text
    assert "--to-candidate-digest" in text
    assert "--release-evidence-ref" not in text
    assert "--release-manifest" not in text
    assert "fetch_mainline_release_artifact.py" not in text
    assert "--service-factory-material" in text
    assert "--app-factory-material" in text
    assert "--hosted-receipt-readback" in text
    assert "--hosted-soak-readback" in text
    assert '--prod-activation-admission "$STORE/$ADMISSION_LOCAL_REF"' in text
    assert "prod-materialize-input" in text
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


def test_prod_rollout_stackctl_contract_rejects_unprotected_job(tmp_path: Path) -> None:
    workflow = tmp_path / "deploy-prod-auto.yml"
    workflow.write_text(yaml.safe_dump({"jobs": {"prod_activation_admission": {"environment": "production"}, "prod_rollout": {"environment": "production"}, "unreviewed": {"environment": "production"}}}), encoding="utf-8")
    assert any("unreviewed" in issue for issue in gate.prod_environment_job_issues(workflow))


def test_formal_surface_gate_rejects_retired_release_authority(tmp_path: Path) -> None:
    legacy = tmp_path / "formal.py"
    legacy.write_text("fetch_mainline_release_artifact.py --release-manifest\n", encoding="utf-8")
    issues = gate.formal_surface_issues((legacy,))
    assert any("fetch_mainline_release_artifact.py" in issue for issue in issues)
    assert any("--release-manifest" in issue for issue in issues)
