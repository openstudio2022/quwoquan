from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
ROOT = Path(__file__).resolve().parents[3]
STACKCTL = ROOT / "quwoquan_ops" / "cli" / "stackctl.py"
PROD_APP_SOURCE = ROOT / "quwoquan_app" / "configs" / "prod" / "app_runtime.yaml"


def test_prod_app_packages_block_on_unapproved_legal_identity_without_mutating_source(
    tmp_path: Path,
) -> None:
    deploy_root = tmp_path / "deploy"
    output_root = tmp_path / "output"
    source_before = PROD_APP_SOURCE.read_bytes()
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "QWQ_DEPLOY_WORK_ROOT": str(deploy_root),
            "QWQ_OUTPUT_ROOT": str(output_root),
        }
    )

    for target in ("prod-sim", "prod-hosted"):
        result = subprocess.run(
            [
                sys.executable,
                str(STACKCTL),
                "package",
                "--env",
                "prod",
                "--target",
                target,
                "--report-dir",
                str(tmp_path / f"report-{target}"),
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, result.stdout + result.stderr
        assert "legal-static/prod" in result.stdout
        assert "placeholder text" in result.stdout
        assert not (deploy_root / target / "active-candidate.json").exists()

    assert PROD_APP_SOURCE.read_bytes() == source_before
