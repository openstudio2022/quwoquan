"""stackctl `research-consumer-credential` 子命令域。

为 ship verify 的 research readiness 签发消费核验凭证：白名单研究账号
Bearer session + research attestation。凭证只经 stdout JSON（evidence）
传给调用方进程，report.json 仅记录不含凭证的元数据。
"""

from __future__ import annotations

import argparse
import hashlib
from typing import Any


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "research-consumer-credential",
        help=(
            "签发 research 消费核验凭证（白名单账号 Bearer + attestation），"
            "凭证只经 stdout 传递"
        ),
    )
    parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    parser.add_argument("--env", choices=("alpha", "beta", "gamma"), required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--verify-run-id", required=True)


def command_research_consumer_credential(
    args: argparse.Namespace,
) -> dict[str, Any]:
    """登录白名单研究账号、签发 research session、经 stdout 返回凭证。"""
    import quwoquan_ops.cli.stackctl as _stackctl

    env_name = str(args.env)
    release_id = str(args.release_id)
    verify_run_id = str(args.verify_run_id)
    report_dir = _stackctl.resolve_report_dir(args, env_name, f"{env_name}-local")
    started_monotonic, started_at = _stackctl._start_timing()
    evidence: dict[str, Any] = {}
    report_evidence: dict[str, Any] = {}
    try:
        evidence = _stackctl.issue_research_consumer_credential(
            environment=env_name,
            release_id=release_id,
            verify_run_id=verify_run_id,
        )
        exit_code = 0
        details = ["research consumer credential issued (stdout only)"]
        report_evidence = {
            "subjectHash": evidence["subjectHash"],
            "attestationIdHash": "sha256:"
            + hashlib.sha256(
                str(evidence["attestationToken"]).encode("utf-8")
            ).hexdigest(),
            "expiresAt": evidence["expiresAt"],
        }
    except _stackctl.ResearchConsumerCredentialError as exc:
        exit_code = 1
        details = [str(exc)]
    except (OSError, RuntimeError, ValueError) as exc:
        exit_code = 2
        details = [str(exc)]
    timing = _stackctl._finish_timing(started_monotonic, started_at)
    _stackctl.write_json(
        report_dir / "report.json",
        {
            "command": "research-consumer-credential",
            "status": "passed" if exit_code == 0 else "gate_block",
            "environment": env_name,
            "releaseId": release_id,
            "verifyRunId": verify_run_id,
            "evidence": report_evidence,
            "details": details,
            **timing,
        },
    )
    return {
        "exitCode": exit_code,
        "summary": (
            "research consumer credential issued"
            if exit_code == 0
            else "research consumer credential is GATE_BLOCK"
        ),
        "details": details,
        "evidence": evidence,
        "reportDir": _stackctl.relpath(report_dir),
        **timing,
    }
