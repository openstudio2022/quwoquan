"""stackctl `filter-catalog` 子命令域。

从 stackctl.py 逐字迁出 argparse 表面与编排胶水；业务逻辑保持在
`quwoquan_ops/cli/lib/**`。测试通过 ``mock.patch.object(stackctl, ...)``
patch `resolve_report_dir` / `execute_filter_catalog_command` /
`mint_local_filter_catalog_service_token` / `_write_filter_catalog_command_report`
等符号，因此命令函数体内一律经函数内延迟导入 `_stackctl` 属性访问，
既保持 patch 语义也避免顶层循环 import。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    import quwoquan_ops.cli.stackctl as _stackctl

    filter_catalog_parser = subparsers.add_parser(
        "filter-catalog",
        help="按环境绑定的受信发布身份发布或复核 FilterCatalogRelease",
    )
    filter_catalog_parser.add_argument(
        "--target",
        choices=("alpha-local", "beta-local", "gamma-local", "prod-hosted"),
        required=True,
    )
    filter_catalog_parser.add_argument(
        "--action",
        choices=("stage", "activate", "stage-and-activate", "verify", "rollback"),
        required=True,
    )
    filter_catalog_parser.add_argument("--rollback-release-id", default="")
    filter_catalog_parser.add_argument(
        "--token-env",
        default=_stackctl.PUBLISH_TOKEN_ENV_DEFAULT,
        help="prod service-principal bearer 的环境变量名；值绝不进入 argv 或报告",
    )
    filter_catalog_parser.add_argument(
        "--prod-gray-activation",
        action="store_true",
        help="仅在 prod gray 已获人工审批后允许 activate",
    )


def command_filter_catalog(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    topology = _stackctl.load_environment_topology()
    target = _stackctl.get_target(topology, args.target)
    environment = str(target["env"])
    public_bases = target.get("publicBases") or {}
    api_base_url = str(public_bases.get("api") or "")
    report_dir = _stackctl.resolve_report_dir(args, environment, args.target)
    started_monotonic, started_at = _stackctl._start_timing()
    if not api_base_url:
        detail = "target topology has no public API base"
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        _stackctl._write_filter_catalog_command_report(
            report_dir=report_dir,
            target_name=args.target,
            action=args.action,
            status="gate_block",
            details=[detail],
            publish_receipt=None,
            argv=(),
            timing=timing,
        )
        return {
            "exitCode": 2,
            "summary": "stackctl filter-catalog is GATE_BLOCK",
            "details": [detail],
            "reportDir": _stackctl.relpath(report_dir),
            **timing,
        }
    try:
        token_value = ""
        ssl_cafile = ""
        if args.target in _stackctl.LOCAL_FILTER_CATALOG_TARGETS:
            from quwoquan_ops.cli.lib.public_domain_tls import root_certificate_path

            ssl_cafile = str(root_certificate_path(args.target))
        if (
            args.target in _stackctl.LOCAL_FILTER_CATALOG_TARGETS
            and args.action in _stackctl.FILTER_CATALOG_MUTATING_ACTIONS
        ):
            token_value = _stackctl.mint_local_filter_catalog_service_token(
                environment,
                args.target,
            )
        execution = _stackctl.execute_filter_catalog_command(
            repo_root=_stackctl.ROOT,
            target_name=args.target,
            environment=environment,
            api_base_url=api_base_url,
            action=args.action,
            rollback_release_id=args.rollback_release_id,
            token_env=args.token_env,
            prod_gray_activation=bool(args.prod_gray_activation),
            token_value=token_value,
            ssl_cafile=ssl_cafile,
            diagnostic_log_path=(
                _stackctl.target_process_dir(args.target)
                / "stdout"
                / "filter-catalog.log"
            ),
        )
    except (RuntimeError, ValueError) as exc:
        detail = str(exc)
        timing = _stackctl._finish_timing(started_monotonic, started_at)
        _stackctl._write_filter_catalog_command_report(
            report_dir=report_dir,
            target_name=args.target,
            action=args.action,
            status="gate_block",
            details=[detail],
            publish_receipt=None,
            argv=(),
            timing=timing,
        )
        return {
            "exitCode": 2,
            "summary": "stackctl filter-catalog is GATE_BLOCK",
            "details": [detail],
            "reportDir": _stackctl.relpath(report_dir),
            **timing,
        }

    publish_receipt: dict[str, Any] | None = None
    details: list[str]
    status = "ok"
    exit_code = 0
    if execution.return_code == 0:
        try:
            decoded = json.loads(execution.stdout)
            if not isinstance(decoded, dict) or not bool(decoded.get("passed")):
                raise ValueError("qwq-data filter-catalog publish did not emit a passed receipt")
            publish_receipt = decoded
            details = [
                f"{args.action} release={decoded.get('releaseId', '')}",
                f"digest={decoded.get('canonicalDigest', '')}",
            ]
        except (json.JSONDecodeError, ValueError) as exc:
            status = "failed"
            exit_code = 1
            details = [f"invalid filter catalog publish receipt: {exc}"]
    else:
        status = "failed"
        exit_code = 1
        details = [
            _stackctl._filter_catalog_failure_detail(
                stderr=execution.stderr,
                stdout=execution.stdout,
                return_code=execution.return_code,
            )
        ]
    timing = _stackctl._finish_timing(started_monotonic, started_at)
    _stackctl._write_filter_catalog_command_report(
        report_dir=report_dir,
        target_name=args.target,
        action=args.action,
        status=status,
        details=details,
        publish_receipt=publish_receipt,
        argv=execution.argv,
        timing=timing,
    )
    return {
        "exitCode": exit_code,
        "summary": (
            "stackctl filter-catalog passed"
            if exit_code == 0
            else "stackctl filter-catalog failed"
        ),
        "details": details,
        "reportDir": _stackctl.relpath(report_dir),
        **timing,
    }


def _filter_catalog_failure_detail(
    *,
    stderr: str,
    stdout: str,
    return_code: int,
) -> str:
    """从 Data CLI 输出提取可排障摘要，不把 bearer token 写入报告。"""
    combined = "\n".join(
        part.strip() for part in (stderr or "", stdout or "") if part and part.strip()
    )
    for line in combined.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if "authorization" in lower or "bearer " in lower:
            continue
        if "gate_block" in lower or "http " in lower or "filtercatalog" in lower.replace(
            "-", ""
        ).replace("_", ""):
            return stripped
    if combined:
        first = next((line.strip() for line in combined.splitlines() if line.strip()), "")
        if first:
            return first[:300]
    return (
        f"qwq-data filter-catalog publish failed (exit={return_code}); "
        "see process/stdout/filter-catalog.log for redacted child output"
    )


def _write_filter_catalog_command_report(
    *,
    report_dir: Path,
    target_name: str,
    action: str,
    status: str,
    details: list[str],
    publish_receipt: dict[str, Any] | None,
    argv: tuple[str, ...],
    timing: dict[str, Any],
) -> None:
    import quwoquan_ops.cli.stackctl as _stackctl

    payload = {
        "command": "filter-catalog",
        "target": target_name,
        "action": action,
        "status": status,
        "details": details,
        "argv": list(argv),
        "publishReceipt": publish_receipt,
        **timing,
    }
    _stackctl.write_json(report_dir / "report.json", payload)
    _stackctl.write_json(
        report_dir / "findings.json", {"issues": details if status != "ok" else []}
    )
    _stackctl._write_summary_bundle(
        report_dir,
        command="filter-catalog",
        target=target_name,
        status=status,
        summary=(
            "FilterCatalogRelease publish receipt verified"
            if status == "ok"
            else "FilterCatalogRelease publish is blocked or failed"
        ),
        details=details,
        extra={"action": action, "publishReceipt": publish_receipt},
        timing=timing,
    )
