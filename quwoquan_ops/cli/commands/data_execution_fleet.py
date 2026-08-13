"""stackctl `data-execution-fleet` 子命令域。

从 stackctl.py 逐字迁出 argparse 表面与编排胶水；业务逻辑保持在
`quwoquan_ops/cli/lib/**`。stackctl 命名空间符号一律经函数内延迟导入
`_stackctl` 属性访问，保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
from typing import Any


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    import quwoquan_ops.cli.stackctl as _stackctl

    data_fleet_parser = subparsers.add_parser(
        "data-execution-fleet",
        help="解析或管理 Data ReliableTask 专属的本地 Mongo+Redis fleet。",
    )
    data_fleet_parser.add_argument(
        "--action",
        choices=_stackctl.FLEET_ACTIONS,
        default="resolve",
    )


def command_data_execution_fleet(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    endpoint = _stackctl.resolve_data_execution_fleet_endpoint()
    action = str(getattr(args, "action", "resolve") or "resolve")
    if action == "resolve":
        return {
            "exitCode": 0,
            "summary": "stackctl data execution fleet resolved",
            "details": [f"target={endpoint.target}"],
            "fleet": endpoint.document(),
        }
    report_dir = _stackctl.artifact_run_dir(
        "repo",
        f"data-execution-fleet-{action}",
        target=endpoint.target,
    )
    try:
        runtime = _stackctl.manage_data_execution_fleet(action, endpoint)
        exit_code = 0 if action == "down" or runtime.ready else 1
        evidence = runtime.document()
        details = list(runtime.details)
        if not details:
            details = [
                f"mongo={runtime.mongo} redis={runtime.redis} owned={runtime.owned}"
            ]
    except (OSError, RuntimeError, ValueError) as exc:
        exit_code = 2
        evidence = {"action": action, "target": endpoint.target, "ready": False}
        details = [str(exc)]
    _stackctl.write_json(
        report_dir / "report.json",
        {
            "command": "data-execution-fleet",
            "status": "passed" if exit_code == 0 else "gate_block",
            "fleet": endpoint.document(),
            "evidence": evidence,
            "details": details,
        },
    )
    return {
        "exitCode": exit_code,
        "summary": f"stackctl data execution fleet {action}",
        "details": details,
        "fleet": endpoint.document(),
        "evidence": evidence,
        "reportDir": _stackctl.relpath(report_dir),
    }
