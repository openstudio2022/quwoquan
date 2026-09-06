"""Code Health Delta 判据精度：分类、brace 解析、candidate 内重复、owner-scope 拆分与入口识别。

spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/incremental-code-health-governance/spec.md#gwt-001.t1
spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/incremental-code-health-governance/spec.md#gwt-001.t3
spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/incremental-code-health-governance/spec.md#gwt-001.t4
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from quwoquan_ops.gate.code_health_delta.base_ref import BaseResolutionError, resolve_auto_base
from quwoquan_ops.gate.code_health_delta.classification import classify_path
from quwoquan_ops.gate.code_health_delta.engine import analyze_delta
from quwoquan_ops.gate.code_health_delta.metrics import (
    candidate_duplicate_windows, function_metrics, has_repository_entry, strip_code_noise,
)
from quwoquan_ops.gate.code_health_delta.policy import load_policy
from quwoquan_ops.tests.support.code_health_delta_test_support import (
    POLICY, commit, git, init_repo, policy_path, write,
)


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
