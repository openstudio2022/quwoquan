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
import json
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
