"""stackctl `assistant-skill-package` 子命令域。

从 stackctl.py 逐字迁出 argparse 表面与编排胶水；Alpha test_live
Assistant Skill package 的构建与发布逻辑保持在
`quwoquan_ops/cli/lib/local_assistant_skill_package_publication.py`。
stackctl 命名空间符号一律经函数内延迟导入 `_stackctl` 属性访问，
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
from typing import Any


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    assistant_skill_package_parser = subparsers.add_parser(
        "assistant-skill-package",
        help="构建并发布不可提升的 Alpha test_live Assistant Skill package",
    )
    assistant_skill_package_parser.add_argument(
        "--target",
        choices=("alpha-local",),
        required=True,
    )
    assistant_skill_package_parser.add_argument(
        "--report-dir",
        default=argparse.SUPPRESS,
    )


def command_assistant_skill_package(
    args: argparse.Namespace,
) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    if str(args.target) != "alpha-local":
        return {
            "exitCode": 2,
            "summary": "stackctl assistant-skill-package is GATE_BLOCK",
            "details": ["only alpha-local test_live is supported"],
        }
    report_dir = _stackctl.resolve_report_dir(args, "alpha", str(args.target))
    try:
        receipt = _stackctl.publish_alpha_test_live(report_dir)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return {
            "exitCode": 2,
            "summary": "stackctl assistant-skill-package is GATE_BLOCK",
            "details": [str(exc)],
            "reportDir": _stackctl.relpath(report_dir),
        }
    return {
        "exitCode": 0,
        "summary": "Alpha test_live Assistant Skill package published",
        "details": [
            f"sourceDigest={receipt['sourceDigest']}",
            f"publicationDigest={receipt['publicationDigest']}",
            "promotionEligibility=GATE_BLOCK",
        ],
        "reportDir": _stackctl.relpath(report_dir),
        "receipt": receipt,
    }
