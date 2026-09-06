"""Code Health Delta 判据精度：分类、brace 解析、candidate 内重复、owner-scope 拆分与入口识别。

spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/incremental-code-health-governance/spec.md#gwt-001.t1
spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/incremental-code-health-governance/spec.md#gwt-001.t3
spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/incremental-code-health-governance/spec.md#gwt-001.t4
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from quwoquan_ops.gate import verify_incremental_code_health
from quwoquan_ops.gate.code_health_delta.base_ref import BaseResolutionError, resolve_auto_base
from quwoquan_ops.gate.code_health_delta.classification import classify_path
from quwoquan_ops.gate.code_health_delta.engine import analyze_delta
from quwoquan_ops.gate.code_health_delta.metrics import (
    candidate_duplicate_windows, duplicate_window_index, duplicate_windows, function_metrics,
    has_repository_entry, strip_code_noise,
)
from quwoquan_ops.gate.code_health_delta.policy import load_policy
from quwoquan_ops.tests.support.code_health_delta_test_support import (
    POLICY, commit, git, init_repo, policy_path, write,
)

_DELTA_SOURCES = (
    _REPO_ROOT / "quwoquan_ops/gate/code_health_delta/engine.py",
    _REPO_ROOT / "quwoquan_ops/gate/code_health_delta/metrics.py",
)
#: 只作信息、terminal 恒为 PASS 的 code，不属于 advisory/blocking 任一清单。
_INFORMATIONAL_CODES = {"CODE_HEALTH.DUPLICATION_CANDIDATE"}


def test_l10n_and_native_test_directories_are_not_handwritten_production() -> None:
    policy = load_policy(POLICY)
    assert classify_path("quwoquan_app/lib/l10n/app_localizations.dart", policy) == "generated"
    assert classify_path("quwoquan_app/lib/l10n/app_localizations_zh.dart", policy) == "generated"
    assert classify_path("quwoquan_app/ios/RunnerTests/RunnerTests.swift", policy) == "test"
    assert classify_path("quwoquan_app/android/app/src/androidTest/java/Probe.java", policy) == "test"
    assert classify_path("quwoquan_app/ios/Runner/AppDelegate.swift", policy) == "handwritten-production"


def test_brace_parser_ignores_control_flow_heads_and_string_braces() -> None:
    source = "\n".join([
        "package feed",
        "",
        "func (s *Service) List(ctx context.Context) error {",
        '\tlog.Printf("if { while } for %s", "x || y")',
        "\tif len(items) == cap(items) {",
        "\t\treturn nil",
        "\t}",
        "\tfor _, item := range items {",
        "\t\t// if this comment counted, complexity would inflate",
        "\t\tuse(item)",
        "\t}",
        "\treturn nil",
        "}",
        "",
        "func helper() {",
        "}",
    ])
    metrics = {item.name: item for item in function_metrics("quwoquan_service/x.go", source.encode())}
    assert set(metrics) == {"List", "helper"}
    assert metrics["List"].end == 13
    # 两个真实分支（if、for），字符串与注释里的关键字不计。
    assert metrics["List"].cyclomatic == 3


def test_strip_code_noise_preserves_line_numbers() -> None:
    source = 'a = "x\\"{"\nb = \'\'\'multi\n{ line\'\'\'\nc = 1 /* block {\n} */ d = 2\n// tail {\n'
    stripped = strip_code_noise(source)
    assert stripped.count("\n") == source.count("\n")
    assert "{" not in stripped.replace("\n", "")


def test_intra_candidate_duplicate_windows_only_attribute_changed_lines() -> None:
    block = "\n".join(f"alpha_{index} = compute({index})" for index in range(6)) + "\n"
    first = ("quwoquan_ops/ci/a.py", ("head = 1\n" + block).encode(), frozenset(range(1, 8)))
    second = ("quwoquan_ops/ci/b.py", ("other = 2\n" + block).encode(), frozenset({1}))
    result = candidate_duplicate_windows([first, second], block_lines=6)
    assert result["quwoquan_ops/ci/a.py"][0] == frozenset(range(2, 8))
    assert result["quwoquan_ops/ci/a.py"][1] == "quwoquan_ops/ci/b.py"
    # b.py 只改了第 1 行，重复窗口不触及 changed lines，不归责。
    assert "quwoquan_ops/ci/b.py" not in result


def test_intra_candidate_duplication_reaches_candidate_report(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)
    block = "\n".join(f"    value_{index} = load({index})" for index in range(12)) + "\n"
    write(repo, "quwoquan_ops/ci/left.py", "def left():\n" + block)
    write(repo, "quwoquan_ops/ci/right.py", "def right():\n" + block)
    head = commit(repo)
    report = analyze_delta(repo, base=base, head=head, policy_path=policy_path(repo), mode="full")
    candidates = [item for item in report["findings"] if item["code"] == "CODE_HEALTH.DUPLICATION_CANDIDATE"]
    assert {item["path"] for item in candidates} == {"quwoquan_ops/ci/left.py", "quwoquan_ops/ci/right.py"}
    assert all(item["candidateDuplicatedLines"] == 12 and item["baselineDuplicatedLines"] == 0 for item in candidates)
    assert any(item["code"] == "CODE_HEALTH.DUPLICATION_ADVISORY" for item in report["findings"])


def test_deletion_only_file_contributes_no_duplication(tmp_path: Path) -> None:
    repo, _base = init_repo(tmp_path)
    shared = "\n".join(f"setting_{index} = load({index})" for index in range(25)) + "\n"
    write(repo, "quwoquan_ops/ci/constants.py", "HEADER = 1\n" + shared + "TRAILER = 2\n")
    write(repo, "quwoquan_ops/ci/sibling.py", shared)
    base = commit(repo, "baseline with existing clone")
    # 只删一行、不新增：窗口在基线里确实重复，但没有任何“新行”可归责。
    write(repo, "quwoquan_ops/ci/constants.py", "HEADER = 1\n" + shared)
    write(repo, "quwoquan_ops/ci/fresh.py", "\n".join(f"fresh_{index} = {index}" for index in range(30)) + "\n")
    head = commit(repo, "delete trailer")
    report = analyze_delta(repo, base=base, head=head, policy_path=policy_path(repo), mode="full")
    assert not [item for item in report["findings"] if item["code"] == "CODE_HEALTH.DUPLICATION_CANDIDATE"]
    assert report["summary"]["duplicatedLines"] == 0
    assert report["summary"]["measuredNewLines"] == 30

    index = duplicate_window_index([("quwoquan_ops/ci/sibling.py", shared.encode())], block_lines=6)
    covered, source = duplicate_windows(shared.encode(), block_lines=6, baseline_index=index, changed_lines=frozenset())
    assert (covered, source) == (frozenset(), None)


def test_notes_code_lists_match_engine_terminals() -> None:
    notes = load_policy(POLICY)["notes"]
    source = "\n".join(path.read_text(encoding="utf-8") for path in _DELTA_SOURCES)
    emitted = set(re.findall(r'"(CODE_HEALTH\.[A-Z_]+)"', source)) - _INFORMATIONAL_CODES
    assert emitted == set(notes["advisory_only_codes"]) | set(notes["blocking_codes"])
    for code in notes["blocking_codes"]:
        assert re.search(rf'"{re.escape(code)}",\s*[^,]+,\s*"GATE_BLOCK"', source), code
    for code in notes["advisory_only_codes"]:
        assert re.search(
            rf'"{re.escape(code)}",\s*[^,]+,\s*"PR_WARN"|"code": "{re.escape(code)}"[\s\S]{{0,200}}?"terminal": "PR_WARN"',
            source,
        ), code


def test_size_observation_tiers_cover_advisory_and_block() -> None:
    policy = load_policy(POLICY)
    tiers = policy["report"]["size_observation_tiers"]
    assert policy["thresholds"]["file_lines"]["advisory"] in tiers
    assert policy["thresholds"]["file_lines"]["block"] in tiers


def test_cli_stdout_leads_with_blockers_and_debt_delta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    repo, _base = init_repo(tmp_path)
    block = load_policy(policy_path(repo))["thresholds"]["file_lines"]["block"]
    write(repo, "quwoquan_ops/ci/huge.py", "value = 1\n" * (block + 1))
    monkeypatch.setattr(verify_incremental_code_health, "ROOT", repo)
    summary = tmp_path / "summary.md"
    code = verify_incremental_code_health.main(["--mode", "fast", "--output", str(tmp_path / "report.json"), "--summary-markdown", str(summary)])
    out = capsys.readouterr().out
    assert code == 1
    assert out.startswith("# Code Health Delta — GATE_BLOCK")
    assert "recovery: `split_or_reduce_new_file_below_block_threshold`" in out
    assert "## 债务 delta" in out and "- 新越过 block 的文件: +1" in out
    assert summary.read_text(encoding="utf-8") == out.split("verify_incremental_code_health:")[0]


def test_split_analysis_requires_multiple_owner_scopes(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)
    body = "\n".join(f"value_{index} = {index}" for index in range(1100)) + "\n"
    write(repo, "quwoquan_ops/ci/single_scope.py", body)
    head = commit(repo, "single scope")
    report = analyze_delta(repo, base=base, head=head, policy_path=policy_path(repo), mode="fast")
    codes = {item["code"] for item in report["findings"]}
    assert "CODE_HEALTH.CHANGE_SIZE_ADVISORY" in codes
    assert "CODE_HEALTH.SPLIT_ANALYSIS_REQUIRED" not in codes

    write(repo, "quwoquan_ops/gate/second_scope.py", body)
    write(repo, "quwoquan_data/scripts/content/third_scope.py", "if __name__ == '__main__':\n    pass\n" + body)
    spread = commit(repo, "three scopes")
    report = analyze_delta(repo, base=base, head=spread, policy_path=policy_path(repo), mode="fast")
    split = next(item for item in report["findings"] if item["code"] == "CODE_HEALTH.SPLIT_ANALYSIS_REQUIRED")
    assert split["terminal"] == "PR_WARN"
    assert len(split["measure"]["scopes"]) == 3
    assert report["summary"]["handwrittenScopes"] == split["measure"]["scopes"]


def test_relative_import_counts_as_repository_entry(tmp_path: Path) -> None:
    repo, _base = init_repo(tmp_path)
    write(repo, "quwoquan_data/scripts/content/pkg/__init__.py", "")
    write(repo, "quwoquan_data/scripts/content/pkg/helper.py", "VALUE = 1\n")
    write(repo, "quwoquan_data/scripts/content/pkg/consumer.py", "from .helper import VALUE\n\nprint(VALUE)\n")
    write(repo, "quwoquan_data/scripts/content/pkg/orphan.py", "ORPHAN = 1\n")
    head = commit(repo)
    assert has_repository_entry(repo, head, "quwoquan_data/scripts/content/pkg/helper.py")
    assert not has_repository_entry(repo, head, "quwoquan_data/scripts/content/pkg/orphan.py")


def test_auto_base_resolves_merge_base_with_dev_reference(tmp_path: Path) -> None:
    repo, base = init_repo(tmp_path)
    git(repo, "branch", "dev1.0")
    write(repo, "quwoquan_ops/ci/lane_work.py", "value = 1\n")
    lane_head = commit(repo, "lane work")
    git(repo, "checkout", "-q", "dev1.0")
    write(repo, "README.md", "dev moved on\n")
    commit(repo, "dev advance")
    git(repo, "checkout", "-q", "-")
    resolved = resolve_auto_base(repo)
    assert resolved == {"ref": "refs/heads/dev1.0", "sha": base}

    report = analyze_delta(repo, base="auto", head="HEAD", policy_path=policy_path(repo), mode="fast", working_tree=True)
    assert report["baseResolution"] == {"requested": "auto", "ref": "refs/heads/dev1.0", "sha": base}
    assert report["baseSha"] == base
    assert report["headSha"] == lane_head
    assert "quwoquan_ops/ci/lane_work.py" in report["changedPaths"]


def test_auto_base_fails_closed_without_dev_reference(tmp_path: Path) -> None:
    repo, _base = init_repo(tmp_path)
    with pytest.raises(BaseResolutionError, match="git fetch origin dev1.0"):
        resolve_auto_base(repo)
    with pytest.raises(BaseResolutionError):
        analyze_delta(repo, base="auto", head="HEAD", policy_path=policy_path(repo), mode="fast", working_tree=True)
