"""CLI adapter for deterministic task initialization."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from content.execution.task_init import initialize_task


def handle_task_init(args: argparse.Namespace) -> None:
    try:
        result = initialize_task(
            carrier_demand_path=Path(str(args.carrier_demand)),
            candidate_bindings_path=Path(str(args.candidate_bindings)),
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"[task init] GATE_BLOCK {exc}") from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


def register_task_init_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("init", help="从 confirmed demand 与 immutable candidates 原子创建工作包")
    parser.add_argument("--carrier-demand", required=True)
    parser.add_argument("--candidate-bindings", required=True)
    parser.set_defaults(handler=handle_task_init)


__all__ = ["handle_task_init", "register_task_init_parser"]
