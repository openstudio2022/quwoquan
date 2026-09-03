import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "quwoquan_ops" / "ci" / "render_ci_timing_summary.py"
CANONICAL_TOP_LEVEL_KEYS = {
    "schema",
    "generatedAt",
    "workflow",
    "workflowRunId",
    "sourceGitSha",
    "candidateDigest",
    "status",
    "outcomePolicy",
    "timestamps",
    "durations",
    "budget",
    "criticalPath",
    "phases",
    "missingEvidence",
    "notes",
}


def write_budget(tmp_path: Path) -> Path:
    path = tmp_path / "budgets.json"
    path.write_text(
        json.dumps(
            {
                "gates": {
                    "test_gate": {
                        "budgetSeconds": 600,
                        "hardFailSeconds": 1800,
                        "timingPolicy": "release_sla",
                        "profileTiming": {
                            "pr_light": {
                                "policy": "telemetry_advisory",
                                "hardFailSeconds": 5400,
                            },
                            "mainline_auto_prod": {
                                "policy": "release_sla",
                                "hardFailSeconds": 7800,
                            },
                        },
                        "criticalPath": "candidate + environments + prod",
                        "phaseBudgetsSeconds": {"candidate": 120},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def complete_args(end_to_end_seconds: int, *, machine_seconds: int = 500) -> list[str]:
    return [
        "--workflow",
        "Four Environment Release",
        "--workflow-run-id",
        "12345",
        "--source-git-sha",
        "a" * 40,
        "--candidate-digest",
        "sha256:" + "b" * 64,
        "--machine-critical-path-seconds",
        str(machine_seconds),
        "--critical-path-source",
        "github_run_calendar",
        "--run-created-at",
        "2026-07-28T01:00:00Z",
        "--candidate-ready-at",
        "2026-07-28T01:02:00Z",
        "--approval-requested-at",
        "2026-07-28T01:03:00Z",
        "--approval-approved-at",
        "2026-07-28T01:04:00Z",
        "--prod-fully-verified-at",
        "2026-07-28T01:10:00Z",
        "--queue-seconds",
        "10",
        "--setup-seconds",
        "20",
        "--execution-seconds",
        "500",
        "--human-decision-wait-seconds",
        "30",
        "--approval-wait-seconds",
        "30",
        "--calendar-lead-time-seconds",
        str(end_to_end_seconds),
        "--phase",
        "candidate=120",
    ]


def run_renderer(
    tmp_path: Path,
    end_to_end_seconds: int,
    *,
    complete: bool,
    budget_profile: str = "",
) -> Dict[str, Any]:
    output_path = tmp_path / "summary.json"
    command = [
        sys.executable,
        str(SCRIPT),
        "--gate-key",
        "test_gate",
        "--title",
        "Test Gate",
        "--budget-file",
        str(write_budget(tmp_path)),
    ]
    if complete:
        command.extend(complete_args(end_to_end_seconds))
    else:
        command.extend(
            [
                "--machine-critical-path-seconds",
                str(end_to_end_seconds),
                "--phase",
                "candidate=0",
            ]
        )
    if budget_profile:
        command.extend(["--budget-profile", budget_profile])
    command.extend(["--write-json", str(output_path)])
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={
            key: value
            for key, value in os.environ.items()
            if key
            not in {
                "GITHUB_WORKFLOW",
                "GITHUB_RUN_ID",
                "GITHUB_SHA",
                "QWQ_CANDIDATE_DIGEST",
                "QWQ_CI_CRITICAL_PATH_SOURCE",
            }
        },
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(output_path.read_text(encoding="utf-8"))


def nested_keys(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from nested_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from nested_keys(nested)


def test_cli_emits_only_the_canonical_unversioned_shape(tmp_path: Path) -> None:
    payload = run_renderer(tmp_path, 600, complete=True)

    assert set(payload) == CANONICAL_TOP_LEVEL_KEYS
    assert payload["schema"] == "ci-timing-summary"
    assert payload["status"] == "within_budget"
    assert payload["outcomePolicy"] == {
        "functional": "unknown",
        "telemetryClassification": "attempted",
        "timing": "PASS",
    }
    assert payload["missingEvidence"] == []
    assert payload["budget"] == {
        "policy": "release_sla",
        "softSeconds": 600,
        "hardSeconds": 1800,
        "deltaFromSoftSeconds": 0,
        "deltaFromHardSeconds": -1200,
        "phaseSeconds": {"candidate": 120},
    }
    assert payload["durations"]["machineCriticalPathSeconds"] == 500
    assert payload["durations"]["calendarLeadTimeSeconds"] == 600
    assert payload["criticalPath"]["source"] == "github_run_calendar"
    assert payload["criticalPath"]["seconds"] == 600

    forbidden_keys = {
        "".join(("schema", "Version")),
        "".join(("contract", "Version")),
        "".join(("registry", "Revision")),
        "".join(("ver", "sions")),
    }
    assert forbidden_keys.isdisjoint(set(nested_keys(payload)))


def test_missing_historical_evidence_is_not_filled_with_zero(tmp_path: Path) -> None:
    payload = run_renderer(tmp_path, 0, complete=False)

    assert payload["status"] == "historical_incomplete"
    assert payload["workflowRunId"] is None
    assert payload["timestamps"]["runCreatedAt"] is None
    assert payload["durations"]["queueSeconds"] is None
    assert payload["durations"]["setupSeconds"] is None
    assert payload["durations"]["executionSeconds"] is None
    assert "durations.queueSeconds" in payload["missingEvidence"]
    assert "timestamps.runCreatedAt" in payload["missingEvidence"]
    assert "criticalPath.githubRunCalendar" in payload["missingEvidence"]


def test_missing_machine_critical_path_is_null_and_explicitly_missing(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "summary.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--gate-key",
            "test_gate",
            "--title",
            "Failure Path",
            "--budget-file",
            str(write_budget(tmp_path)),
            "--workflow-run-id",
            "12345",
            "--source-git-sha",
            "a" * 40,
            "--missing-evidence",
            "workflowTiming.authoritativeDAG",
            "--write-json",
            str(output_path),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["status"] == "historical_incomplete"
    assert payload["durations"]["machineCriticalPathSeconds"] is None
    assert "durations.machineCriticalPathSeconds" in payload["missingEvidence"]
    assert "workflowTiming.authoritativeDAG" in payload["missingEvidence"]


@pytest.mark.parametrize(
    ("seconds", "expected_status"),
    [
        (600, "within_budget"),
        (601, "released_over_soft_budget"),
        (1800, "released_over_soft_budget"),
        (1801, "failed"),
    ],
)
def test_soft_and_hard_statuses_come_from_the_budget_file(
    tmp_path: Path, seconds: int, expected_status: str
) -> None:
    payload = run_renderer(tmp_path, seconds, complete=True)

    assert payload["budget"]["softSeconds"] == 600
    assert payload["budget"]["hardSeconds"] == 1800
    assert payload["status"] == expected_status


@pytest.mark.parametrize(
    ("profile", "seconds", "expected_hard"),
    [
        ("pr_light", 6000, 5400),
        ("mainline_auto_prod", 8000, 7800),
    ],
)
def test_profile_hard_budget_is_the_canonical_rendered_gate_outcome(
    tmp_path: Path,
    profile: str,
    seconds: int,
    expected_hard: int,
) -> None:
    payload = run_renderer(
        tmp_path,
        seconds,
        complete=True,
        budget_profile=profile,
    )

    assert payload["status"] == "failed"
    assert payload["budget"]["profile"] == profile
    assert payload["budget"]["hardSeconds"] == expected_hard
    assert payload["budget"]["gateHardSeconds"] == 1800
    assert payload["outcomePolicy"]["timing"] == (
        "GATE_BLOCK" if profile == "mainline_auto_prod" else "PR_WARN"
    )


def test_release_sla_and_advisory_have_distinct_hard_budget_projection(
    tmp_path: Path,
) -> None:
    release = run_renderer(
        tmp_path,
        8000,
        complete=True,
        budget_profile="mainline_auto_prod",
    )
    advisory = run_renderer(
        tmp_path,
        6000,
        complete=True,
        budget_profile="pr_light",
    )

    assert release["status"] == "failed"
    assert release["budget"]["policy"] == "release_sla"
    assert release["outcomePolicy"]["timing"] == "GATE_BLOCK"
    assert advisory["status"] == "failed"
    assert advisory["budget"]["policy"] == "telemetry_advisory"
    assert advisory["outcomePolicy"]["timing"] == "PR_WARN"


def test_unknown_profile_fails_closed_before_writing_summary(tmp_path: Path) -> None:
    output_path = tmp_path / "summary.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--gate-key",
            "test_gate",
            "--budget-file",
            str(write_budget(tmp_path)),
            "--budget-profile",
            "unknown",
            *complete_args(500),
            "--write-json",
            str(output_path),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "canonical profile timing budget is missing: unknown" in completed.stderr
    assert not output_path.exists()


def test_fast_machine_dag_cannot_hide_slow_end_to_end_release(tmp_path: Path) -> None:
    output_path = tmp_path / "summary.json"
    command = [
        sys.executable,
        str(SCRIPT),
        "--gate-key",
        "test_gate",
        "--title",
        "Test Gate",
        "--budget-file",
        str(write_budget(tmp_path)),
        *complete_args(1801, machine_seconds=580),
        "--write-json",
        str(output_path),
    ]
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["status"] == "failed"
    assert payload["criticalPath"]["seconds"] == 1801
    assert payload["durations"]["machineCriticalPathSeconds"] == 580


@pytest.mark.parametrize("outcome", ["rolled-back", "rollback-failed"])
def test_non_release_terminal_outcome_cannot_be_counted_green(
    tmp_path: Path, outcome: str
) -> None:
    output_path = tmp_path / "summary.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--gate-key",
            "test_gate",
            "--title",
            "Test Gate",
            "--budget-file",
            str(write_budget(tmp_path)),
            *complete_args(590),
            "--release-outcome",
            outcome,
            "--write-json",
            str(output_path),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["status"] == "failed"
    assert f"releaseOutcome={outcome}" in payload["notes"]


def test_dry_run_is_historical_and_never_an_slo_release(tmp_path: Path) -> None:
    output_path = tmp_path / "summary.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--gate-key",
            "test_gate",
            "--title",
            "Test Gate",
            "--budget-file",
            str(write_budget(tmp_path)),
            *complete_args(590),
            "--release-outcome",
            "dry-run",
            "--write-json",
            str(output_path),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["status"] == "historical_incomplete"
    assert "releaseOutcome=dry-run" in payload["notes"]


def test_missing_official_approval_timestamps_stays_historical(tmp_path: Path) -> None:
    output_path = tmp_path / "summary.json"
    args = complete_args(590)
    for option in ("--approval-requested-at", "--approval-approved-at"):
        index = args.index(option)
        del args[index : index + 2]
    for option in ("--approval-wait-seconds", "--human-decision-wait-seconds"):
        index = args.index(option)
        del args[index : index + 2]
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--gate-key",
            "test_gate",
            "--title",
            "Test Gate",
            "--budget-file",
            str(write_budget(tmp_path)),
            *args,
            "--write-json",
            str(output_path),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["status"] == "historical_incomplete"
    assert "timestamps.approvalRequestedAt" in payload["missingEvidence"]
    assert "timestamps.approvalApprovedAt" in payload["missingEvidence"]
    assert "durations.approvalWaitSeconds" in payload["missingEvidence"]
    assert "durations.humanDecisionWaitSeconds" in payload["missingEvidence"]


def test_upstream_job_timestamp_gap_is_preserved_as_missing_evidence(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "summary.json"
    args = complete_args(590)
    queue_index = args.index("--queue-seconds")
    del args[queue_index : queue_index + 2]
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--gate-key",
            "test_gate",
            "--title",
            "Test Gate",
            "--budget-file",
            str(write_budget(tmp_path)),
            *args,
            "--missing-evidence",
            "githubJobs.createdAt",
            "--write-json",
            str(output_path),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["status"] == "historical_incomplete"
    assert payload["durations"]["queueSeconds"] is None
    assert "durations.queueSeconds" in payload["missingEvidence"]
    assert "githubJobs.createdAt" in payload["missingEvidence"]


def test_functional_green_with_provider_timeout_is_timing_pr_warn(tmp_path: Path) -> None:
    output_path = tmp_path / "summary.json"
    args = complete_args(590)
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--gate-key", "test_gate",
         "--budget-file", str(write_budget(tmp_path)), *args,
         "--functional-outcome", "pass",
         "--telemetry-classification", "infra",
         "--write-json", str(output_path)],
        cwd=REPO_ROOT, check=False, capture_output=True, text=True,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "within_budget"
    assert payload["outcomePolicy"]["functional"] == "pass"
    assert payload["outcomePolicy"]["timing"] == "PR_WARN"


def test_functional_timeout_remains_fail_even_when_timing_is_infra(tmp_path: Path) -> None:
    output_path = tmp_path / "summary.json"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--gate-key", "test_gate",
         "--budget-file", str(write_budget(tmp_path)), *complete_args(590),
         "--functional-outcome", "fail",
         "--telemetry-classification", "infra",
         "--write-json", str(output_path)],
        cwd=REPO_ROOT, check=False, capture_output=True, text=True,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["outcomePolicy"]["timing"] == "FUNCTIONAL_FAIL"
