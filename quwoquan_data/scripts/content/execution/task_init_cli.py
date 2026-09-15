"""确定性 task init 的 CLI 适配器：一份 round spec 建一轮全部 carrier execution。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from content.coordination.runtime import current_tokens, producer_call
from content.coordination.store import CoordinationError
from content.execution.task_init import (
    TaskInitConflict, initialize_round, _load_submitted_document, _round_documents, _normalized_targets,
)


def handle_task_init(args: argparse.Namespace) -> None:
    try:
        current_tokens()
        document = _load_submitted_document(Path(args.round), schema_name="round_spec")
        batches = {}
        for demand, bindings in _round_documents(document):
            _targets, refs = _normalized_targets(bindings["targets"], carrier=demand["carrier"])
            batches[demand["executionId"]] = refs
        result = producer_call(lambda: initialize_round(submitted_round_spec=document), operation="init", batches=batches)
    except (CoordinationError, FileNotFoundError, OSError, TypeError, ValueError, KeyError) as exc:
        print(f"task init 拒绝：{exc}", file=sys.stderr)
        raise SystemExit(3 if isinstance(exc, TaskInitConflict) else 2) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


def register_task_init_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("init", help="从一份 round spec 原子创建该轮全部 carrier execution")
    parser.add_argument("--round", required=True, help="round_spec JSON：executions 与逐 target 身份")
    parser.set_defaults(handler=handle_task_init)


__all__ = ["handle_task_init", "register_task_init_parser"]
