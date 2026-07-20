"""`qwq-data template` 的唯一 CLI 入口。"""
from __future__ import annotations

import argparse
import json

from content.templates.lint import lint_all


def handle_lint(_args: argparse.Namespace) -> None:
    issues = lint_all()
    report = {
        "schema": "quwoquan_data.template_lint_report",
        "passed": not issues,
        "issueCount": len(issues),
        "issues": issues,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if issues:
        raise SystemExit(1)


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "template",
        help="校验内容模板、蓝图、作者与来源目录",
    )
    commands = parser.add_subparsers(dest="template_command", required=True)
    lint_parser = commands.add_parser("lint", help="执行全部模板合同门")
    lint_parser.set_defaults(handler=handle_lint)


__all__ = ["handle_lint", "register_parser"]
