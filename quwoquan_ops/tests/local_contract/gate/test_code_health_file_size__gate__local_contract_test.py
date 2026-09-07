"""文件规模单轨：Code Health Delta 是唯一的行数判罚来源。

spec_ref: specs/feature-tree/platform-ops-governance/config-and-reliability-governance/spec.md#sit-002
spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/incremental-code-health-governance/spec.md#gwt-001.t2
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from quwoquan_ops.gate.code_health_delta.engine import analyze_delta
from quwoquan_ops.gate.code_health_delta.policy import load_policy
from quwoquan_ops.gate.python_script_governance import constants as governance_constants
from quwoquan_ops.tests.support.code_health_delta_test_support import (
    POLICY, commit, init_repo, policy_path, policy_text_with, write,
)

BLOCK = 2000
ADVISORY = 1000
PIPED_CONTRACT_SCRIPT = "quwoquan_ops/cli/prod/hosted_release_ledger.py"


def _codes(report: dict) -> set[str]:
    return {str(item["code"]) for item in report["findings"]}


def _analyze(repo: Path, base: str, head: str) -> dict:
    return analyze_delta(repo, base=base, head=head, policy_path=policy_path(repo), mode="fast")


def test_python_script_governance_owns_no_second_line_budget() -> None:
    assert importlib.util.find_spec("quwoquan_ops.gate.python_script_governance.line_budget") is None
    assert not any(name.startswith("PYTHON_LINE_BUDGET") for name in dir(governance_constants))
    policy = load_policy(POLICY)
    assert policy["policy_id"] == "incremental-code-health-v2"
    assert policy["thresholds"]["file_lines"] == {"advisory": ADVISORY, "block": BLOCK}


def test_piped_contract_script_uses_same_threshold_as_other_production_files(tmp_path: Path) -> None:
    text = policy_text_with(file_lines={"advisory": ADVISORY, "block": BLOCK})
    repo, base = init_repo(tmp_path, policy_text=text)
    write(repo, PIPED_CONTRACT_SCRIPT, "value = 1\n" * (BLOCK + 1))
    write(repo, "quwoquan_ops/ci/other_module.py", "value = 2\n" * (BLOCK + 1))
    head = commit(repo)
    report = _analyze(repo, base, head)
    blocked = sorted(
        item["path"] for item in report["findings"]
        if item["code"] == "CODE_HEALTH.NEW_FILE_OVER_BLOCK"
    )
    assert blocked == sorted([PIPED_CONTRACT_SCRIPT, "quwoquan_ops/ci/other_module.py"])
    assert report["terminal"] == "GATE_BLOCK"


def test_block_and_advisory_tiers_follow_policy_thresholds(tmp_path: Path) -> None:
    text = policy_text_with(file_lines={"advisory": ADVISORY, "block": BLOCK})
    repo, base = init_repo(tmp_path, policy_text=text)

    write(repo, "quwoquan_ops/ci/over_block.py", "value = 1\n" * (BLOCK + 1))
    write(repo, "quwoquan_ops/ci/over_advisory.py", "value = 1\n" * (ADVISORY + 500))
    write(repo, "quwoquan_ops/ci/small.py", "value = 1\n" * (ADVISORY - 1))
    head = commit(repo, "tiers")
    report = _analyze(repo, base, head)
    by_path = {item["path"]: item for item in report["findings"] if item["path"].startswith("quwoquan_ops/ci/")}
    assert by_path["quwoquan_ops/ci/over_block.py"]["code"] == "CODE_HEALTH.NEW_FILE_OVER_BLOCK"
    assert by_path["quwoquan_ops/ci/over_block.py"]["measure"]["threshold"] == BLOCK
    assert by_path["quwoquan_ops/ci/over_advisory.py"]["code"] == "CODE_HEALTH.FILE_LINES_ADVISORY"
    assert by_path["quwoquan_ops/ci/over_advisory.py"]["terminal"] == "PR_WARN"
    assert "quwoquan_ops/ci/small.py" not in by_path

    # 1000–2000 区间的增长只是 advisory；超过 2000 的存量继续增长才阻断，收缩即 PASS。
    write(repo, "quwoquan_ops/ci/over_advisory.py", "value = 1\n" * (ADVISORY + 600))
    write(repo, "quwoquan_ops/ci/over_block.py", "value = 1\n" * (BLOCK + 2))
    grown = commit(repo, "grow")
    report = _analyze(repo, head, grown)
    assert {
        item["code"] for item in report["findings"] if item["path"] == "quwoquan_ops/ci/over_advisory.py"
    } == {"CODE_HEALTH.FILE_LINES_ADVISORY"}
    assert {
        item["code"] for item in report["findings"] if item["path"] == "quwoquan_ops/ci/over_block.py"
    } == {"CODE_HEALTH.OVERSIZED_FILE_GROWTH"}

    write(repo, "quwoquan_ops/ci/over_block.py", "value = 1\n" * (BLOCK + 1))
    shrunk = commit(repo, "shrink")
    report = _analyze(repo, grown, shrunk)
    assert not _codes(report) & {"CODE_HEALTH.OVERSIZED_FILE_GROWTH", "CODE_HEALTH.NEW_FILE_OVER_BLOCK"}
