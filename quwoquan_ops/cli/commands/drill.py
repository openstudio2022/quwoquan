"""stackctl `drill` 子命令域。

从 stackctl.py 逐字迁出 argparse 表面与编排胶水；故障演练执行逻辑保持在
`quwoquan_ops/cli/lib/fault_drill_orchestration.py`。stackctl 命名空间符号
一律经函数内延迟导入 `_stackctl` 属性访问，保持 monkeypatch 语义并
避免顶层循环 import。
"""

from __future__ import annotations

import argparse
from typing import Any


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    import quwoquan_ops.cli.stackctl as _stackctl

    drill_parser = subparsers.add_parser("drill")
    drill_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    drill_parser.add_argument("--env", choices=_stackctl.ENVIRONMENTS, required=True)
    drill_parser.add_argument("--target", choices=_stackctl.TARGETS, required=True)
    drill_parser.add_argument(
        "--profile", choices=list(_stackctl.FAULT_PROFILES), required=True
    )
    drill_parser.add_argument("--hold-seconds", type=float, default=5.0)


def command_drill(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    report_dir = _stackctl.resolve_report_dir(args, args.env, args.target)
    payload = _stackctl.run_drill(
        env_name=args.env,
        target_name=args.target,
        profile=args.profile,
        hold_seconds=args.hold_seconds,
        report_dir=report_dir,
    )
    status = str(payload.get("status"))
    details: list[str] = []
    if status == "unavailable":
        details.append(str(payload.get("reason")))
    else:
        evidence = payload.get("healthEvidence", {})
        details.append(
            "fault confirmed unavailable="
            + str(evidence.get("unavailableDuringFault"))
            + ", healthy after restore="
            + str(evidence.get("healthyAfterRestore"))
        )
        details.append(
            "alert readback: " + str(payload.get("alertReadback", {}).get("status"))
        )
    return {
        "summary": f"drill {args.env}/{args.target} profile={args.profile} status={status}",
        "reportDir": str(report_dir),
        "details": details,
        "receipt": payload,
        "exitCode": 0 if status in {"restored", "unavailable"} else 1,
    }
