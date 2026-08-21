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
    assert 'packaging_envs="$${QWQ_PACKAGING_ENVS:-alpha beta gamma}"' in recipe
    assert '--env "$$env_name"' in recipe
    assert "--env prod" not in recipe
    assert "for env_name in $$packaging_envs" in recipe
    assert 'prepare_environment_packaging_contract_inputs.py "$$deploy_work_root";' in recipe
    assert "run_phase()" in recipe
    for phase in (
        "prepare",
        "package-$$env_name",
        "contract-$$env_name",
        "isolation-$$env_name",
        "gamma-prod-isomorphism",
    ):
        assert phase in recipe
    assert "durationSeconds=" in recipe
    assert "GATE_BLOCK phase=$$phase_name status=$$phase_status" in recipe
    assert "FIX: repair the first typed blocker above" in recipe
    assert ">/dev/null" not in recipe
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
    assert "GATE_BLOCK phase=prepare status=27" in result.stderr
    assert "FIX: repair the first typed blocker above" in result.stderr
    assert "Error 27" in result.stderr
    assert "candidate" not in result.stderr
    assert not marker.exists()


def test_environment_packaging_stops_on_first_package_blocker_and_preserves_status(
    tmp_path: Path,
) -> None:
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir()
    invocation_log = tmp_path / "python-invocations"
    python_shim = shim_dir / "python3"
    python_shim.write_text(
        """#!/bin/sh
printf '%s\n' "$*" >> "$QWQ_TEST_PYTHON_INVOCATIONS"
case "$1" in
  *prepare_environment_packaging_contract_inputs.py)
    exit 0
    ;;
  *stackctl.py)
    case " $* " in
      *" --env beta "*)
        echo 'GATE_BLOCK: controlled beta package failure' >&2
        exit 29
        ;;
    esac
    exit 0
    ;;
  *cleanup_deployment_test_workspace.py)
    rmdir "$2"
    exit 0
    ;;
  *)
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
            "QWQ_TEST_PYTHON_INVOCATIONS": str(invocation_log),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0, result.stdout + result.stderr
    assert "START phase=package-alpha" in result.stdout
    assert "DONE phase=package-alpha" in result.stdout
    assert "START phase=package-beta" in result.stdout
    assert "GATE_BLOCK: controlled beta package failure" in result.stderr
    assert "GATE_BLOCK phase=package-beta status=29" in result.stderr
    assert "Error 29" in result.stderr
    invocations = invocation_log.read_text(encoding="utf-8")
    assert "--env alpha" in invocations
    assert "--env beta" in invocations
    assert "--env gamma" not in invocations
    assert "verify_environment_packaging_contract.py" not in invocations


def _pass_through_python_shim(tmp_path: Path) -> tuple[Path, Path]:
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir()
    invocation_log = tmp_path / "python-invocations"
    python_shim = shim_dir / "python3"
    python_shim.write_text(
        """#!/bin/sh
printf '%s\\n' "$*" >> "$QWQ_TEST_PYTHON_INVOCATIONS"
case "$1" in
  *cleanup_deployment_test_workspace.py)
    rmdir "$2"
    exit 0
    ;;
esac
exit 0
""",
        encoding="utf-8",
    )
    python_shim.chmod(0o755)
    return shim_dir, invocation_log


def _run_env_packaging(
    shim_dir: Path,
    invocation_log: Path,
    **extra_env: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", "verify-env-packaging"],
        cwd=ROOT,
        env={
            **os.environ,
            "PATH": f"{shim_dir}:{os.environ['PATH']}",
            "QWQ_TEST_PYTHON_INVOCATIONS": str(invocation_log),
            **extra_env,
        },
        text=True,
        capture_output=True,
        check=False,
    )


def test_environment_packaging_covers_all_three_envs_by_default(tmp_path: Path) -> None:
    shim_dir, invocation_log = _pass_through_python_shim(tmp_path)

    result = _run_env_packaging(shim_dir, invocation_log)

    assert result.returncode == 0, result.stdout + result.stderr
    invocations = invocation_log.read_text(encoding="utf-8")
    for env_name in ("alpha", "beta", "gamma"):
        assert f"package --env {env_name}" in invocations
        assert f"verify_environment_packaging_contract.py --env {env_name}" in invocations
        assert f"verify_env_artifact_isolation.py --env {env_name}" in invocations
    assert "verify_gamma_local_prod_isomorphism.py" in invocations
    assert "--env prod" not in invocations


def test_single_env_selection_packages_only_that_env(tmp_path: Path) -> None:
    shim_dir, invocation_log = _pass_through_python_shim(tmp_path)

    result = _run_env_packaging(shim_dir, invocation_log, QWQ_PACKAGING_ENVS="beta")

    assert result.returncode == 0, result.stdout + result.stderr
    invocations = invocation_log.read_text(encoding="utf-8")
    assert "package --env beta" in invocations
    assert "package --env alpha" not in invocations
    assert "package --env gamma" not in invocations
    # gamma/prod 同构只属于 gamma 那一格，否则并行拆分后会被判三遍。
    assert "verify_gamma_local_prod_isomorphism.py" not in invocations


def test_env_selection_refuses_anything_outside_the_three_envs(tmp_path: Path) -> None:
    shim_dir, invocation_log = _pass_through_python_shim(tmp_path)

    result = _run_env_packaging(shim_dir, invocation_log, QWQ_PACKAGING_ENVS="prod")

    assert result.returncode != 0, result.stdout + result.stderr
    assert (
        "GATE_BLOCK: QWQ_PACKAGING_ENVS 只接受 alpha|beta|gamma，收到 prod"
        in result.stderr
    )
    assert not invocation_log.exists()


def test_delivery_gate_packages_the_three_envs_as_parallel_siblings() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")
    job_start = workflow.index("  quwoquan_service_packaging:")
    job_end = workflow.index("\n  search_contract_smoke:", job_start)
    job = workflow[job_start:job_end]

    assert "name: Delivery Gate — Service Packaging (${{ matrix.packaging_env }})" in job
    assert "fail-fast: false" in job
    assert "packaging_env: [alpha, beta, gamma]" in job
    assert "QWQ_PACKAGING_ENVS: ${{ matrix.packaging_env }}" in job
    # 三格并行后时长与结果都按兄弟作业收口：少跑一格必须算证据不齐，而不是默认通过。
    assert '--require-count "service_packaging=3"' in workflow
    assert '--phase "service_packaging=Delivery Gate — Service Packaging"' in workflow


def test_delivery_gate_cancels_superseded_runs_without_merging_the_two_ranges() -> None:
    workflow = (ROOT / ".github/workflows/delivery-gate.yml").read_text(encoding="utf-8")
    concurrency = workflow[workflow.index("concurrency:") : workflow.index("\non:")]

    assert "group: delivery-gate-${{ github.event_name }}-${{ github.ref }}" in concurrency
    assert "cancel-in-progress: true" in concurrency
    # push 对上一个 tip、pull_request 对 main，两段区间不同；按 head SHA 归一会丢区间。
    assert "head.sha" not in concurrency


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
