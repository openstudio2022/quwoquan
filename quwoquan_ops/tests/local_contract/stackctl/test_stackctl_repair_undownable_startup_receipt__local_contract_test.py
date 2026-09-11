"""The legacy undownable repair delegates to attested orphan recovery.

The formal startup receipt does not own a published endpoint inventory. Exact
runtime ownership therefore comes only from the existing orphan Compose
attestation protocol, which samples Docker PortBindings, preserves named
volumes, and requires an exact create-once attestation for confirmation.

spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-005
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib import orphan_compose_teardown as contract
from quwoquan_ops.tests.support.orphan_compose_teardown_test_support import (
    PROJECT,
    multi_sample,
    ports,
    post_sample,
)


def _args(*, confirm: bool, target: str = "alpha-local") -> argparse.Namespace:
    return argparse.Namespace(
        target=target,
        fix="reclaim-undownable-startup-receipt",
        confirm_undownable_startup_receipt_reclaim=confirm,
        orphaned_compose_attestation="",
    )


def test_audit_delegates_to_orphan_planning_with_a_canonical_output_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed: list[tuple[argparse.Namespace, str, Path]] = []

    def delegated(
        args: argparse.Namespace,
        *,
        environment: str,
        report_dir: Path,
    ) -> dict[str, object]:
        observed.append((args, environment, report_dir))
        return {"exitCode": 0, "details": []}

    monkeypatch.setattr(stackctl, "_repair_orphaned_compose", delegated)

    result = stackctl._repair_undownable_startup_receipt(
        _args(confirm=False),
        environment="alpha",
        report_dir=tmp_path,
    )

    assert result["exitCode"] == 0
    delegated_args, environment, report_dir = observed[0]
    assert environment == "alpha"
    assert report_dir == tmp_path
    assert delegated_args.fix == "reclaim-undownable-startup-receipt"
    assert delegated_args.confirm_orphaned_compose_teardown is False
    assert delegated_args.orphaned_compose_attestation == str(
        tmp_path / "orphaned-compose-teardown-attestation.json"
    )


def test_parser_command_auto_report_dir_exists_before_real_attestation_plan(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The default CLI run directory must exist before path safety is checked."""

    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    report_dir = runs_root / "fresh-repair-run"
    args = stackctl.build_parser().parse_args(
        [
            "repair",
            "--target",
            "alpha-local",
            "--fix",
            "reclaim-undownable-startup-receipt",
        ]
    )
    assert args.report_dir == ""

    monkeypatch.setattr(
        stackctl,
        "artifact_run_dir",
        lambda *_args, **_kwargs: report_dir,
    )
    monkeypatch.setattr(stackctl, "env_runs_root", lambda _env: runs_root)
    monkeypatch.setattr(stackctl, "relpath", lambda path: str(path))
    monkeypatch.setattr(
        stackctl,
        "_local_stack_operation_lock",
        lambda _target: contextlib.nullcontext(),
    )
    monkeypatch.setattr(stackctl, "active_consumer_leases", lambda _target: [])
    monkeypatch.setattr(
        stackctl,
        "load_startup_attempt",
        lambda _target: {
            "env": "alpha",
            "target": "alpha-local",
            "status": "running",
            "attemptId": "attempt-undownable",
            "composeProject": PROJECT,
            "candidateDigest": "sha256:" + "a" * 64,
        },
    )
    monkeypatch.setattr(
        stackctl,
        "_normal_down_structurally_impossible",
        lambda _target, _startup: "candidate is no longer present",
    )
    monkeypatch.setattr(
        stackctl,
        "_canonical_port_occupancy_report",
        lambda _target: {"profile": "alpha-local", "ports": ports(opened=False)},
    )
    monkeypatch.setattr(
        stackctl,
        "_other_local_target_port_blocks",
        lambda _target: [
            {"target": "beta-local", "blockStart": 18000, "blockEnd": 18999},
            {"target": "gamma-local", "blockStart": 19000, "blockEnd": 19999},
        ],
    )
    empty_snapshot = post_sample(multi_sample())
    monkeypatch.setattr(
        contract,
        "sample_snapshot",
        lambda **_kwargs: empty_snapshot,
    )
    monkeypatch.setattr(
        stackctl,
        "_write_summary_bundle",
        lambda *_args, **_kwargs: None,
    )

    result = stackctl.command_repair(args)

    assert result["exitCode"] == 0
    assert report_dir.is_dir()
    attestation_path = report_dir / "orphaned-compose-teardown-attestation.json"
    attestation = contract.load_attestation(
        attestation_path,
        allowed_root=runs_root,
        expected_target="alpha-local",
    )
    assert attestation["project"] == PROJECT
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "planned"


def test_confirmation_delegates_only_with_the_exact_planned_attestation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed: list[argparse.Namespace] = []
    attestation = tmp_path / "prior" / "orphaned-compose-teardown-attestation.json"
    args = _args(confirm=True)
    args.orphaned_compose_attestation = str(attestation)
    monkeypatch.setattr(
        stackctl,
        "_repair_orphaned_compose",
        lambda delegated, **_kwargs: observed.append(delegated)
        or {"exitCode": 0, "details": []},
    )

    result = stackctl._repair_undownable_startup_receipt(
        args,
        environment="alpha",
        report_dir=tmp_path,
    )

    assert result["exitCode"] == 0
    assert len(observed) == 1
    assert observed[0].orphaned_compose_attestation == str(attestation)
    assert observed[0].confirm_orphaned_compose_teardown is True


def test_confirmation_without_the_planned_attestation_fails_before_delegation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    delegated: list[object] = []
    monkeypatch.setattr(
        stackctl,
        "_repair_orphaned_compose",
        lambda *_args, **_kwargs: delegated.append(object()),
    )

    result = stackctl._repair_undownable_startup_receipt(
        _args(confirm=True),
        environment="alpha",
        report_dir=tmp_path,
    )

    assert result["exitCode"] == 2
    assert delegated == []
    assert any("--orphaned-compose-attestation" in item for item in result["details"])
    assert any("planning run" in item for item in result["details"])


def test_production_targets_remain_outside_local_orphan_recovery(
    tmp_path: Path,
) -> None:
    result = stackctl._repair_undownable_startup_receipt(
        _args(confirm=True, target="prod-hosted"),
        environment="prod",
        report_dir=tmp_path,
    )

    assert result["exitCode"] == 2
    assert any("only available for" in item for item in result["details"])


# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-001
@pytest.fixture
def legacy_reconciliation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from quwoquan_ops.cli.commands import repair_undownable_startup_receipt as repair
    from quwoquan_ops.cli.lib import output_paths
    from quwoquan_ops.tests.support.startup_attempt_receipt_test_support import _composition

    root = tmp_path.resolve() / "repo"
    root.mkdir()
    monkeypatch.delenv("QWQ_OUTPUT_ROOT", raising=False)
    monkeypatch.setattr(output_paths, "ROOT", root)
    monkeypatch.setattr(output_paths, "DEFAULT_OUTPUT_ROOT", root / ".qwq_output")
    monkeypatch.setattr(output_paths, "DEFAULT_LOCAL_RUNTIME_OUTPUT_ROOT", tmp_path.resolve() / "host")
    monkeypatch.setattr(output_paths, "DEFAULT_DEPLOY_WORK_ROOT", tmp_path.resolve() / "deploy")
    monkeypatch.setattr(repair, "local_runtime_operation_lock_path", lambda target="": tmp_path.resolve() / "locks" / f"{target or 'host'}.lock")
    monkeypatch.setattr(repair, "list_consumer_leases", lambda _target: [])
    monkeypatch.setattr(stackctl, "_local_stack_operation_lock", lambda _target: contextlib.nullcontext())
    monkeypatch.setattr(stackctl, "_write_summary_bundle", lambda *a, **k: None)
    monkeypatch.setattr(stackctl, "relpath", str)
    calls = []

    def docker_readback(argv, **kwargs):
        calls.append(argv)
        assert argv[0] == "docker"
        assert argv[1:3] in (["ps", "-aq"], ["network", "ls"], ["volume", "ls"])
        return subprocess.CompletedProcess(argv, 0, "kept-volume\n" if argv[1] == "volume" else "", "")

    monkeypatch.setattr(stackctl, "run", docker_readback)
    monkeypatch.setattr(stackctl, "_published_endpoint_is_occupied", lambda endpoint: False)
    paths = output_paths.archived_worktree_startup_paths("alpha-local")
    run_id = "legacy-full-alpha-attempt"
    env_root = root / ".qwq_output/env/alpha"
    run_root = env_root / "runs" / run_id
    obs_root = env_root / "observability" / run_id
    run_root.mkdir(parents=True)
    obs_root.mkdir(parents=True)
    composition = _composition()
    startup = {
        "schema": "stackctl-local-startup-attempt", "attemptId": run_id,
        "env": "alpha", "target": "alpha-local", "status": "stopped", "workload": "full",
        "composeProject": PROJECT, "candidateDigest": "sha256:" + "a" * 64,
        "configurationDigest": composition["configurationDigest"],
        "providerRuntimeDigest": "sha256:" + "b" * 64,
        "observabilityLogSinkDigest": "sha256:" + "c" * 64,
        "imageTransportTag": composition["imageVersion"], "imageComposition": composition,
        "runRoot": str(run_root), "startedAt": "2026-09-08T00:00:00Z",
        "updatedAt": "2026-09-08T01:00:00Z", "failure": None, "cleanupFailure": None,
    }
    local_run = {"env": "alpha", "target": "alpha-local", "runId": run_id,
                 "runRoot": str(run_root), "observabilityRoot": str(obs_root)}
    for path, payload in zip(paths, (startup, startup, local_run), strict=True):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    report = output_paths.env_runs_root("alpha") / "receipt-reconciliation-test"
    report.mkdir(parents=True)
    args = _args(confirm=False)
    args.worktree_startup_reconciliation = "plan"
    args.worktree_startup_plan_ref = ""
    return repair, output_paths, args, report, paths, calls


def _legacy_result(fixture):
    repair, _, args, report, _, _ = fixture
    return repair.repair_undownable_startup_receipt(args, environment="alpha", report_dir=report)


def _legacy_apply(fixture):
    result = _legacy_result(fixture)
    assert result["exitCode"] == 0, result
    fixture[2].worktree_startup_reconciliation = "apply"
    fixture[2].worktree_startup_plan_ref = result["planRef"]
    fixture[2].confirm_undownable_startup_receipt_reclaim = True
    return result


def test_legacy_plan_reads_exact_bytes_without_weakening_guard(legacy_reconciliation):
    repair, output_paths, _, _, paths, calls = legacy_reconciliation
    before = [path.read_bytes() for path in paths]
    result = _legacy_result(legacy_reconciliation)
    assert result["exitCode"] == 0, result
    assert result["status"] == "planned"
    assert [path.read_bytes() for path in paths] == before
    with pytest.raises(ValueError, match="OPS.RUNTIME.reconcile_required"):
        output_paths.target_process_dir("alpha-local")
    path, digest = result["planRef"].rsplit("=", 1)
    assert digest == "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()
    plan = json.loads(Path(path).read_text())
    assert {a["source"] for a in plan["actions"]} == {str(p) for p in paths}
    assert plan["actions"][-1]["source"] == str(paths[0])
    assert all(a["digest"] == repair._digest(Path(a["source"]).read_bytes()) for a in plan["actions"])
    assert plan["readback"]["preservedVolumes"] == ["kept-volume"]
    assert all(not Path(a["destination"]).exists() for a in plan["actions"])
    assert len(calls) == 3


def test_legacy_confirmed_apply_moves_original_inodes_and_preserves_bytes(legacy_reconciliation):
    _, output_paths, _, _, paths, _ = legacy_reconciliation
    original = {str(path): (path.stat().st_ino, path.read_bytes()) for path in paths}
    planned = _legacy_apply(legacy_reconciliation)
    plan = json.loads(Path(planned["planRef"].rsplit("=", 1)[0]).read_text())
    result = _legacy_result(legacy_reconciliation)
    assert result["exitCode"] == 0, result
    assert result["status"] == "applied"
    for item in plan["actions"]:
        destination = Path(item["destination"])
        assert (destination.stat().st_ino, destination.read_bytes()) == original[item["source"]]
        assert not Path(item["source"]).exists()
    assert output_paths.target_process_dir("alpha-local").is_relative_to(output_paths.DEFAULT_LOCAL_RUNTIME_OUTPUT_ROOT)
    assert _legacy_result(legacy_reconciliation)["exitCode"] == 2


@pytest.mark.parametrize("resource", ["containers", "networks", "ports", "unknown", "lease", "fence", "slot"])
def test_legacy_active_and_unknown_readbacks_refuse_before_plan(legacy_reconciliation, monkeypatch, resource):
    repair, output_paths, _, report, paths, _ = legacy_reconciliation
    if resource == "containers":
        monkeypatch.setattr(stackctl, "_mutable_test_live_container_ids", lambda p: ["active-container"])
    elif resource == "networks":
        monkeypatch.setattr(stackctl, "_mutable_test_live_resource_names", lambda r, **k: ["remaining-network"])
    elif resource == "ports":
        monkeypatch.setattr(stackctl, "_published_endpoint_is_occupied", lambda p: True)
    elif resource == "unknown":
        monkeypatch.setattr(stackctl, "run", lambda argv, **k: subprocess.CompletedProcess(argv, 1, "", "daemon unavailable"))
    elif resource == "lease":
        monkeypatch.setattr(repair, "list_consumer_leases", lambda t: [{"target": t, "state": "stale"}])
    else:
        exclusion = (repair.local_runtime_operation_lock_path("alpha-local").with_suffix(".executor.json")
                     if resource == "fence" else output_paths.deployment_target_path("alpha-local", "process", "environment-execution", "execution-slot.json"))
        exclusion.parent.mkdir(parents=True)
        exclusion.write_text("{}")
    before = [p.read_bytes() for p in paths]
    result = _legacy_result(legacy_reconciliation)
    assert result["exitCode"] == 2, result
    assert [p.read_bytes() for p in paths] == before
    assert not (report / "worktree-startup-reconciliation-plan.json").exists()


@pytest.mark.parametrize("drift", ["source", "copies", "status", "binding", "plan", "destination", "live"])
def test_legacy_changed_input_or_resource_refuses_apply(legacy_reconciliation, monkeypatch, drift):
    _, _, _, report, paths, _ = legacy_reconciliation
    planned = _legacy_apply(legacy_reconciliation)
    plan_path = Path(planned["planRef"].rsplit("=", 1)[0])
    if drift in {"source", "copies"}:
        paths[0].write_bytes(paths[0].read_bytes() + b" ")
        if drift == "source":
            paths[1].write_bytes(paths[0].read_bytes())
    elif drift == "status":
        for path in paths[:2]:
            data = json.loads(path.read_text())
            data["status"] = "running"
            path.write_text(json.dumps(data))
    elif drift == "binding":
        paths[2].write_text("{}")
    elif drift == "plan":
        plan_path.write_bytes(plan_path.read_bytes() + b" ")
    elif drift == "destination":
        (report / "archive").mkdir()
    else:
        monkeypatch.setattr(stackctl, "_mutable_test_live_container_ids", lambda p: ["late-container"])
    before = [p.read_bytes() for p in paths]
    result = _legacy_result(legacy_reconciliation)
    assert result["exitCode"] == 2, result
    assert [p.read_bytes() for p in paths] == before
    assert not list((report / "archive").glob("*.json"))


@pytest.mark.parametrize("surface", ["source", "source-parent", "plan", "destination", "run-root"])
def test_legacy_symlink_refuses_without_moving_any_original(legacy_reconciliation, surface):
    _, _, _, report, paths, _ = legacy_reconciliation
    planned = _legacy_apply(legacy_reconciliation)
    if surface == "source":
        link = paths[1]
    elif surface == "source-parent":
        link = paths[1].parent
    elif surface == "plan":
        link = Path(planned["planRef"].rsplit("=", 1)[0])
    elif surface == "run-root":
        link = Path(json.loads(paths[0].read_text())["runRoot"])
    else:
        external = report.parent / "outside"
        external.mkdir()
        (report / "archive").symlink_to(external, target_is_directory=True)
        link = None
    if link is not None:
        original = link.with_name(link.name + "-original")
        link.rename(original)
        link.symlink_to(original, target_is_directory=original.is_dir())
    result = _legacy_result(legacy_reconciliation)
    assert result["exitCode"] == 2, result
    assert all(p.exists() for p in paths)
    assert not list((report / "archive").glob("*.json"))


@pytest.mark.parametrize("missing", ["confirm", "plan-ref"])
def test_legacy_apply_requires_exact_plan_and_explicit_confirmation(legacy_reconciliation, missing):
    _legacy_apply(legacy_reconciliation)
    args = legacy_reconciliation[2]
    if missing == "confirm":
        args.confirm_undownable_startup_receipt_reclaim = False
    else:
        args.worktree_startup_plan_ref = ""
    result = _legacy_result(legacy_reconciliation)
    assert result["exitCode"] == 2
    assert all(path.exists() for path in legacy_reconciliation[4])


def test_legacy_partial_move_preserves_originals_and_keeps_primary_guard(legacy_reconciliation, monkeypatch):
    repair, output_paths, _, report, paths, _ = legacy_reconciliation
    _legacy_apply(legacy_reconciliation)
    original_rename = repair.os.rename
    count = 0

    def fail_second_move(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("injected archive failure")
        return original_rename(*args, **kwargs)

    monkeypatch.setattr(repair.os, "rename", fail_second_move)
    expected = paths[1].read_bytes()
    result = _legacy_result(legacy_reconciliation)
    assert result["exitCode"] == 2
    assert (report / "archive/full-startup_attempt.json").read_bytes() == expected
    assert paths[0].exists() and paths[2].exists()
    with pytest.raises(ValueError, match="reconcile_required"):
        output_paths.target_process_dir("alpha-local")
    assert _legacy_result(legacy_reconciliation)["exitCode"] == 2


def test_legacy_readback_drift_before_plan_preserves_all_sources(legacy_reconciliation, monkeypatch):
    _, _, _, report, paths, _ = legacy_reconciliation

    def drift_during_probe(project):
        for path in paths[:2]:
            path.write_bytes(path.read_bytes() + b" ")
        return []

    monkeypatch.setattr(stackctl, "_mutable_test_live_container_ids", drift_during_probe)
    result = _legacy_result(legacy_reconciliation)
    assert result["exitCode"] == 2
    assert "changed during" in result["details"][0]
    assert all(path.exists() for path in paths)
    assert not (report / "worktree-startup-reconciliation-plan.json").exists()


def test_legacy_reconciliation_cli_is_explicit_and_alpha_only(legacy_reconciliation):
    args = stackctl.build_parser().parse_args([
        "repair", "--target", "alpha-local", "--fix", "reclaim-undownable-startup-receipt",
        "--worktree-startup-reconciliation", "plan",
    ])
    assert args.worktree_startup_reconciliation == "plan"
    legacy_reconciliation[2].target = "beta-local"
    result = _legacy_result(legacy_reconciliation)
    assert result["exitCode"] == 2
    assert "alpha-local" in result["details"][0]
