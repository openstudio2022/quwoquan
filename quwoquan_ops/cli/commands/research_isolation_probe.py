"""stackctl `research-isolation-probe` 子命令域。

从 stackctl.py 逐字迁出 argparse 表面与编排胶水；12 个 research
isolation 真实 HTTP 探针与 create-once runtime proof 逻辑保持在
`quwoquan_ops/cli/lib/research_isolation_runtime_probe.py`。stackctl
命名空间符号一律经函数内延迟导入 `_stackctl` 属性访问，保持
monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
from typing import Any


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    research_isolation_probe_parser = subparsers.add_parser(
        "research-isolation-probe",
        help=(
            "对本地环境执行 12 个 research isolation 真实 HTTP 探针并写入 "
            "create-once runtime proof"
        ),
    )
    research_isolation_probe_parser.add_argument(
        "--report-dir",
        default=argparse.SUPPRESS,
    )
    research_isolation_probe_parser.add_argument(
        "--env",
        choices=("alpha", "beta", "gamma"),
        required=True,
    )
    research_isolation_probe_parser.add_argument("--release-id", required=True)
    research_isolation_probe_parser.add_argument("--verify-run-id", required=True)
    research_isolation_probe_parser.add_argument("--manifest-digest", required=True)


def command_research_isolation_probe(args: argparse.Namespace) -> dict[str, Any]:
    """执行 12 个 research isolation 真实探针并冻结 create-once runtime proof。"""
    import quwoquan_ops.cli.stackctl as _stackctl

    env_name = str(args.env)
    release_id = str(args.release_id)
    verify_run_id = str(args.verify_run_id)
    manifest_digest = str(args.manifest_digest)
    report_dir = _stackctl.resolve_report_dir(args, env_name, f"{env_name}-local")
    started_monotonic, started_at = _stackctl._start_timing()
    evidence: dict[str, Any] = {}
    try:
        evidence = _stackctl.run_research_isolation_runtime_probe(
            environment=env_name,
            release_id=release_id,
            verify_run_id=verify_run_id,
            manifest_digest=manifest_digest,
        )
        exit_code = 0
        details = [f"runtime proof written: {evidence['outputPath']}"]
    except _stackctl.ResearchIsolationProbeError as exc:
        exit_code = 1
        evidence = {"blockerCode": exc.code}
        details = [str(exc)]
    except (OSError, RuntimeError, ValueError) as exc:
        exit_code = 2
        details = [str(exc)]
    timing = _stackctl._finish_timing(started_monotonic, started_at)
    _stackctl.write_json(
        report_dir / "report.json",
        {
            "command": "research-isolation-probe",
            "status": "passed" if exit_code == 0 else "gate_block",
            "environment": env_name,
            "releaseId": release_id,
            "verifyRunId": verify_run_id,
            "manifestDigest": manifest_digest,
            "evidence": evidence,
            "details": details,
            **timing,
        },
    )
    return {
        "exitCode": exit_code,
        "summary": (
            "research isolation runtime probe passed"
            if exit_code == 0
            else "research isolation runtime probe is GATE_BLOCK"
        ),
        "details": details,
        "evidence": evidence,
        "reportDir": _stackctl.relpath(report_dir),
        **timing,
    }
