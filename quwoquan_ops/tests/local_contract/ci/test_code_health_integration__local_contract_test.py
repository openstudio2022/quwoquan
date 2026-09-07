"""Hosted code-health recompute publishes typed facts only for exact dev1.0 fast-forward ranges.

spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-004.t1
spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-004.t2
spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-004.t3
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from quwoquan_ops.ci import code_health_evidence, verify_code_health_integration as driver
from quwoquan_ops.ci.promotion_evidence import canonical_bytes
from quwoquan_ops.gate.code_health_delta.policy import load_policy
from quwoquan_ops.tests.support.code_health_delta_test_support import commit, git, init_repo, policy_path, write

WORKFLOW = _REPO_ROOT / ".github/workflows/code-health-integration.yml"


def _run(repo: Path, tmp_path: Path, before: str, after: str) -> tuple[int, dict, Path]:
    report = tmp_path / "out/report.json"
    fact = tmp_path / "out/fact.json"
    summary = tmp_path / "out/summary.md"
    code = driver.main([
        "--before", before, "--after", after, "--policy", str(policy_path(repo)), "--repo", str(repo),
        "--report-output", str(report), "--fact-output", str(fact), "--summary-markdown", str(summary),
    ])
    return code, json.loads(fact.read_text(encoding="utf-8")), summary


def test_zero_same_and_non_ancestor_before_are_typed_blocks_without_recompute(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)
    write(repo, "quwoquan_ops/ci/a.py", "value = 1\n")
    head = commit(repo, "a")
    git(repo, "checkout", "-q", "-b", "sibling", base)
    write(repo, "quwoquan_ops/ci/b.py", "value = 2\n")
    sibling = commit(repo, "b")
    git(repo, "checkout", "-q", "-")

    for before, expected in (
        ("0" * 40, "CODE_HEALTH.INTEGRATION_RANGE_INVALID"),
        (head, "CODE_HEALTH.INTEGRATION_RANGE_INVALID"),
        (sibling, "CODE_HEALTH.INTEGRATION_NOT_FAST_FORWARD"),
        ("not-a-sha", "CODE_HEALTH.INTEGRATION_RANGE_INVALID"),
    ):
        code, fact, summary = _run(repo, tmp_path / expected / before[:8], before, head)
        assert code == 1
        assert fact["terminal"] == "GATE_BLOCK"
        assert fact["blocker"]["code"] == expected
        assert fact["integration"] == {"schema": driver.FACT_SCHEMA, "before": before, "after": head, "blocksPush": False}
        assert "findings" not in fact
        assert expected in summary.read_text(encoding="utf-8")


def test_gate_block_recompute_fails_run_and_never_writes_pass_fact(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)
    block = load_policy(policy_path(repo))["thresholds"]["file_lines"]["block"]
    write(repo, "quwoquan_ops/ci/huge.py", "value = 1\n" * (block + 1))
    head = commit(repo, "huge")
    code, fact, summary = _run(repo, tmp_path, base, head)
    assert code == 1
    assert fact["terminal"] == "GATE_BLOCK"
    assert fact["integration"]["before"] == base and fact["integration"]["after"] == head
    assert {item["code"] for item in fact["findings"]} >= {"CODE_HEALTH.NEW_FILE_OVER_BLOCK"}
    assert summary.read_text(encoding="utf-8").startswith("# Code Health Delta — GATE_BLOCK")
    written = (tmp_path / "out/fact.json").read_bytes()
    assert written == canonical_bytes(fact) + b"\n"


def test_clean_recompute_succeeds_and_fact_stays_report_only(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)
    write(repo, "quwoquan_ops/ci/small.py", "value = 1\n")
    head = commit(repo, "small")
    code, fact, summary = _run(repo, tmp_path, base, head)
    assert code == 0
    assert fact["terminal"] == "PASS"
    assert fact["integration"] == {"schema": driver.FACT_SCHEMA, "before": base, "after": head, "blocksPush": False}
    assert fact["baseSha"] == base and fact["headSha"] == head
    assert fact["changedPaths"] == ["quwoquan_ops/ci/small.py"]
    assert "# Code Health Delta — PASS" in summary.read_text(encoding="utf-8")


def test_publish_rejects_non_canonical_tags_and_pull_history_is_typed_when_registry_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"schema": driver.FACT_SCHEMA, "terminal": "PASS"}), encoding="utf-8")
    with pytest.raises(code_health_evidence.CodeHealthEvidenceError, match="transport tag"):
        code_health_evidence.publish(report, repository="ghcr.io/acme/code-health-integration", transport_tag="latest")
    with pytest.raises(code_health_evidence.CodeHealthEvidenceError, match="schema/terminal"):
        code_health_evidence.write_fact({"terminal": "PASS"}, tmp_path / "bad.json")

    def missing_oras(*_args: str) -> str:
        raise code_health_evidence.CodeHealthEvidenceError("oras unavailable")

    monkeypatch.setattr(code_health_evidence, "_oras", missing_oras)
    result = code_health_evidence.pull_weekly_history(
        "ghcr.io/acme/code-health-weekly", limit=3, output_dir=tmp_path / "history",
    )
    assert result == {
        "status": "unavailable", "repository": "ghcr.io/acme/code-health-weekly",
        "reason": "oras unavailable", "reports": [],
    }
    with pytest.raises(code_health_evidence.CodeHealthEvidenceError, match="limit"):
        code_health_evidence.pull_weekly_history("ghcr.io/acme/code-health-weekly", limit=0, output_dir=tmp_path)


def test_workflow_binds_exact_event_range_and_stays_out_of_promotion() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "branches: [dev1.0]" in text
    assert "--before \"$RANGE_BEFORE\"" in text and "--after \"$RANGE_AFTER\"" in text
    assert "github.event.before || inputs.before" in text
    assert "timeout-minutes: 5" in text
    assert "code_health_evidence.py publish" in text
    assert "ghcr.io/${{ github.repository }}/code-health-integration" in text
    assert "upload-artifact" not in text
    for forbidden in ("promotion", "delivery-gate", "release_control", "mutation"):
        assert forbidden not in text.casefold()
