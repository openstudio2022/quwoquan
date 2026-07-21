from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib import output_paths
from quwoquan_ops.cli import legal_static
from quwoquan_ops.cli import stackctl
from quwoquan_ops.gate.verify_output_layout import output_layout_issues
from quwoquan_ops.gate.verify_root_layout import source_cache_issues
from quwoquan_ops.gate import verify_output_path_source_contract as source_contract


MANIFEST = ROOT / "quwoquan_ops" / "environments" / "output_layout_manifest.yaml"
GATE_REPO = ROOT / "quwoquan_ops" / "gate" / "gate_repo.sh"
MAKEFILE = ROOT / "Makefile"


def test_legal_static_source_manifest_uses_the_current_versioned_schema() -> None:
    _, issues = legal_static.validate_manifest("alpha")

    assert issues == []


def _mkdirs(root: Path, paths: tuple[str, ...]) -> None:
    for relative in paths:
        (root / relative).mkdir(parents=True)


def test_layout_manifest_freezes_single_output_taxonomy() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert set(manifest) == {"root", "contract", "topLevel"}
    assert manifest["root"] == ".qwq_output"
    assert manifest["contract"]["disposable"] is True
    assert manifest["contract"]["sourceTruthAllowed"] is False
    assert manifest["contract"]["deletionInvariant"] == "repository_remains_buildable"
    assert manifest["contract"]["cachePersistenceRequired"] is False
    assert set(manifest["contract"]["allowedOutputConsumption"]) == {
        "same_execution_stage",
        "verification_evidence",
    }
    rebuild_sources = manifest["contract"]["rebuildSources"]
    assert rebuild_sources
    assert all((ROOT / source).exists() for source in rebuild_sources)
    assert all(".qwq_output" not in Path(source).parts for source in rebuild_sources)
    assert set(manifest["topLevel"]) == {"env", "data"}
    env = manifest["topLevel"]["env"]
    assert set(env["segments"]) == {"alpha", "beta", "gamma", "prod", "repo"}
    assert set(env["deploymentChildren"]) == {
        "runs",
        "observability",
        "local",
    }
    assert set(env["repoChildren"]) == {"runs", "observability", "local"}
    assert set(env["localChildren"]) == {"process", "cache"}
    assert set(manifest["topLevel"]["data"]["children"]) == {
        "tasks",
        "releases",
        "local",
    }


def test_path_resolver_honors_custom_root_and_orthogonal_scopes(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "custom-output"
    deploy_root = tmp_path / "deploy-work"
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(root))
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT", str(deploy_root))

    assert output_paths.output_root() == root
    assert output_paths.deployment_work_root("gamma-local") == deploy_root / "gamma-local"
    assert output_paths.deployment_package_root("gamma") == (
        deploy_root / "gamma-local/packages"
    )
    assert output_paths.app_deployment_package_dir("gamma") == (
        deploy_root / "gamma-local/packages/app"
    )
    assert output_paths.service_deployment_package_dir("gamma", "content-service") == (
        deploy_root / "gamma-local/packages/service/content-service"
    )
    assert output_paths.target_process_dir("gamma-local") == (
        root / "env/gamma/local/gamma-local/process"
    )
    assert output_paths.target_cache_dir("gamma-local") == (
        root / "env/gamma/local/gamma-local/cache"
    )
    assert output_paths.repo_runs_root() == root / "env/repo/runs"
    assert output_paths.data_tasks_root() == root / "data/tasks"
    assert output_paths.data_releases_root() == root / "data/releases"


def test_layout_gate_accepts_canonical_fixture(tmp_path: Path) -> None:
    root = tmp_path / ".qwq_output"
    _mkdirs(
        root,
        (
            "env/alpha/runs/run-1",
            "env/alpha/observability/run-1",
            "env/alpha/local/alpha-local/process",
            "env/alpha/local/alpha-local/cache",
            "env/repo/runs/tests",
            "env/repo/observability/run-1",
            "env/repo/local/ci/process",
            "env/repo/local/ci/cache",
            "data/tasks/execution-1",
            "data/releases/release-1",
            "data/local/workspace",
        ),
    )

    assert output_layout_issues(root) == []


def test_deployment_workspace_cannot_be_nested_under_disposable_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / ".qwq_output"
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(root))
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT", str(root / "deployment"))

    try:
        output_paths.deployment_work_root("gamma-local")
    except ValueError as exc:
        assert "must be outside QWQ_OUTPUT_ROOT" in str(exc)
    else:
        raise AssertionError("deployment workspace nested under output must fail")


def test_stackctl_inspect_keeps_configuration_outside_disposable_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = tmp_path / ".qwq_output"
    deploy = tmp_path / "deploy-work"
    report_dir = output / "env/gamma/runs/inspect-config"
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT", str(deploy))

    result = stackctl.command_inspect(
        Namespace(
            command="inspect",
            report_dir=str(report_dir),
            target="gamma-local",
            scope="config",
        )
    )

    assert result["exitCode"] == 0
    assert not (report_dir / "config.json").exists()
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    assert report["inspection"]["config"] == {
        "status": "stored_outside_output",
        "externalConfigRef": (
            "deployment-work://gamma-local/inspection/inspect-config/config.json"
        ),
    }
    assert (
        deploy / "gamma-local/inspection/inspect-config/config.json"
    ).is_file()
    assert output_layout_issues(output) == []


def test_environment_packaging_uses_hermetic_deploy_workspace_and_rechecks_output() -> None:
    makefile = MAKEFILE.read_text(encoding="utf-8")
    target_start = makefile.index("verify-env-packaging:")
    target_end = makefile.index("\n\n", target_start)
    recipe = makefile[target_start:target_end]
    assert "mktemp -d" in recipe
    assert "QWQ_DEPLOY_WORK_ROOT=" in recipe
    assert "stackctl.py --output-format json package" in recipe

    gate = GATE_REPO.read_text(encoding="utf-8")
    package_index = gate.index("make verify-env-packaging")
    recheck_index = gate.index(
        "python3 quwoquan_ops/gate/verify_output_layout.py",
        package_index,
    )
    assert recheck_index > package_index


def test_layout_gate_rejects_retired_categories_and_misplaced_state(
    tmp_path: Path,
) -> None:
    root = tmp_path / ".qwq_output"
    _mkdirs(
        root,
        (
            "packages",
            "env/staging/runs",
            "env/gamma/packages",
            "env/alpha/release",
            "env/gamma/local/gamma-local/pki",
            "env/repo/release",
            "data/runs",
            "data/observability/run-1",
        ),
    )

    issues = output_layout_issues(root)

    assert any("only permits env/ and data/" in issue for issue in issues)
    assert any("env only permits alpha/beta/gamma/prod/repo" in issue for issue in issues)
    assert sum("invalid" in issue and "output category" in issue for issue in issues) >= 2
    assert any("only permits process/ and cache/" in issue for issue in issues)
    assert any("invalid repo output category" in issue for issue in issues)
    assert sum("data only permits tasks/releases/local" in issue for issue in issues) == 2


def test_layout_gate_rejects_reusable_truth_inside_valid_output_categories(
    tmp_path: Path,
) -> None:
    root = tmp_path / ".qwq_output"
    _mkdirs(
        root,
        (
            "env/repo/local/tool/process/templates",
            "data/local/workspace/schema",
            "env/gamma/runs/run-1/policies",
        ),
    )

    issues = output_layout_issues(root)

    assert sum("reusable source truth is forbidden" in issue for issue in issues) == 3


def test_layout_gate_rejects_deployment_files_and_secret_values(
    tmp_path: Path,
) -> None:
    root = tmp_path / ".qwq_output"
    run = root / "env/gamma/runs/run-1"
    run.mkdir(parents=True)
    (run / "runtime.env").write_text("PROVIDER_TOKEN=plain-text-secret\n", encoding="utf-8")
    (run / "evidence.log").write_text("api_key=plain-text-secret\n", encoding="utf-8")

    issues = output_layout_issues(root)

    assert any("deployment configuration, TLS or secret material" in issue for issue in issues)
    assert any("unredacted secret assignment is forbidden" in issue for issue in issues)


def test_layout_gate_rejects_interpreter_cache_under_disposable_output(
    tmp_path: Path,
) -> None:
    root = tmp_path / ".qwq_output"
    _mkdirs(
        root,
        (
            "env/repo/local/python-envs/cache/quwoquan-data/site-packages/schema",
        ),
    )

    issues = output_layout_issues(root)

    assert any("interpreter caches belong in the external tool cache" in issue for issue in issues)


def test_layout_gate_does_not_misclassify_evidence_or_scan_dependency_payloads(
    tmp_path: Path,
) -> None:
    root = tmp_path / ".qwq_output"
    report = root / "data/tasks/execution-1/env_ready_report.json"
    report.parent.mkdir(parents=True)
    report.write_text('{"status":"ready"}\n', encoding="utf-8")
    dependency = root / "env/repo/local/python-test-deps/example.py"
    dependency.parent.mkdir(parents=True)
    dependency.write_text("api_key = generated_example_value\n", encoding="utf-8")

    issues = output_layout_issues(root)

    assert not any("env_ready_report.json" in issue for issue in issues)
    assert not any("example.py" in issue for issue in issues)
    assert any("interpreter caches belong in the external tool cache" in issue for issue in issues)


def test_source_gate_rejects_retired_cache_and_output_owned_truth(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root_config = tmp_path / "pytest.ini"
    root_config.write_text(
        "cache_dir=.qwq_output/env/repo/local/test-cache/pytest\n"
        "schema=.qwq_output/env/repo/local/tool/process/schema\n"
        "caddy=.qwq_output/env/gamma/local/gamma-local/process/caddy-data\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(source_contract, "SOURCE_ROOTS", ())
    monkeypatch.setattr(source_contract, "ROOT_CONFIG_FILES", (root_config,))

    issues = source_contract.source_path_issues()

    assert len(issues) == 3
    assert all("retired output/state path" in issue for issue in issues)


def test_root_layout_rejects_source_interpreter_and_pytest_caches(tmp_path: Path) -> None:
    bytecode_dir = tmp_path / "quwoquan_data" / "scripts" / "core" / "__pycache__"
    bytecode_dir.mkdir(parents=True)
    (bytecode_dir / "paths.cpython-313.pyc").write_bytes(b"bytecode")
    pytest_cache = tmp_path / "quwoquan_ops" / ".pytest_cache"
    pytest_cache.mkdir(parents=True)
    stray_bytecode = tmp_path / "quwoquan_app" / "scripts" / "app.pyo"
    stray_bytecode.parent.mkdir(parents=True)
    stray_bytecode.write_bytes(b"bytecode")

    issues = source_cache_issues(tmp_path)

    assert sum("source cache is forbidden" in issue for issue in issues) == 2
    assert sum("Python bytecode is forbidden" in issue for issue in issues) == 1
