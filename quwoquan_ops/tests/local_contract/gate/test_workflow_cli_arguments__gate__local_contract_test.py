"""workflow 调用仓内 CLI 的 required 参数完整性合同。

spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md#gwt-002
spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-002
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from quwoquan_ops.gate import verify_workflow_cli_arguments as gate

ROOT = Path(__file__).resolve().parents[4]


def _repo(tmp_path: Path, script_body: str, workflow_body: str) -> Path:
    root = tmp_path / "repo"
    (root / "quwoquan_ops/ci").mkdir(parents=True)
    (root / ".github/workflows").mkdir(parents=True)
    (root / "quwoquan_ops/ci/tool.py").write_text(textwrap.dedent(script_body), encoding="utf-8")
    (root / ".github/workflows/w.yml").write_text(textwrap.dedent(workflow_body), encoding="utf-8")
    gate._spec_for.cache_clear()
    return root


FLAT_SCRIPT = """
    import argparse
    def main():
        parser = argparse.ArgumentParser()
        parser.add_argument("--plan", required=True)
        parser.add_argument("--sha", required=True)
        parser.add_argument("--tree", required=True)
        parser.add_argument("--verbose", action="store_true")
        parser.parse_args()
"""


def test_missing_required_option_is_a_finding(tmp_path: Path) -> None:
    root = _repo(tmp_path, FLAT_SCRIPT, """
        jobs:
          j:
            steps:
              - run: |
                  set -euo pipefail
                  python3 quwoquan_ops/ci/tool.py \\
                    --plan "$ROOT/plan.json" --sha "$HEAD_SHA"
    """)
    issues = gate.verify(root)
    assert len(issues) == 1
    assert "quwoquan_ops/ci/tool.py invoked without required --tree" in issues[0]
    assert issues[0].startswith(".github/workflows/w.yml:")


def test_complete_invocation_and_option_values_from_variables_pass(tmp_path: Path) -> None:
    root = _repo(tmp_path, FLAT_SCRIPT, """
        jobs:
          j:
            steps:
              - run: |
                  python3 -B quwoquan_ops/ci/tool.py --plan "$P" --sha "$S" --tree=sha1:abc
    """)
    assert gate.verify(root) == []


def test_subcommand_required_options_are_attributed_per_subcommand(tmp_path: Path) -> None:
    root = _repo(tmp_path, """
        import argparse
        def _parser():
            parser = argparse.ArgumentParser()
            sub = parser.add_subparsers(dest="command", required=True)
            pull = sub.add_parser("materialize")
            pull.add_argument("--ref", required=True)
            pull.add_argument("--output-file", required=True)
            push = sub.add_parser("publish")
            push.add_argument("--fact-file", required=True)
            push.add_argument("--repository", required=True)
            return parser
    """, """
        jobs:
          j:
            steps:
              - run: |
                  python3 quwoquan_ops/ci/tool.py materialize --ref "$R" --output-file "$O"
                  python3 quwoquan_ops/ci/tool.py publish --fact-file "$F"
    """)
    issues = gate.verify(root)
    assert issues == [
        ".github/workflows/w.yml: quwoquan_ops/ci/tool.py invoked without required "
        "--repository; argparse exits 2 at runtime"
    ]


@pytest.mark.parametrize(
    "command",
    (
        'python3 quwoquan_ops/ci/tool.py "${args[@]}"',
        'python3 quwoquan_ops/ci/tool.py --plan p $EXTRA',
        'OUT="$(python3 quwoquan_ops/ci/tool.py --plan p)"',
        'python3 quwoquan_ops/ci/tool.py --plan p | tee log',
    ),
    ids=("array-expansion", "bare-variable", "command-substitution", "pipe-does-not-hide-missing"),
)
def test_opaque_forms_are_skipped_but_pipes_still_check(tmp_path: Path, command: str) -> None:
    root = _repo(tmp_path, FLAT_SCRIPT, f"""
        jobs:
          j:
            steps:
              - run: |
                  {command}
    """)
    issues = gate.verify(root)
    if "| tee" in command:
        assert len(issues) == 1 and "--sha, --tree" in issues[0]
    else:
        assert issues == []


def test_heredoc_body_and_non_argparse_scripts_are_not_parsed(tmp_path: Path) -> None:
    root = _repo(tmp_path, """
        import sys
        print(sys.argv)
    """, """
        jobs:
          j:
            steps:
              - run: |
                  python3 - <<'PY'
                  python3 quwoquan_ops/ci/tool.py
                  PY
                  python3 quwoquan_ops/ci/tool.py
    """)
    assert gate.verify(root) == []


def test_dynamic_required_names_make_the_script_undecidable(tmp_path: Path) -> None:
    """运行期命名的 required 选项使静态比对既不能证明完整也不能证明缺失。

    这不是放行：这类脚本必须由自身 local_contract 与 hosted 运行承担合同；
    门禁只对可静态判定的调用负责，并把边界写进 ParserSpec.dynamic_required。
    """
    root = _repo(tmp_path, """
        import argparse
        ENVS = ("alpha", "beta")
        def _parser():
            parser = argparse.ArgumentParser()
            parser.add_argument("--repository", required=True)
            for env in ENVS:
                parser.add_argument(f"--expected-{env}-signer", required=True)
            return parser
    """, """
        jobs:
          j:
            steps:
              - run: python3 quwoquan_ops/ci/tool.py --expected-alpha-signer a
    """)
    spec = gate.parser_spec(root / "quwoquan_ops/ci/tool.py")
    assert spec is not None and spec.dynamic_required is True
    assert gate.missing_required(
        "quwoquan_ops/ci/tool.py", ["--expected-alpha-signer", "a"], root=root
    ) is None
    assert gate.verify(root) == []


def test_only_filter_restricts_to_staged_workflows(tmp_path: Path) -> None:
    root = _repo(tmp_path, FLAT_SCRIPT, """
        jobs:
          j:
            steps:
              - run: python3 quwoquan_ops/ci/tool.py --plan p
    """)
    (root / ".github/workflows/other.yml").write_text(
        "jobs:\n  k:\n    steps:\n      - run: python3 quwoquan_ops/ci/tool.py --plan p\n",
        encoding="utf-8",
    )
    assert len(gate.verify(root)) == 2
    assert len(gate.verify(root, only=frozenset({".github/workflows/other.yml"}))) == 1
    assert gate.verify(root, only=frozenset({".github/workflows/absent.yml"})) == []


def test_repository_promotion_gate_boundary_call_is_complete() -> None:
    """G2 的回归锚：promotion_verify 对 verify_ci_changed_boundary 必须传全四个 required。"""
    issues = gate.verify(ROOT, only=frozenset({".github/workflows/delivery-gate.yml"}))
    assert not any("verify_ci_changed_boundary.py" in issue for issue in issues), issues
