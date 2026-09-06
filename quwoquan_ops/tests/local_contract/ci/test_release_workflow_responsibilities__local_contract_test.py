from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
WORKFLOWS = ROOT / ".github/workflows"


def load(name: str) -> tuple[str, dict]:
    text = (WORKFLOWS / name).read_text(encoding="utf-8")
    return text, yaml.safe_load(text)


def test_artifact_gc_has_no_workflow_run_fanout() -> None:
    text, workflow = load("artifact-lifecycle.yml")
    assert "workflow_run" not in workflow[True]
    assert set(workflow[True]) == {"schedule", "workflow_dispatch", "pull_request"}
    assert "github.event.workflow_run" not in text


def test_environment_and_device_actions_are_deleted_after_cutover() -> None:
    for name in (
        "pre-release-gate.yml", "app-env-device-matrix-self-hosted.yml",
        "beta-device-platform.yml", "provider-release-evidence.yml",
    ):
        assert not (WORKFLOWS / name).exists()


def test_release_workflows_have_three_separate_responsibilities() -> None:
    qualification, q = load("release-qualification.yml")
    selection, s = load("release-tag-selection.yml")
    prod, p = load("deploy-prod-auto.yml")
    assert set(q[True]) == {"workflow_dispatch"}
    assert set(q[True]["workflow_dispatch"]["inputs"]) == {
        "rc_tag_admission_ref", "qualification_request_ref", "source_git_sha",
        "product_version_manifest_ref", "package_acceptance_fact_ref",
        "provider_fact_ref", "uat_fact_ref", "supply_chain_fact_ref",
    }
    assert q["jobs"]["allocate_build_number"]["environment"] == "release-qualification"
    assert q["jobs"]["service_factory"]["uses"] == "./.github/workflows/service_pipeline.yml"
    assert q["jobs"]["app_factory"]["uses"] == "./.github/workflows/app_pipeline.yml"
    assert "artifact_build_number" not in q[True]["workflow_dispatch"]["inputs"]
    assert "github.run_number" in qualification
    assert "reusable factory omitted" in qualification
    assert "qualification-material" in qualification
    assert "qualification-finalize" in qualification
    assert "QualificationFact issued" in qualification
    assert "pending external qualification facts" not in qualification
    assert set(s[True]) == {"workflow_dispatch"}
    assert s["jobs"]["pre_admission"]["environment"] == "release-selection"
    assert s["jobs"]["create_and_readback"]["environment"] == "release-selection"
    assert selection.index("tag-admit-stable") < selection.index("git push origin")
    assert selection.index("tag-admit-rc") < selection.index("git push origin")
    assert "git tag -a" in selection and "release-controller" in selection
    assert "verified-pre-push-local-admission" not in selection
    assert set(p[True]) == {"workflow_dispatch"}
    assert set(p[True]["workflow_dispatch"]["inputs"]) == {
        "release_tag_admission_ref", "previous_active_released_ledger_ref",
        "rollback_readiness_ref",
    }
    assert "push:" not in prod and "latestQualified" not in prod and "RELEASED_RELEASE_EVIDENCE_REF" not in prod
    assert 'release_control.py --store-root "$STORE" prod-admit' in prod
    assert "prod-materialize-input" in prod
    assert "stackctl.py deploy --target prod-hosted" in prod
    assert '--prod-activation-admission "$STORE/$ADMISSION_LOCAL_REF"' in prod
    assert "${{ steps.publish.outputs.admission_ref }}" in prod
    for retired in (
        "QWQ_ENVIRONMENT_ACCEPTANCE_ROOT",
        "PROD_ENVIRONMENT_ACCEPTANCE_REF",
        "PROD_ENVIRONMENT_ACCEPTANCE_DIGEST",
        "PROD_ENVIRONMENT_ACCEPTANCE_ROOT",
        "--environment-acceptance-ref",
        "--environment-acceptance-sha256",
        "--environment-acceptance-root",
    ):
        assert retired not in prod
    assert "unreachable until" not in prod
    assert "release tag admission transport must expose" not in prod
