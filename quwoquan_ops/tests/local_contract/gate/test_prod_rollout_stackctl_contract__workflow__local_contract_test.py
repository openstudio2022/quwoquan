from __future__ import annotations

from pathlib import Path

import yaml

from quwoquan_ops.gate import verify_prod_rollout_stackctl_contract as gate


ROOT = Path(__file__).resolve().parents[4]


def test_prod_rollout_stackctl_contract_accepts_current_workflow() -> None:
    assert gate.prod_environment_job_issues(
        ROOT / ".github/workflows/deploy-prod-auto.yml"
    ) == []


def test_prod_rollout_stackctl_contract_rejects_unprotected_job(tmp_path: Path) -> None:
    workflow = tmp_path / "deploy-prod-auto.yml"
    workflow.write_text(
        yaml.safe_dump(
            {
                "jobs": {
                    "prod_rollout": {"environment": "release-validation"},
                    "prod_soak_acceptance": {"environment": "production"},
                    "unreviewed": {"environment": "production"},
                }
            }
        ),
        encoding="utf-8",
    )
    assert any(
        "unreviewed" in issue for issue in gate.prod_environment_job_issues(workflow)
    )
