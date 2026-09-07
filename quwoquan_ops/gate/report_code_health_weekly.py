#!/usr/bin/env python3
"""Generate the canonical weekly report-only code health observation."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate.code_health_delta.policy import load_policy
from quwoquan_ops.gate.code_health_delta.render import render_weekly
from quwoquan_ops.gate.code_health_delta.weekly import analyze_weekly


def _load_previous(paths: list[Path]) -> list[dict]:
    reports = []
    for path in paths:
        try:
            reports.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"previous weekly report 无法读取 {path}: {exc}") from exc
    return reports


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--policy", type=Path, default=ROOT / "quwoquan_ops/policies/code_health_policy.yaml")
    parser.add_argument("--delivery-runs", type=Path)
    parser.add_argument("--cloc", default="cloc")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--previous", type=Path, action="append", default=[],
        help="Earlier weekly report.json files (any order); used for ratchet direction and hotspot persistence",
    )
    parser.add_argument("--summary-markdown", type=Path, help="Also write the Markdown projection to this path")
    args = parser.parse_args(argv)
    try:
        pages = None if args.delivery_runs is None else json.loads(args.delivery_runs.read_text(encoding="utf-8"))
        report = analyze_weekly(
            ROOT, head=args.head, policy=load_policy(args.policy), cloc_executable=args.cloc,
            delivery_run_pages=pages, previous_reports=_load_previous(args.previous),
        )
        output = args.output or ROOT / ".qwq_output/env/repo/runs/code-health/weekly" / report["identityDigest"].removeprefix("sha256:") / "report.json"
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
