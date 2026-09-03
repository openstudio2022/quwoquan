"""stackctl `app-managed-prepare` 子命令域。

managed dispatcher 入口（`QWQ_MANAGED_FLUTTER_ENTRY=1` 的 canonical run.sh）在
Flutter build 前消费本命令：状态机实现在
`quwoquan_ops/cli/lib/managed_preparation.py`，这里只有 argparse 表面与
编排胶水。stackctl 命名空间符号一律经函数内延迟导入 `_stackctl` 属性访问。
"""

from __future__ import annotations

import argparse
from typing import Any


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "app-managed-prepare",
        help=(
            "为受管 flutter 入口执行严格 managed preparation："
            "exact device/runtime/lease/trust/binding/strict preflight/receipt"
        ),
    )
    parser.add_argument(
        "--target",
        choices=("alpha-local",),
        required=True,
    )
    parser.add_argument("--device", required=True)
    parser.add_argument(
        "--consumer-id",
        required=True,
        help="由前台 run.sh 预先确定并在 cleanup 释放的稳定 consumer identity",
    )
    parser.add_argument(
        "--platform",
        choices=("ios", "android"),
        default="",
        help="可选平台断言；与连接设备的实际平台冲突时 typed 阻断",
    )
    parser.add_argument("--report-dir", default=argparse.SUPPRESS)


def command_app_managed_prepare(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    env_name = str(
        _stackctl.get_target(_stackctl.load_environment_topology(), args.target)["env"]
    )
    started_monotonic, started_at = _stackctl._start_timing()
    try:
        report_dir = _stackctl.validate_env_run_evidence_dir(
            _stackctl.resolve_report_dir(args, env_name, args.target),
            env_name=env_name,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        return {
            "exitCode": 2,
            "summary": (
                f"stackctl app-managed-prepare blocked for {args.target}"
            ),
            "status": "blocked",
            "firstBlocker": "APP.PREPARATION.receipt_invalid",
            "receiptPath": "",
            "receiptDigest": "",
            "details": [
                f"unsafe app-managed-prepare report directory: {exc}"
            ],
            "warnings": [],
            "reportDir": "",
            **timing,
        }
    result = _stackctl.run_managed_preparation(
        target=str(args.target),
        device_id=str(args.device),
        platform=str(getattr(args, "platform", "") or ""),
        consumer_id=str(args.consumer_id),
        report_dir=report_dir,
    )
    timing = _stackctl._finish_timing(started_monotonic, started_at)
    status = str(result.get("status") or "blocked")
    payload = {
        "exitCode": int(result.get("exitCode", 2)),
        "summary": (
            f"stackctl app-managed-prepare {status} for {args.target}"
        ),
        "status": status,
        "firstBlocker": str(result.get("firstBlocker") or ""),
        "receiptPath": str(result.get("receiptPath") or ""),
        "receiptDigest": str(result.get("receiptDigest") or ""),
        "details": [str(item) for item in result.get("details") or []],
        "warnings": [str(item) for item in result.get("warnings") or []],
        "reportDir": str(report_dir),
        **timing,
    }
    _stackctl.write_json(
        report_dir / "report.json",
        {
            "command": "app-managed-prepare",
            "target": args.target,
            **{key: value for key, value in payload.items() if key != "exitCode"},
        },
    )
    return payload
