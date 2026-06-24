"""qwq-data audit command family."""
from __future__ import annotations

import argparse
import json


def handle_audit(args: argparse.Namespace) -> None:
    if args.audit_command == "release-integrity":
        from _common.release_integrity import scan_release_integrity

        report = scan_release_integrity(args.release)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not report.get("passed"):
            raise SystemExit(1)
        return
    print("[audit] 需要子命令：release-integrity")
    raise SystemExit(2)


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("audit", help="审计数据工程产物，不写入业务状态")
    sub = p.add_subparsers(dest="audit_command")
    pri = sub.add_parser("release-integrity", help="审计 release 证据链、一稿一用与跨作品资产溯源完整性")
    pri.add_argument("--release", required=True, help="Release ID under release/")
    p.set_defaults(handler=handle_audit)

