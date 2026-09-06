"""Weekly code-health observation stays report-only and outcome-aware.

spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/incremental-code-health-governance/spec.md#gwt-003.t3
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from quwoquan_ops.ci.impact_planner_core import canonical_digest
from quwoquan_ops.gate.code_health_delta.policy import load_policy
from quwoquan_ops.gate.code_health_delta.weekly import (
    _clone_facts,
    analyze_weekly,
    delivery_outcomes,
)

ROOT = Path(__file__).resolve().parents[4]
POLICY_PATH = ROOT / "quwoquan_ops/policies/code_health_policy.yaml"


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    return subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True, text=True).stdout.strip()


def _run(created_at: str, *, conclusion: str, attempt: int = 1, seconds: int = 60) -> dict[str, object]:
    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    updated = created.timestamp() + seconds
    return {
        "created_at": created_at,
        "updated_at": datetime.fromtimestamp(updated, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "completed",
        "conclusion": conclusion,
        "run_attempt": attempt,
    }


def _sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 71 and value.startswith("sha256:") and all(
        character in "0123456789abcdef" for character in value.removeprefix("sha256:")
    )


def test_clone_facts_count_unique_cross_file_groups_and_covered_lines() -> None:
    shared = [f"value_{index} = {index}" for index in range(7)]
    blobs = {
        "a.py": ("\n".join(shared) + "\n").encode(),
        "b.py": ("\n".join(shared) + "\n").encode(),
        "c.py": ("\n".join(shared) + "\n").encode(),
        "unique.py": b"one = 1\ntwo = 2\nthree = 3\nfour = 4\nfive = 5\nsix = 6\nseven = 7\n",
    }

    clone_lines, group_count = _clone_facts(blobs, block_lines=6)

    assert group_count == 2
    assert clone_lines == {"a.py": 7, "b.py": 7, "c.py": 7}

    repeated_in_one_file = ("\n".join(shared + shared) + "\n").encode()
    assert _clone_facts({"only.py": repeated_in_one_file}, block_lines=6) == ({}, 0)


def test_weekly_report_is_clean_candidate_report_only(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "config", "user.name", "Fixture")
    policy_path = repo / "quwoquan_ops/policies/code_health_policy.yaml"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_bytes(POLICY_PATH.read_bytes())
    source = repo / "quwoquan_ops/ci/value.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("def value(x):\n    if x:\n        return 1\n    return 0\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    head = _git(repo, "rev-parse", "HEAD")
    fake_cloc = tmp_path / "cloc"
    fake_cloc.write_text(
        "#!/bin/sh\nprintf '%s' '{\"header\":{\"cloc_version\":\"fixture\"},\"SUM\":{\"nFiles\":2,\"blank\":0,\"comment\":0,\"code\":42}}'\n",
        encoding="utf-8",
    )
    fake_cloc.chmod(0o755)
    run_pages = [
        {"workflow_runs": [_run("2026-09-04T00:00:00Z", conclusion="failure", attempt=2, seconds=120)]},
        {"workflow_runs": [_run("2026-08-01T00:00:00Z", conclusion="success")]},
    ]
    observed_at = datetime(2026, 9, 5, 4, 30, 1, 123456, tzinfo=timezone.utc)
    report = analyze_weekly(
        repo,
        head=head,
        policy=load_policy(policy_path),
        cloc_executable=str(fake_cloc),
        delivery_run_pages=run_pages,
        observed_at=observed_at,
    )
    assert report["terminal"] == "REPORT_ONLY"
    assert report["authority"] == {"blocksPullRequests": False, "createsOwnerOpen": False, "automaticRemediation": False}
    assert report["growthHistory"][-1]["sourceLoc"] == 42
    assert report["growthHistory"][-1]["countDuplicatePaths"] is True
    assert report["summary"]["handwrittenProductionFiles"] == 1
    assert report["deliveryOutcomes"]["comparisonStatus"] == "comparable"
    assert report["deliveryOutcomes"]["regressionFlags"]["failureRate"] is True
    assert report["deliveryOutcomes"]["regressionThresholdPercent"] == 10
    assert report["observedAt"] == "2026-09-05T04:30:01.123456+00:00"
    assert report["generatedAt"] == report["observedAt"]
    assert _sha256(report["identityDigest"])
    assert _sha256(report["policyDigest"])
    assert _sha256(report["implementationDigest"])
    assert _sha256(report["deliveryOutcomesDigest"])
    assert report["deliveryOutcomesDigest"] == canonical_digest(run_pages)

    # 身份只绑定输入：同 head/policy/实现/delivery 数据的再次观测得到同一身份，历史序列才能去重。
    later_report = analyze_weekly(
        repo,
        head=head,
        policy=load_policy(policy_path),
        cloc_executable=str(fake_cloc),
        delivery_run_pages=run_pages,
        observed_at=observed_at.replace(microsecond=123457),
    )
    assert later_report["identityDigest"] == report["identityDigest"]
    assert later_report["observedAt"] != report["observedAt"]
    assert report["ratchet"]["comparisonStatus"] == "insufficient-history"
    assert report["hotspotPersistence"] == {"historyReports": 0, "topN": 20, "items": []}
    assert report["sizeDistribution"]["tiers"] == [800, 1000, 2000]
    assert report["sizeDistribution"]["production"]["files"] == 1
    assert report["ownerScopeWeakPoints"][0]["ownerScope"] == "quwoquan_ops/ci"

    changed_delivery = analyze_weekly(
        repo,
        head=head,
        policy=load_policy(policy_path),
        cloc_executable=str(fake_cloc),
        delivery_run_pages=run_pages[:1],
        observed_at=observed_at,
    )
    assert changed_delivery["identityDigest"] != report["identityDigest"]


def test_delivery_outcomes_marks_missing_window_as_insufficient_history() -> None:
    pages = [{"workflow_runs": [_run("2026-09-04T00:00:00Z", conclusion="failure", attempt=2)]}]

    result = delivery_outcomes(pages, end=datetime(2026, 9, 5, tzinfo=timezone.utc), days=28)

    assert result["status"] == "observed"
    assert result["current"]["completedRuns"] == 1
    assert result["previous"]["completedRuns"] == 0
    assert result["comparisonStatus"] == "insufficient-history"
    assert result["regressionFlags"] is None


def test_delivery_outcomes_compares_current_and_previous_paginated_windows() -> None:
    pages = [
        {"workflow_runs": [_run("2026-09-04T00:00:00Z", conclusion="failure", attempt=2, seconds=120)]},
        {"workflow_runs": [_run("2026-08-01T00:00:00Z", conclusion="success", seconds=60)]},
    ]

    result = delivery_outcomes(pages, end=datetime(2026, 9, 5, tzinfo=timezone.utc), days=28)

    assert result["current"]["completedRuns"] == 1
    assert result["current"]["failureRate"] == 1.0
    assert result["current"]["rerunRate"] == 1.0
    assert result["previous"]["completedRuns"] == 1
    assert result["previous"]["failureRate"] == 0.0
    assert result["comparisonStatus"] == "comparable"
    assert result["regressionFlags"] == {
        "failureRate": True,
        "rerunRate": True,
        "calendarP95Seconds": True,
    }


def test_weekly_workflow_slurps_pages_and_preserves_report_only_artifact_contract() -> None:
    workflow = (ROOT / ".github/workflows/code-health-weekly.yml").read_text(encoding="utf-8")

    assert "gh api --paginate --slurp" in workflow
    # lane-gate 是 candidate 验证的真正承载者，治理副作用（失败率/重跑/时长）必须以它为对象。
    assert "lane-gate.yml code-health-integration.yml app_pipeline.yml service_pipeline.yml" in workflow
    assert "delivery-gate.yml/runs" not in workflow
    assert "code_health_evidence.py pull-weekly-history" in workflow
    assert "code_health_evidence.py publish" in workflow
    assert "--transport-tag \"week-$(date -u +%G-W%V)\"" in workflow
    assert "--summary-markdown" in workflow
    assert "weekly-summary.md\" >> \"$GITHUB_STEP_SUMMARY\"" in workflow
    for forbidden in ("promotion", "mutation", "download-artifact"):
        assert forbidden not in workflow.casefold()
    assert workflow.count("actions/upload-artifact@") == 2
    successful_upload = workflow[workflow.index("- name: Upload successful weekly report"):workflow.index("- name: Upload failed weekly diagnostic")]
    assert "if: success()" in successful_upload
    assert "report.json" in successful_upload
    assert "if-no-files-found: error" in successful_upload
    assert "retention-days: 14" in successful_upload
    failed_upload = workflow[workflow.index("- name: Upload failed weekly diagnostic"):]
    assert "if: failure() && !cancelled()" in failed_upload
    assert "if-no-files-found: ignore" in failed_upload
    assert "retention-days: 3" in failed_upload
