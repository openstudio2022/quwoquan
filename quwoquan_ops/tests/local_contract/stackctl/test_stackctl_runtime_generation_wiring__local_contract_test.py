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


def test_prod_sim_legacy_is_typed_blocked_without_executor() -> None:
    with mock.patch.object(stackctl, "_command_up_impl") as start, mock.patch.object(stackctl, "_command_down_unlocked") as stop:
        up = up_domain.command_up(argparse.Namespace(target="prod-sim", env=""))
        down = down_domain.command_down(argparse.Namespace(target="prod-sim"))
    assert up["blockerKind"] == down["blockerKind"] == "unmanaged_runtime_authority"
    start.assert_not_called()
    stop.assert_not_called()
