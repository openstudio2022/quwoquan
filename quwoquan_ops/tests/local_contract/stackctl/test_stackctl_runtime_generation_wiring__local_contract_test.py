# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/multi-environment-instance-isolation/spec.md#gwt-003
from __future__ import annotations

import argparse
import contextlib
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.commands import down_domain, up_domain


def test_down_rejects_stale_generation_before_cleanup() -> None:
    args = argparse.Namespace(target="beta-local", expected_generation="old", workload="", command="down", report_dir="")
    with (
        mock.patch.object(stackctl, "_bounded_workload_down_decision", return_value=None),
        mock.patch.object(stackctl, "_local_stack_operation_lock", return_value=contextlib.nullcontext()),
        mock.patch.object(stackctl, "load_startup_attempt", return_value={"attemptId": "new", "status": "running"}),
        mock.patch.object(stackctl, "load_test_live_startup_attempt", return_value=None),
        mock.patch.object(stackctl, "_command_down_unlocked") as cleanup,
        mock.patch.object(stackctl, "write_json"),
        mock.patch.object(stackctl, "_write_summary_bundle"),
    ):
        result = down_domain.command_down(args)
    assert result["exitCode"] == 2
    assert any("generation_conflict" in item for item in result["details"])
    cleanup.assert_not_called()


def test_up_wrapper_reports_created_generation_and_reuse() -> None:
    args = argparse.Namespace(target="beta-local", env="", workload="full")
    new = {"attemptId": "generation-1", "status": "running", "workload": "full"}
    with (
        mock.patch.object(stackctl, "_local_stack_operation_lock", return_value=contextlib.nullcontext()) as lock,
        mock.patch.object(stackctl, "load_startup_attempt", side_effect=[None, new]),
        mock.patch.object(stackctl, "load_test_live_startup_attempt", return_value=None),
        mock.patch.object(stackctl, "_command_up_impl", return_value={"exitCode": 0}),
    ):
        result = up_domain.command_up(args)
    assert result["runtimeCreated"] is True
    assert result["instanceGeneration"] == "generation-1"
    lock.assert_called_once_with("beta-local", wait_seconds=30)
    with (
        mock.patch.object(stackctl, "_local_stack_operation_lock", return_value=contextlib.nullcontext()),
        mock.patch.object(stackctl, "load_startup_attempt", return_value=new),
        mock.patch.object(stackctl, "load_test_live_startup_attempt", return_value=None),
        mock.patch.object(stackctl, "_command_up_impl", return_value={"exitCode": 0, "runtimeReused": True}),
    ):
        result = up_domain.command_up(args)
    assert result["runtimeCreated"] is False
    assert result["runtimeReused"] is True


def test_prod_sim_holds_lock_and_invokes_generation_executors() -> None:
    up_args = argparse.Namespace(target="prod-sim", env="", workload="full")
    down_args = argparse.Namespace(
        target="prod-sim",
        expected_generation="",
        workload="",
        command="down",
        report_dir="",
    )
    created = {"attemptId": "generation-sim", "status": "running", "workload": "full"}
    with (
        mock.patch.object(stackctl, "_local_stack_operation_lock", return_value=contextlib.nullcontext()) as lock,
        mock.patch.object(stackctl, "load_environment_topology", return_value={"targets": {}}),
        mock.patch.object(stackctl, "assert_local_runtime_available"),
        mock.patch.object(stackctl, "load_startup_attempt", side_effect=[None, created]),
        mock.patch.object(stackctl, "load_test_live_startup_attempt", return_value=None),
        mock.patch.object(stackctl, "_command_up_impl", return_value={"exitCode": 0}) as start,
    ):
        up = up_domain.command_up(up_args)
    assert up["exitCode"] == 0
    assert up["runtimeCreated"] is True
    assert up["instanceGeneration"] == "generation-sim"
    assert "unmanaged_runtime_authority" not in up
    lock.assert_called_once_with("prod-sim", wait_seconds=30)
    start.assert_called_once()

    with (
        mock.patch.object(stackctl, "_bounded_workload_down_decision", return_value=None),
        mock.patch.object(stackctl, "_local_stack_operation_lock", return_value=contextlib.nullcontext()) as down_lock,
        mock.patch.object(stackctl, "load_startup_attempt", return_value=created),
        mock.patch.object(stackctl, "load_test_live_startup_attempt", return_value=None),
        mock.patch.object(stackctl, "active_consumer_leases", return_value=[]),
        mock.patch.object(stackctl, "_command_down_unlocked", return_value={"exitCode": 0}) as stop,
        mock.patch.object(stackctl, "write_json"),
        mock.patch.object(stackctl, "_write_summary_bundle"),
    ):
        down = down_domain.command_down(down_args)
    assert down["exitCode"] == 0
    assert "unmanaged_runtime_authority" not in down
    down_lock.assert_called_once_with("prod-sim")
    stop.assert_called_once()


def test_prod_sim_rejects_foreign_identity() -> None:
    args = argparse.Namespace(
        target="prod-sim",
        expected_generation="old",
        workload="",
        command="down",
        report_dir="",
    )
    with (
        mock.patch.object(stackctl, "_bounded_workload_down_decision", return_value=None),
        mock.patch.object(stackctl, "_local_stack_operation_lock", return_value=contextlib.nullcontext()) as lock,
        mock.patch.object(stackctl, "load_startup_attempt", return_value={"attemptId": "new", "status": "running"}),
        mock.patch.object(stackctl, "load_test_live_startup_attempt", return_value=None),
        mock.patch.object(stackctl, "_command_down_unlocked") as cleanup,
        mock.patch.object(stackctl, "write_json"),
        mock.patch.object(stackctl, "_write_summary_bundle"),
    ):
        result = down_domain.command_down(args)
    assert result["exitCode"] == 2
    assert result["blockerKind"] == "runtime_generation_conflict"
    assert any("generation_conflict" in item for item in result["details"])
    lock.assert_called_once_with("prod-sim")
    cleanup.assert_not_called()
