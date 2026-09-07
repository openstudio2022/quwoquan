"""六步 producer 的 task 控制面：init、acquire、seal。三条命令都是单阶段、无状态的展开，不推进、不恢复。"""
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
        result = acquire(execution_id=args.execution_id, request_path=Path(args.input))
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        print(f"[task acquire] GATE_BLOCK {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))
    # 逐 target 独立报告：全部成功 0，部分失败 1，清单级失败已在上面以 2 退出。
    if result["failed"]:
        raise SystemExit(1)


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
        help="零网络 ingest：从 AI 已下载的本地来源文件与申报事实机械派生字节摘要、探测、预算派生体与权利记录",
    )
    acquire_parser.add_argument("--execution-id", required=True)
    acquire_parser.add_argument("--input", required=True, help="ingest_manifest JSON：该 execution 逐 target 的本地文件与申报事实")
    acquire_parser.set_defaults(handler=_handle_acquire)

    seal_parser = commands.add_parser(
        "seal",
        help="校验当前步骤硬事实并 create-once 写 receipt（1.download / 4.draft / 5.review；5.review 从 reviews 扇出逐对象 content_review.json）",
    )
    seal_parser.add_argument("--execution-id", required=True)
    seal_parser.add_argument("--stage", required=True, choices=STAGES)
    seal_parser.add_argument("--input", required=True, help="seal_input JSON：actor 与 verdict（5.review 另带 reviews）")
    seal_parser.set_defaults(handler=_handle_seal)
