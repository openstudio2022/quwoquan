"""`task stage-record` / `task lane-claim` / `task fleet-status` 三个薄 IO 子命令。

命令契约冻结于 `.agents/skills/content-production/references/handoff-protocol.md`
与 `references/orchestration.md`；本文件只做参数解析与结果呈现，
核心逻辑在 `content.execution.stage_receipt`。
"""
from __future__ import annotations

import argparse
import json
import sys

from content.execution.stage_receipt import (
    DEFAULT_CLAIM_TTL_MINUTES,
    OPEN_ITEM_DISPOSITIONS,
    RECEIPT_NEXT_VALUES,
    RECEIPT_STAGES,
    acquire_lane_claim,
    check_lane_claim,
    fleet_status,
    record_stage_receipt,
    release_lane_claim,
    round_timeout_admission,
)


def _parse_evidence_command(raw: str) -> dict:
    command, sep, exit_code = raw.rpartition("::")
    if not sep or not command:
        raise argparse.ArgumentTypeError(
            f"--evidence-command must be '<command>::<exitCode>': {raw!r}"
        )
    try:
        code = int(exit_code)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"--evidence-command exit code must be an integer: {raw!r}"
        ) from exc
    return {"command": command, "exitCode": code}


def _parse_open_item(raw: str) -> dict:
    parts = raw.split("::")
    if len(parts) not in (2, 3) or not parts[0]:
        raise argparse.ArgumentTypeError(
            "--open-item must be '<item>::<disposition>[::<returnStage>]'"
        )
    item = {"item": parts[0], "disposition": parts[1]}
    if parts[1] not in OPEN_ITEM_DISPOSITIONS:
        raise argparse.ArgumentTypeError(
            f"--open-item disposition must be one of {OPEN_ITEM_DISPOSITIONS}"
        )
    if len(parts) == 3:
        if parts[2] not in RECEIPT_STAGES:
            raise argparse.ArgumentTypeError(
                f"--open-item returnStage must be one of {RECEIPT_STAGES}"
            )
        item["returnStage"] = parts[2]
    return item


def _handle_stage_record(args: argparse.Namespace) -> None:
    try:
        target = record_stage_receipt(
            execution_id=args.execution_id,
            stage=args.stage,
            verdict=args.verdict,
            actor_host=args.actor_host,
            actor_model_family=args.actor_model_family,
            actor_session=args.actor_session,
            artifacts=list(args.artifact or []),
            open_items=list(args.open_item or []),
            next_stage=args.next,
            evidence_commands=list(args.evidence_command or []),
            issue_count=args.issue_count,
            repair_rounds=args.repair_rounds,
        )
    except (ValueError, FileExistsError) as exc:
        print(f"stage-record rejected: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(target)


def register_stage_record_parser(
    commands: argparse._SubParsersAction,
) -> None:
    parser = commands.add_parser(
        "stage-record",
        help="阶段收尾唯一写入口：create-once 落 receipt 并同步 execution_state",
    )
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--stage", required=True, choices=RECEIPT_STAGES)
    parser.add_argument("--verdict", required=True, choices=("pass", "blocked"))
    parser.add_argument("--actor-host", required=True)
    parser.add_argument(
        "--actor-model-family",
        required=True,
        help="实际路由到的模型族；禁止写字面 auto",
    )
    parser.add_argument("--actor-session", required=True)
    parser.add_argument("--artifact", action="append", default=[])
    parser.add_argument("--next", required=True, choices=RECEIPT_NEXT_VALUES)
    parser.add_argument(
        "--evidence-command",
        action="append",
        required=True,
        type=_parse_evidence_command,
        help="判据命令与退出码：'<命令>::<退出码>'，可多次",
    )
    parser.add_argument("--issue-count", type=int, required=True)
    parser.add_argument(
        "--repair-rounds", type=int, required=True, help="自修轮数 0..3"
    )
    parser.add_argument(
        "--open-item",
        action="append",
        default=[],
        type=_parse_open_item,
        help="未决项：'<描述>::<return_to_stage|gate_block|out_of_scope>[::<returnStage>]'",
    )
    parser.set_defaults(handler=_handle_stage_record)


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
    register_stage_record_parser(commands)
    register_lane_claim_parser(commands)
    register_fleet_status_parser(commands)
