"""stackctl `tls` 子命令域。

从 stackctl.py 逐字迁出 argparse 表面与编排胶水；业务逻辑保持在
`quwoquan_ops/cli/lib/**`。stackctl 命名空间符号一律经函数内延迟导入
`_stackctl` 属性访问，保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import os
import shutil
from typing import Any


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    tls_parser = subparsers.add_parser(
        "tls",
        help="local-managed 与公共 DNS-01 TLS 的统一预检、签发和验证门面",
    )
    tls_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    tls_parser.add_argument(
        "--target",
        choices=("alpha-local", "beta-local", "gamma-local", "prod-sim"),
        required=True,
    )
    tls_parser.add_argument(
        "--action",
        choices=("prevalidate", "verify", "issue"),
        required=True,
    )
    tls_parser.add_argument(
        "--confirm-protected-apply",
        action="store_true",
        help="明确确认 DNS-01 challenge 与 ACME 外部状态变更；local-managed 不需要",
    )


def command_tls(args: argparse.Namespace) -> dict[str, Any]:
    """Expose canonical TLS through stackctl without duplicating certificate logic."""
    import quwoquan_ops.cli.stackctl as _stackctl

    env_name = str(
        _stackctl.get_target(_stackctl.load_environment_topology(), args.target)["env"]
    )
    report_dir = _stackctl.resolve_report_dir(args, env_name, args.target)
    started_monotonic, started_at = _stackctl._start_timing()
    details: list[str] = []
    evidence: dict[str, Any] = {}
    exit_code = 0
    try:
        if args.action == "prevalidate":
            policy = _stackctl.load_public_domain_policy()
            profile_name, profile_kind, profile = _stackctl.tls_profile(args.target)
            if profile_kind == "local-managed":
                client = "openssl"
                client_available = shutil.which(client) is not None
                if not client_available:
                    details.append("required local-managed TLS client is unavailable: openssl")
                    exit_code = 2
                evidence = {
                    "target": args.target,
                    "action": "prevalidate",
                    "profile": profile_name,
                    "kind": profile_kind,
                    "clientAvailable": client_available,
                    "protectedInputsReady": True,
                    "status": "passed"
                    if exit_code == 0
                    else _stackctl.ProbeOutcome.GATE_BLOCK.value,
                }
                if exit_code == 0:
                    details.append("local-managed TLS inputs and openssl are ready")
            else:
                acme = policy.get("acme") or {}
                authority = policy.get("acmeChallengeAuthority") or {}
                required_envs = (str(authority.get("apiTokenEnv") or ""),)
                missing_envs = [
                    name for name in required_envs if not name or not os.environ.get(name, "").strip()
                ]
                client = str(acme.get("client") or "lego")
                if shutil.which(client) is None:
                    details.append(f"required ACME client is unavailable: {client}")
                if missing_envs:
                    details.append("missing protected environment inputs: " + ", ".join(missing_envs))
                if details:
                    exit_code = 2
                evidence = {
                    "target": args.target,
                    "action": "prevalidate",
                    "profile": profile_name,
                    "kind": profile_kind,
                    "apex": str(profile.get("apex") or ""),
                    "wildcard": str(profile.get("wildcard") or ""),
                    "clientAvailable": shutil.which(client) is not None,
                    "protectedInputsReady": not missing_envs,
                    "status": "passed"
                    if exit_code == 0
                    else _stackctl.ProbeOutcome.GATE_BLOCK.value,
                }
                if exit_code == 0:
                    details.append("DNS-01 TLS protected inputs and client are ready")
        elif args.action == "verify":
            verified = _stackctl.verify_certificate(args.target)
            evidence = {
                key: value
                for key, value in verified.items()
                if key not in {"certificate", "privateKey"}
            }
            details.append("public certificate, private-key match and SAN verified")
        else:
            _, profile_kind, _ = _stackctl.tls_profile(args.target)
            if profile_kind != "local-managed" and not args.confirm_protected_apply:
                raise _stackctl.PublicDomainTlsError(
                    "GATE_BLOCK: issue requires --confirm-protected-apply after prevalidate"
                )
            issued = _stackctl.issue_certificate(args.target)
            evidence = {
                key: value
                for key, value in issued.items()
                if key not in {"certificate", "privateKey"}
            }
            details.append(f"{profile_kind} certificate issued and verified")
    except _stackctl.PublicDomainTlsError as error:
        exit_code = 2
        details = [str(error)]
        evidence = {
            "target": args.target,
            "action": args.action,
            "status": _stackctl.ProbeOutcome.GATE_BLOCK.value,
        }
    timing = _stackctl._finish_timing(started_monotonic, started_at)
    status = "passed" if exit_code == 0 else "gate_block"
    _stackctl.write_json(
        report_dir / "report.json",
        {
            "command": "tls",
            "target": args.target,
            "action": args.action,
            "status": status,
            "evidence": evidence,
            "details": details,
            **timing,
        },
    )
    _stackctl.write_json(
        report_dir / "findings.json",
        {"issues": [] if exit_code == 0 else details},
    )
    return {
        "exitCode": exit_code,
        "summary": f"stackctl tls {args.action} {status} for {args.target}",
        "details": details,
        "reportDir": _stackctl.relpath(report_dir),
        **timing,
    }
