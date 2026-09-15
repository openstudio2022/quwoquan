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
    assert report["hotspotPersistence"]["historyReports"] == 0
    assert report["summary"]["deadCandidateCount"] is None
    assert report["measurements"]["coverage"]["status"] == "unavailable"
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
    source.write_text("dirty = 2\n" * 10, encoding="utf-8")
    fast = analyze_weekly(repo, head=head, policy=load_policy(policy_path), mode="fast", observation_branch="dev1.0")
    assert fast["inputScope"]["worktreeBytesIncluded"] is False
    assert fast["summary"]["cloneGroupCount"] is None
    assert fast["complexitySummary"]["functionCount"] is None
    assert fast["measurements"]["complexity"]["status"] == "unavailable"
    assert all(item["status"] == "unavailable" and item["sourceLoc"] is None for item in fast["growthHistory"])
    assert fast["modules"]["quwoquan_ops/ci"]["physicalLines"] == 4
    assert fast["ownerScopeWeakPoints"][0]["overComplexity"] is None
    assert source.read_text() == "dirty = 2\n" * 10
    incompatible = {**fast, "headSha": "previous", "implementationDigest": "old-analyzer"}
    checked = analyze_weekly(repo, head=head, policy=load_policy(policy_path), mode="fast",
                             observation_branch="dev1.0", previous_reports=[incompatible])
    assert checked["ratchet"]["comparisonStatus"] == "incomparable"
    assert checked["ratchet"]["incomparableReports"][0]["reasons"] == ["implementationDigest"]
    assert checked["hotspotPersistence"]["historyReports"] == 0
    assert all(item["direction"] == "n/a" for item in checked["ratchet"]["metrics"].values())
    assert checked["measurementSpec"]["sourceLocLegacyComparable"] is False


def test_weekly_reads_exact_blobs_in_dirty_worktree(tmp_path: Path) -> None:
    from quwoquan_ops.gate.code_health_delta.weekly import _commit_blobs
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "fixture@example.invalid")
    _git(tmp_path, "config", "user.name", "Fixture")
    source = tmp_path / "example.py"
    source.write_text("value = 1\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "base")
    head = _git(tmp_path, "rev-parse", "HEAD")
    source.write_text("dirty = 2\n")
    assert _commit_blobs(tmp_path, head, ["example.py"])["example.py"] == b"value = 1\n"
    assert source.read_text() == "dirty = 2\n"


def test_module_facts_are_complete_and_conserve_all_dimensions() -> None:
    from quwoquan_ops.gate.code_health_delta.weekly import aggregate_file_facts, owner_scope_weak_points
    production = {f"quwoquan_ops/module{i}/value.py": b"value = 1\n" for i in range(8)}
    scopes = owner_scope_weak_points(production, {}, {}, [], load_policy(POLICY_PATH))
    assert len(scopes) == 8
    facts = [{"path": path, "category": "handwritten-production", "language": "Python",
              "moduleScope": path.rsplit("/", 1)[0], "physicalLines": 1} for path in production]
    result = aggregate_file_facts(facts)
    assert result["conservation"]["status"] == "available"
    assert len(result["modules"]) == 8
    for dimension in ("categories", "languages", "modules"):
        assert sum(row["files"] for row in result[dimension].values()) == 8
        assert sum(row["physicalLines"] for row in result[dimension].values()) == 8
    assert all(row["owner"]["status"] == "unavailable" for row in result["modules"].values())


def test_unsupported_complexity_is_not_zero_pass() -> None:
    from quwoquan_ops.gate.code_health_delta.weekly import _score_hotspots
    complexity, _ = _score_hotspots({"a.swift": b"func a() {}\n"}, {}, {}, load_policy(POLICY_PATH))
    assert complexity["a.swift"]["status"] == "unavailable"
    assert complexity["a.swift"]["maxCyclomatic"] is None


def test_cloc_reads_exact_canonical_sources_with_duplicate_paths(tmp_path: Path) -> None:
    import shutil
    import pytest
    from quwoquan_ops.gate.code_health_delta.weekly import _cloc
    if shutil.which("cloc") is None:
        pytest.skip("cloc unavailable")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "fixture@example.invalid")
    _git(tmp_path, "config", "user.name", "Fixture")
    for path in ("src/coverage/a.py", "src/coverage/b.py"):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("value = 1\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "base")
    (tmp_path / "src/coverage/a.py").write_text("dirty = 2\n" * 10)
    result = _cloc(tmp_path, _git(tmp_path, "rev-parse", "HEAD"), "cloc", load_policy(POLICY_PATH))
    assert result["files"] == 2
    assert result["sourceLoc"] == 2
    assert result["countDuplicatePaths"] is True


def test_history_rejects_changed_analyzer_toolchain_and_measurement_scope() -> None:
    from quwoquan_ops.gate.code_health_delta.weekly import _comparable_history
    current = {"headSha": "new", "policyDigest": "policy", "implementationDigest": "impl",
               "toolchainDigest": "tools", "measurementSpecDigest": "scope", "mode": "full",
               "generatedSourcesDigest": "new-source", "observationBranch": "dev1.0"}
    previous = {**current, "headSha": "old", "generatedSourcesDigest": "old-source"}
    accepted, state = _comparable_history(current, [previous])
    assert accepted == [previous] and state["status"] == "comparable"
    for field in ("implementationDigest", "toolchainDigest", "measurementSpecDigest", "policyDigest"):
        accepted, state = _comparable_history(current, [{**previous, field: "changed"}])
        assert accepted == [] and state["status"] == "incomparable"
        assert field in state["excluded"][0]["reasons"]
    accepted, state = _comparable_history(current, [{"headSha": "legacy"}])
    assert accepted == [] and state["status"] == "incomparable"


def test_runtime_provenance_does_not_pollute_authoring_policy_identity() -> None:
    from quwoquan_ops.gate.code_health_delta.weekly import _report_identity
    policy = load_policy(POLICY_PATH)
    kwargs = dict(head_sha="head", window={}, delivery_run_pages=None, tools={})
    first = _report_identity(policy=policy, **kwargs)
    dirty = {**policy, "_generated_provenance": {"fake.py": "dirty-source"}, "_generated_sources_digest": "dirty"}
    second = _report_identity(policy=dirty, **kwargs)
    assert first["policyDigest"] == second["policyDigest"]
    assert first["identityDigest"] == second["identityDigest"]


def test_generated_source_digest_reads_commit_not_dirty_source(tmp_path: Path) -> None:
    from quwoquan_ops.gate.code_health_delta.weekly import _classification_policy, _report_identity
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "fixture@example.invalid")
    _git(tmp_path, "config", "user.name", "Fixture")
    source = tmp_path / "generator.py"
    source.write_text("version = 1\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "source")
    head = _git(tmp_path, "rev-parse", "HEAD")
    policy = load_policy(POLICY_PATH)
    policy["classification"] = {**policy["classification"],
                                "generated_exact_sources": {"generated.py": "generator.py"}, "generated_manifests": []}
    first = _classification_policy(tmp_path, head, policy, ["generator.py"])
    source.write_text("version = 2\n")
    dirty = {**policy, "_generated_provenance": {"fake.py": "fake"}, "_generated_sources_digest": "fake"}
    second = _classification_policy(tmp_path, head, dirty, ["generator.py"])
    assert first == second
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "source update")
    changed = _classification_policy(tmp_path, _git(tmp_path, "rev-parse", "HEAD"), policy, ["generator.py"])
    assert first["_generated_sources_digest"] != changed["_generated_sources_digest"]
    kwargs = dict(head_sha=head, window={}, policy=policy, delivery_run_pages=None, tools={})
    original = _report_identity(**kwargs, generated_sources_digest=first["_generated_sources_digest"])
    new = _report_identity(**kwargs, generated_sources_digest=changed["_generated_sources_digest"])
    assert original["policyDigest"] == new["policyDigest"]
    assert original["identityDigest"] != new["identityDigest"]


def test_weekly_r2_generated_outputs_bind_exact_commit_bytes(tmp_path: Path) -> None:
    import hashlib
    from quwoquan_ops.gate.code_health_delta.weekly import _classification_policy
    from quwoquan_ops.gate.code_health_delta.classification import classify_path
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "fixture@example.invalid")
    _git(tmp_path, "config", "user.name", "Fixture")
    body = b"generated_value = 1\n"
    (tmp_path / "generated.py").write_bytes(body)
    (tmp_path / "manifest.json").write_text(json.dumps({"generator": "fixture-generator", "outputs": [
        {"path": "generated.py", "sha256": hashlib.sha256(body).hexdigest()},
        {"path": "missing.py", "sha256": hashlib.sha256(body).hexdigest()},
    ]}))
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "valid generated output")
    head = _git(tmp_path, "rev-parse", "HEAD")
    policy = load_policy(POLICY_PATH)
    policy["classification"] = {**policy["classification"], "generated_exact_sources": {},
                                "generated_manifests": [{"path": "manifest.json", "generator": "fixture-generator", "root": ""}]}
    tracked = ["generated.py", "manifest.json"]
    exact = _classification_policy(tmp_path, head, policy, tracked)
    assert classify_path("generated.py", exact) == "generated"
    assert exact["_generated_statuses"]["generated.py"]["status"] == "manifest-output-verified"
    assert exact["_generated_statuses"]["missing.py"]["status"] == "output-unavailable"
    (tmp_path / "generated.py").write_text("tampered = 2\n")
    assert _classification_policy(tmp_path, head, policy, tracked) == exact
    report = analyze_weekly(tmp_path, head=head, policy=policy, mode="fast")
    assert report["generatedClassification"]["statuses"]["generated.py"]["status"] == "manifest-output-verified"
    assert report["categories"]["generated"]["files"] == 1
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "tampered output")
    tampered_head = _git(tmp_path, "rev-parse", "HEAD")
    tampered = _classification_policy(tmp_path, tampered_head, policy, tracked)
    assert classify_path("generated.py", tampered) == "handwritten-production"
    assert tampered["_generated_statuses"]["generated.py"]["status"] == "output-digest-mismatch"
    assert tampered["_generated_sources_digest"] != exact["_generated_sources_digest"]
    (tmp_path / "generated.py").write_bytes(body)
    report = analyze_weekly(tmp_path, head=tampered_head, policy=policy, mode="fast")
    assert report["generatedClassification"]["statuses"]["generated.py"]["status"] == "output-digest-mismatch"
    assert report["categories"]["handwritten-production"]["files"] == 1


def test_self_reported_exact_evidence_never_grants_verified_owner() -> None:
    from quwoquan_ops.gate.code_health_delta.weekly import _optional_evidence, _attach_owner_evidence
    evidence = {"headSha": "head", "exactRef": "nonexistent:sha256:fake", "modules": {
        "scope": {"ownerIdentityRef": "missing.json", "resolvedOwner": "fake-owner", "status": "available"}}}
    measurement = _optional_evidence(evidence, "head")
    assert measurement["status"] == "supplied-unverified"
    modules = {"scope": {"owner": {"status": "unavailable"}}}
    _attach_owner_evidence(modules, measurement)
    assert modules["scope"]["owner"]["status"] != "available"


def test_missing_delivery_is_unavailable_not_zero_pass() -> None:
    result = delivery_outcomes(None, end=datetime(2026, 9, 5, tzinfo=timezone.utc))
    assert result["status"] == "unavailable"
    assert result["regressionFlags"] is None


def test_weekly_history_never_mixes_observation_branches() -> None:
    from quwoquan_ops.gate.code_health_delta.weekly import _ordered_previous, WEEKLY_SCHEMA
    reports = [{"schema": WEEKLY_SCHEMA, "headSha": "old", "observationBranch": "main",
                "window": {"end": "2026-09-01T00:00:00+00:00"}}]
    assert _ordered_previous(reports, "current", observation_branch="dev1.0") == []


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
    assert "ref: dev1.0" in workflow
    assert '--head "$OBSERVATION_HEAD"' in workflow
    assert '--observation-branch "$OBSERVATION_BRANCH"' in workflow
    assert 'code-health-weekly-dev1.0' in workflow
    assert '--head "${{ github.sha }}"' not in workflow
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
