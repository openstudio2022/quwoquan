from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib import output_paths
from quwoquan_ops.cli import legal_static
from quwoquan_ops.gate.verify_output_layout import output_layout_issues
from quwoquan_ops.gate import verify_output_path_source_contract as source_contract


MANIFEST = ROOT / "quwoquan_ops" / "environments" / "output_layout_manifest.yaml"


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
        "derived_release_deployment",
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
        "release",
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
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(root))

    assert output_paths.output_root() == root
    assert output_paths.env_release_root("gamma") == root / "env/gamma/release"
    assert output_paths.app_release_dir("gamma") == root / "env/gamma/release/app"
    assert output_paths.service_release_dir("gamma", "content-service") == (
        root / "env/gamma/release/service/content-service"
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
            "env/alpha/release/app",
            "env/alpha/release/service/content-service",
            "env/alpha/release/legal-static",
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
            "env/gamma/local/gamma-local/pki",
            "env/repo/release",
            "data/runs",
            "data/observability/run-1",
        ),
    )

    issues = output_layout_issues(root)

    assert any("only permits env/ and data/" in issue for issue in issues)
    assert any("env only permits alpha/beta/gamma/prod/repo" in issue for issue in issues)
    assert any("invalid gamma output category" in issue for issue in issues)
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


def test_layout_gate_treats_python_environment_as_opaque_disposable_cache(
    tmp_path: Path,
) -> None:
    root = tmp_path / ".qwq_output"
    _mkdirs(
        root,
        (
            "env/repo/local/python-envs/cache/quwoquan-data/site-packages/schema",
        ),
    )

    assert output_layout_issues(root) == []


def test_source_gate_rejects_retired_cache_and_output_owned_truth(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root_config = tmp_path / "pytest.ini"
    root_config.write_text(
        "cache_dir=.qwq_output/env/repo/local/test-cache/pytest\n"
        "schema=.qwq_output/env/repo/local/tool/process/schema\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(source_contract, "SOURCE_ROOTS", ())
    monkeypatch.setattr(source_contract, "ROOT_CONFIG_FILES", (root_config,))

    issues = source_contract.source_path_issues()

    assert len(issues) == 2
    assert all("retired output/state path" in issue for issue in issues)
