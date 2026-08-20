"""CLI adapter for typed WorkRequest ports."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from content.execution.planning.work_request import (
    WorkRequestCommandWriter,
    WorkRequestCompilationQuery,
    WorkRequestPreviewQuery,
)
from core.io import read_json


def _intent(path_text: str) -> Mapping[str, Any]:
    path = Path(path_text).expanduser().resolve()
    document = read_json(path)
    if not isinstance(document, Mapping):
        raise ValueError("intent file must contain one JSON object")
    return document


def handle_compile_intent(args: argparse.Namespace) -> None:
    try:
        action = str(args.compile_intent_action)
        if action == "show":
            result = WorkRequestCompilationQuery().get(
                str(args.work_request_digest)
            )
        else:
            intent = _intent(str(args.intent_file))
            if action == "preview":
                result = WorkRequestPreviewQuery().preview(intent)
            elif action == "confirm":
                result = WorkRequestCommandWriter().confirm(
                    intent,
                    preview_digest=str(args.preview_digest),
                )
            elif action == "cancel":
                result = WorkRequestCommandWriter().cancel(
                    intent,
                    preview_digest=str(args.preview_digest),
                )
            else:
                raise ValueError(f"unsupported compile-intent action: {action}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise SystemExit(f"[task compile-intent] GATE_BLOCK {exc}") from exc


def register_compile_intent_parser(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser(
        "compile-intent",
        help="preview/confirm/cancel 用户意图并编译为现有 carrier envelope 单轨",
    )
    actions = parser.add_subparsers(
        dest="compile_intent_action",
        required=True,
    )
    preview = actions.add_parser("preview", help="无副作用解析和依赖校验")
    preview.add_argument("--intent-file", required=True)
    preview.set_defaults(handler=handle_compile_intent)
    for action in ("confirm", "cancel"):
        command = actions.add_parser(action)
        command.add_argument("--intent-file", required=True)
        command.add_argument("--preview-digest", required=True)
        command.set_defaults(handler=handle_compile_intent)
    show = actions.add_parser("show", help="按 WorkRequest digest 读取编译投影")
    show.add_argument("--work-request-digest", required=True)
    show.set_defaults(handler=handle_compile_intent)


__all__ = ["handle_compile_intent", "register_compile_intent_parser"]
