from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
GATE_REPO = ROOT / "quwoquan_ops" / "gate" / "gate_repo.sh"
MAKEFILE = ROOT / "Makefile"


def test_environment_packaging_uses_hermetic_deploy_workspace_and_rechecks_output() -> None:
    makefile = MAKEFILE.read_text(encoding="utf-8")
    target_start = makefile.index("verify-env-packaging:")
    target_end = makefile.index("\n\n", target_start)
    recipe = makefile[target_start:target_end]
    assert "mktemp -d" in recipe
    assert "set -eu" in recipe
    assert "QWQ_DEPLOY_WORK_ROOT=" in recipe
    assert "stackctl.py --output-format json package" in recipe
    assert "cleanup_deployment_test_workspace.py" in recipe
    assert "prepare_environment_packaging_contract_inputs.py" in recipe
    assert "QWQ_GRAPHQL_READ_REGISTRY_SIGNING_KEY_ID" in recipe
    assert "QWQ_GRAPHQL_READ_REGISTRY_SIGNING_PRIVATE_KEY_FILE" in recipe
    assert "QWQ_GRAPHQL_READ_REGISTRY_TRUSTED_PUBLIC_KEYS_FILE" in recipe
    assert "--env alpha" in recipe
    assert "--env beta" in recipe
    assert "--env gamma" in recipe
    assert "--env prod" not in recipe
    assert "for env_name in alpha beta gamma" in recipe
    assert 'prepare_environment_packaging_contract_inputs.py "$$deploy_work_root";' in recipe
    assert "rm -rf" not in recipe
    assert 'trap \'cleanup_deploy_work_root "$$?"\' EXIT' in recipe
    assert 'exit "$$cleanup_status"' in recipe

    gate = GATE_REPO.read_text(encoding="utf-8")
    package_index = gate.index("make verify-env-packaging")
    recheck_index = gate.index(
        "python3 quwoquan_ops/gate/verify_output_layout.py",
        package_index,
    )
    assert recheck_index > package_index


def test_environment_packaging_preserves_the_first_prepare_blocker(
    tmp_path: Path,
) -> None:
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir()
    marker = tmp_path / "unexpected-python-invocation"
    python_shim = shim_dir / "python3"
    python_shim.write_text(
        """#!/bin/sh
case "$1" in
  *prepare_environment_packaging_contract_inputs.py)
    echo 'GATE_BLOCK: controlled prepare failure' >&2
    exit 27
    ;;
  *cleanup_deployment_test_workspace.py)
    rmdir "$2"
    exit 0
    ;;
  *)
    printf '%s\\n' "$*" >> "$QWQ_TEST_UNEXPECTED_PYTHON_MARKER"
    exit 99
    ;;
esac
""",
        encoding="utf-8",
    )
    python_shim.chmod(0o755)

    result = subprocess.run(
        ["make", "verify-env-packaging"],
        cwd=ROOT,
        env={
            **os.environ,
            "PATH": f"{shim_dir}:{os.environ['PATH']}",
            "QWQ_TEST_UNEXPECTED_PYTHON_MARKER": str(marker),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0, result.stdout + result.stderr
    assert "GATE_BLOCK: controlled prepare failure" in result.stderr
    assert "Error 27" in result.stderr
    assert "candidate" not in result.stderr
    assert not marker.exists()


def test_prod_packaging_contract_and_runtime_readiness_are_separate_and_wired() -> None:
    makefile = MAKEFILE.read_text(encoding="utf-8")
    gate = GATE_REPO.read_text(encoding="utf-8")
    prod_workflow = (
        ROOT / ".github/workflows/deploy-prod-auto.yml"
    ).read_text(encoding="utf-8")

    contract_start = makefile.index("verify-prod-packaging-contract:")
    contract_end = makefile.index("\n\n", contract_start)
    contract_recipe = makefile[contract_start:contract_end]
    assert "test_prod_target_app_package__local_contract_test.py" in contract_recipe
    assert "test_prod_hosted_package_oci_manifest__contract__local_contract_test.py" in contract_recipe
    assert "test_environment_package_entrypoints__local_contract_test.py" in contract_recipe
    assert "verify_prod_package_purity.py --target prod-hosted" in contract_recipe
    assert "stackctl.py" not in contract_recipe

    assert "make verify-env-packaging" in gate
    assert "make verify-prod-packaging-contract" in gate
    assert gate.index("make verify-env-packaging") < gate.index(
        "make verify-prod-packaging-contract"
    )
    assert "make verify-prod-hosted-runtime-readiness" not in gate

    runtime_start = makefile.index("verify-prod-hosted-runtime-readiness:")
    runtime_end = makefile.index("\n\n", runtime_start)
    runtime_recipe = makefile[runtime_start:runtime_end]
    assert "stackctl.py --output-format json doctor --target prod-hosted" in runtime_recipe
    assert "packaging" not in runtime_recipe

    package_step = prod_workflow.index("Materialize canonical configuration packages once")
    verify_step = prod_workflow.index("Verify exact Prod packaging candidate")
    assert package_step < verify_step
    assert "--kind packaging" in prod_workflow[verify_step:]
    assert "--profile smoke" in prod_workflow[verify_step:]
