"""最小 stage-open / stage-close CLI。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from content.execution.stage_receipt import (
    RECEIPT_STAGES,
    StageConflict,
    close_stage,
    open_stage,
)


def _run(command: str, operation: object, args: argparse.Namespace) -> None:
    try:
        path = operation(args.execution_id, args.stage, Path(args.input))
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        print(f"{command} 拒绝：{exc}", file=sys.stderr)
        raise SystemExit(3 if isinstance(exc, StageConflict) else 2) from exc
    print(json.dumps({"executionId": args.execution_id, "stage": args.stage, "artifact": str(path)}, ensure_ascii=False, indent=2))


def _handle_stage_open(args: argparse.Namespace) -> None:
    _run("stage-open", open_stage, args)


def _handle_stage_close(args: argparse.Namespace) -> None:
    _run("stage-close", close_stage, args)


def register_stage_receipt_parsers(commands: argparse._SubParsersAction) -> None:
    for name, handler, help_text in (
        ("stage-open", _handle_stage_open, "校验并冻结 stage 输入引用"),
        ("stage-close", _handle_stage_close, "校验并冻结 stage 结果 receipt"),
    ):
        parser = commands.add_parser(name, help=help_text)
        parser.add_argument("--execution-id", required=True)
        parser.add_argument("--stage", required=True, choices=RECEIPT_STAGES)
        parser.add_argument("--input", required=True, help="结构化 JSON 输入文件")
        parser.set_defaults(handler=handler)


__all__ = ["register_stage_receipt_parsers"]
