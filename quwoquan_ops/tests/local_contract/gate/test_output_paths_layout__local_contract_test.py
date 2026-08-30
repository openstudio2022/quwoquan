from __future__ import annotations

import json
import os
import stat
import sys
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli import legal_static, stackctl
from quwoquan_ops.cli.lib import output_paths
from quwoquan_ops.cli.lib.common import artifact_run_dir
from quwoquan_ops.cli.prod import render_prod_plane_stack as render
from quwoquan_ops.gate import verify_output_path_source_contract as source_contract
from quwoquan_ops.gate.verify_output_layout import output_layout_issues
from quwoquan_ops.gate.verify_root_layout import (
    ALLOWED_TOP_LEVEL,
    source_cache_issues,
    top_level_issues,
)

MANIFEST = ROOT / "quwoquan_ops" / "environments" / "output_layout_manifest.yaml"
DEPLOY_BASH_ENTRIES = {
    ROOT / "quwoquan_ops/cli/prod_sim/start_prod_sim_stack.sh": "prod-sim",
    ROOT / "quwoquan_ops/cli/prod/deploy_to_prod.sh": "prod-hosted",
}


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
    assert output_paths.deployment_work_root("gamma-local") == (
        deploy_root / "gamma-local"
    ).resolve()
    assert output_paths.deployment_package_root("gamma") == (
        deploy_root / "gamma-local/packages"
    )
    assert output_paths.app_deployment_package_dir("gamma") == (
        deploy_root / "gamma-local/packages/app"
    )
    assert output_paths.service_deployment_package_dir("gamma", "content-service") == (
        deploy_root / "gamma-local/packages/services/content-service"
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


def _install_full_candidate_loader(
    monkeypatch,
) -> list[tuple[str, str, str, bool]]:
    from quwoquan_ops.cli.lib import deployment_candidate_manifest

    calls: list[tuple[str, str, str, bool]] = []

    def load_candidate_manifest(
        environment: str,
        target: str,
        baseline_id: str,
        *,
        require_full: bool,
    ) -> dict[str, str]:
        calls.append((environment, target, baseline_id, require_full))
        return {
            "candidateType": "runtime-full",
            "target": target,
            "baselineId": baseline_id,
        }

    monkeypatch.setattr(
        deployment_candidate_manifest,
        "load_candidate_manifest",
        load_candidate_manifest,
    )
    return calls


def test_package_root_switches_atomically_to_fully_validated_candidate(
    tmp_path: Path, monkeypatch
) -> None:
    deploy_root = tmp_path / "deploy-work"
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT", str(deploy_root))
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path / "output"))
    baseline_id = f"sha256:{'a' * 64}"
    candidate = output_paths.deployment_candidate_dir("alpha-local", baseline_id)
    (candidate / "packages/app").mkdir(parents=True)
    (candidate / "manifest.json").write_text(
        json.dumps(
            {
                "candidateType": "runtime-full",
                "target": "alpha-local",
                "baselineId": baseline_id,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    validation_calls = _install_full_candidate_loader(monkeypatch)
    directory_fsyncs: list[int] = []
    actual_fsync = os.fsync

    def recording_fsync(descriptor: int) -> None:
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            directory_fsyncs.append(descriptor)
        actual_fsync(descriptor)

    monkeypatch.setattr(output_paths.os, "fsync", recording_fsync)

    pointer = output_paths.activate_deployment_candidate(
        "alpha-local",
        baseline_id,
    )

    assert pointer == deploy_root / "alpha-local/active-runtime-candidate.json"
    assert output_paths.deployment_package_root("alpha") == candidate / "packages"
    assert output_paths.app_deployment_package_dir("alpha") == candidate / "packages/app"
    # public Web 包不是 runtime candidate 的成员：它由独立 job 构建、自带 content
    # digest 与 current 指针，所以候选切换不得移动它的家，否则写读会落到两处。
    assert output_paths.web_deployment_package_dir("alpha") == (
        deploy_root / "alpha-local/standalone-packages/web/packages/public-web"
    )
    assert output_paths.active_deployment_candidate("alpha-local") == {
        "schema": output_paths.ACTIVE_CANDIDATE_SCHEMA,
        "candidateType": "runtime-full",
        "target": "alpha-local",
        "baselineId": baseline_id,
        "candidateDir": str(candidate),
    }
    assert validation_calls
    assert set(validation_calls) == {
        ("alpha", "alpha-local", baseline_id, True),
    }
    assert directory_fsyncs


def test_fixed_candidate_snapshot_detects_an_active_pointer_switch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    deploy_root = tmp_path / "deploy-work"
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT", str(deploy_root))
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path / "output"))
    first = f"sha256:{'a' * 64}"
    second = f"sha256:{'b' * 64}"
    for baseline_id in (first, second):
        candidate = output_paths.deployment_candidate_dir(
            "alpha-local",
            baseline_id,
        )
        (candidate / "packages").mkdir(parents=True)
        (candidate / "manifest.json").write_text("{}\n", encoding="utf-8")
    _install_full_candidate_loader(monkeypatch)
    output_paths.activate_deployment_candidate("alpha-local", first)

    snapshot = output_paths.active_deployment_candidate_snapshot("alpha-local")

    assert snapshot is not None
    assert snapshot["baselineId"] == first
    assert snapshot["manifest"]["baselineId"] == first
    output_paths.activate_deployment_candidate("alpha-local", second)
    with pytest.raises(ValueError, match="changed during operation"):
        output_paths.assert_active_deployment_candidate_snapshot(snapshot)


def test_active_candidate_rejects_resolved_candidate_directory_alias(
    tmp_path: Path,
    monkeypatch,
) -> None:
    deploy_root = tmp_path / "deploy-work"
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT", str(deploy_root))
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path / "output"))
    baseline_id = f"sha256:{'a' * 64}"
    candidate = output_paths.deployment_candidate_dir("alpha-local", baseline_id)
    (candidate / "packages").mkdir(parents=True)
    (candidate / "manifest.json").write_text("{}\n", encoding="utf-8")
    _install_full_candidate_loader(monkeypatch)
    pointer = output_paths.activate_deployment_candidate(
        "alpha-local",
        baseline_id,
    )
    payload = json.loads(pointer.read_text(encoding="utf-8"))
    payload["candidateDir"] = (
        f"{candidate.parent}/../runtime-full/{candidate.name}"
    )
    pointer.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="identity mismatch"):
        output_paths.active_deployment_candidate("alpha-local")


def test_candidate_activation_rejects_incomplete_and_symlinked_manifests(
    tmp_path: Path,
    monkeypatch,
) -> None:
    deploy_root = tmp_path / "deploy-work"
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT", str(deploy_root))
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path / "output"))
    baseline_id = f"sha256:{'a' * 64}"
    candidate = output_paths.deployment_candidate_dir("alpha-local", baseline_id)
    (candidate / "packages").mkdir(parents=True)
    manifest = candidate / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "candidateType": "runtime-full",
                "target": "alpha-local",
                "baselineId": baseline_id,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid full candidate"):
        output_paths.activate_deployment_candidate("alpha-local", baseline_id)
    assert not output_paths.active_candidate_manifest_path("alpha-local").exists()

    external = tmp_path / "external-candidate-manifest.json"
    external.write_text(manifest.read_text(encoding="utf-8"), encoding="utf-8")
    manifest.unlink()
    manifest.symlink_to(external)
    with pytest.raises(ValueError, match="invalid full candidate"):
        output_paths.activate_deployment_candidate("alpha-local", baseline_id)
    assert not output_paths.active_candidate_manifest_path("alpha-local").exists()


def test_active_candidate_rejects_pointer_and_parent_symlinks_without_overwrite(
    tmp_path: Path,
    monkeypatch,
) -> None:
    deploy_root = tmp_path / "deploy-work"
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT", str(deploy_root))
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path / "output"))
    baseline_id = f"sha256:{'a' * 64}"
    candidate = output_paths.deployment_candidate_dir("alpha-local", baseline_id)
    (candidate / "packages").mkdir(parents=True)
    (candidate / "manifest.json").write_text("{}\n", encoding="utf-8")
    _install_full_candidate_loader(monkeypatch)

    pointer = output_paths.active_candidate_manifest_path("alpha-local")
    external_pointer = tmp_path / "external-pointer.json"
    sentinel = '{"external":"must-survive"}\n'
    external_pointer.write_text(sentinel, encoding="utf-8")
    pointer.symlink_to(external_pointer)
    with pytest.raises(ValueError, match="symlink or non-regular"):
        output_paths.active_deployment_candidate("alpha-local")
    with pytest.raises(ValueError, match="symlink or non-regular"):
        output_paths.activate_deployment_candidate("alpha-local", baseline_id)
    assert external_pointer.read_text(encoding="utf-8") == sentinel

    pointer.unlink()
    target_root = deploy_root / "alpha-local"
    real_target_root = deploy_root / "real-alpha"
    target_root.rename(real_target_root)
    target_root.symlink_to(real_target_root, target_is_directory=True)
    with pytest.raises(ValueError, match="parent cannot be a symbolic link"):
        output_paths.active_deployment_candidate("alpha-local")
    with pytest.raises(ValueError, match="parent cannot be a symbolic link"):
        output_paths.activate_deployment_candidate("alpha-local", baseline_id)


def test_failed_candidate_validation_preserves_the_existing_pointer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from quwoquan_ops.cli.lib import deployment_candidate_manifest

    deploy_root = tmp_path / "deploy-work"
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT", str(deploy_root))
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path / "output"))
    active_baseline = f"sha256:{'a' * 64}"
    rejected_baseline = f"sha256:{'b' * 64}"
    for baseline_id in (active_baseline, rejected_baseline):
        candidate = output_paths.deployment_candidate_dir(
            "alpha-local",
            baseline_id,
        )
        (candidate / "packages").mkdir(parents=True)
        (candidate / "manifest.json").write_text("{}\n", encoding="utf-8")

    def selective_loader(
        _environment: str,
        target: str,
        baseline_id: str,
        *,
        require_full: bool,
    ) -> dict[str, str]:
        assert require_full is True
        if baseline_id == rejected_baseline:
            raise ValueError("incomplete candidate")
        return {
            "candidateType": "runtime-full",
            "target": target,
            "baselineId": baseline_id,
        }

    monkeypatch.setattr(
        deployment_candidate_manifest,
        "load_candidate_manifest",
        selective_loader,
    )
    pointer = output_paths.activate_deployment_candidate(
        "alpha-local",
        active_baseline,
    )
    before = pointer.read_bytes()

    with pytest.raises(ValueError, match="incomplete candidate"):
        output_paths.activate_deployment_candidate(
            "alpha-local",
            rejected_baseline,
        )

    assert pointer.read_bytes() == before


def test_failed_pointer_replace_preserves_existing_pointer_and_removes_temp(
    tmp_path: Path,
    monkeypatch,
) -> None:
    deploy_root = tmp_path / "deploy-work"
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT", str(deploy_root))
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path / "output"))
    active_baseline = f"sha256:{'a' * 64}"
    next_baseline = f"sha256:{'b' * 64}"
    for baseline_id in (active_baseline, next_baseline):
        candidate = output_paths.deployment_candidate_dir(
            "alpha-local",
            baseline_id,
        )
        (candidate / "packages").mkdir(parents=True)
        (candidate / "manifest.json").write_text("{}\n", encoding="utf-8")
    _install_full_candidate_loader(monkeypatch)
    pointer = output_paths.activate_deployment_candidate(
        "alpha-local",
        active_baseline,
    )
    before = pointer.read_bytes()

    def reject_replace(*_args: object, **_kwargs: object) -> None:
        raise OSError("injected atomic replace failure")

    monkeypatch.setattr(output_paths.os, "replace", reject_replace)
    with pytest.raises(OSError, match="injected atomic replace failure"):
        output_paths.activate_deployment_candidate(
            "alpha-local",
            next_baseline,
        )

    assert pointer.read_bytes() == before
    assert list(pointer.parent.glob(f".{pointer.name}.*.tmp")) == []


def test_concurrent_run_evidence_paths_never_share_a_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class FixedDatetime:
        @classmethod
        def now(cls, tz):
            assert tz == timezone.utc
            return datetime(2026, 7, 28, 20, 19, 19, tzinfo=timezone.utc)

    monkeypatch.setattr(output_paths, "datetime", FixedDatetime)
    env_paths = {
        output_paths.run_evidence_dir(tmp_path, "inspect", "alpha-local")
        for _ in range(128)
    }
    explicit_root_paths = {
        artifact_run_dir(
            "alpha",
            "inspect",
            target="alpha-local",
            output_root=tmp_path,
        )
        for _ in range(128)
    }

    assert len(env_paths) == 128
    assert len(explicit_root_paths) == 128
    assert env_paths.isdisjoint(explicit_root_paths)
    for path in env_paths | explicit_root_paths:
        assert "inspect-alpha-local" in path.name


def test_deployment_workspace_resolves_to_a_real_absolute_target_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    external = tmp_path / "external-workspace"
    external.mkdir()
    alias = tmp_path / "workspace-alias"
    alias.symlink_to(external, target_is_directory=True)
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT", str(alias))
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path / "output"))

    resolved = output_paths.deployment_work_root("gamma-local")

    assert resolved == (external / "gamma-local").resolve()
    assert resolved.is_absolute()
    assert output_paths.deployment_package_root("gamma") == (
        external / "gamma-local/packages"
    ).resolve()
    assert output_paths.certificate_export_dir("gamma-local") == (
        external / "gamma-local/certificates"
    ).resolve()


@pytest.mark.parametrize(
    "configured_root",
    (
        ".",
        str(ROOT / "deployment-work"),
        str(ROOT / ".qwq_output"),
    ),
)
def test_deployment_workspace_rejects_repository_and_output_roots(
    configured_root: str,
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(ROOT)
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path / "output"))
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT", configured_root)

    with pytest.raises(ValueError, match="QWQ_DEPLOY_WORK_ROOT"):
        output_paths.deployment_work_root("gamma-local")


def test_deployment_workspace_rejects_output_root_and_symbolic_link_escape(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = tmp_path / "output"
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output))
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT", str(output / "deployment"))
    with pytest.raises(ValueError, match="QWQ_OUTPUT_ROOT"):
        output_paths.deployment_work_root("gamma-local")

    link_to_repository = tmp_path / "link-to-repository"
    link_to_repository.symlink_to(ROOT, target_is_directory=True)
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT", str(link_to_repository))
    with pytest.raises(ValueError, match="source tree"):
        output_paths.deployment_work_root("gamma-local")

    external = tmp_path / "external"
    external.mkdir()
    (external / "gamma-local").symlink_to(ROOT, target_is_directory=True)
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT", str(external))
    with pytest.raises(ValueError, match="symbolic link"):
        output_paths.deployment_work_root("gamma-local")


def test_deployment_cleanup_and_output_parameters_fail_closed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    deploy_root = tmp_path / "deploy"
    monkeypatch.setenv("QWQ_DEPLOY_WORK_ROOT", str(deploy_root))
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path / "output"))

    with pytest.raises(ValueError, match="target root"):
        output_paths.remove_deployment_tree("gamma-local")

    target_root = output_paths.deployment_work_root("gamma-local")
    (target_root / "cleanup").parent.mkdir(parents=True)
    (target_root / "cleanup").symlink_to(ROOT, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic link"):
        output_paths.remove_deployment_tree("gamma-local", "cleanup")

    legal_root = output_paths.legal_static_deployment_package_dir("alpha")
    assert legal_static._resolve_package_root(
        "alpha",
        output_root=legal_root,
    ) == legal_root
    with pytest.raises(ValueError, match="target-scoped"):
        legal_static._resolve_package_root(
            "alpha",
            output_root=tmp_path / "outside",
        )

    render_root = output_paths.deployment_render_dir(
        "prod",
        target="prod-hosted",
        name="service-prod-r0",
    )
    assert render._resolve_render_output_dir(
        render_root,
        plane="service",
        instance="prod",
    ) == render_root
    with pytest.raises(SystemExit, match="resolver-derived"):
        render._resolve_render_output_dir(
            tmp_path / "outside-render",
            plane="service",
            instance="prod",
        )


def test_deploy_bash_entries_reuse_the_python_target_resolver() -> None:
    for entry, target in DEPLOY_BASH_ENTRIES.items():
        source = entry.read_text(encoding="utf-8")
        assert f'deployment_work_root("{target}")' in source
        assert f"QWQ_DEPLOY_WORK_ROOT/{target}" not in source
    prod_source = (
        ROOT / "quwoquan_ops/cli/prod/deploy_to_prod.sh"
    ).read_text(encoding="utf-8")
    assert "deployment_render_dir(" in prod_source
    alpha_source = (
        ROOT / "quwoquan_ops/cli/alpha/content_release_runtime.py"
    ).read_text(encoding="utf-8")
    beta_source = (
        ROOT / "quwoquan_ops/cli/beta/start_beta_stack.sh"
    ).read_text(encoding="utf-8")
    prod_sim_source = (
        ROOT / "quwoquan_ops/cli/prod_sim/start_prod_sim_stack.sh"
    ).read_text(encoding="utf-8")
    assert "deployment_target_path(" in alpha_source
    assert "certificate_paths(" in alpha_source
    assert "quwoquan_ops/cli/stackctl.py" in beta_source
    assert "--target beta-local" in beta_source
    assert "deployment_render_dir(" not in beta_source
    assert "deployment_render_dir(" in prod_sim_source
    assert "deployment_target_path(" in prod_sim_source


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


def test_stackctl_inspect_captures_configuration_without_deployment_writes(
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

    assert result["exitCode"] == 1
    assert result["details"] == [
        "candidate workspace: no active immutable candidate for gamma-local"
    ]
    assert not (report_dir / "config.json").exists()
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    assert report["findings"] == result["details"]
    assert report["inspection"]["config"]["candidateWorkspace"]["status"] == (
        "no_active_candidate"
    )
    assert not (deploy / "gamma-local/inspection").exists()
    assert output_layout_issues(output) == []
