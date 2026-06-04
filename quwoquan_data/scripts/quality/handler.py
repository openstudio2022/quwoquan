"""qwq-data quality — 数据质量治理入口。"""
from __future__ import annotations

import argparse
from pathlib import Path

from _common.paths import DATA_ROOT
from quality.dirty_data import delete_dirty_data, scan_dirty_data, write_dirty_report


def handle_dirty_scan(args: argparse.Namespace) -> None:
    rows = scan_dirty_data()
    deleted = delete_dirty_data(rows) if args.delete else []
    report_path = Path(args.report or (DATA_ROOT / "runtime" / "reports" / "dirty_data_report.json"))
    write_dirty_report(report_path, rows, deleted)
    print(f"[quality dirty-scan] issues={len(rows)} deleted={len(deleted)} report={report_path}")
    if rows and args.fail_on_issues and not args.delete:
        raise SystemExit(1)


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("quality", help="数据质量治理：dirty-scan")
    sub = p.add_subparsers(dest="quality_command")

    pd = sub.add_parser("dirty-scan", help="扫描/删除历史脏实体主页和 post 包")
    pd.add_argument("--delete", action="store_true", help="删除脏 page.md/manifest/assets 或 post package")
    pd.add_argument("--report")
    pd.add_argument("--fail-on-issues", action="store_true")
    pd.set_defaults(handler=handle_dirty_scan)

    def _dispatch(args: argparse.Namespace) -> None:
        if not getattr(args, "quality_command", None):
            p.print_help()
            raise SystemExit(1)

    p.set_defaults(handler=_dispatch)
