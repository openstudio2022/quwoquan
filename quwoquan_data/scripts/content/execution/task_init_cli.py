"""确定性 task init 的 CLI 适配器。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from content.execution.task_init import TaskInitConflict, initialize_task


def handle_task_init(args: argparse.Namespace) -> None:
    try:
        result = initialize_task(
            carrier_demand_path=Path(args.carrier_demand),
            candidate_bindings_path=Path(args.candidate_bindings),
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        print(f"task init 拒绝：{exc}", file=sys.stderr)
        raise SystemExit(3 if isinstance(exc, TaskInitConflict) else 2) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


def register_task_init_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("init", help="从两份已准备输入原子创建 execution")
    parser.add_argument("--carrier-demand", required=True)
    parser.add_argument("--candidate-bindings", required=True)
    parser.set_defaults(handler=handle_task_init)


__all__ = ["handle_task_init", "register_task_init_parser"]
