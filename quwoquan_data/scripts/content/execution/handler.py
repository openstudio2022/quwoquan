"""六步 producer 的 task 控制面：init、acquire、seal。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from content.execution.seal import STAGES, SealConflict, seal_stage
from content.execution.task_init_cli import register_task_init_parser
from content.source.acquire import acquire


def _handle_acquire(args: argparse.Namespace) -> None:
    try:
        result = acquire(
            execution_id=args.execution_id,
            target_ref=args.target_ref,
            request_path=Path(args.input),
        )
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"[task acquire] GATE_BLOCK {exc}") from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _handle_seal(args: argparse.Namespace) -> None:
    try:
        result = seal_stage(execution_id=args.execution_id, stage=args.stage, input_path=Path(args.input))
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        print(f"[task seal] GATE_BLOCK {exc}", file=sys.stderr)
        raise SystemExit(3 if isinstance(exc, SealConflict) else 2) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("task", help="六步 producer 内核：init / acquire / seal")
    commands = parser.add_subparsers(dest="task_command")
    register_task_init_parser(commands)

    acquire_parser = commands.add_parser(
        "acquire",
        help="按 AI 点名的 URL 与相关性理由机械取得来源字节、权利硬事实与媒体探测",
    )
    acquire_parser.add_argument("--execution-id", required=True)
    acquire_parser.add_argument("--target-ref", required=True)
    acquire_parser.add_argument("--input", required=True, help="acquire_request JSON")
    acquire_parser.set_defaults(handler=_handle_acquire)

    seal_parser = commands.add_parser(
        "seal",
        help="校验当前步骤硬事实并 create-once 写 receipt（1.download / 4.draft / 5.review）",
    )
    seal_parser.add_argument("--execution-id", required=True)
    seal_parser.add_argument("--stage", required=True, choices=STAGES)
    seal_parser.add_argument("--input", required=True, help="seal_input JSON：actor 与 verdict")
    seal_parser.set_defaults(handler=_handle_seal)
