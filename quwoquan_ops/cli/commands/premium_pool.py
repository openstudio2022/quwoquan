"""stackctl `premium-pool` 子命令域。

从 stackctl.py 逐字迁出 argparse 表面与编排胶水；业务逻辑保持在
`quwoquan_ops/cli/lib/**`。测试通过 ``mock.patch.object(stackctl, ...)``
patch `load_environment_topology` / `get_target` / `resolve_report_dir` /
`load_premium_pool_*_binding` / `execute_premium_pool_readback` /
`open_premium_pool_operator_session` 等符号，因此命令函数体内一律经
函数内延迟导入 `_stackctl` 属性访问；`root_certificate_path` 保留原有的
函数内局部 import 形态（测试 patch 源模块 `public_domain_tls`）。
"""

from __future__ import annotations

import argparse
from typing import Any


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    premium_pool_parser = subparsers.add_parser(
        "premium-pool",
        help="以immutable candidate或exact test-live binding验证非生产精品池闭环",
    )
    premium_pool_parser.add_argument(
        "--target",
        choices=("alpha-local", "beta-local", "gamma-local"),
        required=True,
    )
    premium_pool_parser.add_argument(
        "--action",
        choices=("upsert-and-verify", "verify-readback"),
        default="upsert-and-verify",
    )
    premium_pool_parser.add_argument(
        "--launch-policy",
        choices=("immutable-candidate", "test-live", "release-import"),
        default="immutable-candidate",
        help=(
            "默认保持immutable candidate语义；test-live只接受当前running attempt的"
            "run-bound nonPromotable content binding；release-import只用于池为空时的"
            "首次激活，输入为apply已产出的导入报告"
        ),
    )
    premium_pool_parser.add_argument("--readiness-receipt", required=True)
    premium_pool_parser.add_argument("--content-id", required=True)
    premium_pool_parser.add_argument("--quality-score", type=float)
    premium_pool_parser.add_argument("--expires-at")
    premium_pool_parser.add_argument(
        "--projection-deadline-seconds",
        type=float,
        default=30.0,
    )
    premium_pool_parser.add_argument("--report-dir", default=argparse.SUPPRESS)


def command_premium_pool(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    topology = _stackctl.load_environment_topology()
    target = _stackctl.get_target(topology, args.target)
    environment = str(target["env"])
    public_bases = target.get("publicBases") or {}
    api_base_url = str(public_bases.get("api") or "").strip()
    product_ops_base_url = str(public_bases.get("productOps") or "").strip()
    report_dir = _stackctl.resolve_report_dir(args, environment, args.target)
    started_monotonic, started_at = _stackctl._start_timing()
    receipt: dict[str, Any] = {}
    try:
        if not api_base_url:
            raise _stackctl.PremiumPoolReleaseError(
                "target topology lacks API public base"
            )
        launch_policy = str(
            getattr(args, "launch_policy", "immutable-candidate")
        )
        if launch_policy == "immutable-candidate":
            binding = _stackctl.load_premium_pool_candidate_binding(
                environment=environment,
                target=args.target,
                readiness_receipt=args.readiness_receipt,
                content_id=args.content_id,
            )
        elif launch_policy == "test-live":
            binding = _stackctl.load_premium_pool_test_live_binding(
                environment=environment,
                target=args.target,
                readiness_receipt=args.readiness_receipt,
                content_id=args.content_id,
            )
        elif launch_policy != "release-import":
            raise _stackctl.PremiumPoolReleaseError(
                "unsupported premium pool launch policy"
            )
        from quwoquan_ops.cli.lib.public_domain_tls import root_certificate_path

        ssl_cafile = str(root_certificate_path(args.target))
        if launch_policy == "release-import":
            # 空池判定只读内容面，因此必须在取得 CA 之后、任何写入之前完成。
            binding = _stackctl.load_premium_pool_bootstrap_binding(
                environment=environment,
                target=args.target,
                import_report=args.readiness_receipt,
                content_id=args.content_id,
                pool_is_empty=_stackctl.premium_pool_is_empty(
                    api_base_url=api_base_url,
                    ssl_cafile=ssl_cafile,
                ),
            )
        if str(args.action) == "verify-readback":
            receipt = _stackctl.execute_premium_pool_readback(
                binding=binding,
                api_base_url=api_base_url,
                ssl_cafile=ssl_cafile,
                projection_deadline_seconds=float(
                    args.projection_deadline_seconds
                ),
            )
        elif str(args.action) == "upsert-and-verify":
            if not product_ops_base_url:
                raise _stackctl.PremiumPoolReleaseError(
                    "target topology lacks Product Ops public base"
                )
            if args.quality_score is None or not str(args.expires_at or "").strip():
                raise _stackctl.PremiumPoolReleaseError(
                    "upsert-and-verify requires qualityScore and expiresAt"
                )
            session, operator_kind = _stackctl.open_premium_pool_operator_session(
                environment=environment,
                target=args.target,
            )
            receipt = _stackctl.execute_premium_pool_upsert(
                binding=binding,
                product_ops_base_url=product_ops_base_url,
                api_base_url=api_base_url,
                session=session,
                operator_kind=operator_kind,
                quality_score=float(args.quality_score),
                expires_at=str(args.expires_at),
                ssl_cafile=ssl_cafile,
                projection_deadline_seconds=float(
                    args.projection_deadline_seconds
                ),
            )
        else:
            raise _stackctl.PremiumPoolReleaseError("unsupported premium pool action")
        status = "ok"
        exit_code = 0
        details = [
            f"release={binding.release_id}",
            f"importRunId={binding.import_run_id}",
            f"contentId={binding.content_id}",
        ]
        if launch_policy == "immutable-candidate":
            details.append(f"baselineId={binding.baseline_id}")
        elif launch_policy == "release-import":
            details.extend(
                (
                    "launchPolicy=release_import",
                    f"baselineId={binding.baseline_id}",
                    f"importReportRef={binding.import_report_ref}",
                )
            )
        else:
            details.extend(
                (
                    "launchPolicy=test_live",
                    f"startupAttemptId={binding.startup_attempt_id}",
                    "nonPromotable=true",
                )
            )
    except (OSError, ValueError, _stackctl.PremiumPoolReleaseError) as exc:
        status = "gate_block"
        exit_code = 2
        details = [str(exc)]
    timing = _stackctl._finish_timing(started_monotonic, started_at)
    _stackctl.write_json(
        report_dir / "report.json",
        {
            "command": "premium-pool",
            "target": args.target,
            "action": args.action,
            "status": status,
            "receipt": receipt,
            "details": details,
            **timing,
        },
    )
    summary = (
        f"stackctl premium-pool passed for {args.target}"
        if exit_code == 0
        else f"stackctl premium-pool is GATE_BLOCK for {args.target}"
    )
    _stackctl._write_summary_bundle(
        report_dir,
        command="premium-pool",
        target=args.target,
        status=status,
        summary=summary,
        details=details,
        timing=timing,
    )
    return {
        "exitCode": exit_code,
        "summary": summary,
        "details": details,
        "reportDir": _stackctl.relpath(report_dir),
        **timing,
    }
