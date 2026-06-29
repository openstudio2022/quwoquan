from __future__ import annotations

import argparse
from pathlib import Path

from task import scaled_e2e


def _args(**overrides):
    data = {
        "task": "旅行/地域/四川省/景区/fixture",
        "batch": "batch_1",
        "plan": "plan_1",
        "catalog": None,
        "strategy": "by-batch",
        "concurrency": 2,
        "max_workers": 2,
        "runtime": "local",
        "model": "composer-2.5",
        "cwd": "/tmp/workspace",
        "spend_limit": None,
        "cycles": 2,
        "reset_state": False,
        "skip_prepare": False,
        "skip_startup_probe": False,
    }
    data.update(overrides)
    return argparse.Namespace(**data)


def test_scaled_e2e_run_sequences_prepare_author_finalize_verify():
    calls: list[str] = []

    def invoke(ns):
        calls.append(ns.scaled_e2e_command)

    scaled_e2e._handle_scaled_e2e_run(_args(cycles=1), invoke=invoke)

    assert calls == [
        "prepare",
        "fanout-author",
        "author-runner",
        "rollup",
        "finalize",
        "rollup",
        "verify",
    ]


def test_scaled_e2e_run_retries_after_verify_failure():
    calls: list[str] = []
    verify_count = 0

    def invoke(ns):
        nonlocal verify_count
        calls.append(ns.scaled_e2e_command)
        if ns.scaled_e2e_command == "verify":
            verify_count += 1
            if verify_count == 1:
                raise SystemExit(1)

    scaled_e2e._handle_scaled_e2e_run(_args(skip_prepare=True, cycles=2), invoke=invoke)

    assert calls.count("fanout-author") == 1
    assert calls.count("author-runner") == 2
    assert calls.count("finalize") == 2
    assert calls.count("verify") == 2


def test_cs100_author_resume_loop_does_not_mutate_workflow_state_json():
    repo_root = Path(__file__).resolve().parents[4]
    script = repo_root / "agent_ops" / "runners" / "cs100_author_resume_loop.sh"
    text = script.read_text(encoding="utf-8")

    assert "controllerYield" not in text
    assert "activeAgentScheduler" not in text
    assert "p.write_text" not in text
    assert "controller_lease.json" not in text
