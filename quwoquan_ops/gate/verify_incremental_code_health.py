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


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--base", help="Commit-range base; omit base/head for the current worktree relative to HEAD")
    value.add_argument("--head", help="Commit-range head; requires --base")
    value.add_argument("--mode", choices=("fast", "full"), default="full")
    value.add_argument("--changed-file", action="append", default=[])
    value.add_argument("--policy", type=Path, default=ROOT / "quwoquan_ops/policies/code_health_policy.yaml")
    value.add_argument("--output", type=Path)
    value.add_argument("--report-only", action="store_true")
    value.add_argument("--working-tree", action="store_true", help="Compare current worktree materialization to --base; default when base/head are omitted")
    value.add_argument("--index-only", action="store_true", help="Compare staged index materialization to --base; requires --working-tree")
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if (args.base is None) != (args.head is None):
            raise ValueError("--base and --head must be provided together")
        if args.index_only and not args.working_tree:
            raise ValueError("--index-only requires --working-tree")
        explicit_range = args.base is not None
        report = analyze_delta(
            ROOT,
            base=args.base or "HEAD",
            head=args.head or "HEAD",
            policy_path=args.policy,
            mode=args.mode,
            explicit_paths=args.changed_file or None,
            working_tree=args.working_tree or not explicit_range,
            index_only=args.index_only,
        )
    except Exception as exc:  # fail closed at the public boundary
        print(f"verify_incremental_code_health: GATE_BLOCK: {exc}", file=sys.stderr)
        return 2
    fingerprint = report["evidenceFingerprint"]["digest"].removeprefix("sha256:")
    output = args.output or ROOT / ".qwq_output/env/repo/runs/code-health" / fingerprint / "report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"verify_incremental_code_health: {report['terminal']} findings={report['summary']['findingCount']} output={output}")
    if args.report_only or report["terminal"] in {"PASS", "PR_WARN"}:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
