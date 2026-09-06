#!/usr/bin/env python3
"""Generate the canonical weekly report-only code health observation."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate.code_health_delta.policy import load_policy
from quwoquan_ops.gate.code_health_delta.render import render_weekly
from quwoquan_ops.gate.code_health_delta.weekly import WEEKLY_SCHEMA, analyze_weekly


LOCAL_HISTORY_LIMIT = 8


def _load_previous(paths: list[Path]) -> list[dict]:
    reports = []
    for path in paths:
        try:
            reports.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"previous weekly report 无法读取 {path}: {exc}") from exc
    return reports


def discover_local_previous(weekly_root: Path, *, current_head: str, limit: int = LOCAL_HISTORY_LIMIT) -> list[Path]:
    """本地既有 weekly report（不同 head，按 window end 倒序），让本地运行也能给出棘轮方向。"""
    candidates: list[tuple[str, Path]] = []
    for path in sorted(weekly_root.glob("*/report.json")):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(report, dict) or report.get("schema") != WEEKLY_SCHEMA or report.get("headSha") == current_head:
            continue
        candidates.append((str(report["window"]["end"]), path))
    return [path for _, path in sorted(candidates, reverse=True)[:limit]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--policy", type=Path, default=ROOT / "quwoquan_ops/policies/code_health_policy.yaml")
    parser.add_argument("--delivery-runs", type=Path)
    parser.add_argument("--cloc", default="cloc")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--previous", type=Path, action="append", default=[],
        help="Earlier weekly report.json files (any order); omit to discover local reports under the policy report root",
    )
    parser.add_argument("--summary-markdown", type=Path, help="Also write the Markdown projection to this path")
    args = parser.parse_args(argv)
    try:
        pages = None if args.delivery_runs is None else json.loads(args.delivery_runs.read_text(encoding="utf-8"))
        policy = load_policy(args.policy)
        weekly_root = ROOT / policy["report"]["root"] / "weekly"
        head_sha = subprocess.run(
            ["git", "rev-parse", "--verify", f"{args.head}^{{commit}}"], cwd=ROOT, check=True, capture_output=True, text=True,
        ).stdout.strip()
        previous_paths = args.previous or discover_local_previous(weekly_root, current_head=head_sha)
        report = analyze_weekly(
            ROOT, head=args.head, policy=policy, cloc_executable=args.cloc,
            delivery_run_pages=pages, previous_reports=_load_previous(previous_paths),
        )
        output = args.output or weekly_root / report["identityDigest"].removeprefix("sha256:") / "report.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        markdown = render_weekly(report)
        if args.summary_markdown is not None:
            args.summary_markdown.parent.mkdir(parents=True, exist_ok=True)
            args.summary_markdown.write_text(markdown, encoding="utf-8")
        print(markdown)
        print(
            f"code-health-weekly: REPORT_ONLY hotspots={len(report['topHotspots'])} "
            f"history={report['hotspotPersistence']['historyReports']} output={output}"
        )
        return 0
    except Exception as exc:
        print(f"code-health-weekly: FAILED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
