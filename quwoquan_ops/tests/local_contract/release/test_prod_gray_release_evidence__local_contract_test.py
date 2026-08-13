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


def test_hosted_ledger_uses_candidate_digest_for_cas_identity() -> None:
    assert rollout_gate.candidate_identity_issues() == []


def test_unified_prod_has_no_legacy_release_identity_or_config_copy_path() -> None:
    text = CONTROLLED_WORKFLOW.read_text(encoding="utf-8")

    for token in rollout_gate.FORBIDDEN_ROLLOUT_TOKENS:
        assert token not in text


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
        ".release-evidence-manifest: forbidden top-level directory" in issue
        for issue in issues
    )
