"""Trigger-aware Delivery Data summary contract support."""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

DATA_TESTS_JOB = "quwoquan_data_tests"
DATA_TRIGGER_SCOPE = "${{ inputs.release_call || github.event_name != 'push' }}"


def run_summary(
    summary: dict, *, event_name: str, data_tests: str, repo_root: Path
) -> subprocess.CompletedProcess[str]:
    step = next(candidate for candidate in summary["steps"] if "DATA_TESTS" in candidate.get("env", {}))
    script = step["run"].replace("${{ needs.topology_regression.outputs.candidate_app }}", "true")
    fanout = "skipped" if event_name == "push" else "success"
    environment = {
        **os.environ,
        "COMMON_GOVERNANCE": "success", "CODE_HEALTH_DELTA": "success", "TOPOLOGY": "success",
        "SERVICE": "skipped", "SERVICE_PACKAGING": "skipped", "SERVICE_COVERAGE": "skipped",
        "SERVICE_COVERAGE_IMPACTED": "false", "SEARCH": fanout, "APP": fanout,
        "APP_STATIC": fanout, "APP_TESTS": fanout, "APP_SERIAL": "skipped", "APP_COVERAGE": "skipped",
        "DATA": fanout, "DATA_TESTS": data_tests, "SERVICE_IMPACTED": "false", "PORTAL": fanout,
        "RELEASE_EVIDENCE": "skipped", "PRODUCE_RELEASE_EVIDENCE": "false", "RELEASE_CALL": "false",
        "EVENT_NAME": event_name,
    }
    with tempfile.TemporaryDirectory() as directory:
        environment["GITHUB_OUTPUT"] = str(Path(directory) / "github-output")
        return subprocess.run(
            ["bash", "-c", script], cwd=repo_root, env=environment,
            capture_output=True, text=True, check=False,
        )


def assert_summary_contract(summary: dict, *, repo_root: Path) -> None:
    assert summary.get("if") == "always()"
    assert summary.get("continue-on-error") in (None, False)
    steps = [candidate for candidate in summary["steps"] if "DATA_TESTS" in candidate.get("env", {})]
    assert len(steps) == 1
    step = steps[0]
    assert step.get("if") == "always()"
    assert step.get("continue-on-error") in (None, False)
    assert step.get("shell") is None
    assert step["env"]["DATA_TESTS"] == "${{ needs.quwoquan_data_tests.result }}"
    assert type(step.get("run")) is str
    assert 'if [[ "$RELEASE_CALL" != "true" && "$EVENT_NAME" == "push" ]]' in step["run"]
    assert step["run"].count(
        'expect_success "quwoquan_data_tests" "${DATA_TESTS}" '
        '"PR/release Delivery 必须执行 Data tests"'
    ) == 1
    admitted = run_summary(summary, event_name="pull_request", data_tests="success", repo_root=repo_root)
    assert admitted.returncode == 0, admitted.stdout + admitted.stderr
    red = run_summary(summary, event_name="pull_request", data_tests="failure", repo_root=repo_root)
    assert red.returncode == 1
    assert "quwoquan_data_tests expected success, got failure" in red.stdout
    stopped = run_summary(summary, event_name="push", data_tests="skipped", repo_root=repo_root)
    assert stopped.returncode == 0, stopped.stdout + stopped.stderr


def assert_data_jobs_trigger_scoped(workflow: dict) -> None:
    for job_name in ("quwoquan_data", DATA_TESTS_JOB):
        job = workflow["jobs"][job_name]
        assert job.get("if") == DATA_TRIGGER_SCOPE, (
            f"{job_name} 必须只在 PR/release Delivery 调用执行，dev1.0 push 保持 trigger-stop"
        )
        assert job.get("continue-on-error") in (None, False)
