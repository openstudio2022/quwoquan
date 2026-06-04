"""qwq-data homepage-assets — scan/repair entity homepage image assets."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _common.paths import DATA_ROOT
from homepage_assets.repair import repair_homepage, scan_homepages, write_report
from quality.dirty_data import entity_homepage_dirty_issues

DEFAULT_REPORT = DATA_ROOT / "runtime" / "reports" / "homepage_assets_report.json"


def handle_homepage_assets(args: argparse.Namespace) -> None:
    issues = scan_homepages(include_runtime=args.include_runtime, include_publish=args.include_publish)
    if args.dirty_only:
        issues = [
            issue
            for issue in issues
            if entity_homepage_dirty_issues(issue.issues)
        ]
    repairs = []
    if args.repair:
        for issue in issues:
            repairs.append(repair_homepage(issue))
    report_path = Path(args.report or DEFAULT_REPORT)
    write_report(report_path, issues, repairs)
    print(
        f"[homepage-assets] issues={len(issues)} repairs={len(repairs)} report={report_path}"
    )
    remaining = [row for row in repairs if row.get("remainingIssues")]
    if remaining:
        for row in remaining[:20]:
            print(
                f"[homepage-assets] remaining {row['entityRef']}: {row['remainingIssues']}",
                file=sys.stderr,
            )
        raise SystemExit(1)
    if args.fail_on_issues and issues and not args.repair:
        raise SystemExit(1)


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("homepage-assets", help="Scan/repair entity homepage image asset closure")
    p.add_argument("--repair", action="store_true", help="Rewrite affected page.md/manifest/assets")
    p.add_argument("--report", help=f"Report path (default: {DEFAULT_REPORT})")
    p.add_argument("--fail-on-issues", action="store_true", help="Exit non-zero when scan finds issues")
    p.add_argument("--dirty-only", action="store_true", help="Only report polluted/unsafe/stale homepage asset issues")
    p.add_argument("--include-runtime", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--include-publish", action=argparse.BooleanOptionalAction, default=True)
    p.set_defaults(handler=handle_homepage_assets)
