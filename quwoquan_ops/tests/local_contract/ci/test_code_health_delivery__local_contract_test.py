"""Delivery Code Health clean-candidate identity contracts.

spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/incremental-code-health-governance/spec.md#gwt-003.t1
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from quwoquan_ops.ci import verify_code_health_delivery as delivery_cli
from quwoquan_ops.ci.impact_planner_core import build_delivery_impact_plan
from quwoquan_ops.ci.verify_code_health_delivery import verify_delivery
from quwoquan_ops.gate.code_health_delta.engine import analyze_delta
from quwoquan_ops.gate.code_health_delta.render import render_candidate

ROOT = Path(__file__).resolve().parents[4]
POLICY = ROOT / "quwoquan_ops/policies/code_health_policy.yaml"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def test_delivery_recomputes_exact_commit_and_rejects_stale_path_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "config", "user.name", "Fixture")
    policy = repo / "quwoquan_ops/policies/code_health_policy.yaml"
    policy.parent.mkdir(parents=True)
    policy.write_bytes(POLICY.read_bytes())
    source = repo / "quwoquan_ops/ci/value.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    base = _git(repo, "rev-parse", "HEAD")
    source.write_text("VALUE = 2\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "candidate")
    head = _git(repo, "rev-parse", "HEAD")
    report = analyze_delta(repo, base=base, head=head, policy_path=policy, mode="full")
    tree_digest = "sha1:" + _git(repo, "rev-parse", f"{head}^{{tree}}")
    plan = build_delivery_impact_plan(
        report["changedPaths"], source_sha=head, base_sha=base,
        source_tree_digest=tree_digest,
    )

    passed, output, identity = verify_delivery(
        repo,
        base_sha=base,
        head_sha=head,
        expected_path_digest=report["changedPathsDigest"],
        expected_impact_plan_digest=plan["plan_digest"],
        policy_path=policy,
    )
    assert passed["candidateSource"] == "commit"
    assert output.is_file()
    assert identity.startswith("sha256:")
    assert json.loads(output.read_text(encoding="utf-8"))["headSha"] == head

    with pytest.raises(ValueError, match="changed-path digest differs"):
        verify_delivery(
            repo,
            base_sha=base,
            head_sha=head,
            expected_path_digest="sha256:" + "0" * 64,
            expected_impact_plan_digest=plan["plan_digest"],
            policy_path=policy,
        )

    # CLI 把同一份 Markdown 投影写到 --summary-markdown 并打印，供 Lane Gate step summary 使用。
    summary = tmp_path / "summary.md"
    monkeypatch.setattr(delivery_cli, "ROOT", repo)
    monkeypatch.setattr(sys, "argv", [
        "verify_code_health_delivery.py", "--base-sha", base, "--head-sha", head,
        "--expected-path-digest", report["changedPathsDigest"],
        "--expected-impact-plan-digest", plan["plan_digest"],
        "--summary-markdown", str(summary),
    ])
    assert delivery_cli.main() == 0
    out = capsys.readouterr().out
    assert summary.read_text(encoding="utf-8") == render_candidate(passed)
    assert out.startswith("# Code Health Delta — PASS") and "code-health-delivery: PASS" in out
