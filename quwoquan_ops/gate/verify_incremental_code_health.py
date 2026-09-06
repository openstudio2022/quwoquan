#!/usr/bin/env python3
"""Thin CLI for the canonical incremental code-health delta."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate.code_health_delta.engine import analyze_delta
from quwoquan_ops.gate.code_health_delta.git_delta import in_progress_merge_parents
from quwoquan_ops.gate.code_health_delta.render import render_candidate


def resolve_merge_parents(
    repo: Path, *, working_tree: bool, explicit: list[str]
) -> list[str]:
    """Other parents whose bytes this candidate inherits rather than authors.

    working-tree 模式读 MERGE_HEAD，无歧义。commit 模式不做自动推导：一次真实整合并
    与 GitHub pull_request 的合成合并提交在结构上完全相同（parents=[base_tip, other]），
    后者若被当作"继承自 other"会把整个 PR 的改动都丢弃并恒 PASS。调用方必须显式声明。
    """
    if working_tree:
        if explicit:
            raise ValueError("--merge-parent 只用于 commit range；working-tree 模式自动读取 MERGE_HEAD")
        return in_progress_merge_parents(repo)
    return list(explicit)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--base", help="Commit-range base, or `auto` for the merge-base of HEAD and dev1.0; omit base/head for the current worktree relative to HEAD")
    value.add_argument("--head", help="Commit-range head; requires --base")
    value.add_argument("--mode", choices=("fast", "full"), default="full")
    value.add_argument("--changed-file", action="append", default=[])
    value.add_argument("--policy", type=Path, default=ROOT / "quwoquan_ops/policies/code_health_policy.yaml")
    value.add_argument("--output", type=Path)
    value.add_argument("--summary-markdown", type=Path, help="Also write the Markdown projection to this path")
    value.add_argument("--working-tree", action="store_true", help="Compare current worktree materialization to --base; default when base/head are omitted")
    value.add_argument("--index-only", action="store_true", help="Compare staged index materialization to --base; requires --working-tree")
    value.add_argument(
        "--merge-parent", action="append", default=[],
        help="Exact SHA of another parent whose bytes --head inherits verbatim (repeatable, commit range only). "
             "Never inferred: a GitHub pull_request synthetic merge is structurally identical to a real merge.",
    )
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if (args.base is None) != (args.head is None):
            raise ValueError("--base and --head must be provided together")
        if args.index_only and not args.working_tree:
            raise ValueError("--index-only requires --working-tree")
        explicit_range = args.base is not None
        working_tree = args.working_tree or not explicit_range
        report = analyze_delta(
            ROOT,
            base=args.base or "HEAD",
            head=args.head or "HEAD",
            policy_path=args.policy,
            mode=args.mode,
            explicit_paths=args.changed_file or None,
            working_tree=working_tree,
            index_only=args.index_only,
            merge_parents=resolve_merge_parents(
                ROOT, working_tree=working_tree, explicit=args.merge_parent,
            ),
        )
    except Exception as exc:  # fail closed at the public boundary
        print(f"verify_incremental_code_health: GATE_BLOCK: {exc}", file=sys.stderr)
        return 2
    fingerprint = report["evidenceFingerprint"]["digest"].removeprefix("sha256:")
    output = args.output or ROOT / ".qwq_output/env/repo/runs/code-health" / fingerprint / "report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.summary_markdown is not None:
        args.summary_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.summary_markdown.write_text(render_candidate(report), encoding="utf-8")
    # 开发者直接在 stdout 看到 blocker 与 recovery，不必打开 JSON。
    print(render_candidate(report), end="")
    print(f"verify_incremental_code_health: {report['terminal']} findings={report['summary']['findingCount']} output={output}")
    if report["terminal"] in {"PASS", "PR_WARN"}:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
