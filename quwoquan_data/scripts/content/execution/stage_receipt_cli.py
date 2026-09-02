"""`task stage-open/stage-gate/stage-close` / `task lane-claim` / `task fleet-status` 三个薄 IO 子命令。

命令契约冻结于 `.agents/skills/content-production/references/handoff-protocol.md`
与 `references/orchestration.md`；本文件只做参数解析与结果呈现，
核心逻辑在 `content.execution.stage_receipt`。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from content.execution.stage_receipt import (
    DEFAULT_CLAIM_TTL_MINUTES,
    RECEIPT_STAGES,
    acquire_lane_claim,
    check_lane_claim,
    fleet_status,
    release_lane_claim,
    round_timeout_admission,
)


def _load_context(path_value: str | None) -> dict:
    if not path_value:
        return {}
    path = Path(path_value).expanduser().resolve()
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("stage context must contain one JSON object")
    return value


def _authority_error(command: str, exc: Exception) -> None:
    from content.execution.stage_authority import StageAuthorityConflict
    from content.execution.stage_semantic_recorder import StageSemanticConflict

    print(f"{command} rejected: {exc}", file=sys.stderr)
    raise SystemExit(3 if isinstance(exc, (StageAuthorityConflict, StageSemanticConflict)) else 2) from exc


def _handle_stage_open(args: argparse.Namespace) -> None:
    from content.execution.stage_authority import open_stage
    try:
        print(open_stage(args.execution_id, args.stage))
    except (OSError, TypeError, ValueError) as exc:
        _authority_error("stage-open", exc)


def _handle_stage_gate(args: argparse.Namespace) -> None:
    from content.execution.stage_authority import run_stage_gate
    try:
        print(run_stage_gate(
            args.execution_id, args.stage, close_context=_load_context(args.context)
        ))
    except (OSError, TypeError, ValueError) as exc:
        _authority_error("stage-gate", exc)


def _handle_stage_close(args: argparse.Namespace) -> None:
    from content.execution.stage_authority import close_stage
    try:
        print(close_stage(
            args.execution_id, args.stage, close_context=_load_context(args.context)
        ))
    except (OSError, TypeError, ValueError) as exc:
        _authority_error("stage-close", exc)


def _register_authority_parser(
    commands: argparse._SubParsersAction, *, name: str, handler: object, help_text: str
) -> None:
    parser = commands.add_parser(name, help=help_text)
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--stage", required=True, choices=RECEIPT_STAGES)
    if name != "stage-open":
        parser.add_argument(
            "--context",
            help="结构化 JSON context 文件；不接受自由 command/exitCode/next/actor",
        )
    parser.set_defaults(handler=handler)


def register_stage_authority_parsers(commands: argparse._SubParsersAction) -> None:
    _register_authority_parser(
        commands, name="stage-open", handler=_handle_stage_open,
        help_text="验证唯一合法 next 并 create-once 冻结 workflow/open request",
    )
    _register_authority_parser(
        commands, name="stage-gate", handler=_handle_stage_gate,
        help_text="执行 registry canonical argv 并冻结机器 gate receipt",
    )
    _register_authority_parser(
        commands, name="stage-close", handler=_handle_stage_close,
        help_text="从 open+gate+typed issues 派生 verdict/next 并写 receipt",
    )


def _handle_semantic_prepare(args: argparse.Namespace) -> None:
    from content.execution.stage_semantic_recorder import prepare_stage_semantic_request
    try:
        print(prepare_stage_semantic_request(args.execution_id, args.stage))
    except (OSError, TypeError, ValueError) as exc:
        _authority_error("semantic-prepare", exc)


def _handle_semantic_record(args: argparse.Namespace) -> None:
    from content.execution.stage_semantic_recorder import record_stage_semantic_result
    try:
        print(record_stage_semantic_result(
            args.execution_id, args.stage, _load_context(args.input)
        ))
    except (OSError, TypeError, ValueError) as exc:
        _authority_error("semantic-record", exc)


def register_stage_semantic_parsers(commands: argparse._SubParsersAction) -> None:
    from content.execution.stage_semantic_recorder import SEMANTIC_STAGES

    prepare = commands.add_parser(
        "semantic-prepare",
        help="从 registry 确定性发现输入闭包并冻结 semantic request",
    )
    prepare.add_argument("--execution-id", required=True)
    prepare.add_argument("--stage", required=True, choices=SEMANTIC_STAGES)
    prepare.set_defaults(handler=_handle_semantic_prepare)

    record = commands.add_parser(
        "semantic-record",
        help="校验一份结构化 result input 并 create-once 写 semantic wrapper",
    )
    record.add_argument("--execution-id", required=True)
    record.add_argument("--stage", required=True, choices=SEMANTIC_STAGES)
    record.add_argument("--input", required=True, help="唯一结构化 JSON result input 文件")
    record.set_defaults(handler=_handle_semantic_record)


def _handle_lane_claim(args: argparse.Namespace) -> None:
    if args.check:
        if args.round_timeout_seconds is not None:
            admission = round_timeout_admission(
                args.execution_id,
                round_timeout_seconds=args.round_timeout_seconds,
            )
            if not admission["admitted"]:
                print(
                    f"lane-claim rejected: {admission['reason']}",
                    file=sys.stderr,
                )
                raise SystemExit(64)
        result = check_lane_claim(args.execution_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result["active"]:
            raise SystemExit(3)
        return
    if not args.actor_session:
        print("lane-claim rejected: --actor-session is required", file=sys.stderr)
        raise SystemExit(2)
    if args.release:
        result = release_lane_claim(
            args.execution_id, actor_session=args.actor_session
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if not args.actor_host:
        print("lane-claim rejected: --actor-host is required", file=sys.stderr)
        raise SystemExit(2)
    result = acquire_lane_claim(
        args.execution_id,
        actor_host=args.actor_host,
        actor_session=args.actor_session,
        ttl_minutes=args.ttl_minutes,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["acquired"]:
        raise SystemExit(3)


def register_lane_claim_parser(
    commands: argparse._SubParsersAction,
) -> None:
    parser = commands.add_parser(
        "lane-claim",
        help="single-writer lane claim：同 session 刷心跳，冲突退出码 3，"
        "--release 释放，--check 只读探测（驱动预检）",
    )
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--actor-host", default=None)
    parser.add_argument("--actor-session", default=None)
    parser.add_argument(
        "--ttl-minutes", type=int, default=DEFAULT_CLAIM_TTL_MINUTES
    )
    parser.add_argument(
        "--release",
        action="store_true",
        help="释放本 session 持有的 claim（异主 no-op）",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="只读探测：活跃 claim 存在退出码 3，不写盘不刷心跳",
    )
    parser.add_argument(
        "--round-timeout-seconds",
        type=int,
        default=None,
        help="随 --check 声明驱动的单轮 hard timeout；长到会与 claim TTL "
        "形成双写窗口时退出码 64",
    )
    parser.set_defaults(handler=_handle_lane_claim)


def _handle_fleet_status(args: argparse.Namespace) -> None:
    status = fleet_status(list(args.execution_id or []) or None)
    if args.json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return
    print(
        f"executions={status['total']} succeeded={status['succeeded']}"
    )
    for key, count in status["stageDistribution"].items():
        print(f"  next={key}: {count}")
    for family, count in status["modelFamilies"].items():
        print(f"  modelFamily={family}: {count}")
    for reason, count in status["blockedReasons"].items():
        print(f"  blocked: {reason} ({count})")


def register_fleet_status_parser(
    commands: argparse._SubParsersAction,
) -> None:
    parser = commands.add_parser(
        "fleet-status",
        help="只读聚合 receipt 链：产出率、阶段分布、blocked 原因、模型族切片",
    )
    parser.add_argument(
        "--execution-id",
        action="append",
        default=[],
        help="缺省聚合全部 execution，可多次指定",
    )
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(handler=_handle_fleet_status)


def register_stage_receipt_parsers(
    commands: argparse._SubParsersAction,
) -> None:
    register_stage_authority_parsers(commands)
    register_stage_semantic_parsers(commands)
    register_lane_claim_parser(commands)
    register_fleet_status_parser(commands)
