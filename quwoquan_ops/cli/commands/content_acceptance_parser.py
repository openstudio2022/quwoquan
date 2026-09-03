"""Argparse surfaces for stackctl content acceptance commands."""

from __future__ import annotations

import argparse
import os

from quwoquan_ops.cli.lib.content_release_readiness import ReadinessPhase


def register_content_api_consumer_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register the explicit-authority Alpha Research API consumer."""

    parser = subparsers.add_parser(
        "content-api-consumer",
        help="消费显式 Alpha Research release 权威并写 4×4 只读 API raw 结果",
    )
    parser.add_argument("--target", choices=("alpha-local",), required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--import-run-id", required=True)
    parser.add_argument("--verify-run-id", required=True)
    parser.add_argument(
        "--manifest-digest",
        required=True,
        help="显式 immutable payload/Data readiness manifestDigest（不等于 releaseDigest）",
    )
    parser.add_argument("--sample-plan-ref", required=True)
    parser.add_argument("--sample-plan-digest", required=True)
    parser.add_argument("--data-readiness-ref", required=True)
    parser.add_argument("--data-readiness-digest", required=True)
    parser.add_argument("--consumer-health-ref", required=True)
    parser.add_argument("--consumer-health-digest", required=True)
    parser.add_argument("--report-dir", required=True)


def register_content_readiness_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    import quwoquan_ops.cli.stackctl as _stackctl

    content_readiness_parser = subparsers.add_parser(
        "content-readiness",
        help="验证指定内容发布 phase 的环境能力，不创建内容工作包",
    )
    content_readiness_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    content_readiness_parser.add_argument(
        "--phase",
        choices=[phase.value for phase in ReadinessPhase],
        required=True,
    )
    content_readiness_parser.add_argument(
        "--env", choices=_stackctl.ENVIRONMENTS, required=True
    )
    content_readiness_parser.add_argument(
        "--release-id",
        default="",
        help="consumer/commercial readiness 绑定的 canonical Data releaseId",
    )
    content_readiness_parser.add_argument(
        "--verify-run-id",
        default="",
        help="canonical Data environment verify runId；禁止隐式选择 latest",
    )
    content_readiness_parser.add_argument(
        "--manifest-digest",
        default="",
        help="预期 immutable Data payload digest（sha256:...）",
    )
    content_readiness_parser.add_argument(
        "--lifecycle-exit-ref",
        default="",
        help="commercial phase 必需的 canonical rollback/replay lifecycle Exit ref",
    )


def register_uat_parsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    import quwoquan_ops.cli.stackctl as _stackctl

    content_uat_parser = subparsers.add_parser(
        "content-uat",
        help="以当前 Gamma data-release 的运行案例执行实体主页真实端侧消费验收",
    )
    content_uat_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    content_uat_parser.add_argument(
        "--target",
        choices=(_stackctl.GAMMA_CONTENT_UAT_TARGET,),
        default=_stackctl.GAMMA_CONTENT_UAT_TARGET,
    )
    content_uat_parser.add_argument("--release-uat-cases", required=True)
    content_uat_parser.add_argument(
        "--data-verify-run-id",
        required=True,
        help="与案例 import run 配对的 canonical Data verify runId；禁止选择 latest",
    )
    content_uat_parser.add_argument(
        "--acceptance-lease-id",
        required=True,
        help="本次真实设备 UAT 的 create-once acceptance lease id",
    )
    content_uat_parser.add_argument(
        "--platform",
        choices=("android", "ios", "all"),
        default="all",
    )
    content_uat_parser.add_argument("--device-id", action="append", default=[])

    account_enforcement_uat_parser = subparsers.add_parser(
        "account-enforcement-uat",
        help=(
            "在统一 Gamma 环境树中执行 account-enforcement 真机阶段，或聚合 "
            "GWT-003 的 fail-closed CaseResult"
        ),
    )
    account_enforcement_uat_parser.add_argument(
        "--report-dir", default=argparse.SUPPRESS
    )
    account_enforcement_uat_parser.add_argument(
        "--target",
        choices=("gamma-local",),
        default="gamma-local",
    )
    account_enforcement_uat_parser.add_argument(
        "--action",
        choices=("device-suspended", "device-restored", "verify"),
        required=True,
    )
    account_enforcement_uat_parser.add_argument(
        "--manifest",
        default=_stackctl.ACCOUNT_ENFORCEMENT_GAMMA_UAT_MANIFEST,
    )
    account_enforcement_uat_parser.add_argument(
        "--run-id",
        default=os.environ.get("QWQ_ACCOUNT_ENFORCEMENT_GAMMA_RUN_ID", ""),
    )
    account_enforcement_uat_parser.add_argument(
        "--candidate-digest",
        default=os.environ.get("QWQ_ACCOUNT_ENFORCEMENT_GAMMA_CANDIDATE_DIGEST", ""),
    )
    account_enforcement_uat_parser.add_argument(
        "--journey-receipt",
        default=os.environ.get("QWQ_ACCOUNT_ENFORCEMENT_GAMMA_JOURNEY_RECEIPT", ""),
    )
    account_enforcement_uat_parser.add_argument(
        "--suspended-device-report",
        default=os.environ.get(
            "QWQ_ACCOUNT_ENFORCEMENT_GAMMA_SUSPENDED_DEVICE_REPORT", ""
        ),
    )
    account_enforcement_uat_parser.add_argument(
        "--restored-device-report",
        default=os.environ.get(
            "QWQ_ACCOUNT_ENFORCEMENT_GAMMA_RESTORED_DEVICE_REPORT", ""
        ),
    )
    account_enforcement_uat_parser.add_argument(
        "--device-id", action="append", default=[]
    )
