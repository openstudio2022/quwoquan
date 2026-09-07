"""确定性 task init 的 CLI 适配器：一份 round spec 建一轮全部 carrier execution。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from content.execution.task_init import TaskInitConflict, initialize_round


def handle_task_init(args: argparse.Namespace) -> None:
    try:
        result = initialize_round(round_spec_path=Path(args.round))
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        print(f"task init 拒绝：{exc}", file=sys.stderr)
        raise SystemExit(3 if isinstance(exc, TaskInitConflict) else 2) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


def register_task_init_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("init", help="从一份 round spec 原子创建该轮全部 carrier execution")
    parser.add_argument("--round", required=True, help="round_spec JSON：executions 与逐 target 身份")
    parser.set_defaults(handler=handle_task_init)


__all__ = ["handle_task_init", "register_task_init_parser"]
