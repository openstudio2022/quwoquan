"""stackctl `loadtest` 子命令域。

从 stackctl.py 逐字迁出 argparse 表面与编排胶水；负载执行逻辑保持在
`quwoquan_ops/cli/lib/loadtest_orchestration.py`。stackctl 命名空间符号
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

    loadtest_parser = subparsers.add_parser("loadtest")
    loadtest_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    loadtest_parser.add_argument("--env", choices=_stackctl.ENVIRONMENTS, required=True)
    loadtest_parser.add_argument("--target", choices=_stackctl.TARGETS, required=True)
    loadtest_parser.add_argument(
        "--operation",
        action="append",
        required=True,
        help="contract operation selector: <service>/<context>/<object>#<OperationName>",
    )
    loadtest_parser.add_argument("--concurrency", type=int, default=4)
    loadtest_parser.add_argument("--requests-per-operation", type=int, default=50)
    loadtest_parser.add_argument("--timeout-seconds", type=float, default=5.0)


def command_loadtest(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    report_dir = _stackctl.resolve_report_dir(args, args.env, args.target)
    payload = _stackctl.run_loadtest(
        env_name=args.env,
        target_name=args.target,
        operation_selectors=list(args.operation),
        concurrency=args.concurrency,
        requests_per_operation=args.requests_per_operation,
        timeout_seconds=args.timeout_seconds,
        report_dir=report_dir,
    )
    operations = payload.get("loadgen", {}).get("operations", [])
    details = [
        (
            f"{item.get('operationId')}: verdict={item.get('verdict')} "
            f"p95={item.get('p95Ms')}ms availability={item.get('availabilityPercent')}% "
            f"samples={item.get('samples')}"
        )
        for item in operations
    ]
    failed = payload.get("verdict") == "fail"
    return {
        "summary": (
            f"loadtest {args.env}/{args.target} verdict={payload.get('verdict')} "
            f"operations={len(operations)}"
        ),
        "reportDir": str(report_dir),
        "details": details,
        "report": payload,
        "exitCode": 1 if failed else 0,
    }
