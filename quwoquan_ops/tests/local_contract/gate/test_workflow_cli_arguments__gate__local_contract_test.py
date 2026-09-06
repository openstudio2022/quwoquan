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


def test_constant_loop_fstring_required_is_rendered_not_skipped(tmp_path: Path) -> None:
    """`for x in <常量元组>` 内的 f-string required 必须展开成确定名字。

    上一版把这种脚本整体判为 dynamic_required 跳过，于是 delivery-gate.yml 对
    integration_qualification.py 漏传 6 个 required 参数在门禁上是绿的。
    """
    root = _repo(tmp_path, """
        import argparse
        ENVS = ("alpha", "beta")
        def _parser():
            parser = argparse.ArgumentParser()
            parser.add_argument("--repository", required=True)
            for env in ENVS:
                parser.add_argument(f"--expected-{env}-signer", required=True)
            for name in ("request", "material"):
                parser.add_argument(f"--{name}", required=True)
            return parser
    """, """
        jobs:
          j:
            steps:
              - run: python3 quwoquan_ops/ci/tool.py --expected-alpha-signer a
    """)
    spec = gate.parser_spec(root / "quwoquan_ops/ci/tool.py")
    assert spec is not None and spec.dynamic_required is False
    assert spec.top_level == frozenset({
        "--repository", "--expected-alpha-signer", "--expected-beta-signer",
        "--request", "--material",
    })
    assert gate.missing_required(
        "quwoquan_ops/ci/tool.py", ["--expected-alpha-signer", "a"], root=root
    ) == ["--expected-beta-signer", "--material", "--repository", "--request"]
    assert len(gate.verify(root)) == 1


@pytest.mark.parametrize(
    ("iterable", "argument"),
    (
        ("os.environ['ENVS'].split(',')", "f'--{env}'"),
        ("ENVS", "f'--{env}-{suffix()}'"),
        ("ENVS", "f'--{env!r}'"),
        ("ENVS", "name_for(env)"),
    ),
    ids=("runtime-iterable", "extra-call-interpolation", "conversion", "non-fstring-expression"),
)
def test_truly_dynamic_required_names_stay_undecidable(
    tmp_path: Path, iterable: str, argument: str,
) -> None:
    """迭代源或插值不是常量时仍不可判定：既不报缺失也不宣称完整。"""
    root = _repo(tmp_path, f"""
        import argparse, os
        ENVS = ("alpha", "beta")
        def suffix():
            return "x"
        def name_for(env):
            return "--" + env
        def _parser():
            parser = argparse.ArgumentParser()
            parser.add_argument("--repository", required=True)
            for env in {iterable}:
                parser.add_argument({argument}, required=True)
            return parser
    """, """
        jobs:
          j:
            steps:
              - run: python3 quwoquan_ops/ci/tool.py --alpha a
    """)
    spec = gate.parser_spec(root / "quwoquan_ops/ci/tool.py")
    assert spec is not None and spec.dynamic_required is True
    assert gate.missing_required("quwoquan_ops/ci/tool.py", ["--alpha", "a"], root=root) is None
    assert gate.verify(root) == []


INTEGRATION_QUALIFICATION_PARSER = """
    import argparse
    from pathlib import Path
    _ENVIRONMENTS = ("alpha", "beta", "gamma")
    def _parser() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--repository", required=True, type=Path)
        parser.add_argument("--store-root", required=True, type=Path)
        parser.add_argument("--qualification-ref", required=True)
        parser.add_argument("--qualification-digest", required=True)
        parser.add_argument("--expected-dev-head", required=True)
        parser.add_argument("--expected-dev-tree", required=True)
        parser.add_argument("--verified-at", required=True)
        parser.add_argument("--qualification-verification-key-env", required=True)
        parser.add_argument("--expected-qualification-signer-identity", required=True)
        parser.add_argument("--environment-verification-key-env", required=True)
        for environment in _ENVIRONMENTS:
            parser.add_argument(f"--expected-{environment}-signer-identity", required=True)
        return parser
"""

# 7b848b8c3 及之前 delivery-gate.yml promotion_verify 的原调用：漏 6 个 required。
INTEGRATION_QUALIFICATION_OLD_CALL = """
    jobs:
      promotion_verify:
        steps:
          - run: |
              set -euo pipefail
              python3 quwoquan_ops/ci/tool.py \\
                --repository "$GITHUB_WORKSPACE" --store-root "$CONTROL_ROOT" \\
                --qualification-ref "$QUALIFICATION_LOCAL_REF" \\
                --qualification-digest "$QUALIFICATION_LOCAL_DIGEST" \\
                --expected-dev-head "$HEAD_SHA" --expected-dev-tree "$HEAD_TREE" \\
                --verified-at "$PROMOTION_READY_AT"
"""

INTEGRATION_QUALIFICATION_COMPLETE_CALL = INTEGRATION_QUALIFICATION_OLD_CALL.rstrip("\n") + """ \\
                --qualification-verification-key-env QWQ_INTEGRATION_QUALIFICATION_SIGNING_KEY \\
                --expected-qualification-signer-identity "$QUALIFICATION_SIGNER_IDENTITY" \\
                --environment-verification-key-env QWQ_ENVIRONMENT_ACCEPTANCE_SIGNING_KEY \\
                --expected-alpha-signer-identity "$ENVIRONMENT_SIGNER_IDENTITY" \\
                --expected-beta-signer-identity "$ENVIRONMENT_SIGNER_IDENTITY" \\
                --expected-gamma-signer-identity "$ENVIRONMENT_SIGNER_IDENTITY"
"""


def test_integration_qualification_old_call_lists_all_six_missing_required(tmp_path: Path) -> None:
    """G2 盲点回归锚：对 7b848b8c3 的原调用必须精确列出 6 个缺参，而不是整体跳过。"""
    root = _repo(tmp_path, INTEGRATION_QUALIFICATION_PARSER, INTEGRATION_QUALIFICATION_OLD_CALL)
    issues = gate.verify(root)
    assert len(issues) == 1
    assert issues[0].endswith(
        "invoked without required --environment-verification-key-env, "
        "--expected-alpha-signer-identity, --expected-beta-signer-identity, "
        "--expected-gamma-signer-identity, --expected-qualification-signer-identity, "
        "--qualification-verification-key-env; argparse exits 2 at runtime"
    )


def test_integration_qualification_complete_call_is_green(tmp_path: Path) -> None:
    root = _repo(tmp_path, INTEGRATION_QUALIFICATION_PARSER, INTEGRATION_QUALIFICATION_COMPLETE_CALL)
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
