"""argparse 与 main。"""
from __future__ import annotations

import argparse

from .commands import command_candidate_evidence, command_change_report, command_context, command_overview
from .verify import command_verify

_DESCRIPTION = """从目录与 Markdown 直接读取、校验和展示特性树。

本工具刻意不支持 tree/index/registry/acceptance/changelog 兼容读取。
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=_DESCRIPTION)
    subparsers = parser.add_subparsers(dest="command", required=True)
    context_parser = subparsers.add_parser("context", help="生成目标最小完整上下文")
    context_parser.add_argument("--target", required=True)
    context_parser.add_argument(
        "--format",
        choices=("manifest", "expanded"),
        default="manifest",
        help="默认仅生成渐进加载 manifest；expanded 仅供人工诊断",
    )
    context_parser.set_defaults(func=command_context)
    candidate_parser = subparsers.add_parser("candidate-evidence", help="生成 POST candidate evidence")
    candidate_parser.add_argument("--owner-identity", required=True)
    candidate_parser.add_argument("--changed-path", action="append", required=True)
    candidate_parser.set_defaults(func=command_candidate_evidence)
    overview_parser = subparsers.add_parser("overview", help="生成动态特性树总览")
    overview_parser.set_defaults(func=command_overview)
    change_parser = subparsers.add_parser("change-report", help="生成当前 Git 增量影响报告")
    change_parser.set_defaults(func=command_change_report)
    verify_parser = subparsers.add_parser("verify", help="校验目录原生特性树")
    verify_parser.add_argument("--changes", action="store_true", help="同时阻断未归属 Git 变更")
    verify_parser.set_defaults(func=command_verify)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)
