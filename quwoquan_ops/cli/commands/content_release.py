"""stackctl content-release：Ops-owned 环境发布编排入口。"""
from __future__ import annotations

import argparse
import contextlib
import io
import sys
from pathlib import Path
from typing import Any

_DATA_SCRIPTS = Path(__file__).resolve().parents[3] / "quwoquan_data" / "scripts"
if str(_DATA_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_DATA_SCRIPTS))

from quwoquan_ops.cli.lib.content_release_environment.cli import register_content_release_arguments
from quwoquan_ops.cli.lib.content_release_environment.handler import handle_ship


def register_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "content-release",
        help="执行 immutable content release 的 apply/activate/verify/rollback",
    )
    register_content_release_arguments(parser)


def command_content_release(args: argparse.Namespace) -> dict[str, Any]:
    output = io.StringIO()
    try:
        with contextlib.redirect_stdout(output):
            handle_ship(args)
    except SystemExit as exc:
        detail = str(exc)
        return {
            "exitCode": int(exc.code) if isinstance(exc.code, int) else 2,
            "summary": "stackctl content-release is GATE_BLOCK",
            "details": [detail] if detail else [],
        }
    details = [line for line in output.getvalue().splitlines() if line.strip()]
    return {
        "exitCode": 0,
        "summary": f"stackctl content-release {args.release_command} passed",
        "details": details,
    }
