from __future__ import annotations

from pathlib import Path


RUNNER_ROOT = Path(__file__).resolve().parents[3] / "scripts/content/execution/runner"


def test_host_only_runners_are_process_receipt_status_only() -> None:
    loop = (RUNNER_ROOT / "loop_driver.sh").read_text(encoding="utf-8")
    fleet = (RUNNER_ROOT / "fleet_dispatcher.sh").read_text(encoding="utf-8")
    combined = loop + fleet
    for forbidden in (
        "content.execution.agent", "content.execution.queue", "content.execution.controller",
        "content.execution.recovery", "content.execution.campaign", "cursor_sdk", "codex_sdk",
        "ReliableTask", "reliabletask", "pool-dispatch", "capacity-bootstrap",
        "calibrate-capacity", "prepare-campaign", "task execute",
    ):
        assert forbidden not in combined
    assert "task lane-claim" in loop
    assert "task fleet-status" in loop
    assert "task stage-record" not in combined


def test_host_only_runners_never_automatically_retry_a_failed_host_session() -> None:
    loop = (RUNNER_ROOT / "loop_driver.sh").read_text(encoding="utf-8")
    fleet = (RUNNER_ROOT / "fleet_dispatcher.sh").read_text(encoding="utf-8")
    assert "stopping without automatic retry" in loop
    assert "infra_retries" not in fleet
    assert "attempt=" not in fleet
    assert "2 **" not in fleet
